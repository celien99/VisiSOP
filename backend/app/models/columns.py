"""Column helpers shared by the table models."""

from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB


def timestamptz(*, nullable: bool = False) -> Column[datetime]:
    """A UTC timezone-aware column; every stored time is UTC-aware."""
    return Column(DateTime(timezone=True), nullable=nullable)


def jsonb(*, nullable: bool = False) -> Column:  # type: ignore[type-arg]
    return Column(JSONB, nullable=nullable)
