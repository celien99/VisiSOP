from fastapi.testclient import TestClient

from app.main import app


def test_lifespan_starts_and_stops_workers() -> None:
    with TestClient(app) as client:
        assert client.get("/api/utils/health-check/").status_code == 200
