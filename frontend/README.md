# VisiSOP - Frontend

The frontend is built with [Vite](https://vitejs.dev/), [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [TanStack Query](https://tanstack.com/query), [TanStack Router](https://tanstack.com/router), [Tailwind CSS](https://tailwindcss.com/), and [shadcn/ui](https://ui.shadcn.com/).

## Requirements

- [Bun](https://bun.sh/)

## Quick Start

From the project root, install the dependencies and start the frontend development server:

```bash
bun install
bun run dev
```

Then open <http://localhost:5173/> in your browser.

Run `uv run bash scripts/prestart.sh` and `uv run fastapi dev` from the `backend` directory, with PostgreSQL running in Docker Compose. See [../development.md](../development.md) for the complete setup.

To serve the frontend with FastAPI, run `bun run build` from the `frontend` directory and open `http://localhost:8000`.

## Code Structure

* `frontend/src/client` - The generated OpenAPI client. Do not edit it by hand.
* `frontend/src/components` - App components and the shadcn/ui components in `frontend/src/components/ui`.
* `frontend/src/routes` - File-based routes.
* `frontend/src/lib` - Shared frontend utilities.

## Generate Client

From the project root:

```bash
bash ./scripts/generate-client.sh
```

The script dumps the backend OpenAPI schema, regenerates `frontend/src/client`, and lints. Commit the generated files.

## Using a Remote API

By default, the built frontend uses the same origin as the FastAPI app. To point the Vite dev server at a remote API, set `VITE_API_URL` in `frontend/.env`.

## End-to-End Testing with Playwright

Start the app (backend at `http://localhost:8000` or the Vite dev server at `http://localhost:5173`) and run:

```bash
cd frontend
bunx playwright test
bunx playwright test --ui   # interactive mode
```

Playwright starts the Vite dev server automatically when `PLAYWRIGHT_BASE_URL` is not set.
