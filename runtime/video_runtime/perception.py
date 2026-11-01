"""One shared perception pass per camera: detections plus stable track ids."""

from dataclasses import dataclass
from datetime import datetime

from video_runtime.frame import Frame
from video_runtime.inference.base import Detection

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Track:
    track_id: str
    class_name: str
    bbox: BBox
    confidence: float
    hits: int = 1
    last_seen: datetime | None = None


@dataclass(frozen=True)
class Perception:
    frame: Frame
    detections: tuple[Detection, ...]
    tracks: tuple[Track, ...]
    at: datetime

    def track_for(self, detection: Detection) -> Track | None:
        best: Track | None = None
        best_overlap = 0.0
        for track in self.tracks:
            if track.class_name != detection.class_name:
                continue
            overlap = iou(track.bbox, detection.bbox)
            if overlap > best_overlap:
                best = track
                best_overlap = overlap
        return best


def iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _TrackState:
    track_id: str
    class_name: str
    bbox: BBox
    confidence: float
    hits: int
    missed: int
    last_seen: datetime


class IoUTracker:
    """Greedy IoU association within a class; ids survive short occlusions."""

    def __init__(self, *, iou_threshold: float = 0.3, max_missed: int = 15) -> None:
        self._iou_threshold = iou_threshold
        self._max_missed = max_missed
        self._states: list[_TrackState] = []
        self._counter = 0

    def update(
        self, detections: tuple[Detection, ...], *, camera_id: str, at: datetime
    ) -> tuple[Track, ...]:
        unmatched = list(self._states)
        current: list[_TrackState] = []
        for detection in detections:
            match: _TrackState | None = None
            best = self._iou_threshold
            for state in unmatched:
                if state.class_name != detection.class_name:
                    continue
                overlap = iou(state.bbox, detection.bbox)
                if overlap > best:
                    match = state
                    best = overlap
            if match is None:
                self._counter += 1
                match = _TrackState(
                    track_id=f"{camera_id}:{self._counter}",
                    class_name=detection.class_name,
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                    hits=1,
                    missed=0,
                    last_seen=at,
                )
            else:
                unmatched.remove(match)
                match.bbox = detection.bbox
                match.confidence = detection.confidence
                match.hits += 1
                match.missed = 0
                match.last_seen = at
            current.append(match)

        for state in unmatched:
            state.missed += 1
        self._states = [
            state
            for state in (*current, *unmatched)
            if state.missed <= self._max_missed
        ]
        return tuple(
            Track(
                track_id=state.track_id,
                class_name=state.class_name,
                bbox=state.bbox,
                confidence=state.confidence,
                hits=state.hits,
                last_seen=state.last_seen,
            )
            for state in current
        )
