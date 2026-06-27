from config_loader import load_config


def audit_event(user, resource, decision, *, config_override=None):
    """Build a deterministic audit payload safe to expose in reports."""
    config = load_config(config_override)
    event = {
        "user": user,
        "resource": resource,
        "decision": decision,
        "debug": {"config": config},
    }
    if not config["audit"].get("include_debug"):
        event.pop("debug", None)
    return event
