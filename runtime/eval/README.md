# Perception datasets and event-level evaluation

This directory holds the offline tooling for the B2 domain models. Data and
model artifacts stay out of git; only the tooling, class names, manifests,
and golden-video scripts are committed.

## Dataset layout

```
runtime/data/remote-battery/
  raw/<operator>-<run>/          # recorded frames from runtime/tools/record_clips.py
  frames/                        # selected frames to label
  labels/<run>/                  # YOLO txt, one .txt per image
  clips/                         # short replay clips for the evaluator
```

## Classes (v0)

| Class | Meaning |
|---|---|
| `remote` | the remote control body |
| `battery` | one battery instance (count is the number of boxes) |
| `CORRECT` | battery polarity label class |
| `REVERSED` | battery polarity label class |
| `OPEN` | lid state label class |
| `CLOSED` | lid state label class |
| `hand` | operator hand |

State and orientation are extra detection classes in v0 so the runtime can
read them with `state_classify` / `orientation_match`; a segmentation or
classifier head can replace them later without changing the event contract.

## Collection and labelling

1. `cd runtime && EVIDENCE_DIR=... uv run python -m video_runtime.tools.record_clips --config config.demo.yaml --seconds 30 --fps 5 --out data/remote-battery/raw/<operator>-<run>`
2. Label every fifth frame with the classes above (YOLO format).
3. Cover at least these scenarios per operator: normal, one battery, reversed
   battery, lid left open, hand blocking the compartment. 3 operators × 10
   runs is the minimum acceptance set.

## GPU (RTX 4060 and similar)

`uv sync --extra train` installs the default CPU torch build. After the
first sync, replace it with the CUDA build matching the installed driver
(cu124 here) and verify:

```bash
cd runtime
uv sync --extra train
uv pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

The trainer resolves `TRAINING_DEVICE` (default `0`) to `cpu` when CUDA is
unavailable and records the resolved device in `metrics.json` and the model
manifest, so a CPU run is visible rather than silent.

## Model handoff

Train YOLO11n on the labelled set, export ONNX (opset 17, `imgsz=640`, no NMS),
and write the manifest:

```
runtime/models/remote_battery.onnx   # gitignored
runtime/models/remote_battery.names  # one class name per line
runtime/models/remote_battery.yaml   # name/version/classes/calibration/metrics
```

Then run the runtime with `config.remote_battery.yaml`.

## Event-level gates (catalog §7)

| Metric | Completion events | Auxiliary events |
|---|---|---|
| precision | ≥ 0.99 | ≥ 0.95 |
| recall | ≥ 0.95 | ≥ 0.90 |
| latency p95 | ≤ 500 ms | ≤ 1 s |
| false completions | 0 across ≥ 30 runs | — |

Use `eval/event_eval.py` to match predicted events to hand-labelled truth by
type, key attributes, and a time window; duplicates inside the dedupe window
count once. A model that misses a gate does **not** replace the demo path.
