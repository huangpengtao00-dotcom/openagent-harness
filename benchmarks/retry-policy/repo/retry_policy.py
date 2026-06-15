def should_retry(status_code, attempt, max_attempts):
    return attempt < max_attempts
