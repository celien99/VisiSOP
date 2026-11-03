import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import contracts.demo  # noqa: F401  (registers the demo event catalog)
from contracts.enums import CameraRole
from sqlmodel import Session, col, select

from app.application.execution_service import abort_execution, create_execution
from app.application.sop_service import create_sop, publish_sop, update_draft
from app.core.db import engine
from app.domain.sop.model import ExecutionStatus
from app.models import (
    Camera,
    SOPDefinition,
    SOPExecution,
    SOPVersion,
    SopVersionStatus,
    Station,
    StationCameraBinding,
)

SEED_DIR = Path(__file__).parents[1] / "seed"
DEFAULT_SOP_KEY = "bottle_transfer"
_ACTIVE = (
    ExecutionStatus.RUNNING,
    ExecutionStatus.PAUSED,
    ExecutionStatus.NEEDS_REVIEW,
)


@dataclass(frozen=True)
class SeedSpec:
    key: str
    name: str
    path: Path


SEED_SPECS = (
    SeedSpec("bottle_transfer", "瓶体转移演示", SEED_DIR / "bottle_transfer.json"),
    SeedSpec("remote_battery", "遥控器装电池", SEED_DIR / "remote_battery.json"),
)


@dataclass(frozen=True)
class SeedResult:
    sop_key: str
    station_id: str
    camera_id: str
    sop_version_id: str
    execution_id: str
    created_execution: bool


def _station_and_camera(session: Session, now: datetime) -> None:
    if session.get(Station, "st-01") is None:
        session.add(
            Station(
                id="st-01",
                code="ST-01",
                name="演示工位",
                zone="A",
                created_at=now,
            )
        )
    if session.get(Camera, "cam-01") is None:
        session.add(
            Camera(
                id="cam-01",
                code="CAM-01",
                name="主相机",
                runtime_id="runtime-01",
                source_type="mvs",
                source_config={"serial": "demo"},
                preview_url="http://127.0.0.1:8001/stream/cam-01",
                snapshot_url="http://127.0.0.1:8001/snapshot/cam-01",
                created_at=now,
            )
        )
    session.flush()
    binding = session.exec(
        select(StationCameraBinding).where(
            col(StationCameraBinding.station_id) == "st-01",
            col(StationCameraBinding.camera_id) == "cam-01",
            col(StationCameraBinding.valid_to).is_(None),
        )
    ).first()
    if binding is None:
        session.add(
            StationCameraBinding(
                id=str(uuid4()),
                station_id="st-01",
                camera_id="cam-01",
                role=CameraRole.OVERVIEW,
                valid_from=now,
            )
        )
        session.flush()


def _content(dsl: dict[str, object]) -> dict[str, object]:
    """DSL without the fields the store derives (version, key)."""
    return {
        key: value for key, value in dsl.items() if key not in {"version", "sop_key"}
    }


def _published_version(session: Session, spec: SeedSpec, now: datetime) -> SOPVersion:
    dsl = json.loads(spec.path.read_text(encoding="utf-8"))
    definition = session.exec(
        select(SOPDefinition).where(SOPDefinition.key == spec.key)
    ).first()
    if definition is None:
        version = create_sop(
            session,
            key=spec.key,
            name=spec.name,
            dsl=dsl,
            now=now,
        )
        session.flush()
        published = publish_sop(session, sop_id=version.sop_id, now=now)
        session.flush()
        return published

    versions = list(
        session.exec(
            select(SOPVersion)
            .where(SOPVersion.sop_id == definition.id)
            .order_by(col(SOPVersion.version).desc())
        ).all()
    )
    latest = versions[0]
    stored = _content(latest.dsl)
    if stored == _content(dsl) and latest.status == SopVersionStatus.PUBLISHED:
        return latest
    # The seed JSON drifted from what is published: publish a new version.
    update_draft(session, sop_id=definition.id, dsl=dsl, now=now)
    session.flush()
    published = publish_sop(session, sop_id=definition.id, now=now)
    session.flush()
    return published


def _active_on_station(session: Session) -> list[SOPExecution]:
    return list(
        session.exec(
            select(SOPExecution).where(
                col(SOPExecution.station_id) == "st-01",
                col(SOPExecution.status).in_(_ACTIVE),
            )
        ).all()
    )


def seed_demo(
    session: Session, now: datetime, active_sop: str = DEFAULT_SOP_KEY
) -> SeedResult:
    """Publish every seed SOP and leave one execution active for ``active_sop``.

    A station may only run one SOP at a time, so switching the active SOP
    aborts the previous execution before creating the new one.
    """
    specs = {spec.key: spec for spec in SEED_SPECS}
    if active_sop not in specs:
        raise ValueError(f"unknown seed SOP: {active_sop}")

    _station_and_camera(session, now)
    versions = {
        key: _published_version(session, spec, now) for key, spec in specs.items()
    }
    version = versions[active_sop]

    reused: SOPExecution | None = None
    for execution in _active_on_station(session):
        if execution.sop_version_id == version.id and reused is None:
            reused = execution
            continue
        abort_execution(
            session,
            execution_id=execution.id,
            reason=f"demo seed activated {active_sop}",
            now=now,
        )

    if reused is not None and reused.accept_events_until < now:
        abort_execution(
            session,
            execution_id=reused.id,
            reason="demo seed replaced an execution past its accept window",
            now=now,
        )
        reused = None
    created_execution = reused is None
    if reused is None:
        detail = create_execution(
            session,
            station_id="st-01",
            sop_version_id=version.id,
            workpiece_id=None,
            now=now,
        )
        execution_id = detail.id
    else:
        execution_id = reused.id
    session.commit()
    return SeedResult(
        sop_key=active_sop,
        station_id="st-01",
        camera_id="cam-01",
        sop_version_id=version.id,
        execution_id=execution_id,
        created_execution=created_execution,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sop", default=DEFAULT_SOP_KEY, choices=[s.key for s in SEED_SPECS]
    )
    args = parser.parse_args()
    with Session(engine) as session:
        result = seed_demo(session, datetime.now(UTC), active_sop=args.sop)
    print(  # noqa: T201
        f"sop={result.sop_key} station={result.station_id} "
        f"camera={result.camera_id} sop_version={result.sop_version_id} "
        f"execution={result.execution_id} "
        f"created_execution={result.created_execution}",
        file=sys.stdout,
    )
    print(  # noqa: T201
        "preview: http://127.0.0.1:8001/stream/cam-01", file=sys.stdout
    )


if __name__ == "__main__":
    main()
