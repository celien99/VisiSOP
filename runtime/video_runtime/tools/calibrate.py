"""Measure detector confidence and suggest SOP thresholds.

The tool replays a recorded clip through the same bindings and primitives the
runtime uses, so the numbers match what the SOP engine will actually see. It
prints per-class confidence distributions, per-event statistics, and a
threshold sweep for every SOP completion condition. With ``--apply`` it writes
the suggested thresholds back to the SOP JSON and the runtime YAML, keeping a
timestamped backup of each file.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import cv2
from contracts.events import ModelRef

from video_runtime.config import RuntimeConfig, load_config
from video_runtime.event_builder import EventBinding, binding_from_config
from video_runtime.frame import Frame
from video_runtime.inference.base import Detection
from video_runtime.inference.onnx_yolo import OnnxYoloBackend
from video_runtime.models import ModelProvider, StaticModelProvider
from video_runtime.perception import Perception
from video_runtime.primitives.base import centre_inside

COMPLETION_FLOOR = 0.3
BINDING_FLOOR = 0.15
_PASS_QUANTILE = 0.10


class Detector(Protocol):
    def infer(self, frame: Frame) -> list[Detection]: ...


def _quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round(q * (len(ordered) - 1))
    return ordered[max(0, min(index, len(ordered) - 1))]


def suggest_completion(values: Sequence[float]) -> float | None:
    """The value 90% of events meet, floored at ``COMPLETION_FLOOR``.

    Capped below 1.0: a threshold of exactly 1.0 would reject every real
    detection the moment its confidence dips.
    """
    value = _quantile(values, _PASS_QUANTILE)
    if value is None:
        return None
    return min(0.95, max(COMPLETION_FLOOR, round(value, 2)))


def suggest_binding(values: Sequence[float]) -> float | None:
    value = _quantile(values, _PASS_QUANTILE)
    if value is None:
        return None
    return max(BINDING_FLOOR, round(value, 2))


@dataclass
class Analysis:
    frames: int = 0
    class_confidences: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    event_confidences: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    event_samples: dict[str, list[tuple[dict[str, Any], float]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    event_frames: Counter[str] = field(default_factory=Counter)
    counts: dict[str, Counter[int]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    roi_hits: dict[str, list[tuple[str, bool]]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _binding_classes(binding: EventBinding) -> tuple[str, ...]:
    params = binding.params
    names: list[str] = []
    single = getattr(params, "object_class", None)
    if isinstance(single, str):
        names.append(single)
    names.extend(getattr(params, "count_classes", ()) or ())
    correct = getattr(params, "correct_class", None)
    if isinstance(correct, str):
        names.append(correct)
    reversed_class = getattr(params, "reversed_class", None)
    if isinstance(reversed_class, str):
        names.append(reversed_class)
    names.extend(getattr(params, "states", ()) or ())
    return tuple(dict.fromkeys(names))


def _binding_rect(binding: EventBinding) -> tuple[float, float, float, float] | None:
    rect = getattr(binding.params, "roi", None) or getattr(binding.params, "rect", None)
    return tuple(rect) if rect is not None else None


def analyze(
    frames: Iterable[Frame],
    provider: Detector,
    bindings: Sequence[EventBinding],
) -> Analysis:
    result = Analysis()
    for frame in frames:
        detections = provider.infer(frame)
        result.frames += 1
        for detection in detections:
            result.class_confidences[detection.class_name].append(detection.confidence)
        perception = Perception(
            frame=frame, detections=tuple(detections), tracks=(), at=frame.captured_at
        )
        for binding in bindings:
            observations = binding.primitive.evaluate(perception, binding.params)
            if observations:
                result.event_frames[binding.event_type] += 1
            for observation in observations:
                result.event_confidences[binding.event_type].append(
                    observation.confidence
                )
                result.event_samples[binding.event_type].append(
                    (dict(observation.attributes), observation.confidence)
                )
                count = observation.attributes.get("count")
                if isinstance(count, int):
                    result.counts[binding.event_type][count] += 1
            rect = _binding_rect(binding)
            if rect is not None:
                classes = set(_binding_classes(binding))
                for detection in detections:
                    if detection.class_name in classes:
                        result.roi_hits[binding.event_type].append(
                            (detection.class_name, centre_inside(detection.bbox, rect))
                        )
    return result


@dataclass(frozen=True)
class SopCondition:
    step_key: str
    event_type: str
    min_confidence: float
    attributes: dict[str, Any] = field(default_factory=dict)


def sop_conditions(path: Path) -> list[SopCondition]:
    data = json.loads(path.read_text(encoding="utf-8"))
    conditions: list[SopCondition] = []
    for step in data.get("steps", []):
        completion = step.get("completion") or {}
        for key in ("all", "any", "not_"):
            for condition in completion.get(key, []):
                event_type = condition.get("event_type")
                if event_type:
                    conditions.append(
                        SopCondition(
                            step_key=str(step.get("key", "?")),
                            event_type=str(event_type),
                            min_confidence=float(condition.get("min_confidence", 0.0)),
                            attributes=dict(condition.get("attributes") or {}),
                        )
                    )
    return conditions


def _attributes_match(predicates: dict[str, Any], attributes: dict[str, Any]) -> bool:
    """The subset of the SOP predicate grammar the calibration needs."""
    for name, predicate in predicates.items():
        if not isinstance(predicate, dict):
            return False
        if predicate.get("exists") is not None:
            if (name in attributes) is not predicate["exists"]:
                return False
            continue
        if name not in attributes:
            return False
        value = attributes[name]
        if "eq" in predicate and value != predicate["eq"]:
            return False
        if "in" in predicate and value not in predicate["in"]:
            return False
        if "gte" in predicate and not (
            isinstance(value, (int, float)) and value >= predicate["gte"]
        ):
            return False
        if "lte" in predicate and not (
            isinstance(value, (int, float)) and value <= predicate["lte"]
        ):
            return False
    return True


def _matching_confidences(analysis: Analysis, condition: SopCondition) -> list[float]:
    return [
        confidence
        for attributes, confidence in analysis.event_samples.get(
            condition.event_type, []
        )
        if _attributes_match(condition.attributes, attributes)
    ]


def _report(analysis: Analysis, conditions: Sequence[SopCondition]) -> str:
    lines: list[str] = [f"frames analyzed: {analysis.frames}"]
    lines.append("\ndetections by class:")
    lines.append(
        f"  {'class':10s} {'n':>6s} {'min':>6s} {'mean':>6s} "
        f"{'p10':>6s} {'p50':>6s} {'p90':>6s} {'max':>6s}"
    )
    for class_name in sorted(analysis.class_confidences):
        values = analysis.class_confidences[class_name]
        lines.append(
            f"  {class_name:10s} {len(values):6d} {min(values):6.2f} "
            f"{sum(values) / len(values):6.2f} "
            f"{_quantile(values, 0.1) or 0:6.2f} "
            f"{_quantile(values, 0.5) or 0:6.2f} "
            f"{_quantile(values, 0.9) or 0:6.2f} {max(values):6.2f}"
        )

    lines.append("\nevents by type:")
    lines.append(
        f"  {'event_type':24s} {'frames':>6s} {'with':>6s} {'events':>6s} "
        f"{'p10':>6s} {'p50':>6s}"
    )
    for event_type in sorted(analysis.event_confidences):
        values = analysis.event_confidences[event_type]
        lines.append(
            f"  {event_type:24s} {analysis.frames:6d} "
            f"{analysis.event_frames[event_type]:6d} {len(values):6d} "
            f"{_quantile(values, 0.1) or 0:6.2f} "
            f"{_quantile(values, 0.5) or 0:6.2f}"
        )

    counts = {
        event_type: dict(counter)
        for event_type, counter in analysis.counts.items()
        if counter
    }
    if counts:
        lines.append("\ncount distributions:")
        for event_type, counter in sorted(counts.items()):
            lines.append(f"  {event_type}: {counter}")

    if analysis.roi_hits:
        lines.append("\nROI coverage (relevant detections):")
        for event_type, hits in sorted(analysis.roi_hits.items()):
            inside = sum(1 for _, hit in hits if hit)
            lines.append(
                f"  {event_type:24s} inside={inside} outside={len(hits) - inside}"
            )

    if conditions:
        lines.append("\nSOP completion conditions (after attribute predicates):")
        lines.append(
            f"  {'step':16s} {'event_type':24s} {'current':>7s} "
            f"{'matched':>7s} {'suggest':>7s} pass@thresholds 0.2/0.4/0.6/0.8"
        )
        for condition in conditions:
            values = _matching_confidences(analysis, condition)
            suggestion = suggest_completion(values)
            rates = "/".join(
                f"{_pass_rate(values, threshold):.0%}"
                for threshold in (0.2, 0.4, 0.6, 0.8)
            )
            shown = f"{suggestion:.2f}" if suggestion is not None else "n/a"
            lines.append(
                f"  {condition.step_key:16s} {condition.event_type:24s} "
                f"{condition.min_confidence:7.2f} {len(values):7d} "
                f"{shown:>7s} {rates}"
            )
    return "\n".join(lines)


def _pass_rate(values: Sequence[float], threshold: float) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value >= threshold) / len(values)


def _backup(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, target)
    return target


def _replace_sop_value(text: str, event_type: str, value: float) -> str:
    """Replace one condition's ``min_confidence`` without reformatting the DSL."""
    pattern = re.compile(
        r'("event_type"\s*:\s*"'
        + re.escape(event_type)
        + r'"\s*,\s*"min_confidence"\s*:\s*)([0-9.]+)'
    )
    return pattern.sub(lambda match: f"{match.group(1)}{value:.2f}", text)


