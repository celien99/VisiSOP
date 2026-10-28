from collections.abc import Callable
from datetime import datetime

import pytest
from contracts.enums import ReasonCode

from app.domain.sop.correlation import CandidateEvent, correlate
from tests.domain.sop.conftest import T0


@pytest.fixture
def cam() -> Callable[..., CandidateEvent]:
    def make(
        event_id: str,
        camera_id: str,
        key: str | None,
        *,
        role: str = "hands",
        conclusion: str = "installed",
        occurred_at: datetime = T0,
        confidence: float = 0.9,
    ) -> CandidateEvent:
        return CandidateEvent(
            event_id=event_id,
            event_type="part_placed",
            camera_id=camera_id,
            camera_role=role,
            confidence=confidence,
            occurred_at=occurred_at,
            correlation_key=key,
            conclusion=conclusion,
        )

    return make


def test_same_camera_duplicate_is_deduped(cam) -> None:
    result = correlate([cam("e1", "c1", "k1"), cam("e2", "c1", "k1")])
    assert [e.event_id for e in result.accepted] == ["e1"]


def test_different_cameras_are_independent(cam) -> None:
    result = correlate([cam("e1", "c1", "k1"), cam("e2", "c2", "k1")])
    assert len(result.accepted) == 2


def test_conflict_without_priority_needs_review(cam) -> None:
    result = correlate(
        [
            cam("e1", "c1", "k1", conclusion="installed"),
            cam("e2", "c2", "k1", conclusion="missing"),
        ]
    )
    assert result.reason_code is ReasonCode.CAMERA_CONFLICT
    assert result.conflicts


def test_conflict_with_priority_picks_higher_rank(cam) -> None:
    result = correlate(
        [
            cam("e1", "c1", "k1", role="hands", conclusion="installed"),
            cam("e2", "c2", "k1", role="tool", conclusion="missing"),
        ],
        priority={"hands": 2, "tool": 1},
    )
    assert [e.event_id for e in result.accepted] == ["e1"]


def test_missing_required_role_needs_review(cam) -> None:
    result = correlate(
        [cam("e1", "c1", "k1", role="hands")],
        required_roles={"overview"},
    )
    assert result.reason_code is ReasonCode.EVIDENCE_MISSING


def test_insufficient_independent_evidence_needs_review(cam) -> None:
    result = correlate([cam("e1", "c1", "k1")], min_independent_evidence=2)
    assert result.reason_code is ReasonCode.EVIDENCE_MISSING


def test_no_key_is_not_deduped(cam) -> None:
    result = correlate([cam("e1", "c1", None), cam("e2", "c1", None)])
    assert len(result.accepted) == 2
