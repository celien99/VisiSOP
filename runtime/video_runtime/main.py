import argparse
import logging
import signal
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn
from contracts.catalog import catalog_snapshot
from contracts.events import ModelRef
from contracts.runtime import HealthStatus, RuntimeHeartbeat, RuntimeRegistration

from video_runtime import __version__
from video_runtime.config import BindingConfig, RuntimeConfig, load_config
from video_runtime.event_builder import EventBuilder, binding_from_config
from video_runtime.evidence import EvidenceWriter
from video_runtime.inference.onnx_yolo import OnnxYoloBackend
from video_runtime.models import ModelManager, ModelProvider, StaticModelProvider
from video_runtime.perception import BBox, IoUTracker
from video_runtime.pipeline import Pipeline
from video_runtime.publisher import HttpEventPublisher
from video_runtime.registrar import RuntimeRegistrar
from video_runtime.server import create_app
from video_runtime.sources.factory import build_source
from video_runtime.state import RuntimeState

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VisiSOP video runtime")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    config = load_config(args.config)
    (config.evidence_dir / "tmp").mkdir(parents=True, exist_ok=True)

    state = RuntimeState(
        runtime_id=config.runtime_id,
        preview_fps=config.preview.fps,
        overlay=config.preview.overlay,
        regions=_binding_regions(config.bindings),
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(state),
            host=config.preview.host,
            port=config.preview.port,
            log_level="info",
        )
    )
    threading.Thread(target=server.run, daemon=True).start()

    stop_event = threading.Event()
    publisher = _build_publisher(config)
    registrar = RuntimeRegistrar(
        config.backend.base_url,
        _registration(config),
        lambda: _heartbeat(config, state, publisher),
    )
    threading.Thread(
        target=registrar.run_forever, args=(stop_event,), daemon=True
    ).start()

    provider, class_names = build_provider(config)
    if isinstance(provider, ModelManager):
        _model_health(state, provider.health_error())
        threading.Thread(
            target=provider.run_poller,
            args=(stop_event,),
            kwargs={"on_error": lambda error: _model_health(state, error)},
            daemon=True,
        ).start()
    pipeline = build_pipeline(config, state, publisher, provider, class_names)
    for handled in (signal.SIGINT, signal.SIGTERM):
        signal.signal(handled, _stopper(pipeline, stop_event))

    logger.info(
        "runtime %s watching %s via %s; preview http://%s:%s/stream/%s",
        config.runtime_id,
        config.station_id,
        config.camera.source.kind,
        config.preview.host,
        config.preview.port,
        config.camera.camera_id,
    )
    try:
        pipeline.run()
    finally:
        stop_event.set()
        server.should_exit = True
        pipeline.close()
    logger.info("runtime stopped")
    return 0


def preflight(config: RuntimeConfig, class_names: list[str]) -> None:
    """Fail at startup, not silently per frame, on a misconfigured binding."""
    registered = catalog_snapshot()
    known_classes = set(class_names)
    for binding in config.bindings:
        if binding.event_type not in registered:
            raise SystemExit(
                f"binding uses unregistered event type {binding.event_type!r}"
            )
        if not known_classes:
            continue
        for key in ("object_class", "correct_class", "reversed_class"):
            value = binding.params.get(key)
            if isinstance(value, str) and value not in known_classes:
                raise SystemExit(
                    f"binding {binding.event_type!r} uses class the model does "
                    f"not know: {value!r}"
                )
        for state in binding.params.get("states", ()):
            if state not in known_classes:
                raise SystemExit(
                    f"binding {binding.event_type!r} uses class the model does "
                    f"not know: {state!r}"
                )


def _binding_regions(
    bindings: list[BindingConfig],
) -> tuple[tuple[BBox, str], ...]:
    regions: list[tuple[BBox, str]] = []
    for binding in bindings:
        for key in ("rect", "roi"):
            rect = binding.params.get(key)
            if rect is not None:
                regions.append((tuple(rect), binding.event_type))
    return tuple(regions)


