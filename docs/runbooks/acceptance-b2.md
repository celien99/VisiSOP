# B2 acceptance — perception primitives and the remote-battery SOP

Status: **code complete, model untrained, lab matrix not executed.**

What is ready:

- Event types are primitive instances (`contracts/contracts/primitives.py`).
- SOP DSL 2.0 attribute predicates (`eq / in / gte / lte / exists`) and the
  engine reads them; the remote-battery SOP compiles and validates.
- Runtime: one shared detection pass per camera, IoU tracking, stateful
  primitives (`object_present`, `object_absent`, `object_in_zone`,
  `count_threshold`, `state_classify`, `orientation_match`), bindings,
  evidence annotation, preview overlay, `GET /detections/{camera_id}`.
- Event detail exposes the decisive attributes to the operator.

What is not ready:

- The `remote_battery` model (no labelled data yet; `runtime/models/remote_battery.yaml`
  is `status: untrained`).
- The lab matrix below; every row is `PENDING`.

Whoever runs it: record the environment, copy the table into the report, fill
`Result` with `PASS`/`FAIL` and `At` with the local time, and attach the
`/detections` JSON or event ids named in each row.

## Machine and environment

| Field | Value |
|---|---|
| Windows version | |
| MVS version + camera serial | |
| Model file + manifest version | |
| Git commit | |
| Dataset version / run count | |

## Event-level gates (catalog §7)

| Metric | Gate | Measured |
|---|---|---|
| Completion-event precision | ≥ 0.99 | |
| Completion-event recall | ≥ 0.95 | |
| Latency p95 | ≤ 500 ms | |
| False completions | 0 across ≥ 30 runs | |
| Auxiliary precision / recall | ≥ 0.95 / ≥ 0.90 | |

Use `runtime/eval/event_eval.py` with `key_attributes` matching the event
type (for example `("count", "slots")` for `batteries_installed`).

## Scenario matrix (3 operators × 10 runs each)

| # | Scenario | Expected | Result | At | Evidence |
|---|---|---|---|---|---|
| 1 | Normal install (2 batteries, lid closed, hand away) | execution `COMPLETED`; all steps have `AVAILABLE` evidence | PENDING | | |
| 2 | Only one battery | `insert_batteries` never completes; timeout → `NEEDS_REVIEW` | PENDING | | |
| 3 | One battery reversed | orientation condition fails; timeout/review | PENDING | | |
| 4 | Lid left open | `close_lid` never completes; timeout/review | PENDING | | |
| 5 | Hand stays in the compartment | `operator_hand_clear(present=false)` never holds; timeout/review | PENDING | | |
| 6 | Bottle-transfer regression | B1 bottle happy path still completes on the primitive pipeline | PENDING | | |
| 7 | Overlay and detections | preview shows boxes/tracks/regions; `/detections` matches | PENDING | | |

## Reproduction

```bash
# 1. Collect labelled material (camera free, MVS closed)
cd runtime
export EVIDENCE_DIR=C:/VisiSOP/evidence
uv run python -m video_runtime.tools.record_clips \
  --config config.demo.yaml --seconds 30 --fps 5 \
  --out data/remote-battery/raw/op1-run1

# 2. Label, train, export, fill runtime/models/remote_battery.yaml
# 3. Run the battery bindings
uv run python -m video_runtime.main --config config.remote_battery.yaml

# 4. Replay and score
uv run python -c "from eval.event_eval import evaluate; ..."
```

## Notes to record with a failure

- The event `result` and `reason_code` from `GET /api/events?station_id=...`.
- The step `reason_code` and the decisive attributes from the execution
  detail.
- Whether the failure is perception (no box / wrong class) or semantics
  (attribute predicate never satisfied).
