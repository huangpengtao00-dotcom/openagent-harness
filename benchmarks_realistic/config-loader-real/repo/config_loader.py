DEFAULTS = {
    "timeout_seconds": 5,
    "retries": 2,
    "headers": {
        "accept": "application/json",
        "user-agent": "openagent-client",
    },
}


def load_config(user_config: dict | None) -> dict:
    """Merge user configuration over defaults."""
    config = DEFAULTS.copy()
    if user_config:
        config.update(user_config)
    return config
