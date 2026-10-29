import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import contracts.demo  # noqa: F401  (registers the demo event catalog)
from contracts.enums import CameraRole
from sqlmodel import Session, col, select

from app.application.execution_service import create_execution
from app.application.sop_service import create_sop, publish_sop
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

SEED_PATH = Path(__file__).parents[1] / "seed" / "bottle_transfer.json"
_ACTIVE = (
    ExecutionStatus.RUNNING,
    ExecutionStatus.PAUSED,
    ExecutionStatus.NEEDS_REVIEW,
)


@dataclass(frozen=True)
class SeedResult:
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
                source_type="gige",
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


def _published_version(session: Session, now: datetime) -> SOPVersion:
    definition = session.exec(
        select(SOPDefinition).where(SOPDefinition.key == "bottle_transfer")
    ).first()
    if definition is None:
        dsl = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        version = create_sop(
            session,
            key="bottle_transfer",
            name="瓶体转移演示",
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
    for version in versions:
        if version.status == SopVersionStatus.PUBLISHED:
            return version
    if not versions:
        raise RuntimeError("bottle_transfer has no versions")
    published = publish_sop(session, sop_id=definition.id, now=now)
    session.flush()
    return published


def seed_demo(session: Session, now: datetime) -> SeedResult:
    _station_and_camera(session, now)
    version = _published_version(session, now)

    active = session.exec(
        select(SOPExecution).where(
            col(SOPExecution.station_id) == "st-01",
            col(SOPExecution.status).in_(_ACTIVE),
        )
    ).first()
    created_execution = active is None
    if active is None:
        detail = create_execution(
            session,
            station_id="st-01",
            sop_version_id=version.id,
            workpiece_id=None,
            now=now,
        )
        execution_id = detail.id
    else:
        execution_id = active.id
    session.commit()
    return SeedResult(
        station_id="st-01",
        camera_id="cam-01",
        sop_version_id=version.id,
        execution_id=execution_id,
        created_execution=created_execution,
    )


def main() -> None:
    with Session(engine) as session:
        result = seed_demo(session, datetime.now(UTC))
    print(  # noqa: T201
        f"station={result.station_id} camera={result.camera_id} "
        f"sop_version={result.sop_version_id} execution={result.execution_id} "
        f"created_execution={result.created_execution}",
        file=sys.stdout,
    )
    print(  # noqa: T201
        "preview: http://127.0.0.1:8001/stream/cam-01", file=sys.stdout
    )


if __name__ == "__main__":
    main()
