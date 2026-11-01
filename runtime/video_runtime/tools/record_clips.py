"""Record frames from the configured camera for dataset labelling."""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2

from video_runtime.config import load_config
from video_runtime.sources.factory import build_source

_JPEG_QUALITY = 92


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    source = build_source(config.camera.source, config.camera.camera_id)

    interval = 1.0 / args.fps
    saved = 0
    started_at = datetime.now(UTC)
    source.start()
    try:
        deadline = time.monotonic() + args.seconds
        next_save = time.monotonic()
        while time.monotonic() < deadline:
            frame = source.read()
            if frame is None:
                time.sleep(0.01)
                continue
            now = time.monotonic()
            if now < next_save:
                continue
            path = args.out / f"frame-{saved:06d}.jpg"
            cv2.imwrite(
                str(path), frame.data, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
            )
            saved += 1
            next_save = now + interval
    finally:
        source.stop()

    manifest = {
        "camera_id": config.camera.camera_id,
        "station_id": config.station_id,
        "source": config.camera.source.kind,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "fps": args.fps,
        "frames": saved,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"saved {saved} frames to {args.out}", file=sys.stdout)
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