def _required_classes(bindings: list[BindingConfig]) -> tuple[str, ...]:
    names: set[str] = set()
    for binding in bindings:
        for key in ("object_class", "correct_class", "reversed_class"):
            value = binding.params.get(key)
            if isinstance(value, str):
                names.add(value)
        for state in binding.params.get("states", ()):
            if isinstance(state, str):
                names.add(state)
    return tuple(sorted(names))


def _model_health(state: RuntimeState, error: str | None) -> None:
    if error is None:
        if state.status is HealthStatus.DEGRADED:
            state.status = HealthStatus.HEALTHY
        state.error = None
        return
    state.error = error
    if state.status is HealthStatus.HEALTHY:
        state.status = HealthStatus.DEGRADED


def build_provider(
    config: RuntimeConfig,
) -> tuple[ModelProvider, list[str]]:
    model = config.model

    def factory(onnx_path: Path, names: list[str]) -> OnnxYoloBackend:
        return OnnxYoloBackend(
            onnx_path,
            names,
            input_size=model.input_size,
            conf_threshold=model.confidence,
            iou_threshold=model.iou,
        )

    if model.source == "backend":
        if model.project_key is None:
            raise SystemExit("model.project_key is required for the backend source")
        manager = ModelManager(
            config.backend.base_url,
            model.project_key,
            cache_dir=model.onnx_path.parent / "active",
            backend_factory=factory,
            poll_s=model.poll_s,
            required_classes=_required_classes(config.bindings),
        )
        try:
            manager.refresh()
        except Exception as exc:  # network boundary: the poller keeps retrying
            logger.warning("no active model yet: %s", exc)
        return manager, list(manager.classes())
    class_names = model.class_names_path.read_text(encoding="utf-8").splitlines()
    backend = factory(model.onnx_path, class_names)
    provider = StaticModelProvider(
        backend,
        ModelRef(name=model.onnx_path.stem, version="1"),
        class_names,
    )
    return provider, class_names


def build_pipeline(
    config: RuntimeConfig,
    state: RuntimeState,
    publisher: HttpEventPublisher,
    provider: ModelProvider,
    class_names: list[str],
) -> Pipeline:
    preflight(config, class_names)
    builder = EventBuilder(
        config.station_id,
        config.camera.camera_id,
        config.camera.role.value,
        model_name=config.model.onnx_path.stem,
        model_version="1",
        writer=EvidenceWriter(config.evidence_dir),
        bindings=[binding_from_config(binding) for binding in config.bindings],
    )
    return Pipeline(
        build_source(config.camera.source, config.camera.camera_id),
        provider,
        IoUTracker(),
        builder,
        publisher,
        state,
        inference_interval_ms=config.inference_interval_ms,
    )


def _build_publisher(config: RuntimeConfig) -> HttpEventPublisher:
    return HttpEventPublisher(
        config.backend.base_url,
        timeout_ms=config.backend.timeout_ms,
        retries=config.backend.retries,
    )


def _registration(config: RuntimeConfig) -> RuntimeRegistration:
    preview_url = f"http://{config.preview.host}:{config.preview.port}"
    return RuntimeRegistration(
        runtime_id=config.runtime_id,
        base_url=preview_url,
        preview_base_url=preview_url,
        version=__version__,
        camera_ids=(config.camera.camera_id,),
    )


def _heartbeat(
    config: RuntimeConfig, state: RuntimeState, publisher: HttpEventPublisher
) -> RuntimeHeartbeat:
    metrics = dict(state.metrics)
    metrics.update(
        {
            "events_pending": float(len(publisher.pending)),
            "events_dropped": float(publisher.dropped),
            "events_failed": float(publisher.metrics.failed),
            "events_retries": float(publisher.metrics.retries),
            "events_duplicates": float(publisher.metrics.duplicates),
        }
    )
    return RuntimeHeartbeat(
        status=state.status,
        metrics=metrics,
        cameras=(state.camera_status(config.camera.camera_id),),
    )


def _stopper(
    pipeline: Pipeline, stop_event: threading.Event
) -> Callable[[int, object], None]:
    def handle(signum: int, _frame: object) -> None:
        logger.info("signal %s received; stopping", signum)
        stop_event.set()
        pipeline.stop()

    return handle


if __name__ == "__main__":
    raise SystemExit(main())
