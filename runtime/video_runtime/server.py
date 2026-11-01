from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse

from video_runtime.preview import mjpeg_chunks
from video_runtime.state import RuntimeState


def create_app(state: RuntimeState) -> FastAPI:
    app = FastAPI(title="VisiSOP video runtime")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "runtime_id": state.runtime_id,
            "status": state.status,
            "cameras": [
                state.camera_status(camera_id).model_dump(mode="json")
                for camera_id in state.cameras()
            ],
        }

    @app.get("/detections/{camera_id}")
    def detections(camera_id: str) -> dict[str, Any]:
        perception = state.perception(camera_id)
        if perception is None:
            raise HTTPException(status_code=404, detail="no perception for camera")
        return {
            "camera_id": camera_id,
            "at": perception.at.isoformat(),
            "detections": [
                {
                    "class_name": detection.class_name,
                    "confidence": detection.confidence,
                    "bbox": list(detection.bbox),
                }
                for detection in perception.detections
            ],
            "tracks": [
                {
                    "track_id": track.track_id,
                    "class_name": track.class_name,
                    "confidence": track.confidence,
                    "bbox": list(track.bbox),
                }
                for track in perception.tracks
            ],
            "events": [
                {
                    "event_type": event.event_type,
                    "confidence": event.confidence,
                    "attributes": event.attributes,
                }
                for event in state.events(camera_id)
            ],
        }

    @app.get("/snapshot/{camera_id}")
    def snapshot(camera_id: str) -> Response:
        jpeg = state.jpeg(camera_id)
        if jpeg is None:
            raise HTTPException(status_code=404, detail="no frame for camera")
        return Response(content=jpeg, media_type="image/jpeg")

    @app.get("/stream/{camera_id}")
    def stream(camera_id: str, max_chunks: int | None = None) -> StreamingResponse:
        if state.jpeg(camera_id) is None:
            raise HTTPException(status_code=404, detail="no frame for camera")
        return StreamingResponse(
            mjpeg_chunks(
                state, camera_id, fps=state.preview_fps, max_chunks=max_chunks
            ),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.post("/cameras/{camera_id}/start")
    def start_camera(camera_id: str) -> dict[str, str]:
        state.start()
        return {"camera_id": camera_id, "result": "started"}

    @app.post("/cameras/{camera_id}/stop")
    def stop_camera(camera_id: str) -> dict[str, str]:
        state.stop()
        return {"camera_id": camera_id, "result": "stopped"}

    return app
