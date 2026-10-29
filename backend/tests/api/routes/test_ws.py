from fastapi.testclient import TestClient


def test_websocket_accepts_and_disconnects(client: TestClient) -> None:
    with client.websocket_connect("/api/ws") as websocket:
        websocket.send_text("ping")
