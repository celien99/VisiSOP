# Windows demo runbook (B1 vertical slice)

One Windows 10/11 machine runs four things:

| Process | Port | Command |
|---|---|---|
| PostgreSQL (Docker Desktop) | 5432 | `docker compose up -d db` |
| FastAPI + workers | 8000 | `uv run fastapi dev` |
| Vite (optional; FastAPI serves the built SPA) | 5173 | `bun run dev` |
| Video runtime | 8001 | `uv run python -m video_runtime.main --config config.demo.yaml` |

Run every shell command in **Git Bash** from the repository root unless a
`cd` says otherwise.

## 1. Install

- [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/)
- Docker Desktop (for PostgreSQL)
- HIKROBOT MVS SDK (camera driver + GenTL producer)
- NVIDIA driver only if you later move inference to a GPU

## 2. Environment file

Create `.env` in the repository root from `.env.example` and fill in:

```dotenv
PROJECT_NAME=VisiSOP
POSTGRES_PASSWORD=changethis
DATABASE_URL=postgresql://postgres:changethis@localhost:5432/app
EVIDENCE_DIR=C:/VisiSOP/evidence
FRONTEND_HOST=http://localhost:5173
RUNTIME_STALE_AFTER_MS=15000
EXECUTION_ACCEPT_WINDOW_MS=600000
OUTBOX_POLL_MS=200
TIMEOUT_POLL_MS=1000
WORKERS_ENABLED=true
```

The backend and the runtime both use `EVIDENCE_DIR`; create the directory
(`C:/VisiSOP/evidence`). Do not put it on a network share: the backend moves
files with an atomic rename inside the same filesystem.

## 3. PostgreSQL

```bash
docker compose up -d db
```

## 4. Backend

```bash
cd backend
uv sync
uv run bash scripts/prestart.sh     # alembic upgrade head
uv run fastapi dev                  # http://localhost:8000/docs
```

Leave it running in this terminal. It also starts the outbox dispatcher and
the timeout worker (single process; `WORKERS_ENABLED=true`).

## 5. Frontend

```bash
bun install
bun run dev                         # http://localhost:5173
```

Vite proxies `/api` (including the WebSocket) to `http://127.0.0.1:8000`, so
the browser talks to one origin and CORS is not involved. Keep
`frontend/.env`'s `VITE_API_URL` empty; setting it to an absolute backend URL
bypasses the proxy and brings the origin whitelist back into play.

For a production-like run: `cd frontend && bun run build`, then use the
FastAPI origin at `http://localhost:8000` (it serves the built SPA).

## 6. Seed the demo data

```bash
cd backend
uv run python -m app.scripts.seed_demo --sop remote_battery
```

Use `--sop bottle_transfer` (the default) for the bottle demo. The seed
publishes both SOPs and leaves one execution active for the selected one.
It prints the SOP key, station (`st-01`), camera (`cam-01`), published SOP
version and the active execution ID. It is idempotent; re-running never
deletes data. A station runs one SOP at a time, so switching SOPs aborts the
previous execution (audited).

An execution only accepts events for `EXECUTION_ACCEPT_WINDOW_MS` (10 min) after
it was created; later events are quarantined as `LATE_EVENT`. If the active
execution is past that window, the seed **aborts it and creates a fresh one**
(audited), so run the seed right before the demo. Copy the execution ID for
step 11.

## 7. Camera check (before the runtime)

Follow `docs/runbooks/camera-spike.md`. Do not tune zone rectangles or
thresholds until the spike shows ≥ 10 FPS and a usable image.

## 8. Model export (once)

The ONNX model is not committed. In `runtime/`:

```bash
uv run --with "ultralytics[export]" yolo export model=yolo11n.pt format=onnx opset=17 imgsz=640 simplify=False
```

Copy the file to `runtime/models/yolo11n.onnx`. Class names are already in
`runtime/models/coco.names` (bottle is index 39). The runtime decodes the raw
`[1, 84, 8400]` output itself, so NMS must not be baked into the export.

## 9. Video runtime

