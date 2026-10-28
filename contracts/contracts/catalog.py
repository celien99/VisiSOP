import re
from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from contracts.version import SCHEMA_VERSION


class UnknownEventType(ValueError):
    """Raised when an event type is not registered in the catalog."""


class InvalidAttributes(ValueError):
    """Raised when event attributes do not match the registered schema."""


class _StrictAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _EmptyAttributes(_StrictAttributes):
    pass


class _PartPlacedAttributes(_StrictAttributes):
    part_id: str
    zone: str


class _ScrewTightenedVisualAttributes(_StrictAttributes):
    tool_id: str


@dataclass(frozen=True)
class EventTypeSpec:
    event_type: str
    attributes_model: type[BaseModel]
    correlation_key_template: str | None = None
    schema_version: str = SCHEMA_VERSION


_ALLOWED_PLACEHOLDER = re.compile(
    r"^(?:station_id|(?:attributes|binding)\.[A-Za-z_][A-Za-z0-9_]*)$"
)

_CATALOG: dict[str, EventTypeSpec] = {}


def _validate_template(template: str) -> None:
    for _, field_name, format_spec, conversion in Formatter().parse(template):
        if field_name is None:
            continue
        if format_spec or conversion or not _ALLOWED_PLACEHOLDER.fullmatch(field_name):
            raise ValueError(f"disallowed correlation key placeholder: {field_name!r}")


def register_event_type(spec: EventTypeSpec) -> None:
    if spec.correlation_key_template is not None:
        _validate_template(spec.correlation_key_template)
    _CATALOG[spec.event_type] = spec


def get_event_type(event_type: str) -> EventTypeSpec:
    try:
        return _CATALOG[event_type]
    except KeyError:
        raise UnknownEventType(event_type) from None


def validate_attributes(event_type: str, attributes: Mapping[str, Any]) -> BaseModel:
    spec = get_event_type(event_type)
    try:
        return spec.attributes_model.model_validate(attributes)
    except ValidationError as exc:
        raise InvalidAttributes(str(exc)) from exc


def _resolve_placeholder(
    field_name: str,
    attributes: Mapping[str, Any],
    station_id: str,
    binding: Mapping[str, str],
) -> str | None:
    if field_name == "station_id":
        return station_id
    namespace, _, key = field_name.partition(".")
    source: Mapping[str, Any] = attributes if namespace == "attributes" else binding
    value = source.get(key)
    return None if value is None else str(value)


def correlation_key_for(
    event_type: str,
    attributes: Mapping[str, Any],
    *,
    station_id: str,
    binding: Mapping[str, str] | None = None,
) -> str | None:
    template = get_event_type(event_type).correlation_key_template
    if template is None:
        return None

    parts: list[str] = []
    for literal, field_name, _, _ in Formatter().parse(template):
        parts.append(literal)
        if field_name is None:
            continue
        value = _resolve_placeholder(field_name, attributes, station_id, binding or {})
        if value is None:
            return None
        parts.append(value)
    return "".join(parts)


def catalog_snapshot() -> Mapping[str, EventTypeSpec]:
    return MappingProxyType(dict(_CATALOG))


for _event_type in (
    "frame_placed",
    "left_bolt_installed",
    "right_bolt_installed",
    "both_bolts_present",
    "assembly_present",
):
    register_event_type(
        EventTypeSpec(event_type=_event_type, attributes_model=_EmptyAttributes)
    )

register_event_type(
    EventTypeSpec(event_type="part_placed", attributes_model=_PartPlacedAttributes)
)
register_event_type(
    EventTypeSpec(
        event_type="screw_tightened_visual",
        attributes_model=_ScrewTightenedVisualAttributes,
    )
)
