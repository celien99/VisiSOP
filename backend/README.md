# VisiSOP - Backend

## Requirements

* [Docker](https://www.docker.com/).
* [uv](https://docs.astral.sh/uv/) for Python package and environment management.

## Local Development

Start PostgreSQL from the project root:

```console
$ docker compose up -d db
```

Then, from `./backend/`, install the dependencies, prepare the database, and start the development server:

```console
$ uv sync
$ uv run bash scripts/prestart.sh
$ uv run fastapi dev
```

The API is available at `http://localhost:8000`, with automatic interactive docs at `http://localhost:8000/docs`.

## General Workflow

Run backend commands from `./backend/` with `uv run`. Make sure your editor uses the Python interpreter at `.venv/bin/python` in the project root.

Add SQLModel models in `./backend/app/models.py` and API endpoints in `./backend/app/api/routes/`. After adding models, generate a migration with Alembic:

```console
$ uv run alembic revision --autogenerate -m "Add ..."
$ uv run alembic upgrade head
```

## Full Stack with Docker Compose

To run the backend and built frontend in Docker Compose:

```console
$ docker compose run --rm backend bash scripts/prestart.sh
$ docker compose watch
```

The application is available at `http://localhost:8000`.

## Backend Tests

To test the backend from the `backend` directory, run:

```console
$ uv run bash scripts/test.sh
```

The tests run with Pytest. Add new tests in `./backend/tests/`.
