"""SOP DSL schema version, independent of the event contract version."""

SOP_SCHEMA_VERSION: str = "2.0"
SUPPORTED_SOP_SCHEMA_VERSIONS: frozenset[str] = frozenset({SOP_SCHEMA_VERSION})
