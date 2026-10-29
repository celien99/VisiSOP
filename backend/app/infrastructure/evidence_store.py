import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.models.evidence import EvidenceAsset, EvidenceStatus


@dataclass(frozen=True)
class IngestedEvidence:
    storage_key: str
    final_key: str | None
    sha256: str | None
    byte_size: int | None
    width: int | None
    height: int | None
    status: EvidenceStatus


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, asset: EvidenceAsset) -> Path:
        return self.root / asset.storage_key

    def ingest(self, _event_id: str, refs: Sequence[str]) -> list[IngestedEvidence]:
        return [self._ingest_one(ref) for ref in refs]

    def _ingest_one(self, ref: str) -> IngestedEvidence:
        key = self._normalise(ref)
        source = (self.root / key).resolve()
        if not source.is_relative_to(self.root):
            raise ValueError(f"evidence ref escapes root: {ref!r}")
        if not source.is_file():
            return IngestedEvidence(
                storage_key=key,
                final_key=None,
                sha256=None,
                byte_size=None,
                width=None,
                height=None,
                status=EvidenceStatus.MISSING,
            )

        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        try:
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
        except UnidentifiedImageError:
            return IngestedEvidence(
                storage_key=key,
                final_key=None,
                sha256=digest,
                byte_size=len(data),
                width=None,
                height=None,
                status=EvidenceStatus.PENDING_VERIFY,
            )

        final_key = f"evidence/{uuid4()}.jpg"
        destination = self.root / final_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        return IngestedEvidence(
            storage_key=final_key,
            final_key=final_key,
            sha256=digest,
            byte_size=len(data),
            width=width,
            height=height,
            status=EvidenceStatus.AVAILABLE,
        )

    @staticmethod
    def _normalise(ref: str) -> str:
        path = PurePosixPath(ref)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or path.parts[0] != "tmp"
            or ":" in path.parts[0]
        ):
            raise ValueError(f"invalid evidence ref: {ref!r}")
        return path.as_posix()
