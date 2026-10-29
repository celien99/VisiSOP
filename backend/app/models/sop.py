from datetime import datetime
from enum import StrEnum
from typing import Any

from sop_dsl.schema import StepType
from sqlalchemy import Column, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.columns import jsonb, timestamptz


class SopVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class SOPDefinition(SQLModel, table=True):
    __tablename__ = "sop_definitions"

    id: str = Field(primary_key=True)
    key: str = Field(unique=True, index=True)
    name: str
    created_at: datetime = Field(sa_column=timestamptz())


class SOPVersion(SQLModel, table=True):
    __tablename__ = "sop_versions"
    __table_args__ = (
        UniqueConstraint("sop_id", "version", name="uq_sop_versions_sop_id_version"),
    )

    id: str = Field(primary_key=True)
    sop_id: str = Field(foreign_key="sop_definitions.id", index=True)
    version: int
    status: SopVersionStatus = Field(sa_column=Column(String, nullable=False))
    dsl: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    dsl_schema_version: str
    content_hash: str
    created_at: datetime = Field(sa_column=timestamptz())
    published_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )


class SOPStepDefinition(SQLModel, table=True):
    __tablename__ = "sop_step_definitions"
    __table_args__ = (
        UniqueConstraint(
            "sop_version_id", "step_key", name="uq_sop_step_definitions_version_step"
        ),
    )

    id: str = Field(primary_key=True)
    sop_version_id: str = Field(foreign_key="sop_versions.id", index=True)
    step_key: str
    name: str
    type: StepType = Field(sa_column=Column(String, nullable=False))
    required: bool
    depends_on: list[str] = Field(default_factory=list, sa_column=jsonb())


class SOPStepDependency(SQLModel, table=True):
    __tablename__ = "sop_step_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "sop_version_id",
            "step_key",
            "depends_on_key",
            name="uq_sop_step_dependencies_version_step_dependency",
        ),
    )

    id: str = Field(primary_key=True)
    sop_version_id: str = Field(foreign_key="sop_versions.id", index=True)
    step_key: str
    depends_on_key: str
