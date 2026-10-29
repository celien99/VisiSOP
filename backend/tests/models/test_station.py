import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import (
    Camera,
    SOPDefinition,
    SOPVersion,
    Station,
    StationCameraBinding,
)


def test_station_camera_binding_round_trip(db_session: Session, now) -> None:
    station = Station(id="st-01", code="ST-01", name="演示工位", created_at=now)
    camera = Camera(
        id="cam-01",
        code="CAM-01",
        name="主相机",
        runtime_id="runtime-01",
        source_type="gige",
        source_config={"serial": "demo"},
        created_at=now,
    )
    db_session.add(station)
    db_session.add(camera)
    db_session.commit()
    db_session.add(
        StationCameraBinding(
            id="bind-01",
            station_id="st-01",
            camera_id="cam-01",
            role="overview",
            valid_from=now,
        )
    )
    db_session.commit()
    binding = db_session.get(StationCameraBinding, "bind-01")
    assert binding is not None
    assert binding.role == "overview"


def test_sop_version_is_unique_per_definition(db_session: Session, now) -> None:
    sop = SOPDefinition(id="sop-1", key="k", name="K", created_at=now)
    db_session.add(sop)
    db_session.commit()
    base = {
        "sop_id": "sop-1",
        "version": 1,
        "status": "DRAFT",
        "dsl": {},
        "dsl_schema_version": "1.0",
        "content_hash": "h",
        "created_at": now,
    }
    db_session.add(SOPVersion(id="v1", **base))  # type: ignore[arg-type]
    db_session.commit()
    db_session.add(SOPVersion(id="v2", **base))  # type: ignore[arg-type]
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
