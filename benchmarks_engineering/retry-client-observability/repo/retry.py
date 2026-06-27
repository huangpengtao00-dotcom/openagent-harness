RETRYABLE_STATUSES = {500, 502, 503, 504}


class RetryExhausted(RuntimeError):
    def __init__(self, status_code, attempts):
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(f"request failed after {attempts} attempts")


def should_retry(status_code, attempt, max_attempts):
    if attempt >= max_attempts:
        return False
    return status_code in RETRYABLE_STATUSES


def compute_backoff(attempt, base_seconds=0.1):
    return base_seconds * attempt
