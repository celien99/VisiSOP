import asyncio
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.application.execution_service import apply_transitions
from app.application.graph_cache import load_graph
from app.application.state_codec import state_from_rows
from app.core.config import settings
from app.core.db import engine
from app.domain.sop.engine import timed_out
from app.domain.sop.model import (
    AlarmIntent,
    ExecutionStatus,
    StepStatus,
    StepTransition,
)
from app.models import SOPExecution as SOPExecutionRow
from app.models import StepExecution


def timeout_alarm(transition: StepTransition) -> AlarmIntent | None:
    if transition.to_status is StepStatus.TIMED_OUT:
        return AlarmIntent(
            category="PROCESS_COMPLIANCE",
            severity="HIGH",
            reason_code=transition.reason_code,
            step_key=transition.step_key,
            message=f"step {transition.step_key} timed out",
        )
    if transition.to_status is StepStatus.NEEDS_REVIEW:
        return AlarmIntent(
            category="VISION_QUALITY",
            severity="MEDIUM",
            reason_code=transition.reason_code,
            step_key=transition.step_key,
            message=f"step {transition.step_key} needs review after timeout",
        )
    return None


def process_timeouts(session: Session, now: datetime) -> int:
    statement = select(SOPExecutionRow).where(
        col(SOPExecutionRow.status) == ExecutionStatus.RUNNING.value
    )
    processed = 0
    for execution in session.exec(statement).all():
        graph = load_graph(session, execution.sop_version_id)
        rows = list(
            session.exec(
                select(StepExecution).where(StepExecution.execution_id == execution.id)
            ).all()
        )
        state = state_from_rows(execution, rows, graph)
        transitions = timed_out(graph, state, now)
        if not transitions:
            continue
        alarms = [
            alarm
            for alarm in (timeout_alarm(transition) for transition in transitions)
            if alarm is not None
        ]
        apply_transitions(
            session,
            execution=execution,
            graph=graph,
            transitions=tuple(transitions),
            alarms=tuple(alarms),
            now=now,
        )
        processed += 1
    session.commit()
    return processed


async def run_timeout_worker() -> None:
    while True:
        with Session(engine) as session:
            process_timeouts(session, datetime.now(UTC))
        await asyncio.sleep(settings.TIMEOUT_POLL_MS / 1000)
