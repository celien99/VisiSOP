from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import EvidenceStoreDep, SessionDep
from app.models import EvidenceAsset, EvidenceStatus

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/{evidence_id}", response_class=FileResponse, name="get_evidence")
def get_evidence(
    evidence_id: str, session: SessionDep, store: EvidenceStoreDep
) -> FileResponse:
    asset = session.get(EvidenceAsset, evidence_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    status = EvidenceStatus(asset.status)
    if status is not EvidenceStatus.AVAILABLE:
        raise HTTPException(
            status_code=404, detail=f"evidence unavailable: {status.value}"
        )
    path = store.path_for(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="evidence unavailable: MISSING")
    return FileResponse(path, media_type="image/jpeg")
