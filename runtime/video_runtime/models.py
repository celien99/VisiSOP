"""Model providers: a fixed file model or the backend's active artifact."""

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import httpx
from contracts.events import ModelRef

from video_runtime.frame import Frame
from video_runtime.inference.base import Detection, InferenceBackend

logger = logging.getLogger(__name__)

BackendFactory = Callable[[Path, list[str]], InferenceBackend]


class ModelProvider(Protocol):
    def infer(self, frame: Frame) -> list[Detection]: ...

    def current_ref(self) -> ModelRef: ...

    def classes(self) -> tuple[str, ...]: ...

    def close(self) -> None: ...


class StaticModelProvider:
    """A model loaded once from the runtime's config files."""

    def __init__(
        self,
        backend: InferenceBackend,
        ref: ModelRef,
        classes: Sequence[str] = (),
    ) -> None:
        self._backend = backend
        self._ref = ref
        self._classes = tuple(classes)

    def infer(self, frame: Frame) -> list[Detection]:
        return self._backend.infer(frame)

    def current_ref(self) -> ModelRef:
        return self._ref

    def classes(self) -> tuple[str, ...]:
        return self._classes

    def close(self) -> None:
        self._backend.close()


class ModelManager:
    """Polls the backend for the active model and swaps it without a restart."""

    def __init__(
        self,
        base_url: str,
        project_key: str,
        cache_dir: Path,
        backend_factory: BackendFactory,
        *,
        poll_s: int = 10,
        transport: httpx.BaseTransport | None = None,
        fallback_ref: ModelRef | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._cache_dir = Path(cache_dir)
        self._backend_factory = backend_factory
        self._poll_s = max(1, poll_s)
        self._client = httpx.Client(transport=transport, timeout=10.0)
        self._fallback_ref = fallback_ref or ModelRef(
            name=f"model:{project_key}", version="0"
        )
        self._lock = threading.Lock()
        self._backend: InferenceBackend | None = None
        self._ref = self._fallback_ref
        self._classes: tuple[str, ...] = ()
        self._model_id: str | None = None

    def refresh(self) -> bool:
        """Fetch the active model; returns True when a new version was swapped in."""
        response = self._client.get(
            f"{self._base_url}/training/projects/{self._project_key}/active-model"
        )
        response.raise_for_status()
        data = response.json()
        model_id = str(data["id"])
        with self._lock:
            if model_id == self._model_id and self._backend is not None:
                return False

        onnx_path = self._cache_dir / f"{model_id}.onnx"
        names_path = self._cache_dir / f"{model_id}.names"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        onnx_path.write_bytes(self._download(str(data["onnx_url"])))
        names_path.write_bytes(self._download(str(data["names_url"])))
        names = [
            line for line in names_path.read_text(encoding="utf-8").splitlines() if line
        ]
        classes = [str(name) for name in data.get("classes", [])] or names
        backend = self._backend_factory(onnx_path, names or classes)
        ref = ModelRef(name=f"model:{self._project_key}", version=str(data["version"]))

        with self._lock:
            previous = self._backend
            self._backend = backend
            self._ref = ref
            self._classes = tuple(classes)
            self._model_id = model_id
        if previous is not None:
            previous.close()
        logger.info(
            "model %s v%s activated from %s",
            self._project_key,
            data["version"],
            data["onnx_url"],
        )
        return True

    def infer(self, frame: Frame) -> list[Detection]:
        with self._lock:
            backend = self._backend
            if backend is None:
                return []
            return backend.infer(frame)

    def current_ref(self) -> ModelRef:
        with self._lock:
            return self._ref

    def classes(self) -> tuple[str, ...]:
        with self._lock:
            return self._classes

    def close(self) -> None:
        with self._lock:
            backend = self._backend
            self._backend = None
        if backend is not None:
            backend.close()
        self._client.close()

    def run_poller(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.refresh()
            except Exception as exc:  # network boundary: retry on the next tick
                logger.warning("active model refresh failed: %s", exc)
            stop_event.wait(self._poll_s)

    def _download(self, url: str) -> bytes:
        target = f"{self._base_url}{url.removeprefix('/api')}"
        response = self._client.get(target)
        response.raise_for_status()
        return response.content
