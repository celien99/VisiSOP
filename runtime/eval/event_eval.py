"""Event-level matching and precision/recall for golden-video replay."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LabelledEvent:
    event_type: str
    attributes: Mapping[str, Any]
    at: float


@dataclass(frozen=True)
class Metrics:
    precision: float
    recall: float
    matched: int
    predicted: int
    truth: int


def _key(event: LabelledEvent, key_attributes: Sequence[str]) -> tuple[Any, ...]:
    return (event.event_type,) + tuple(
        event.attributes.get(name) for name in key_attributes
    )


def _dedupe(
    events: Sequence[LabelledEvent],
    key_attributes: Sequence[str],
    dedupe_window_s: float,
) -> list[LabelledEvent]:
    kept: list[LabelledEvent] = []
    for event in sorted(events, key=lambda item: item.at):
        if any(
            _key(event, key_attributes) == _key(other, key_attributes)
            and abs(event.at - other.at) <= dedupe_window_s
            for other in kept
        ):
            continue
        kept.append(event)
    return kept


def evaluate(
    predicted: Sequence[LabelledEvent],
    truth: Sequence[LabelledEvent],
    *,
    match_window_s: float = 1.0,
    key_attributes: Sequence[str] = (),
    dedupe_window_s: float = 0.5,
) -> Metrics:
    """Greedy one-to-one match by type/key attributes within the time window."""
    predictions = _dedupe(predicted, key_attributes, dedupe_window_s)
    remaining = list(predictions)
    matched = 0
    for expected in sorted(truth, key=lambda item: item.at):
        candidates = [
            event
            for event in remaining
            if _key(event, key_attributes) == _key(expected, key_attributes)
            and abs(event.at - expected.at) <= match_window_s
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda event: abs(event.at - expected.at))
        remaining.remove(best)
        matched += 1

    false_positives = len(predictions) - matched
    precision = matched / (matched + false_positives) if predictions else 1.0
    recall = matched / len(truth) if truth else 1.0
    return Metrics(
        precision=precision,
        recall=recall,
        matched=matched,
        predicted=len(predictions),
        truth=len(truth),
    )
