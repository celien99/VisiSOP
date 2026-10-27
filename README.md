# VisiSOP

Full-stack skeleton:

- **Backend**: FastAPI + SQLModel + PostgreSQL, Python 3.14 managed with `uv`.
- **Frontend**: React 19 + Vite + TanStack Router/Query + Tailwind CSS + shadcn/ui, managed with `bun`.
- The built frontend is served by FastAPI on the same origin.
- The TypeScript API client is generated from the backend's OpenAPI schema.
- Playwright for end-to-end tests; Pytest for the backend.

There is no domain logic yet: the only endpoint is a health check.

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

- Backend: [backend/README.md](./backend/README.md)
- Frontend: [frontend/README.md](./frontend/README.md)
- Deployment to FastAPI Cloud: [deployment.md](./deployment.md)
- Self-hosted deployment with Docker Compose: [deployment-docker-compose.md](./deployment-docker-compose.md)

## License

MIT
