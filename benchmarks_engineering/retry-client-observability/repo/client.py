from retry import RetryExhausted, compute_backoff, should_retry


def fetch_with_retry(transport, url, *, max_attempts=3, sleep=None, events=None):
    sleep = sleep or (lambda seconds: None)
    events = events if events is not None else []
    attempt = 1
    while True:
        response = transport(url)
        status = response["status_code"]
        events.append({"attempt": attempt, "status_code": status})
        if 200 <= status < 300:
            return response
        if not should_retry(status, attempt, max_attempts):
            raise RetryExhausted(status, attempt)
        sleep(compute_backoff(attempt))
        attempt += 1
