# VisiSOP

Full-stack skeleton:

- **Backend**: FastAPI + SQLModel + PostgreSQL, Python 3.14 managed with `uv`.
- **Frontend**: React 19 + Vite + TanStack Router/Query + Tailwind CSS + shadcn/ui, managed with `bun`.
- The built frontend is served by FastAPI on the same origin.
- The TypeScript API client is generated from the backend's OpenAPI schema.
- Playwright for end-to-end tests; Pytest for the backend.

The bottle-transfer demo runs the API, the React wall, and the native video
runtime in `runtime/` on one machine: see the
[Windows demo runbook](./docs/runbooks/windows-demo.md).

## Local Development

```bash
docker compose up -d db                # PostgreSQL
cd backend
uv sync
uv run bash scripts/prestart.sh        # alembic upgrade head
uv run fastapi dev                     # API at :8000, docs at /docs
```

In another terminal, from the repo root:

```bash
bun install
bun run dev                            # Vite at :5173
```

General development docs: [development.md](./development.md).

## Documentation

- Windows demo: [runbook](./docs/runbooks/windows-demo.md), [B1 acceptance](./docs/runbooks/acceptance-b1.md), [camera spike](./docs/runbooks/camera-spike.md)
- Backend: [backend/README.md](./backend/README.md)
- Frontend: [frontend/README.md](./frontend/README.md)
- Deployment to FastAPI Cloud: [deployment.md](./deployment.md)
- Self-hosted deployment with Docker Compose: [deployment-docker-compose.md](./deployment-docker-compose.md)

## License

MIT
