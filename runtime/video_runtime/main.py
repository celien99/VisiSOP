import argparse
import logging
import signal
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn
from contracts.catalog import catalog_snapshot
from contracts.runtime import RuntimeHeartbeat, RuntimeRegistration

from video_runtime import __version__
from video_runtime.config import BindingConfig, RuntimeConfig, load_config
from video_runtime.event_builder import EventBuilder, binding_from_config
from video_runtime.evidence import EvidenceWriter
from video_runtime.inference.onnx_yolo import OnnxYoloBackend
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

    pipeline = build_pipeline(config, state, publisher)
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


def build_pipeline(
    config: RuntimeConfig, state: RuntimeState, publisher: HttpEventPublisher
) -> Pipeline:
    class_names = config.model.class_names_path.read_text(encoding="utf-8").splitlines()
    preflight(config, class_names)
    inference = OnnxYoloBackend(
        config.model.onnx_path,
        class_names,
        input_size=config.model.input_size,
        conf_threshold=config.model.confidence,
        iou_threshold=config.model.iou,
    )
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
        inference,
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
