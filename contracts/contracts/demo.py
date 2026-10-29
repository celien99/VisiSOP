"""Demo event types for the bottle-transfer vertical slice (B1).

These are demo fixtures, not catalog defaults: B2 replaces them with
parameterized catalog instances. Importing this module registers them.
"""

from pydantic import BaseModel, ConfigDict

from contracts.catalog import EventTypeSpec, register_event_type
from contracts.version import SCHEMA_VERSION


class ZoneObjectAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_class: str
    zone: str
    bbox: tuple[float, float, float, float]
    track_id: str | None = None


CORRELATION_KEY_TEMPLATE = "{station_id}:{attributes.zone}:{attributes.object_class}"

for _event_type in ("bottle_in_pickup_zone", "bottle_in_target_zone"):
    register_event_type(
        EventTypeSpec(
            event_type=_event_type,
            attributes_model=ZoneObjectAttributes,
            correlation_key_template=CORRELATION_KEY_TEMPLATE,
            schema_version=SCHEMA_VERSION,
        )
    )
