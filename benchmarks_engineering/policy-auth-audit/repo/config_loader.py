DEFAULTS = {
    "limits": {
        "anonymous_per_minute": 2,
        "user_per_minute": 10,
    },
    "audit": {
        "redact_fields": ["token", "password", "secret"],
        "include_debug": False,
    },
    "features": {
        "private_reads_require_role": True,
        "locked_writes_blocked": True,
    },
}


def load_config(override=None):
    """Return runtime config with user overrides applied."""
    config = DEFAULTS.copy()
    if override:
        config.update(override)
    return config
