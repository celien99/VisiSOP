"""Perception primitive registry.

A primitive is one reusable visual capability (presence, count, state, ...).
Event types are primitive instances: they pin the primitive id and define the
attributes that flow to the SOP engine. Primitives only look at one camera;
process state stays in the backend.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict


class UnknownPrimitive(ValueError):
    """Raised when an event type references an unregistered primitive."""


class _StrictParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObjectPresentParams(_StrictParams):
    object_class: str
    zone: str
    rect: tuple[float, float, float, float] | None = None
    min_conf: float = 0.25


class ObjectAbsentParams(ObjectPresentParams):
    frames: int = 3


class ObjectInZoneParams(ObjectPresentParams):
    rect: tuple[float, float, float, float]
    dwell_ms: int = 0


class ObjectPlacedParams(ObjectInZoneParams):
    stable_ms: int = 500


class CountThresholdParams(_StrictParams):
    object_class: str
    # Extra classes that also denote the same instance kind. The remote-battery
    # labels a battery as either ``battery`` or its orientation class
    # (``CORRECT`` / ``REVERSED``), never both.
    count_classes: tuple[str, ...] = ()
    compartment: str
    roi: tuple[float, float, float, float]
    slots: int = 2
    min_conf: float = 0.25


class StateClassifyParams(_StrictParams):
    roi: tuple[float, float, float, float]
    states: tuple[str, ...]
    min_conf: float = 0.5


class OrientationMatchParams(_StrictParams):
    object_class: str
    compartment: str
    roi: tuple[float, float, float, float]
    correct_class: str = "CORRECT"
    reversed_class: str | None = None
    min_conf: float = 0.5


class FasteningActionParams(_StrictParams):
    tool_class: str
    zone: str
    min_duration_ms: int = 300


@dataclass(frozen=True)
class PrimitiveSpec:
    primitive_id: str
    version: str
    description: str
    params_model: type[BaseModel]


_REGISTRY: dict[str, PrimitiveSpec] = {}


def register_primitive(spec: PrimitiveSpec) -> None:
    _REGISTRY[spec.primitive_id] = spec


def get_primitive(primitive_id: str) -> PrimitiveSpec:
    try:
        return _REGISTRY[primitive_id]
    except KeyError:
        raise UnknownPrimitive(primitive_id) from None


def primitive_snapshot() -> Mapping[str, PrimitiveSpec]:
    return MappingProxyType(dict(_REGISTRY))


for _spec in (
    PrimitiveSpec(
        "object_present",
        "1.0",
        "an object class appears in a zone",
        ObjectPresentParams,
    ),
    PrimitiveSpec(
        "object_absent",
        "1.0",
        "a zone stays free of an object class",
        ObjectAbsentParams,
    ),
    PrimitiveSpec(
        "object_in_zone",
        "1.0",
        "an object center stays inside a rectangle",
        ObjectInZoneParams,
    ),
    PrimitiveSpec(
        "object_placed",
        "1.0",
        "an object comes to rest inside a rectangle",
        ObjectPlacedParams,
    ),
    PrimitiveSpec(
        "count_threshold",
        "1.0",
        "count object instances inside a rectangle",
        CountThresholdParams,
    ),
    PrimitiveSpec(
        "state_classify",
        "1.0",
        "classify a region into a closed state set",
        StateClassifyParams,
    ),
    PrimitiveSpec(
        "orientation_match",
        "1.0",
        "check an object orientation against a reference",
        OrientationMatchParams,
    ),
    PrimitiveSpec(
        "fastening_action",
        "1.0",
        "a tool performs a fastening action in a zone",
        FasteningActionParams,
    ),
):
    register_primitive(_spec)


def params_for(primitive_id: str, params: dict[str, Any]) -> BaseModel:
    return get_primitive(primitive_id).params_model.model_validate(params)
