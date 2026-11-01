# Video Runtime

Native capture → inference → event pipeline for VisiSOP. It reports
observations only: the backend decides process state.

Python 3.12, standalone `uv` project with a path dependency on `../contracts`
(the backend stays on 3.14, so the runtime is not a workspace member).

```bash
cd runtime
uv sync                 # add --extra gige for the GenTL/harvesters source
EVIDENCE_DIR=/path/to/evidence uv run python -m video_runtime.main --config config.demo.yaml
```

Camera sources are chosen in the YAML: `file` (replay), `mvs` (HIKROBOT's
MVS SDK) and `gige` (harvesters over a GenTL producer). The demo camera uses
`mvs`: the MVS GenTL producer returns device metadata in a non-UTF-8 codepage
that genicam's bindings cannot decode on CPython 3.12, so its supported SDK is
the reliable path. `load_sdk()` finds the vendor bindings through
`MVCAM_COMMON_RUNENV`, which the MVS installer sets.

The `mvs` source writes exposure and gain only; resolution, pixel format,
triggering, and packet size are whatever MVS configured on the camera. Frames
are decoded from the type reported in each frame (RGB8Packed, BGR8Packed,
YUV422, Mono8, BayerRG8).

Detection is primitive-based: one shared detection pass per camera feeds
stateful primitives (`object_in_zone`, `object_present`, `object_absent`,
`count_threshold`, `state_classify`, `orientation_match`), and each
`bindings[]` entry maps one primitive instance to one event type. The preview
draws detection boxes, track ids, and the binding rectangles
(`preview.overlay: off | boxes | all`); `GET /detections/{camera_id}` returns
the current detections, tracks, and observations as JSON.

- Evidence frames are written to `$EVIDENCE_DIR/tmp/{event_id}.jpg`; the backend
  moves and verifies them. A preview is not evidence. `EVIDENCE_DIR` is resolved
  to an absolute path and must be the **same directory** the backend uses.
- The preview server binds `127.0.0.1:8001` (`/stream/{camera_id}`,
  `/snapshot/{camera_id}`, `/health`).
- The YOLO model is not committed. Export it once:
  `uv run --with "ultralytics[export]" yolo export model=yolo11n.pt format=onnx opset=17 imgsz=640 simplify=False`
  (no NMS baked in; the runtime decodes and applies NMS) and place it at
  `runtime/models/yolo11n.onnx`. Class names live in `models/coco.names`.

Windows setup, camera calibration, and acceptance live in
`../docs/runbooks/windows-demo.md`.
