from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas.sop import (
    SopCreate,
    SopDetailRead,
    SopDraftUpdate,
    SopRead,
    SopValidationRead,
    SopVersionRead,
)
from app.application import sop_service

router = APIRouter(prefix="/sops", tags=["sops"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[SopRead], name="list_sops")
def list_sops(session: SessionDep) -> list[SopRead]:
    return sop_service.list_sops(session)


@router.post("", response_model=SopVersionRead, status_code=201, name="create_sop")
def create_sop(payload: SopCreate, session: SessionDep) -> SopVersionRead:
    try:
        version = sop_service.create_sop(
            session,
            key=payload.key,
            name=payload.name,
            dsl=payload.dsl,
            now=_now(),
        )
    except sop_service.SopKeyConflict:
        raise HTTPException(status_code=409, detail="SOP key already exists") from None
    except sop_service.SopInvalid as exc:
        raise HTTPException(
            status_code=422, detail=[issue.model_dump() for issue in exc.issues]
        ) from None
    session.commit()
    session.refresh(version)
    return sop_service.version_read(session, version)


@router.get("/{sop_id}", response_model=SopDetailRead, name="get_sop")
def get_sop(sop_id: str, session: SessionDep) -> SopDetailRead:
    try:
        return sop_service.get_sop(session, sop_id=sop_id)
    except sop_service.SopNotFound:
        raise HTTPException(status_code=404, detail="SOP not found") from None


@router.patch("/{sop_id}", response_model=SopVersionRead, name="update_sop_draft")
def update_sop_draft(
    sop_id: str, payload: SopDraftUpdate, session: SessionDep
) -> SopVersionRead:
    try:
        version = sop_service.update_draft(
            session, sop_id=sop_id, dsl=payload.dsl, now=_now()
        )
    except sop_service.SopNotFound:
        raise HTTPException(status_code=404, detail="SOP not found") from None
    except sop_service.SopInvalid as exc:
        raise HTTPException(
            status_code=422, detail=[issue.model_dump() for issue in exc.issues]
        ) from None
    session.commit()
    session.refresh(version)
    return sop_service.version_read(session, version)


@router.post(
    "/{sop_id}/validate", response_model=SopValidationRead, name="validate_sop"
)
def validate_sop(sop_id: str, session: SessionDep) -> SopValidationRead:
    try:
        return sop_service.validate_sop(session, sop_id=sop_id)
    except sop_service.SopNotFound:
        raise HTTPException(status_code=404, detail="SOP not found") from None


@router.post("/{sop_id}/publish", response_model=SopVersionRead, name="publish_sop")
def publish_sop(sop_id: str, session: SessionDep) -> SopVersionRead:
    try:
        version = sop_service.publish_sop(session, sop_id=sop_id, now=_now())
    except sop_service.SopNotFound:
        raise HTTPException(status_code=404, detail="SOP not found") from None
    except sop_service.SopAlreadyPublished:
        raise HTTPException(
            status_code=409, detail="SOP version is already published"
        ) from None
    except sop_service.SopInvalid as exc:
        raise HTTPException(
            status_code=422, detail=[issue.model_dump() for issue in exc.issues]
        ) from None
    session.commit()
    session.refresh(version)
    return sop_service.version_read(session, version)


@router.get(
    "/{sop_id}/versions",
    response_model=list[SopVersionRead],
    name="list_sop_versions",
)
def list_sop_versions(sop_id: str, session: SessionDep) -> list[SopVersionRead]:
    try:
        return sop_service.list_versions(session, sop_id=sop_id)
    except sop_service.SopNotFound:
        raise HTTPException(status_code=404, detail="SOP not found") from None
