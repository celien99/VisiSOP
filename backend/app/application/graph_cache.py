from contracts.catalog import catalog_snapshot
from sop_dsl.schema import SOPSpec
from sqlmodel import Session

from app.domain.sop.compiler import compile_spec
from app.domain.sop.model import SOPGraph
from app.models import SOPVersion


class GraphNotFound(LookupError):
    pass


# shortcut: in-process cache; published versions are immutable, no invalidation.
_CACHE: dict[tuple[str, str], SOPGraph] = {}


def load_graph(session: Session, sop_version_id: str) -> SOPGraph:
    version = session.get(SOPVersion, sop_version_id)
    if version is None:
        raise GraphNotFound(sop_version_id)
    key = (version.id, version.content_hash)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    graph = compile_spec(
        SOPSpec.model_validate(version.dsl),
        known_event_types=catalog_snapshot().keys(),
    )
    _CACHE[key] = graph
    return graph
