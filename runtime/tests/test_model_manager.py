import httpx
from contracts.events import ModelRef

from video_runtime.models import ModelManager, StaticModelProvider


class FakeBackend:
    instances: list["FakeBackend"] = []

    def __init__(self, onnx_path, names) -> None:
        self.onnx_path = onnx_path
        self.names = list(names)
        self.closed = False
        FakeBackend.instances.append(self)

    def infer(self, frame):
        return []

    def close(self) -> None:
        self.closed = True


def make_manager(
    tmp_path, state: dict, *, required_classes: tuple[str, ...] = ()
) -> ModelManager:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/training/projects/remote/active-model"):
            return httpx.Response(
                200,
                json={
                    "id": state["id"],
                    "version": state["version"],
                    "classes": ["remote", "battery"],
                    "onnx_url": f"/api/training/models/{state['id']}/artifact",
                    "names_url": f"/api/training/models/{state['id']}/names",
                },
            )
        if url.endswith("/artifact"):
            return httpx.Response(200, content=b"onnx")
        if url.endswith("/names"):
            return httpx.Response(200, content=b"remote\nbattery\n")
        return httpx.Response(404)

    return ModelManager(
        "http://api/api",
        "remote",
        tmp_path / "cache",
        FakeBackend,
        poll_s=1,
        transport=httpx.MockTransport(handler),
        required_classes=required_classes,
    )


def test_refresh_downloads_and_swaps_models(tmp_path) -> None:
    FakeBackend.instances.clear()
    state = {"id": "m1", "version": 1}
    manager = make_manager(tmp_path, state)

    assert manager.refresh() is True
    assert manager.current_ref() == ModelRef(name="model:remote", version="1")
    assert manager.classes() == ("remote", "battery")
    first = FakeBackend.instances[-1]
    assert first.onnx_path.read_bytes() == b"onnx"
    assert first.names == ["remote", "battery"]

    assert manager.refresh() is False
    assert first.closed is False

    state.update({"id": "m2", "version": 2})
    assert manager.refresh() is True
    assert first.closed is True
    assert manager.current_ref().version == "2"
    second = FakeBackend.instances[-1]
    assert second is not first
    manager.close()


def test_refresh_refuses_a_model_missing_binding_classes(tmp_path) -> None:
    FakeBackend.instances.clear()
    manager = make_manager(
        tmp_path, {"id": "m1", "version": 1}, required_classes=("hand",)
    )

    assert manager.refresh() is False
    assert "hand" in (manager.health_error() or "")
    assert FakeBackend.instances == []
    manager.close()


def test_static_provider_keeps_the_configured_ref(tmp_path) -> None:
    backend = FakeBackend(tmp_path / "x.onnx", [])
    provider = StaticModelProvider(
        backend, ModelRef(name="yolo11n-coco", version="1"), ["bottle"]
    )
    assert provider.current_ref().name == "yolo11n-coco"
    assert provider.classes() == ("bottle",)
    provider.close()
    assert backend.closed is True
