from http_client import backoff_seconds, should_retry


def test_retries_rate_limit_response_before_budget_is_exhausted():
    assert should_retry(429, attempt=1, max_attempts=3) is True


def test_does_not_retry_ordinary_client_errors():
    assert should_retry(400, attempt=1, max_attempts=3) is False
    assert should_retry(404, attempt=1, max_attempts=3) is False


def test_does_not_retry_after_budget_is_exhausted():
    assert should_retry(429, attempt=3, max_attempts=3) is False


def test_backoff_stays_deterministic_for_audit_logs():
    assert backoff_seconds(2) == 0.4
