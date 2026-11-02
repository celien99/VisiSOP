"""Export a trained YOLO checkpoint to ONNX, names, and validation metrics."""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--names", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args(argv)

    try:
        from ultralytics import YOLO

        model = YOLO(str(args.weights))
        names = getattr(model, "names", None) or {}
        ordered = [names[index] for index in sorted(names)] if isinstance(names, dict) else list(names)
        args.names.parent.mkdir(parents=True, exist_ok=True)
        args.names.write_text("\n".join(ordered) + "\n", encoding="utf-8")

        validation = model.val(
            data=str(args.data), imgsz=args.imgsz, device="cpu", verbose=False
        )
        metrics = {
            str(key): float(value)
            for key, value in (validation.results_dict or {}).items()
        }

        exported = model.export(
            format="onnx", opset=args.opset, imgsz=args.imgsz, simplify=False
        )
        args.onnx.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(exported), args.onnx)

        import onnxruntime

        onnxruntime.InferenceSession(
            str(args.onnx), providers=["CPUExecutionProvider"]
        )
    except Exception as exc:  # export boundary: SDK error text varies
        print(f"export failed: {exc}", file=sys.stderr)
        return 1

    _write_json(
        args.metrics,
        {"metrics": metrics, "names": ordered, "valid": True, "device": "cpu"},
    )
    print(f"exported {args.onnx} with {len(ordered)} classes", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
