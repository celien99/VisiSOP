"""Filesystem layout for training videos, frames, datasets, and models."""

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np

_DEDUPE_THRESHOLD = 1.0
_SIGNATURE_SIZE = (64, 48)


class TrainingStoreError(ValueError):
    """Raised when a media file cannot be read or written safely."""


@dataclass(frozen=True)
class VideoInfo:
    duration_ms: int
    fps: float
    width: int
    height: int
    frame_count: int


@dataclass(frozen=True)
class ExtractedFrame:
    frame_index: int
    timestamp_ms: int
    width: int
    height: int
    storage_key: str
    thumb_key: str


@dataclass(frozen=True)
class ExportAnnotation:
    class_name: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class ExportFrame:
    frame_id: str
    image_path: Path
    annotations: tuple[ExportAnnotation, ...]
    video_key: str = ""


@dataclass(frozen=True)
class DatasetExport:
    storage_key: str
    frame_count: int
    train_count: int
    val_count: int
    manifest: dict[str, Any]


class TrainingStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise TrainingStoreError(f"path escapes TRAINING_DIR: {key!r}")
        return path

    def project_dir(self, project_key: str) -> str:
        return f"projects/{project_key}"

    def save_video(
        self, project_key: str, video_id: str, suffix: str, data: bytes
    ) -> str:
        key = f"{self.project_dir(project_key)}/videos/{video_id}{suffix}"
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def probe_video(self, key: str) -> VideoInfo:
        capture = cv2.VideoCapture(str(self.resolve(key)))
        if not capture.isOpened():
            raise TrainingStoreError("cannot open the uploaded video")
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            capture.release()
        duration_ms = int(round(count / fps * 1000)) if fps > 0 else 0
        return VideoInfo(duration_ms, fps, width, height, count)

    def extract_frames(
        self,
        video_key: str,
        project_key: str,
        video_id: str,
        *,
        fps: float,
        max_frames: int,
        dedupe: bool = True,
    ) -> list[ExtractedFrame]:
        video_path = self.resolve(video_key)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise TrainingStoreError(f"cannot open video {video_key!r}")
        frames: list[ExtractedFrame] = []
        last_signature: np.ndarray | None = None
        try:
            source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            step = max(1, round(source_fps / fps)) if fps > 0 and source_fps > 0 else 1
            source_index = 0
            while len(frames) < max_frames:
                ok, image = capture.read()
                if not ok:
                    break
                if source_index % step != 0:
                    source_index += 1
                    continue
                signature = _frame_signature(image) if dedupe else None
                if dedupe and last_signature is not None and signature is not None:
                    difference = float(np.mean(cv2.absdiff(signature, last_signature)))
                    if difference < _DEDUPE_THRESHOLD:
                        source_index += 1
                        continue
                if signature is not None:
                    last_signature = signature
                height, width = image.shape[:2]
                frame_index = len(frames)
                image_key = (
                    f"{self.project_dir(project_key)}/frames/{video_id}/"
                    f"{frame_index:06d}.jpg"
                )
                thumb_key = (
                    f"{self.project_dir(project_key)}/frames/{video_id}/"
                    f"thumb-{frame_index:06d}.jpg"
                )
                self._write_jpeg(image_key, image, quality=90)
                self._write_jpeg(thumb_key, _thumbnail(image), quality=80)
                timestamp_ms = (
                    int(round(source_index / source_fps * 1000))
                    if source_fps > 0
                    else 0
                )
                frames.append(
                    ExtractedFrame(
                        frame_index=frame_index,
                        timestamp_ms=timestamp_ms,
                        width=width,
                        height=height,
                        storage_key=image_key,
                        thumb_key=thumb_key,
                    )
                )
                source_index += 1
        finally:
            capture.release()
        if not frames:
            raise TrainingStoreError("no frames could be extracted")
        return frames

    def save_dataset(
        self,
        project_key: str,
        version: int,
        *,
        classes: Sequence[str],
        frames: Sequence[ExportFrame],
        val_ratio: float,
    ) -> DatasetExport:
        if not frames:
            raise TrainingStoreError("no labelled frames to export")
        base_key = f"{self.project_dir(project_key)}/datasets/v{version}"
        base = self.resolve(base_key)
        for split in ("train", "val"):
            (base / "images" / split).mkdir(parents=True, exist_ok=True)
            (base / "labels" / split).mkdir(parents=True, exist_ok=True)

        ordered = sorted(frames, key=lambda frame: frame.frame_id)
        groups: dict[str, list[ExportFrame]] = {}
        for frame in frames:
            groups.setdefault(frame.video_key or "", []).append(frame)

        assigned: list[tuple[ExportFrame, str]]
        if len(groups) > 1:
            # Keep every video in exactly one split; frames from one take are
            # near-duplicates and would inflate validation metrics.
            keys = sorted(groups)
            val_videos = 0
            if val_ratio > 0:
                val_videos = max(1, round(len(keys) * val_ratio))
                val_videos = min(val_videos, len(keys) - 1)
            val_keys = set(keys[:val_videos]) if val_videos else set()
            assigned = [
                (frame, "val" if key in val_keys else "train")
                for key, group in groups.items()
                for frame in group
            ]
            split_by = "video"
        else:
            stride = max(2, round(1 / val_ratio)) if val_ratio > 0 else 0
            assigned = [
                (
                    frame,
                    "val"
                    if stride and index % stride == 0 and len(ordered) > 4
                    else "train",
                )
                for index, frame in enumerate(ordered)
            ]
            split_by = "frame"

        splits: list[str] = []
        for frame, split in assigned:
            splits.append(split)
            image_target = base / "images" / split / f"{frame.frame_id}.jpg"
            shutil.copyfile(frame.image_path, image_target)
            (base / "labels" / split / f"{frame.frame_id}.txt").write_text(
                _yolo_labels(frame.annotations, classes), encoding="utf-8"
            )
        train_count = splits.count("train")
        val_count = splits.count("val")
        val_split = "val" if val_count else "train"
        data_yaml = base / "data.yaml"
        data_yaml.write_text(
            "\n".join(
                [
                    f'path: "{base.as_posix()}"',
                    "train: images/train",
                    f"val: images/{val_split}",
                    f"nc: {len(classes)}",
                    f"names: {json.dumps(list(classes))}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        manifest = {
            "classes": list(classes),
            "frame_count": len(ordered),
            "train_count": train_count,
            "val_count": val_count,
            "data_yaml": f"{base_key}/data.yaml",
            "frame_ids": [frame.frame_id for frame in ordered],
            "split_by": split_by,
        }
        (base / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return DatasetExport(
            storage_key=base_key,
            frame_count=len(ordered),
            train_count=train_count,
            val_count=val_count,
            manifest=manifest,
        )

    def model_paths(self, model_id: str) -> tuple[Path, Path]:
        base = self.resolve(f"models/{model_id}")
        return base / "best.onnx", base / "names.txt"

    def job_dir(self, project_key: str, job_id: str) -> Path:
        path = self.resolve(f"{self.project_dir(project_key)}/jobs/{job_id}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_jpeg(self, key: str, image: Any, *, quality: int) -> None:
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(
            ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        if not ok:
            raise TrainingStoreError(f"cannot encode {key!r}")
        path.write_bytes(encoded.tobytes())


def _frame_signature(image: Any) -> np.ndarray:
    small = cv2.resize(image, _SIGNATURE_SIZE, interpolation=cv2.INTER_AREA)
    return cast(np.ndarray, cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))


def _thumbnail(image: Any, width: int = 320) -> Any:
    height, source_width = image.shape[:2]
    if source_width <= width:
        return image
    scale = width / source_width
    return cv2.resize(image, (width, max(1, round(height * scale))))


def _yolo_labels(
    annotations: Sequence[ExportAnnotation], classes: Sequence[str]
) -> str:
    index = {name: position for position, name in enumerate(classes)}
    lines: list[str] = []
    for annotation in annotations:
        class_index = index.get(annotation.class_name)
        if class_index is None:
            continue
        width = annotation.x2 - annotation.x1
        height = annotation.y2 - annotation.y1
        if width <= 0 or height <= 0:
            continue
        lines.append(
            f"{class_index} {(annotation.x1 + annotation.x2) / 2:.6f} "
            f"{(annotation.y1 + annotation.y2) / 2:.6f} {width:.6f} {height:.6f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")
