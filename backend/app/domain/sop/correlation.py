from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from contracts.enums import ReasonCode


@dataclass(frozen=True)
class CandidateEvent:
    event_id: str
    event_type: str
    camera_id: str
    camera_role: str | None
    confidence: float
    occurred_at: datetime
    correlation_key: str | None
    conclusion: str | None


@dataclass(frozen=True)
class CorrelationConflict:
    correlation_key: str
    event_ids: tuple[str, ...]
    reason_code: ReasonCode


@dataclass(frozen=True)
class CorrelationResult:
    accepted: tuple[CandidateEvent, ...]
    conflicts: tuple[CorrelationConflict, ...]
    reason_code: ReasonCode | None


def _dedupe(events: Iterable[CandidateEvent]) -> list[CandidateEvent]:
    ordered = sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    retained: list[CandidateEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in ordered:
        if event.correlation_key is not None:
            dedupe_key = (event.camera_id, event.correlation_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
        retained.append(event)
    return retained


def correlate(
    events: Iterable[CandidateEvent],
    *,
    required_roles: Collection[str] = (),
    min_independent_evidence: int = 1,
    max_skew_ms: int = 2000,
    priority: Mapping[str, int] | None = None,
) -> CorrelationResult:
    retained = _dedupe(events)

    groups: dict[str, list[CandidateEvent]] = defaultdict(list)
    for event in retained:
        if event.correlation_key is not None:
            groups[event.correlation_key].append(event)

    conflicts: list[CorrelationConflict] = []
    excluded: set[str] = set()
    unresolved = False

    for key in sorted(groups):
        group = groups[key]
        conclusions = {
            event.conclusion for event in group if event.conclusion is not None
        }
        if len(conclusions) <= 1:
            continue
        span = max(event.occurred_at for event in group) - min(
            event.occurred_at for event in group
        )
        if span > timedelta(milliseconds=max_skew_ms):
            continue

        conflicts.append(
            CorrelationConflict(
                correlation_key=key,
                event_ids=tuple(event.event_id for event in group),
                reason_code=ReasonCode.CAMERA_CONFLICT,
            )
        )
        if priority is None:
            unresolved = True
            excluded.update(event.event_id for event in group)
            continue
        ranks = {
            event.event_id: priority.get(event.camera_role or "", 0) for event in group
        }
        best = max(ranks.values())
        excluded.update(event_id for event_id, rank in ranks.items() if rank != best)

    accepted = tuple(event for event in retained if event.event_id not in excluded)

    present_roles = {
        event.camera_role for event in retained if event.camera_role is not None
    }
    missing_role = any(role not in present_roles for role in required_roles)
    independent = len({event.camera_id for event in accepted})

    reason_code: ReasonCode | None = None
    if unresolved:
        reason_code = ReasonCode.CAMERA_CONFLICT
    elif missing_role or independent < min_independent_evidence:
        reason_code = ReasonCode.EVIDENCE_MISSING

    return CorrelationResult(
        accepted=accepted,
        conflicts=tuple(conflicts),
        reason_code=reason_code,
    )
