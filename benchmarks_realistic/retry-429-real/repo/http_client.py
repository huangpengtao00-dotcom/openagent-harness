RETRYABLE_STATUSES = {500, 502, 503, 504}


def should_retry(status_code: int, attempt: int, max_attempts: int) -> bool:
    """Return whether a failed HTTP request should be retried."""
    if attempt >= max_attempts:
        return False
    return status_code in RETRYABLE_STATUSES


def backoff_seconds(attempt: int, base: float = 0.2) -> float:
    return round(base * attempt, 3)
