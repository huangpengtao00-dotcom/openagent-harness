from config_loader import load_config


def decide_request(user, resource, action, *, now, config_override=None):
    """Return an authorization decision for one request."""
    config = load_config(config_override)
    user = user or {}
    resource = resource or {}
    roles = set(user.get("roles", []))

    if action == "read":
        return {"allowed": True, "reason": "read_allowed", "limit": config["limits"]["user_per_minute"]}

    if "admin" in roles:
        return {"allowed": True, "reason": "admin", "limit": config["limits"]["user_per_minute"]}

    if resource.get("locked"):
        return {"allowed": False, "reason": "locked", "limit": config["limits"]["user_per_minute"]}

    if action == "write" and "editor" in roles:
        return {"allowed": True, "reason": "editor", "limit": config["limits"]["user_per_minute"]}

    return {"allowed": False, "reason": "forbidden", "limit": config["limits"]["user_per_minute"]}
