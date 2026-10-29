import httpx
import pytest

from app.infrastructure.runtime_client import RuntimeClient, RuntimeUnavailable


def test_start_and_stop_hit_the_runtime_paths() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200)

    client = RuntimeClient(
        "http://runtime:8001/", transport=httpx.MockTransport(handler)
    )
    with client:
        client.start_camera("cam-01")
        client.stop_camera("cam-01")
    assert paths == ["/cameras/cam-01/start", "/cameras/cam-01/stop"]


def test_runtime_error_status_raises() -> None:
    client = RuntimeClient(
        "http://runtime:8001",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    with pytest.raises(RuntimeUnavailable):
        client.start_camera("cam-01")
    client.close()


def test_connection_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = RuntimeClient(
        "http://runtime:8001", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(RuntimeUnavailable):
        client.stop_camera("cam-01")
    client.close()