```bash
cd runtime
uv sync                 # --extra gige only for a GenTL/harvesters producer
export EVIDENCE_DIR=C:/VisiSOP/evidence
uv run python -m video_runtime.main --config config.remote_battery.yaml
```

Use `config.demo.yaml` for the bottle demo and `config.remote_battery.yaml`
for the trained battery model. `config.remote_battery.replay.yaml` replays a
recorded clip instead of the camera. **The backend (8000) and the runtime
(8001) are separate processes; both must be running for the preview and the
event chain.**

`source.kind: mvs` is the HIKROBOT SDK; `config.demo.yaml` also uses it. Do
not open the same camera in MVS while the runtime runs: the SDK takes it
exclusively.

The runtime writes **exposure and gain only**. Resolution, pixel format,
triggering, and packet size come from the camera as configured in MVS. Select
`RGB8Packed` in MVS for camera-processed colour; the runtime decodes whatever
format the camera streams (RGB8Packed, BGR8Packed, YUV422, Mono8, BayerRG8).

- Preview: `http://127.0.0.1:8001/stream/cam-01`, snapshot at
  `/snapshot/cam-01`, health at `/health`, current detections/tracks at
  `/detections/cam-01`. The stream carries the detection overlay
  (`preview.overlay: off | boxes | all`).
- It registers with `http://127.0.0.1:8000/api` and heartbeats every 5 s. If
  the backend goes down it keeps capturing, retries queued events (bounded at
  100), and re-registers after the backend comes back.
- `Ctrl+C` stops the preview server and the pipeline.

The runtime acquires frames from launch; the API's camera start/stop commands
are acknowledged but do not pause the pipeline in this slice.

### Preview or snapshot cannot connect

Check in this order:

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-WebRequest http://127.0.0.1:8001/snapshot/cam-01 -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8000/api/runtimes
```

- No listener on 8001: the runtime process stopped (a replay exits when the
  clip ends; start the live config again).
- `/health` not `HEALTHY` or snapshot 404: the camera source has not produced
  a frame yet, or MVS still owns the camera.
- `GET /api/runtimes` empty: the backend (8000) is down or restarted; the
  runtime re-registers on its next heartbeat.
- Opening the UI from another machine: `127.0.0.1` in the preview URL points
  at that machine, not the demo PC. This is a known limitation until the URL
  is derived from the registered runtime.

## 10. Calibrate the bindings

For the bottle demo, watch `http://127.0.0.1:8001/stream/cam-01` (the overlay
draws the rectangles), then edit `bindings[].params.rect` in
`config.demo.yaml` (`[x1, y1, x2, y2]`, normalized 0–1). A detection counts
when its box center is inside the rectangle. Restart the runtime after
editing the config; the `/detections/cam-01` endpoint shows the raw boxes
when the overlay is off.

For the remote-battery SOP, measure thresholds from a recorded clip instead:

```bash
cd runtime
uv run python -m video_runtime.tools.calibrate \
  --config config.remote_battery.yaml \
  --video data/remote-battery/clips/remote_battery-normal.avi \
  --model /path/to/best.onnx --names /path/to/names.txt \
  --sop ../backend/app/seed/remote_battery.json --apply
```

See `runtime/eval/README.md` and `docs/runbooks/acceptance-b3.md`.

## 11. Demo

Open `http://localhost:5173`:

1. **监控墙** — the station card shows the live preview, process status, and
   step rail. `无信号`/`预览不可用` means the preview is down, not the process.
2. **工位详情** — start an execution (if the seed did not), then run the
   bottle through the pickup and target zones.
3. **执行详情** — steps, the four facts, timeline, evidence thumbnails, and
   review when a step is `NEEDS_REVIEW`.

Record the outcomes in `docs/runbooks/acceptance-b1.md` as you go.

## 12. Restart and recovery

- Backend restart: the wall restores from REST; the runtime notices the lost
  heartbeat (404) and re-registers on the next tick (≤ ~10 s); queued events retry.
- Runtime restart: the wall shows `无信号` within ~15 s (`RUNTIME_STALE_AFTER_MS`).
- Camera unplug: the runtime reports `UNAVAILABLE`, the wall keeps showing the
  process facts, and the preview falls back to the last frame or `预览不可用`.
