#!/usr/bin/env bash

set -e
set -x

uv run alembic upgrade head
FASTAPI_ENV=development coverage run -m pytest tests/
coverage report
coverage html --title "${@-coverage}"
