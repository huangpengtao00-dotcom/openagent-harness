import pytest

from client import fetch_with_retry
from retry import RetryExhausted, compute_backoff, should_retry


class SequenceTransport:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def __call__(self, url):
        self.calls += 1
        status = self.statuses.pop(0)
        return {"status_code": status, "body": f"{url}:{status}"}


def test_429_is_retried_and_observability_records_attempts():
    transport = SequenceTransport([429, 200])
    sleeps = []
    events = []

    response = fetch_with_retry(
        transport,
        "/v1/search",
        max_attempts=3,
        sleep=sleeps.append,
        events=events,
    )

    assert response["status_code"] == 200
    assert transport.calls == 2
    assert sleeps == [0.1]
    assert events == [
        {"attempt": 1, "status_code": 429, "backoff_seconds": 0.1},
        {"attempt": 2, "status_code": 200},
    ]


def test_ordinary_4xx_is_not_retried():
    transport = SequenceTransport([404, 200])
    events = []

    with pytest.raises(RetryExhausted) as exc:
        fetch_with_retry(transport, "/missing", max_attempts=3, events=events)

    assert exc.value.status_code == 404
    assert exc.value.attempts == 1
    assert transport.calls == 1
    assert events == [{"attempt": 1, "status_code": 404}]


def test_5xx_retries_until_budget_then_raises_last_status():
    transport = SequenceTransport([503, 502, 500])
    sleeps = []
    events = []

    with pytest.raises(RetryExhausted) as exc:
        fetch_with_retry(transport, "/unstable", max_attempts=3, sleep=sleeps.append, events=events)

    assert exc.value.status_code == 500
    assert exc.value.attempts == 3
    assert sleeps == [0.1, 0.2]
    assert events == [
        {"attempt": 1, "status_code": 503, "backoff_seconds": 0.1},
        {"attempt": 2, "status_code": 502, "backoff_seconds": 0.2},
        {"attempt": 3, "status_code": 500},
    ]


def test_retry_policy_boundary_conditions():
    assert should_retry(429, attempt=1, max_attempts=2) is True
    assert should_retry(500, attempt=1, max_attempts=2) is True
    assert should_retry(400, attempt=1, max_attempts=2) is False
    assert should_retry(500, attempt=2, max_attempts=2) is False
    assert compute_backoff(3, base_seconds=0.25) == 0.75
