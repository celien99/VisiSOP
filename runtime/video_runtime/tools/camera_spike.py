"""Manual camera check: capture frames, print FPS, save sample JPEGs."""

import argparse
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from video_runtime.config import FileSourceConfig, GigESourceConfig, load_config
from video_runtime.sources.base import VideoSource
from video_runtime.sources.file import FileSource
from video_runtime.sources.gige import GigEHKSource

_SAMPLES = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--save-dir", type=Path, default=Path("spike"))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    args.save_dir.mkdir(parents=True, exist_ok=True)
    source = _build_source(config.camera.source, config.camera.camera_id)

    source.start()
    intervals: list[float] = []
    previous: float | None = None
    saved = 0
    first_brightness: float | None = None
    last_frame = None
    captured = 0
    try:
        for _ in range(args.frames):
            frame = source.read()
            if frame is None:
                break
            captured += 1
            last_frame = frame
            now = time.monotonic()
            if previous is not None:
                intervals.append(now - previous)
            previous = now
            if first_brightness is None:
                first_brightness = float(np.mean(frame.data))
            if saved < _SAMPLES:
                cv2.imwrite(str(args.save_dir / f"sample-{saved:02d}.jpg"), frame.data)
                saved += 1
    finally:
        source.stop()

    if last_frame is None or first_brightness is None:
        print("no frames captured", file=sys.stderr)
        return 1

    fps = 1.0 / statistics.mean(intervals) if intervals else 0.0
    print(
        f"frames={captured} size={last_frame.width}x{last_frame.height} "
        f"fps={fps:.1f} brightness={first_brightness:.1f} "
        f"samples={saved} dir={args.save_dir}"
    )
    if first_brightness <= 0:
        print(
            "warning: first frame is black (mean 0) - check the lens cap, "
            "exposure time, and gain",
            file=sys.stderr,
        )
    return 0


def _build_source(source_config: object, camera_id: str) -> VideoSource:
    if isinstance(source_config, GigESourceConfig):
        return GigEHKSource(source_config, camera_id=camera_id)
    if isinstance(source_config, FileSourceConfig):
        return FileSource(
            source_config.path,
            camera_id=camera_id,
            loop=source_config.loop,
        )
    raise SystemExit(f"unsupported source for the camera spike: {source_config!r}")


if __name__ == "__main__":
    raise SystemExit(main())
