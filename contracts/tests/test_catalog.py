import pytest
from pydantic import BaseModel, ConfigDict

from contracts.catalog import (
    EventTypeSpec,
    InvalidAttributes,
    UnknownEventType,
    catalog_snapshot,
    correlation_key_for,
    register_event_type,
    validate_attributes,
)


class _Keyed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    side: str


def test_registered_type_validates_attributes() -> None:
    assert validate_attributes("part_placed", {"part_id": "p1", "zone": "Z1"})
    with pytest.raises(InvalidAttributes):
        validate_attributes("part_placed", {"part_id": "p1"})
    with pytest.raises(InvalidAttributes):
        validate_attributes("part_placed", {"part_id": "p1", "zone": "Z1", "x": 1})


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(UnknownEventType):
        validate_attributes("not_registered", {})


def test_catalog_snapshot_is_read_only() -> None:
    snapshot = catalog_snapshot()
    assert "part_placed" in snapshot
    with pytest.raises(TypeError):
        snapshot["x"] = snapshot["part_placed"]  # type: ignore[index]  # ty: ignore[invalid-assignment]


def test_correlation_key_uses_only_whitelisted_placeholders() -> None:
    register_event_type(
        EventTypeSpec(
            event_type="test_keyed",
            attributes_model=_Keyed,
            correlation_key_template="{station_id}:{binding.workpiece}:{attributes.side}",
        )
    )
    assert (
        correlation_key_for(
            "test_keyed",
            {"side": "left"},
            station_id="s1",
            binding={"workpiece": "w1"},
        )
        == "s1:w1:left"
    )


def test_missing_placeholder_yields_no_key() -> None:
    register_event_type(
        EventTypeSpec(
            event_type="test_missing",
            attributes_model=_Keyed,
            correlation_key_template="{station_id}:{attributes.workpiece}",
        )
    )
    assert (
        correlation_key_for("test_missing", {"side": "left"}, station_id="s1") is None
    )


def test_disallowed_placeholder_is_rejected_at_registration() -> None:
    with pytest.raises(ValueError):
        register_event_type(
            EventTypeSpec(
                event_type="test_bad",
                attributes_model=_Keyed,
                correlation_key_template="{attributes.side.__class__}",
            )
        )