def apply_sop_thresholds(
    path: Path, suggestions: dict[str, float]
) -> tuple[Path | None, list[str]]:
    """Write suggested ``min_confidence`` values; returns (backup, changes)."""
    text = path.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    changes: list[str] = []
    replacements: dict[str, float] = {}
    for step in data.get("steps", []):
        completion = step.get("completion") or {}
        for key in ("all", "any", "not_"):
            for condition in completion.get(key, []):
                event_type = condition.get("event_type")
                if event_type not in suggestions:
                    continue
                new_value = round(suggestions[event_type], 2)
                old_value = condition.get("min_confidence")
                if old_value != new_value:
                    replacements[event_type] = new_value
                    changes.append(
                        f"{step.get('key')}:{event_type} {old_value} -> {new_value}"
                    )
    if not changes:
        return None, changes
    updated = text
    for event_type, value in replacements.items():
        updated = _replace_sop_value(updated, event_type, value)
    backup = _backup(path)
    path.write_text(updated, encoding="utf-8")
    return backup, changes


def replace_min_conf(text: str, event_type: str, value: float) -> str:
    """Replace one binding's ``min_conf`` without disturbing the YAML layout."""
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"- event_type: {event_type}":
            start = index
            break
    if start is None:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].lstrip().startswith("- event_type:"):
            end = index
            break
    for index in range(start + 1, end):
        match = re.match(r"^(\s*min_conf:\s*)([0-9.]+)(\s*)$", lines[index])
        if match:
            lines[index] = f"{match.group(1)}{value:.2f}{match.group(3)}"
            return "".join(lines)
    return text


