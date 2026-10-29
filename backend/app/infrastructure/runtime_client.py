from collections.abc import Callable
from types import TracebackType

import httpx


class RuntimeUnavailable(RuntimeError):
    """The runtime cannot be reached or rejected the command."""


class RuntimeClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_ms: int = 2000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_ms / 1000,
            transport=transport,
        )

    def __enter__(self) -> RuntimeClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def start_camera(self, camera_id: str) -> None:
        self._command("start", camera_id)

    def stop_camera(self, camera_id: str) -> None:
        self._command("stop", camera_id)

    def _command(self, command: str, camera_id: str) -> None:
        try:
            response = self._client.post(f"/cameras/{camera_id}/{command}")
        except httpx.HTTPError as exc:
            raise RuntimeUnavailable(
                f"runtime request failed: {command} {camera_id}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise RuntimeUnavailable(
                f"runtime rejected {command} {camera_id}: {response.status_code}"
            )


RuntimeClientFactory = Callable[[str], RuntimeClient]
