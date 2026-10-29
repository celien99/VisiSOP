import logging
import threading
from collections.abc import Callable

import httpx
from contracts.runtime import RuntimeHeartbeat, RuntimeRegistration

logger = logging.getLogger(__name__)


class RuntimeRegistrar:
    """Registers the runtime with the backend and keeps its heartbeat going.

    A missing backend is logged and retried; it never stops the pipeline. A
    404 heartbeat means the backend restarted and lost its in-memory
    registry, so the next tick re-registers.
    """

    def __init__(
        self,
        backend_url: str,
        registration: RuntimeRegistration,
        heartbeat_provider: Callable[[], RuntimeHeartbeat],
        *,
        interval_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=backend_url.rstrip("/"),
            timeout=5.0,
            transport=transport,
        )
        self._registration = registration
        self._heartbeat_provider = heartbeat_provider
        self._interval_s = interval_s
        self._registered = False

    def register(self) -> None:
        response = self._client.post(
            "/runtimes/register",
            json=self._registration.model_dump(mode="json"),
        )
        response.raise_for_status()

    def heartbeat(self) -> None:
        response = self._client.post(
            f"/runtimes/{self._registration.runtime_id}/heartbeat",
            json=self._heartbeat_provider().model_dump(mode="json"),
        )
        response.raise_for_status()

    def run_forever(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                if not self._registered:
                    self.register()
                    self._registered = True
                self.heartbeat()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    self._registered = False
                logger.warning("runtime heartbeat failed: %s", exc)
            except httpx.HTTPError as exc:
                logger.warning("runtime registration failed: %s", exc)
            stop_event.wait(self._interval_s)
