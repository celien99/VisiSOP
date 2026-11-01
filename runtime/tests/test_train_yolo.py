import json
from pathlib import Path
from types import SimpleNamespace

from video_runtime.tools.train_yolo import TrainSpec, run_training


def make_spec(tmp_path: Path) -> TrainSpec:
    data = tmp_path / "data.yaml"
    data.write_text("path: x\n", encoding="utf-8")
    return TrainSpec(
        job_id="job-1",
        data_yaml=data,
        output_dir=tmp_path / "run",
        progress_path=tmp_path / "progress.json",
        metrics_path=tmp_path / "metrics.json",
        onnx_path=tmp_path / "models" / "best.onnx",
        names_path=tmp_path / "models" / "names.txt",
        epochs=2,
        imgsz=640,
        device="0",
        base_model="yolo11n.pt",
    )


class FakeModel:
    names = {0: "remote", 1: "battery"}

    def __init__(self, export_path: Path) -> None:
        self._export_path = export_path
        self.callback = None
        self.trainer = SimpleNamespace(metrics={"metrics/mAP50(B)": 0.8})

    def add_callback(self, name, callback) -> None:
        self.callback = callback

    def train(self, **kwargs) -> None:
        assert kwargs["epochs"] == 2
        if self.callback is not None:
            self.callback(
                SimpleNamespace(
                    epoch=0,
                    epochs=kwargs["epochs"],
                    metrics=self.trainer.metrics,
                )
            )

    def export(self, **kwargs) -> str:
        self._export_path.parent.mkdir(parents=True, exist_ok=True)
        self._export_path.write_bytes(b"onnx")
        return str(self._export_path)


def test_run_training_exports_the_artifacts(tmp_path) -> None:
    spec = make_spec(tmp_path)
    exported = tmp_path / "exported.onnx"

    payload = run_training(
        spec,
        model_factory=lambda base: FakeModel(exported),
        validator=lambda path: None,
    )

    assert spec.onnx_path.read_bytes() == b"onnx"
    assert spec.names_path.read_text(encoding="utf-8").splitlines() == [
        "remote",
        "battery",
    ]
    assert payload["metrics"]["metrics/mAP50(B)"] == 0.8
    assert payload["valid"] is True
    assert payload["device"] in {"cpu", "0"}
    progress = json.loads(spec.progress_path.read_text(encoding="utf-8"))
    assert progress["status"] == "SUCCEEDED"
