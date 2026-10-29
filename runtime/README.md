# Video Runtime

Native capture → inference → event pipeline for VisiSOP. It reports
observations only: the backend decides process state.

Python 3.12, standalone `uv` project with a path dependency on `../contracts`
(the backend stays on 3.14, so the runtime is not a workspace member).

```bash
cd runtime
uv sync                 # add --extra gige for the Hikvision GigE source
EVIDENCE_DIR=/path/to/evidence uv run python -m video_runtime.main --config config.demo.yaml
```

- Evidence frames are written to `$EVIDENCE_DIR/tmp/{event_id}.jpg`; the backend
  moves and verifies them. A preview is not evidence.
- The preview server binds `127.0.0.1:8001` (`/stream/{camera_id}`,
  `/snapshot/{camera_id}`, `/health`).
- The YOLO model is not committed. Export it once:
  `uv run --with "ultralytics[export]" yolo export model=yolo11n.pt format=onnx opset=17 imgsz=640 simplify=False`
  (no NMS baked in; the runtime decodes and applies NMS) and place it at
  `runtime/models/yolo11n.onnx`. Class names live in `models/coco.names`.

Windows setup, camera calibration, and acceptance live in
`../docs/runbooks/windows-demo.md`.
