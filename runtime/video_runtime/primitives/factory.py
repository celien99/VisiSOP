from collections.abc import Callable

from video_runtime.primitives.base import Primitive
from video_runtime.primitives.count import CountThreshold
from video_runtime.primitives.in_zone import ObjectInZone
from video_runtime.primitives.orientation import OrientationMatch
from video_runtime.primitives.presence import ObjectAbsent, ObjectPresent
from video_runtime.primitives.state import StateClassify

_FACTORIES: dict[str, Callable[[], Primitive]] = {
    "object_present": ObjectPresent,
    "object_absent": ObjectAbsent,
    "object_in_zone": ObjectInZone,
    "count_threshold": CountThreshold,
    "state_classify": StateClassify,
    "orientation_match": OrientationMatch,
}


def build_primitive(primitive_id: str) -> Primitive:
    """Give every binding its own stateful primitive instance."""
    try:
        factory = _FACTORIES[primitive_id]
    except KeyError:
        raise NotImplementedError(
            f"primitive {primitive_id!r} has a contract but no runtime implementation"
        ) from None
    return factory()
