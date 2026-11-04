from pathlib import Path

import cv2
import numpy as np

from video_runtime.tools.record_clips import main


def write_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    for index in range(30):
        writer.write(np.full((48, 64, 3), index * 8 % 255, dtype=np.uint8))
    writer.release()


def test_record_clips_writes_frames_and_a_video(tmp_path, monkeypatch) -> None:
    clip = tmp_path / "clip.avi"
    write_video(clip)
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
runtime_id: runtime-01
station_id: st-01
camera:
  camera_id: cam-01
  role: overview
  source:
    kind: file
    path: {clip.as_posix()}
    loop: true
model:
  onnx_path: artifacts/yolo11n.onnx
  class_names_path: artifacts/coco.names
backend:
  base_url: http://127.0.0.1:8000/api
""",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    code = main(
        [
            "--config",
            str(config),
            "--seconds",
            "1",
            "--fps",
            "5",
            "--out",
            str(out),
            "--video",
            "take.avi",
        ]
    )

    assert code == 0
    assert list(out.glob("frame-*.jpg"))
    video = out / "take.avi"
    assert video.is_file()
    capture = cv2.VideoCapture(str(video))
    try:
        assert capture.isOpened()
        assert capture.get(cv2.CAP_PROP_FRAME_COUNT) > 0
    finally:
        capture.release()
    assert (out / "manifest.json").is_file()
