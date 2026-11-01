"""Fine-tune a YOLO model on an exported dataset and export ONNX.

The backend worker spawns this module in the runtime's Python 3.12
environment; the backend itself never imports torch. A job spec JSON carries
every path so the frontend and backend never guess.
"""

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrainSpec:
    job_id: str
    data_yaml: Path
    output_dir: Path
    progress_path: Path
    metrics_path: Path
    onnx_path: Path
    names_path: Path
    epochs: int
    imgsz: int
    device: str
    base_model: str

    @classmethod
    def load(cls, path: Path) -> "TrainSpec":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            job_id=str(data["job_id"]),
            data_yaml=Path(data["data_yaml"]),
            output_dir=Path(data["output_dir"]),
            progress_path=Path(data["progress_path"]),
            metrics_path=Path(data["metrics_path"]),
            onnx_path=Path(data["onnx_path"]),
            names_path=Path(data["names_path"]),
            epochs=int(data["epochs"]),
            imgsz=int(data["imgsz"]),
            device=str(data["device"]),
            base_model=str(data["base_model"]),
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def _resolved_device(device: str) -> str:
    if device == "cpu":
        return device
    try:
        import torch

        if not torch.cuda.is_available():
            return "cpu"
    except ImportError:
        return "cpu"
    return device


def _metrics(trainer: Any) -> dict[str, float]:
    raw = getattr(trainer, "metrics", None) or {}
    values: dict[str, float] = {}
    for key, value in raw.items():
        try:
            values[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return values


def _validate_onnx(path: Path) -> None:
    import onnxruntime

    onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def run_training(
    spec: TrainSpec,
    *,
    model_factory: Callable[[str], Any] | None = None,
    validator: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    if model_factory is None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is not installed; run `uv sync --extra train`"
            ) from exc
        model_factory = YOLO

    spec.output_dir.mkdir(parents=True, exist_ok=True)
    model = model_factory(spec.base_model)

    def on_epoch(trainer: Any) -> None:
        _write_json(
            spec.progress_path,
            {
                "status": "RUNNING",
                "epoch": int(getattr(trainer, "epoch", 0)) + 1,
                "epochs": int(getattr(trainer, "epochs", spec.epochs)),
                "metrics": _metrics(trainer),
            },
        )

    add_callback = getattr(model, "add_callback", None)
    if callable(add_callback):
        add_callback("on_train_epoch_end", on_epoch)

    _write_json(
        spec.progress_path,
        {"status": "RUNNING", "epoch": 0, "epochs": spec.epochs, "metrics": {}},
    )
    model.train(
        data=str(spec.data_yaml),
        epochs=spec.epochs,
        imgsz=spec.imgsz,
        device=_resolved_device(spec.device),
        project=str(spec.output_dir),
        name="train",
        exist_ok=True,
        verbose=False,
    )

    names = getattr(model, "names", None) or {}
    if isinstance(names, dict):
        ordered = [names[index] for index in sorted(names)]
    else:
        ordered = list(names)
    spec.names_path.parent.mkdir(parents=True, exist_ok=True)
    spec.names_path.write_text("\n".join(ordered) + "\n", encoding="utf-8")

    exported = model.export(format="onnx", opset=17, imgsz=spec.imgsz, simplify=False)
    spec.onnx_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(exported), spec.onnx_path)
    # Activation must never point at an artifact the runtime cannot load.
    (validator or _validate_onnx)(spec.onnx_path)

    trainer = getattr(model, "trainer", None)
    metrics = _metrics(trainer)
    payload = {
        "job_id": spec.job_id,
        "metrics": metrics,
        "epochs": spec.epochs,
        "names": ordered,
        "valid": True,
    }
    _write_json(spec.metrics_path, payload)
    _write_json(
        spec.progress_path,
        {
            "status": "SUCCEEDED",
            "epoch": spec.epochs,
            "epochs": spec.epochs,
            "metrics": metrics,
        },
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = TrainSpec.load(args.job)
    try:
        run_training(spec)
    except Exception as exc:  # training boundary: surface the SDK error
        _write_json(
            spec.progress_path,
            {"status": "FAILED", "error": str(exc)},
        )
        print(f"training failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
