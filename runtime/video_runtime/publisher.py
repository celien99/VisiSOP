import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx
from contracts.events import VisionEvent

_MAX_PENDING = 100


@dataclass(frozen=True)
class PublishOutcome:
    delivered: bool
    duplicate: bool
    status_code: int | None
    error: str | None


@dataclass
class PublisherMetrics:
    sent: int = 0
    failed: int = 0
    duplicates: int = 0
    retries: int = 0
    last_error: str | None = field(default=None)


class HttpEventPublisher:
    """Posts VisionEvents to the backend; keeps a bounded retry queue in memory.

    The event_id is the idempotency key, so redelivery after a lost response
    is safe. The queue is memory-only: a runtime crash loses at most the
    pending tail, which the health surface reports as `dropped`.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_ms: int = 2000,
        retries: int = 3,
        backoff_ms: tuple[int, ...] = (100, 300, 900),
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_ms / 1000,
            transport=transport,
        )
        self._retries = retries
        self._backoff_ms = backoff_ms
        self._pending: deque[VisionEvent] = deque(maxlen=_MAX_PENDING)
        self._dropped = 0
        self._metrics = PublisherMetrics()

    @property
    def pending(self) -> deque[VisionEvent]:
        return self._pending

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def metrics(self) -> PublisherMetrics:
        return self._metrics

    def publish(self, event: VisionEvent) -> PublishOutcome:
        outcome = self._deliver(event)
        if outcome.delivered:
            self._metrics.sent += 1
        else:
            self._metrics.failed += 1
            if not _is_permanent(outcome):
                if len(self._pending) == _MAX_PENDING:
                    self._dropped += 1
                self._pending.append(event)
        return outcome

    def flush(self) -> int:
        delivered = 0
        while self._pending:
            outcome = self._deliver(self._pending[0])
            if not outcome.delivered:
                self._metrics.failed += 1
                break
            self._pending.popleft()
            self._metrics.sent += 1
            delivered += 1
        return delivered

    def close(self) -> None:
        self._client.close()

    def _deliver(self, event: VisionEvent) -> PublishOutcome:
        payload = event.model_dump(mode="json")
        last_error: str | None = None
        last_status: int | None = None
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post("/events", json=payload)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                last_status = None
            else:
                last_status = response.status_code
                if response.status_code == 202:
                    duplicate = _result(response) == "DUPLICATE"
                    if duplicate:
                        self._metrics.duplicates += 1
                    return PublishOutcome(True, duplicate, 202, None)
                if 400 <= response.status_code < 500:
                    return PublishOutcome(
                        False, False, response.status_code, _error_text(response)
                    )
                last_error = f"status {response.status_code}"
            if attempt < self._retries:
                self._metrics.retries += 1
                time.sleep(self._backoff(attempt))
        self._metrics.last_error = last_error
        return PublishOutcome(False, False, last_status, last_error)

    def _backoff(self, attempt: int) -> float:
        if not self._backoff_ms:
            return 0.0
        return self._backoff_ms[min(attempt, len(self._backoff_ms) - 1)] / 1000


def _is_permanent(outcome: PublishOutcome) -> bool:
    status = outcome.status_code
    return status is not None and 400 <= status < 500


def _result(response: httpx.Response) -> Any:
    try:
        return response.json().get("result")
    except ValueError:
        return None


def _error_text(response: httpx.Response) -> str:
    try:
        return f"rejected with {response.status_code}: {response.json()}"
    except ValueError:
        return f"rejected with {response.status_code}"
