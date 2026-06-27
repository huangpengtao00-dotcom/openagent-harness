from copy import deepcopy

from audit import audit_event
from config_loader import DEFAULTS, load_config
from policy_engine import decide_request


def test_load_config_deep_merges_nested_overrides_without_mutating_defaults():
    before = deepcopy(DEFAULTS)

    config = load_config({"limits": {"user_per_minute": 4}, "audit": {"include_debug": True}})

    assert config["limits"]["anonymous_per_minute"] == 2
    assert config["limits"]["user_per_minute"] == 4
    assert config["audit"]["redact_fields"] == ["token", "password", "secret"]
    assert config["audit"]["include_debug"] is True
    assert DEFAULTS == before


def test_suspended_user_is_denied_even_when_admin():
    decision = decide_request(
        {"id": "u1", "roles": ["admin"], "suspended": True, "tokens_remaining": 10},
        {"visibility": "public"},
        "write",
        now=100,
    )

    assert decision == {"allowed": False, "reason": "suspended", "limit": 10}


def test_rate_limited_user_is_denied_before_role_checks():
    decision = decide_request(
        {"id": "u2", "roles": ["admin"], "tokens_remaining": 0},
        {"visibility": "public"},
        "write",
        now=100,
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "rate_limited"


def test_private_read_requires_member_role_when_feature_enabled():
    denied = decide_request(
        {"id": "u3", "roles": ["viewer"], "tokens_remaining": 2},
        {"visibility": "private"},
        "read",
        now=100,
    )
    allowed = decide_request(
        {"id": "u4", "roles": ["member"], "tokens_remaining": 2},
        {"visibility": "private"},
        "read",
        now=100,
    )

    assert denied["allowed"] is False
    assert denied["reason"] == "private_resource"
    assert allowed["allowed"] is True
    assert allowed["reason"] == "read_allowed"


def test_locked_resource_blocks_editor_writes_but_not_admin_writes():
    editor = decide_request(
        {"id": "u5", "roles": ["editor"], "tokens_remaining": 2},
        {"visibility": "public", "locked": True},
        "write",
        now=100,
    )
    admin = decide_request(
        {"id": "u6", "roles": ["admin"], "tokens_remaining": 2},
        {"visibility": "public", "locked": True},
        "write",
        now=100,
    )

    assert editor["allowed"] is False
    assert editor["reason"] == "locked"
    assert admin["allowed"] is True
    assert admin["reason"] == "admin"


def test_anonymous_limit_is_used_for_missing_user():
    decision = decide_request(None, {"visibility": "public"}, "read", now=100)

    assert decision["allowed"] is True
    assert decision["limit"] == 2


def test_audit_event_recursively_redacts_sensitive_fields_and_sorts_keys():
    payload = audit_event(
        {"id": "u1", "token": "abc", "profile": {"password": "pw", "name": "Ada"}},
        {"id": "r1", "secret": "hidden", "visibility": "public"},
        {"allowed": True, "reason": "admin"},
        config_override={"audit": {"include_debug": True}},
    )

    assert payload == {
        "debug": {
            "config": {
                "audit": {
                    "include_debug": True,
                    "redact_fields": ["token", "password", "secret"],
                },
                "features": {
                    "locked_writes_blocked": True,
                    "private_reads_require_role": True,
                },
                "limits": {
                    "anonymous_per_minute": 2,
                    "user_per_minute": 10,
                },
            }
        },
        "decision": {"allowed": True, "reason": "admin"},
        "resource": {"id": "r1", "secret": "[REDACTED]", "visibility": "public"},
        "user": {
            "id": "u1",
            "profile": {"name": "Ada", "password": "[REDACTED]"},
            "token": "[REDACTED]",
        },
    }
