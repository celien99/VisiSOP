import json
import threading

import httpx
from contracts.runtime import (
    CameraHealthStatus,
    CameraStatus,
    RuntimeHeartbeat,
    RuntimeRegistration,
    RuntimeStatus,
)

from video_runtime.registrar import RuntimeRegistrar

REGISTRATION = RuntimeRegistration(
    runtime_id="runtime-01",
    base_url="http://127.0.0.1:8001",
    preview_base_url="http://127.0.0.1:8001",
    version="0.1.0",
    camera_ids=("cam-01",),
)
HEARTBEAT = RuntimeHeartbeat(
    status=RuntimeStatus.HEALTHY,
    metrics={"fps": 9.8},
    cameras=(CameraStatus(camera_id="cam-01", status=CameraHealthStatus.HEALTHY),),
)


def test_register_and_heartbeat_post_contract_payloads() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    registrar = RuntimeRegistrar(
        "http://api/api",
        REGISTRATION,
        lambda: HEARTBEAT,
        transport=httpx.MockTransport(handler),
    )
    registrar.register()
    registrar.heartbeat()

    assert [str(call.url) for call in calls] == [
        "http://api/api/runtimes/register",
        "http://api/api/runtimes/runtime-01/heartbeat",
    ]
    assert json.loads(calls[0].content)["camera_ids"] == ["cam-01"]
    assert json.loads(calls[1].content)["status"] == "HEALTHY"


def test_run_forever_survives_a_missing_backend() -> None:
    stop = threading.Event()
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        stop.set()
        raise httpx.ConnectError("backend down")

    registrar = RuntimeRegistrar(
        "http://api/api",
        REGISTRATION,
        lambda: HEARTBEAT,
        interval_s=0,
        transport=httpx.MockTransport(handler),
    )
    registrar.run_forever(stop)

    assert attempts == ["/api/runtimes/register"]


def test_run_forever_re_registers_after_the_backend_forgets_it() -> None:
    stop = threading.Event()
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if len(paths) >= 4:
            stop.set()
        if request.url.path.endswith("/register"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"detail": "runtime not registered"})

    registrar = RuntimeRegistrar(
        "http://api/api",
        REGISTRATION,
        lambda: HEARTBEAT,
        interval_s=0,
        transport=httpx.MockTransport(handler),
    )
    registrar.run_forever(stop)

    assert paths == [
        "/api/runtimes/register",
        "/api/runtimes/runtime-01/heartbeat",
        "/api/runtimes/register",
        "/api/runtimes/runtime-01/heartbeat",
    ]
