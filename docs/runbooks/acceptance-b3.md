# B3 acceptance — training loop and remote-battery replay

Status: **demo chain verified on 2026-11-03; the 3x10 lab matrix is still
pending.** This report covers what was actually observed, not the full B2
acceptance matrix.

## Environment

| Field | Value |
|---|---|
| OS | Windows 11 |
| GPU | RTX 4060, CUDA 12.4 torch build |
| PostgreSQL | 18.6 (Docker Compose) |
| Model | `b9047600-e083-4661-992f-42116462e523`, v3, mAP50 0.806, device 0 |
| SOP version | `remote_battery` v3, `91b8fca5-e603-4977-85aa-79d1dab5f93b` |
| Execution | `14181e6d-ad3d-40e9-a7de-7caf9765fd8c` |
| Clip | `36953599-eaa1-497f-b3c3-3675247028bd.avi` → `runtime/data/remote-battery/clips/remote_battery-normal.avi` |

## Results

- Execution reached `COMPLETED`.
- Steps: `place_remote`, `insert_batteries`, `close_lid`, `verify` all
  `COMPLETED`.
- All five event types were accepted for the execution:
  `remote_present`, `batteries_installed`, `battery_orientation_ok`,
  `remote_lid_closed`, `operator_hand_clear`.
- Calibration values applied to the SOP and runtime config:

| Condition | min_confidence | stable_for_ms |
|---|---|---|
| `place_remote` / `remote_present` | 0.83 | 500 |
| `insert_batteries` / `batteries_installed` | 0.63 | 0 |
| `insert_batteries` / `battery_orientation_ok` | 0.53 | 0 |
| `close_lid` / `remote_lid_closed` | 0.87 | 0 |
| `close_lid` / `operator_hand_clear` | 0.95 | 0 |

- Camera health during the run: `/health` reported `HEALTHY` (~8.9 FPS),
  `/snapshot/cam-01` returned `200 image/jpeg` (~340 KB), and
  `/stream/cam-01` returned `multipart/x-mixed-replace`.

Why the stability windows are 0: the runtime emits a changed observation
once and then only every 2 s (heartbeat). The brief-clip states (two
batteries, hand-away, closed lid, correct orientation) can last less than
2 s, so two eligible events 500–800 ms apart do not exist. The attribute
predicates (`count >= 2`, `orientation == CORRECT`, `state == CLOSED`,
`present == false`) still gate completion. Production should either lower the
heartbeat for these bindings or measure stability from observation duration
instead of event timestamps.

## Not verified

- The 3 operators x 10 runs matrix, including normal, one battery, reversed
  battery, lid open, and hand blocking.
- Event-level precision/recall and latency gates from catalog §7.
- `REVERSED` reliability: dataset v2 has only 4 labelled reversed instances.
- Live MVS camera completion: the camera was used for preview/health; SOP
  completion was verified by replay.
- Held-out data: the calibration clip comes from the same recorded set as the
  training frames, so the thresholds are optimistic.

## Reproduce

```powershell
# 1. backend (8000) and a disposable test database are not required here;
#    the replay uses the dev database.
cd backend
uv run python -m app.scripts.seed_demo --sop remote_battery

# 2. copy a normal-install clip (gitignored)
#    runtime/data/remote-battery/clips/remote_battery-normal.avi

# 3. replay within EXECUTION_ACCEPT_WINDOW_MS (10 minutes by default)
cd runtime
$env:EVIDENCE_DIR='D:/VisiSOP/evidence'
uv run python -m video_runtime.main --config config.remote_battery.replay.yaml

# 4. inspect
docker compose exec -T db psql -U postgres -d app `
  -c "select id, status from sop_executions order by created_at desc limit 1;"
```

Recalibrate with `video_runtime.tools.calibrate` (see
`runtime/eval/README.md`) whenever the model or camera setup changes.

## Known operational notes

- Preview and snapshot URLs are hardcoded to `127.0.0.1:8001` in the seed.
  Opening the UI from another machine will not reach them; derive the URL
  from the registered runtime's `preview_base_url` in a later change.
- Both the backend (8000) and the runtime (8001) must be running. A stopped
  runtime is the usual cause of "preview cannot connect".
- Duplicate event deliveries are serialized per `event_id` in the backend;
  the runtime retry after a timeout no longer races the `vision_events`
  primary key.
