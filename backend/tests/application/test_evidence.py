from pathlib import Path

import pytest
from PIL import Image

from app.infrastructure.evidence_store import EvidenceStore


def test_ingest_moves_verifies_and_links(evidence_dir: Path) -> None:
    (evidence_dir / "tmp").mkdir()
    Image.new("RGB", (64, 48), "black").save(
        evidence_dir / "tmp" / "evt-1.jpg", "JPEG"
    )
    store = EvidenceStore(evidence_dir)
    [asset] = store.ingest("evt-1", ["tmp/evt-1.jpg"])
    assert asset.status == "AVAILABLE"
    assert asset.width == 64
    assert asset.height == 48
    assert asset.sha256
    assert asset.byte_size is not None and asset.byte_size > 0
    assert not (evidence_dir / "tmp" / "evt-1.jpg").exists()
    assert asset.final_key is not None
    assert (evidence_dir / asset.final_key).exists()


def test_missing_ref_is_explicit_and_path_traversal_is_rejected(
    evidence_dir: Path,
) -> None:
    store = EvidenceStore(evidence_dir)
    [missing] = store.ingest("evt-2", ["tmp/evt-2.jpg"])
    assert missing.status == "MISSING"
    assert missing.sha256 is None
    with pytest.raises(ValueError):
        store.ingest("evt-3", ["../etc/passwd"])
    with pytest.raises(ValueError):
        store.ingest("evt-4", ["C:/Windows/win.ini"])
