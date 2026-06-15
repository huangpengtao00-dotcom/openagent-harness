from retry_policy import should_retry


def test_does_not_retry_ordinary_client_errors():
    assert should_retry(400, attempt=0, max_attempts=3) is False
    assert should_retry(404, attempt=0, max_attempts=3) is False


def test_retries_transient_statuses_with_budget():
    assert should_retry(408, attempt=0, max_attempts=3) is True
    assert should_retry(429, attempt=0, max_attempts=3) is True
    assert should_retry(503, attempt=0, max_attempts=3) is True


def test_stops_when_budget_exhausted():
    assert should_retry(503, attempt=3, max_attempts=3) is False
