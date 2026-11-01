import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import contracts.demo  # noqa: F401  (registers the bottle demo event types)
import yaml
from contracts.catalog import get_event_type
from contracts.enums import CameraRole
from contracts.primitives import get_primitive
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileSourceConfig(_ConfigModel):
    kind: Literal["file"] = "file"
    path: Path
    loop: bool = True


class _GigECameraConfig(_ConfigModel):
    serial: str | None = None
    ip: str | None = None
    timeout_ms: int = 2000


class GigESourceConfig(_GigECameraConfig):
    kind: Literal["gige"] = "gige"
    cti_path: Path
    width: int = 2048
    height: int = 1536
    offset_x: int = 0
    offset_y: int = 0
    pixel_format: str = "BayerRG8"
    exposure_us: int = 8000
    gain_db: float = 0.0
    packet_size: int = 8192


class MvsSourceConfig(_GigECameraConfig):
    """HIKROBOT's own SDK.

    Only exposure and gain are written; resolution, pixel format, triggering,
    and the network packet size stay exactly as configured on the camera.
    """

    kind: Literal["mvs"] = "mvs"
    exposure_us: int = 8000
    gain_db: float = 0.0


SourceConfig = Annotated[
    FileSourceConfig | GigESourceConfig | MvsSourceConfig,
    Field(discriminator="kind"),
]


class CameraConfig(_ConfigModel):
    camera_id: str
    role: CameraRole
    source: SourceConfig


class BackendConfig(_ConfigModel):
    base_url: str
    timeout_ms: int = 2000
    retries: int = 3


class ModelConfig(_ConfigModel):
    onnx_path: Path
    class_names_path: Path
    input_size: int = 640
    confidence: float = 0.25
    iou: float = 0.45


class BindingConfig(_ConfigModel):
    """One event type bound to a primitive and its resolved parameters."""

    event_type: str
    primitive: str
    params: dict[str, Any]
    emit_interval_ms: int = Field(default=500, ge=0)
    evidence: bool = True

    @model_validator(mode="after")
    def _check_binding(self) -> Self:
        spec = get_event_type(self.event_type)
        primitive = get_primitive(self.primitive)
        if spec.primitive_id != self.primitive:
            raise ValueError(
                f"event {self.event_type!r} is a {spec.primitive_id!r} instance, "
                f"not {self.primitive!r}"
            )
        primitive.params_model.model_validate(self.params)
        return self


class PreviewConfig(_ConfigModel):
    host: str = "127.0.0.1"
    port: int = 8001
    fps: int = 10
    overlay: Literal["off", "boxes", "all"] = "all"

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("preview.host must be a loopback address")
        return value


class RuntimeConfig(_ConfigModel):
    runtime_id: str
    station_id: str
    camera: CameraConfig
    backend: BackendConfig
    model: ModelConfig
    bindings: list[BindingConfig] = Field(default_factory=list)
    preview: PreviewConfig = Field(default_factory=PreviewConfig)
    inference_interval_ms: int = 100
    evidence_dir: Path


def load_config(path: Path) -> RuntimeConfig:
    config_path = Path(path)
    data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # Absolute so the backend and the runtime agree on one directory even
    # when they start from different working directories.
    data["evidence_dir"] = Path(os.environ["EVIDENCE_DIR"]).expanduser().resolve()
    _resolve_paths(data, config_path.parent)
    return RuntimeConfig.model_validate(data)


def _resolve_paths(data: dict[str, Any], root: Path) -> None:
    source = data["camera"]["source"]
    path_key = {"file": "path", "gige": "cti_path"}.get(source["kind"])
    if path_key is not None:
        source[path_key] = _resolve(source[path_key], root)
    model = data["model"]
    model["onnx_path"] = _resolve(model["onnx_path"], root)
    model["class_names_path"] = _resolve(model["class_names_path"], root)


def _resolve(value: Any, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path
