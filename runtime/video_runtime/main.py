import argparse
import logging
import signal
import threading
from pathlib import Path

import uvicorn
from contracts.runtime import RuntimeHeartbeat, RuntimeRegistration

from video_runtime import __version__
from video_runtime.config import (
    FileSourceConfig,
    GigESourceConfig,
    RuntimeConfig,
    load_config,
)
from video_runtime.event_builder import EventBuilder
from video_runtime.evidence import EvidenceWriter
from video_runtime.inference.onnx_yolo import OnnxYoloBackend
from video_runtime.pipeline import Pipeline
from video_runtime.publisher import HttpEventPublisher
from video_runtime.registrar import RuntimeRegistrar
from video_runtime.server import create_app
from video_runtime.sources.base import VideoSource
from video_runtime.sources.file import FileSource
from video_runtime.sources.gige import GigEHKSource
from video_runtime.state import RuntimeState
from video_runtime.zones import ZoneMapper

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

    state = RuntimeState(runtime_id=config.runtime_id, preview_fps=config.preview.fps)
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
    registrar = RuntimeRegistrar(
        config.backend.base_url,
        _registration(config),
        lambda: _heartbeat(config, state),
    )
    threading.Thread(
        target=registrar.run_forever, args=(stop_event,), daemon=True
    ).start()

    pipeline = build_pipeline(config, state)
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
    pipeline.run()

    stop_event.set()
    server.should_exit = True
    logger.info("runtime stopped")
    return 0


def build_source(config: RuntimeConfig) -> VideoSource:
    source = config.camera.source
    camera_id = config.camera.camera_id
    if isinstance(source, GigESourceConfig):
        return GigEHKSource(source, camera_id=camera_id)
    if isinstance(source, FileSourceConfig):
        return FileSource(source.path, camera_id=camera_id, loop=source.loop)
    raise SystemExit(f"unsupported source kind: {source.kind}")


def build_pipeline(config: RuntimeConfig, state: RuntimeState) -> Pipeline:
    class_names = config.model.class_names_path.read_text(encoding="utf-8").splitlines()
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
    )
    return Pipeline(
        build_source(config),
        inference,
        ZoneMapper(config.zones),
        builder,
        HttpEventPublisher(
            config.backend.base_url,
            timeout_ms=config.backend.timeout_ms,
            retries=config.backend.retries,
        ),
        state,
        inference_interval_ms=config.inference_interval_ms,
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


def _heartbeat(config: RuntimeConfig, state: RuntimeState) -> RuntimeHeartbeat:
    return RuntimeHeartbeat(
        status=state.status,
        metrics=dict(state.metrics),
        cameras=(state.camera_status(config.camera.camera_id),),
    )


def _stopper(pipeline: Pipeline, stop_event: threading.Event):
    def handle(signum: int, _frame: object) -> None:
        logger.info("signal %s received; stopping", signum)
        stop_event.set()
        pipeline.stop()

    return handle


if __name__ == "__main__":
    raise SystemExit(main())
