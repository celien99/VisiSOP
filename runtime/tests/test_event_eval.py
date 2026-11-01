from eval.event_eval import LabelledEvent, Metrics, evaluate

KEYS = ("count",)


def event(attributes: dict, at: float = 10.0) -> LabelledEvent:
    return LabelledEvent("batteries_installed", attributes, at)


def test_a_perfect_match_scores_one() -> None:
    metrics = evaluate(
        [event({"count": 2})], [event({"count": 2})], key_attributes=KEYS
    )
    assert metrics == Metrics(
        precision=1.0, recall=1.0, matched=1, predicted=1, truth=1
    )


def test_a_false_positive_lowers_precision() -> None:
    metrics = evaluate(
        [event({"count": 2}), event({"count": 2}, at=20.0)],
        [event({"count": 2})],
        key_attributes=KEYS,
    )
    assert metrics.matched == 1
    assert metrics.precision == 0.5
    assert metrics.recall == 1.0


def test_a_miss_lowers_recall() -> None:
    metrics = evaluate([], [event({"count": 2})], key_attributes=KEYS)
    assert metrics.matched == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 0.0


def test_wrong_attributes_do_not_match() -> None:
    metrics = evaluate(
        [event({"count": 1})], [event({"count": 2})], key_attributes=KEYS
    )
    assert metrics.matched == 0


def test_events_outside_the_window_do_not_match() -> None:
    metrics = evaluate(
        [event({"count": 2}, at=100.0)],
        [event({"count": 2}, at=10.0)],
        key_attributes=KEYS,
    )
    assert metrics.matched == 0


def test_duplicates_inside_the_dedupe_window_count_once() -> None:
    metrics = evaluate(
        [event({"count": 2}, at=10.0), event({"count": 2}, at=10.3)],
        [event({"count": 2}, at=10.0)],
        key_attributes=KEYS,
    )
    assert metrics.predicted == 1
    assert metrics.matched == 1
