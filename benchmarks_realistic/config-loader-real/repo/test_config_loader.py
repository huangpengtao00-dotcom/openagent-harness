from config_loader import DEFAULTS, load_config


def test_nested_headers_are_merged_without_dropping_defaults():
    config = load_config({"headers": {"authorization": "Bearer test"}})
    assert config["headers"]["authorization"] == "Bearer test"
    assert config["headers"]["accept"] == "application/json"
    assert config["headers"]["user-agent"] == "openagent-client"


def test_scalar_values_still_override_defaults():
    config = load_config({"timeout_seconds": 30})
    assert config["timeout_seconds"] == 30
    assert config["retries"] == 2


def test_default_config_is_not_mutated_across_calls():
    load_config({"headers": {"x-debug": "1"}})
    assert "x-debug" not in DEFAULTS["headers"]
    assert "x-debug" not in load_config(None)["headers"]
