from fastapi.testclient import TestClient


def test_health_summary_reports_the_database(client: TestClient) -> None:
    body = client.get("/api/health/summary").json()
    assert body["database"] == "HEALTHY"
    assert body["server_time"]
    assert isinstance(body["runtimes"], list)
    assert isinstance(body["cameras"], list)
