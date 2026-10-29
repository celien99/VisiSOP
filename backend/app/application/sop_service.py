import json
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from contracts.catalog import catalog_snapshot
from pydantic import ValidationError
from sop_dsl.schema import SOPSpec
from sop_dsl.validate import DSLValidationError
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.api.schemas.sop import (
    SopDetailRead,
    SopIssue,
    SopRead,
    SopStepRead,
    SopValidationRead,
    SopVersionRead,
    SopVersionSummary,
)
from app.application.audit import write_audit
from app.domain.sop.compiler import compile_spec
from app.domain.sop.model import SOPGraph
from app.models import (
    SOPDefinition,
    SOPStepDefinition,
    SOPStepDependency,
    SOPVersion,
    SopVersionStatus,
)


class SopNotFound(LookupError):
    pass


class SopKeyConflict(ValueError):
    pass


class SopAlreadyPublished(ValueError):
    pass


class SopInvalid(ValueError):
    def __init__(self, issues: list[SopIssue]) -> None:
        self.issues = issues
        super().__init__(f"{len(issues)} SOP validation issue(s)")


def _canonical_hash(dsl: dict[str, Any]) -> str:
    canonical = json.dumps(
        dsl, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _parse(dsl: dict[str, Any]) -> SOPSpec:
    try:
        return SOPSpec.model_validate(dsl)
    except ValidationError as exc:
        issues = [
            SopIssue(code="INVALID_SHAPE", message=str(error["msg"]))
            for error in exc.errors()
        ]
        raise SopInvalid(issues) from exc


def _compile(spec: SOPSpec) -> SOPGraph:
    try:
        return compile_spec(spec, known_event_types=catalog_snapshot().keys())
    except DSLValidationError as exc:
        raise SopInvalid(
            [
                SopIssue(
                    code=issue.code, message=issue.message, step_key=issue.step_key
                )
                for issue in exc.issues
            ]
        ) from exc


def _definition(session: Session, sop_id: str) -> SOPDefinition:
    definition = session.get(SOPDefinition, sop_id)
    if definition is None:
        raise SopNotFound(sop_id)
    return definition


def _versions(session: Session, sop_id: str) -> list[SOPVersion]:
    statement = (
        select(SOPVersion)
        .where(SOPVersion.sop_id == sop_id)
        .order_by(col(SOPVersion.version).desc())
    )
    return list(session.exec(statement).all())


def _latest(session: Session, sop_id: str) -> SOPVersion:
    versions = _versions(session, sop_id)
    if not versions:
        raise SopNotFound(sop_id)
    return versions[0]


def _replace_steps(session: Session, version: SOPVersion, spec: SOPSpec) -> None:
    session.exec(
        delete(SOPStepDefinition).where(
            col(SOPStepDefinition.sop_version_id) == version.id
        )
    )
    session.exec(
        delete(SOPStepDependency).where(
            col(SOPStepDependency.sop_version_id) == version.id
        )
    )
    for step in spec.steps:
        session.add(
            SOPStepDefinition(
                id=str(uuid4()),
                sop_version_id=version.id,
                step_key=step.key,
                name=step.name,
                type=step.type,
                required=step.required,
                depends_on=list(step.depends_on),
            )
        )
        for dependency in step.depends_on:
            session.add(
                SOPStepDependency(
                    id=str(uuid4()),
                    sop_version_id=version.id,
                    step_key=step.key,
                    depends_on_key=dependency,
                )
            )


def create_sop(
    session: Session, *, key: str, name: str, dsl: dict[str, Any], now: datetime
) -> SOPVersion:
    existing = session.exec(
        select(SOPDefinition).where(SOPDefinition.key == key)
    ).first()
    if existing is not None:
        raise SopKeyConflict(key)

    version_dsl = {**dsl, "sop_key": key, "version": 1}
    spec = _parse(version_dsl)
    definition = SOPDefinition(id=str(uuid4()), key=key, name=name, created_at=now)
    version = SOPVersion(
        id=str(uuid4()),
        sop_id=definition.id,
        version=1,
        status=SopVersionStatus.DRAFT,
        dsl=version_dsl,
        dsl_schema_version=spec.schema_version,
        content_hash=_canonical_hash(version_dsl),
        created_at=now,
    )
    session.add(definition)
    session.add(version)
    _replace_steps(session, version, spec)
    write_audit(
        session,
        actor="system",
        action="sop.created",
        object_type="sop_version",
        object_id=version.id,
        detail={"key": key, "version": 1},
        now=now,
    )
    return version


def update_draft(
    session: Session, *, sop_id: str, dsl: dict[str, Any], now: datetime
) -> SOPVersion:
    definition = _definition(session, sop_id)
    latest = _latest(session, sop_id)
    is_draft = latest.status == SopVersionStatus.DRAFT
    target_version = latest.version if is_draft else latest.version + 1

    version_dsl = {**dsl, "sop_key": definition.key, "version": target_version}
    spec = _parse(version_dsl)
    content_hash = _canonical_hash(version_dsl)
    if is_draft:
        version = latest
        version.dsl = version_dsl
        version.dsl_schema_version = spec.schema_version
        version.content_hash = content_hash
    else:
        version = SOPVersion(
            id=str(uuid4()),
            sop_id=definition.id,
            version=target_version,
            status=SopVersionStatus.DRAFT,
            dsl=version_dsl,
            dsl_schema_version=spec.schema_version,
            content_hash=content_hash,
            created_at=now,
        )
    session.add(version)
    _replace_steps(session, version, spec)
    write_audit(
        session,
        actor="system",
        action="sop.draft_updated",
        object_type="sop_version",
        object_id=version.id,
        detail={"key": definition.key, "version": target_version},
        now=now,
    )
    return version


def validate_sop(session: Session, *, sop_id: str) -> SopValidationRead:
    _definition(session, sop_id)
    version = _latest(session, sop_id)
    try:
        _compile(_parse(version.dsl))
    except SopInvalid as exc:
        return SopValidationRead(valid=False, issues=exc.issues)
    return SopValidationRead(valid=True, issues=[])


def publish_sop(session: Session, *, sop_id: str, now: datetime) -> SOPVersion:
    definition = _definition(session, sop_id)
    version = _latest(session, sop_id)
    if version.status != SopVersionStatus.DRAFT:
        raise SopAlreadyPublished(version.id)

    graph = _compile(_parse(version.dsl))
    version.status = SopVersionStatus.PUBLISHED
    version.published_at = now
    version.content_hash = graph.content_hash
    session.add(version)
    write_audit(
        session,
        actor="system",
        action="sop.published",
        object_type="sop_version",
        object_id=version.id,
        detail={"key": definition.key, "version": version.version},
        now=now,
    )
    return version


def _summary(version: SOPVersion) -> SopVersionSummary:
    return SopVersionSummary(
        id=version.id,
        sop_id=version.sop_id,
        version=version.version,
        status=version.status,
        dsl_schema_version=version.dsl_schema_version,
        content_hash=version.content_hash,
        created_at=version.created_at,
        published_at=version.published_at,
    )


def _ordered_steps(session: Session, version: SOPVersion) -> list[SopStepRead]:
    rows = list(
        session.exec(
            select(SOPStepDefinition).where(
                SOPStepDefinition.sop_version_id == version.id
            )
        ).all()
    )
    dsl_steps = version.dsl.get("steps", [])
    position = {
        step["key"]: index
        for index, step in enumerate(dsl_steps)
        if isinstance(step, dict) and isinstance(step.get("key"), str)
    }
    rows.sort(key=lambda row: position.get(row.step_key, len(position)))
    return [
        SopStepRead(
            key=row.step_key,
            name=row.name,
            type=row.type,
            required=row.required,
            depends_on=list(row.depends_on),
        )
        for row in rows
    ]


def version_read(session: Session, version: SOPVersion) -> SopVersionRead:
    summary = _summary(version)
    return SopVersionRead(
        **summary.model_dump(),
        dsl=version.dsl,
        steps=_ordered_steps(session, version),
    )


def list_versions(session: Session, *, sop_id: str) -> list[SopVersionRead]:
    _definition(session, sop_id)
    return [version_read(session, version) for version in _versions(session, sop_id)]


def _read(session: Session, definition: SOPDefinition) -> SopRead:
    versions = _versions(session, definition.id)
    published = [
        version for version in versions if version.status == SopVersionStatus.PUBLISHED
    ]
    return SopRead(
        id=definition.id,
        key=definition.key,
        name=definition.name,
        created_at=definition.created_at,
        latest_published_version_id=published[0].id if published else None,
        versions=[_summary(version) for version in versions],
    )


def list_sops(session: Session) -> list[SopRead]:
    definitions = session.exec(select(SOPDefinition).order_by(SOPDefinition.key)).all()
    return [_read(session, definition) for definition in definitions]


def get_sop(session: Session, *, sop_id: str) -> SopDetailRead:
    definition = _definition(session, sop_id)
    base = _read(session, definition)
    return SopDetailRead(
        id=base.id,
        key=base.key,
        name=base.name,
        created_at=base.created_at,
        latest_published_version_id=base.latest_published_version_id,
        versions=[
            version_read(session, version) for version in _versions(session, sop_id)
        ],
    )
