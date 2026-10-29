from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.infrastructure.evidence_store import EvidenceStore
from app.infrastructure.runtime_client import RuntimeClient, RuntimeClientFactory


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def get_runtime_client_factory() -> RuntimeClientFactory:
    return lambda base_url: RuntimeClient(base_url)


RuntimeClientFactoryDep = Annotated[
    RuntimeClientFactory, Depends(get_runtime_client_factory)
]


def get_evidence_store() -> EvidenceStore:
    return EvidenceStore(settings.EVIDENCE_DIR)


EvidenceStoreDep = Annotated[EvidenceStore, Depends(get_evidence_store)]
