# B1 acceptance checklist

Status: **not executed.** Phases 20–26 were implemented and unit-tested on
macOS without the HIKROBOT camera, MVS SDK, or Windows network setup. Every
row below still needs a pass/fail and a timestamp from a run on the demo
machine, following `docs/runbooks/windows-demo.md`.

Whoever runs it: copy this file's table into your report, fill `Result` with
`PASS`/`FAIL` and `At` with the local time, and attach the evidence named in
each row. A `FAIL` needs the observed behavior, not just the label.

## Machine and environment

| Field | Value |
|---|---|
| Windows version | |
| MVS version + GenTL `cti_path` | |
| Camera serial / IP | |
| NIC jumbo frame MTU / camera packet size | |
| Model file + export command | |
| Git commit | |

## Checks

| # | Check | How | Expected | Result | At | Evidence |
|---|---|---|---|---|---|---|
| 1 | Camera spike | `python -m video_runtime.tools.camera_spike --frames 600 --save-dir spike/` | ≥ 10 FPS at 2048×1536 BayerRG8, stable for 60 s; 5 sample JPEGs | PENDING | | FPS printout + `spike/sample-*.jpg` |
| 2 | Preview live | Wall + station detail | Live MJPEG on both pages | PENDING | | Screenshot |
| 3 | Preview dies, process survives | Kill the runtime | `无信号` / `预览不可用` within 5 s; step/status/health still shown from REST | PENDING | | Screenshot + wall `server_time` |
| 4 | Happy path | Bottle into pickup, then target | `pick_bottle` completes after ≥ 500 ms stable; `place_bottle` completes; `verify_placement` completes; execution `COMPLETED`; two `AVAILABLE` evidence assets; wall shows `已完成` | PENDING | | Execution detail + evidence thumbnails |
| 5 | Missing evidence | Delete the keyframe under `EVIDENCE_DIR/tmp` before the event posts (or stop the runtime writing evidence) | Step `NEEDS_REVIEW`/`EVIDENCE_MISSING`, `DATA_INTEGRITY` alarm; review with operator + reason closes it; evidence shows `缺失` | PENDING | | Execution detail before/after review |
| 6 | Duplicate delivery | Re-post the same event JSON (`event_id` unchanged) with `curl`/PowerShell | `DUPLICATE`; no extra transition, evidence link, or alarm | PENDING | | `POST /api/events` response + unchanged step count |
| 7 | Out of order | Send a pickup-zone event while `place_bottle` is active | `OUT_OF_ORDER` alarm; `pick_bottle` does not regress; `place_bottle` does not complete | PENDING | | Alarm list + execution detail |
| 8 | Timeout | Copy the SOP JSON, set `timeout_ms: 3000`, publish v2, start, wait | `TIMED_OUT` step + alarm; execution `NEEDS_REVIEW`; abort works | PENDING | | Execution detail + alarm |
| 9 | Pause/resume vs timeout | Pause, wait 10 s past the deadline, resume | No timeout while paused; ACTIVE deadlines extended by the paused duration | PENDING | | Step `deadline_at` before/after |
| 10 | Backend restart | Stop and start FastAPI | Wall restores from REST; runtime re-registers within 5 s; queued events retry and land once | PENDING | | Runtime `/health` + records page |

## Notes to record with a failure

- The execution ID and station ID.
- The wall's `server_time` and the step `deadline_at` (clock skew hides
  timeout bugs).
- The event `result` from `GET /api/events?station_id=st-01`.
- For preview failures: whether the camera is `UNAVAILABLE` and whether the
  process state still renders.
