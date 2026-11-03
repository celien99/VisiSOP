# VisiSOP B3 — In-app training loop (record → label → train → activate)

Status: **implemented and demo-verified on 2026-11-03**; see
`docs/runbooks/acceptance-b3.md`. The 3x10 lab matrix and the event-level
precision/recall gates remain pending.

**Goal:** an operator records a correct SOP video, uploads it in the training
page, the platform extracts frames, the operator draws boxes, exports a
dataset, starts a GPU training job, and the runtime hot-swaps to the new model
without a restart.

**Decisions:**
- Built-in canvas labelling; no external labelling service.
- Training runs on this machine in the runtime's Python 3.12 environment
  (`ultralytics` + torch), spawned as a subprocess by a backend worker. The
  backend stays on 3.14 and never imports torch.
- Backend and runtime share `TRAINING_DIR` on one machine (same as
  `EVIDENCE_DIR`); the runtime downloads the active model through the API.
- One training job at a time (`shortcut: single training worker`).
- Model activation is a property of the project; the runtime polls
  `/api/training/projects/{key}/active-model` every `model_poll_s` and swaps
  the ONNX backend when the model id changes.

## Data model (migration 0004)

| Table | Columns |
|---|---|
| `training_projects` | id, key (unique), name, classes JSONB, created_at |
| `training_videos` | id, project_id, filename, storage_key, duration_ms, fps, frame_count, status, error, created_at |
| `training_frames` | id, video_id, frame_index, timestamp_ms, storage_key, thumb_key, width, height; unique(video_id, frame_index) |
| `training_annotations` | id, frame_id, class_name, x1, y1, x2, y2 (normalized); index frame_id |
| `dataset_versions` | id, project_id, version, frame_count, train_count, val_count, storage_key, manifest JSONB, created_at; unique(project_id, version) |
| `training_jobs` | id, project_id, dataset_version_id, status, progress, epochs, metrics JSONB, artifact_key, log_key, error, created_at, started_at, finished_at |
| `model_artifacts` | id, project_id, training_job_id, version, onnx_key, names_key, manifest JSONB, active, created_at; partial unique(project_id) where active |

Statuses: video `UPLOADED|READY|FAILED`; job
`QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED`.

## APIs (tag `training`)

- `GET/POST /training/projects`, `GET /training/projects/{id}`
- `POST /training/projects/{id}/videos` (multipart), `GET /training/videos/{id}/frames`
- `POST /training/videos/{id}/extract` (`fps`, `max_frames`)
- `GET /training/frames/{id}` / `/thumb`; `PUT /training/frames/{id}/annotations`
- `GET /training/projects/{id}/stats`
- `POST /training/projects/{id}/datasets` (`val_ratio`)
- `POST /training/projects/{id}/jobs` (`dataset_version_id`, `epochs`)
- `GET /training/jobs/{id}`, `GET /training/projects/{id}/jobs`
- `GET /training/projects/{id}/models`, `POST /training/models/{id}/activate`
- `GET /training/projects/{key}/active-model` (runtime), `GET /training/models/{id}/artifact|names`

## Phases

### Phase 1 — Storage, data model, label APIs
1. Config + models + migration 0004.
2. `training_store`: save video, extract frames/thumbnails, YOLO dataset export,
   model artifact paths.
3. `training_service`: project/video/frame/annotation/dataset CRUD.
4. Routes + schemas; upload limit and extension check; path safety.
5. Tests: synthetic video extraction; upload→extract→annotate→dataset via HTTP.

### Phase 2 — Training job and worker
1. `runtime/video_runtime/tools/train_yolo.py`: read a job JSON, run
   ultralytics, write `progress.json`, export ONNX + names + metrics.
2. `backend/app/workers/training_worker.py`: claim QUEUED jobs, spawn the
   trainer via `uv run --project ../runtime --with "ultralytics[export]"`,
   mirror progress, store the artifact, mark the model version.
3. Activation endpoint; audit/outbox.
4. Tests with an injected fake trainer (no torch in CI).

### Phase 3 — Training page
1. `/training` route + project list/create.
2. upload, frame grid with labelled/unlabelled state, stats.
3. canvas labeler (draw/select/delete boxes, class picker, save, prev/next).
4. dataset export, job list with progress, model list with metrics + activate.
5. Playwright specs with mocked APIs.

### Phase 4 — Runtime hot swap
1. `model.source: backend`; fetch active model + names, cache under
   `runtime/models/active/`.
2. `ModelManager` with a lock; poll the active model and swap the ONNX backend.
3. Events carry the current model name/version; bindings warn on missing classes.
4. Tests: manager swap with fake backends; polling metadata.

## Acceptance
- A 30–60 s video uploads, extracts frames, and the labeler saves boxes.
- Dataset export produces valid YOLO files; a GPU job runs and records metrics.
- Activation makes the runtime use the new model within `model_poll_s` without
  a restart; the execution detail shows the new model version.
- Existing B1/B2 tests and gates stay green.

## Not in this phase
- Multi-user roles/auth on training endpoints.
- Distributed training, hyper-parameter search, dataset version diffing UI.
- Automatic frame selection (scene change) — v1 samples by fps.
- Label interpolation/tracking-assisted labelling.
