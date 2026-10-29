import pytest
from pydantic import ValidationError

from video_runtime.config import FileSourceConfig, GigESourceConfig, load_config

FILE_CONFIG = """
runtime_id: runtime-01
station_id: st-01
camera:
  camera_id: cam-01
  role: overview
  source:
    kind: file
    path: clips/demo.mp4
    loop: false
model:
  onnx_path: models/yolo11n.onnx
  class_names_path: models/coco.names
backend:
  base_url: http://127.0.0.1:8000/api
zones:
  - name: pickup
    rect: [0.05, 0.15, 0.45, 0.95]
    classes: [bottle]
    event_type: bottle_in_pickup_zone
"""


def test_load_config_uses_defaults_and_resolves_relative_paths(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "demo.yaml"
    path.write_text(FILE_CONFIG, encoding="utf-8")

    config = load_config(path)

    assert isinstance(config.camera.source, FileSourceConfig)
    assert config.camera.source.path == config_dir / "clips" / "demo.mp4"
    assert config.camera.source.loop is False
    assert config.model.onnx_path == config_dir / "models" / "yolo11n.onnx"
    assert config.model.input_size == 640
    assert config.backend.timeout_ms == 2000
    assert config.preview.port == 8001
    assert config.inference_interval_ms == 100
    assert config.evidence_dir == tmp_path / "evidence"
    assert config.zones[0].emit_interval_ms == 500


def test_load_config_parses_the_gige_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    path = tmp_path / "demo.yaml"
    path.write_text(
        FILE_CONFIG.replace(
            "    kind: file\n    path: clips/demo.mp4\n    loop: false",
            "    kind: gige\n    cti_path: sdk/MvProducerGEV.cti",
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    source = config.camera.source
    assert isinstance(source, GigESourceConfig)
    assert source.cti_path == tmp_path / "sdk" / "MvProducerGEV.cti"
    assert source.exposure_us == 8000
    assert source.packet_size == 8192
    assert source.timeout_ms == 2000


def test_evidence_dir_is_required(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EVIDENCE_DIR", raising=False)
    path = tmp_path / "demo.yaml"
    path.write_text(FILE_CONFIG, encoding="utf-8")
    with pytest.raises(KeyError):
        load_config(path)


def test_preview_host_must_be_loopback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    path = tmp_path / "demo.yaml"
    path.write_text(FILE_CONFIG + "preview:\n  host: 0.0.0.0\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_relative_evidence_dir_is_resolved(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "demo.yaml"
    path.write_text(FILE_CONFIG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVIDENCE_DIR", "evidence")

    config = load_config(path)

    assert config.evidence_dir == (tmp_path / "evidence").resolve()