def apply_binding_thresholds(
    path: Path,
    config: RuntimeConfig,
    suggestions: dict[str, float],
) -> list[str]:
    text = path.read_text(encoding="utf-8")
    updated = text
    changes: list[str] = []
    for binding in config.bindings:
        suggested = suggestions.get(binding.event_type)
        current = binding.params.get("min_conf")
        if suggested is None or not isinstance(current, (int, float)):
            continue
        if current <= suggested:
            continue
        before = updated
        updated = replace_min_conf(updated, binding.event_type, suggested)
        if updated != before:
            changes.append(
                f"{binding.event_type}: min_conf {current} -> {suggested:.2f}"
            )
    if changes:
        _backup(path)
        path.write_text(updated, encoding="utf-8")
    return changes


def _provider(
    config: RuntimeConfig, model: Path | None, names: Path | None
) -> ModelProvider:
    if model is None:
        from video_runtime.main import build_provider  # local import: heavy module

        provider, _ = build_provider(config)
        return provider
    if names is None:
        raise SystemExit("--names is required with --model")
    class_names = [
        line for line in names.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    backend = OnnxYoloBackend(
        model,
        class_names,
        input_size=config.model.input_size,
        conf_threshold=config.model.confidence,
        iou_threshold=config.model.iou,
    )
    return StaticModelProvider(
        backend, ModelRef(name=model.stem, version="1"), class_names
    )


def _frames(
    video: Path, camera_id: str, sample_every: int, max_frames: int
) -> Iterable[Frame]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        capture.release()
        raise SystemExit(f"cannot open video: {video}")
    try:
        index = 0
        kept = 0
        while kept < max_frames:
            ok, image = capture.read()
            if not ok:
                break
            if index % sample_every:
                index += 1
                continue
            height, width = image.shape[:2]
            yield Frame(
                camera_id=camera_id,
                frame_seq=index,
                captured_at=datetime.now(UTC),
                width=width,
                height=height,
                pixel_format="BGR8",
                data=image,
            )
            index += 1
            kept += 1
    finally:
        capture.release()


def _video_path(args: argparse.Namespace, config: RuntimeConfig) -> Path:
    if args.video is not None:
        return Path(args.video)
    source = config.camera.source
    path = getattr(source, "path", None)
    if path is None:
        raise SystemExit("--video is required when the config is not a file source")
    return Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--sop", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--names", type=Path)
    parser.add_argument("--sample-every", type=int, default=3)
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("EVIDENCE_DIR", tempfile.gettempdir())
    config = load_config(args.config)
    provider = _provider(config, args.model, args.names)
    bindings = [binding_from_config(binding) for binding in config.bindings]
    try:
        analysis = analyze(
            _frames(
                _video_path(args, config),
                config.camera.camera_id,
                max(1, args.sample_every),
                max(1, args.max_frames),
            ),
            provider,
            bindings,
        )
    finally:
        provider.close()

    conditions = sop_conditions(args.sop) if args.sop else []
    print(_report(analysis, conditions))  # noqa: T201

    if not args.apply:
        return 0

    completion: dict[str, float] = {}
    for condition in conditions:
        value = suggest_completion(_matching_confidences(analysis, condition))
        if value is None:
            continue
        completion[condition.event_type] = min(
            value, completion.get(condition.event_type, value)
        )
    if args.sop is not None:
        backup, changes = apply_sop_thresholds(args.sop, completion)
        print(f"\nsop: {len(changes)} change(s)")  # noqa: T201
        for change in changes:
            print(f"  {change}", file=sys.stdout)  # noqa: T201
        if backup is not None:
            print(f"  backup: {backup}", file=sys.stdout)  # noqa: T201

    binding_suggestions: dict[str, float] = {}
    for binding in bindings:
        values = [
            confidence
            for class_name in _binding_classes(binding)
            for confidence in analysis.class_confidences.get(class_name, [])
        ]
        value = suggest_binding(values)
        if value is not None:
            binding_suggestions[binding.event_type] = value
    changes = apply_binding_thresholds(args.config, config, binding_suggestions)
    print(f"\nruntime: {len(changes)} change(s)")  # noqa: T201
    for change in changes:
        print(f"  {change}", file=sys.stdout)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
