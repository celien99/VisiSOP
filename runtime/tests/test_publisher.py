import json
from uuid import uuid4

import httpx
from conftest import make_event

from video_runtime.publisher import HttpEventPublisher

BASE_URL = "http://api/api"


def test_retries_5xx_then_delivers() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(500)
        return httpx.Response(202, json={"result": "ACCEPTED"})

    publisher = HttpEventPublisher(
        BASE_URL, transport=httpx.MockTransport(handler), backoff_ms=(0, 0, 0)
    )
    outcome = publisher.publish(make_event())
    assert outcome.delivered and not outcome.duplicate
    assert len(calls) == 3
    assert str(calls[0].url) == f"{BASE_URL}/events"
    assert publisher.metrics.retries == 2
    assert not publisher.pending


def test_duplicate_is_delivered() -> None:
    publisher = HttpEventPublisher(
        BASE_URL,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(202, json={"result": "DUPLICATE"})
        ),
        backoff_ms=(0,),
    )
    outcome = publisher.publish(make_event())
    assert outcome.delivered is True
    assert outcome.duplicate is True
    assert publisher.metrics.duplicates == 1
    assert not publisher.pending


def test_retained_failures_are_bounded() -> None:
    publisher = HttpEventPublisher(
        BASE_URL,
        retries=1,
        backoff_ms=(0,),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    assert publisher.publish(make_event()).delivered is False
    assert len(publisher.pending) == 1
    for _ in range(100):
        publisher.publish(make_event(str(uuid4())))
    assert publisher.dropped == 1
    assert len(publisher.pending) == 100


def test_422_is_permanent_and_not_queued() -> None:
    publisher = HttpEventPublisher(
        BASE_URL,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(422, json={"detail": "bad event"})
        ),
        backoff_ms=(0,),
    )
    outcome = publisher.publish(make_event())
    assert outcome.delivered is False
    assert outcome.status_code == 422
    assert not publisher.pending


def test_flush_drains_pending_in_order() -> None:
    state = {"down": True}
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if state["down"]:
            return httpx.Response(503)
        received.append(request.content.decode())
        return httpx.Response(202, json={"result": "ACCEPTED"})

    publisher = HttpEventPublisher(
        BASE_URL,
        retries=0,
        backoff_ms=(0,),
        transport=httpx.MockTransport(handler),
    )
    publisher.publish(make_event("evt-a"))
    publisher.publish(make_event("evt-b"))
    assert len(publisher.pending) == 2
    state["down"] = False
    assert publisher.flush() == 2
    assert not publisher.pending
    assert [json.loads(body)["event_id"] for body in received] == ["evt-a", "evt-b"]
