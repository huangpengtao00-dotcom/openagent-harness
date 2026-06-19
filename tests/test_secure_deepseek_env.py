from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from openagent_harness.cli import app
from openagent_harness.env import load_env_file, sanitize_mapping
from openagent_harness.llm import OpenAICompatibleClient


def test_load_env_file_and_configuration_note_never_exposes_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=sk-test-secret-value\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n", encoding="utf-8")

    loaded = load_env_file(env_path)
    assert loaded["DEEPSEEK_API_KEY"] == "sk-test-secret-value"

    client = OpenAICompatibleClient()
    note = client.configuration_note()
    rendered = json.dumps(note)
    assert note["api_key_configured"] is True
    assert note["api_key_source"] == "DEEPSEEK_API_KEY"
    assert "sk-test-secret-value" not in rendered


def test_load_env_file_accepts_export_prefix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("export DEEPSEEK_API_KEY=sk-test-secret-value\n", encoding="utf-8")

    loaded = load_env_file(env_path)

    assert loaded["DEEPSEEK_API_KEY"] == "sk-test-secret-value"


def test_sanitize_mapping_redacts_secret_like_values() -> None:
    payload = {
        "authorization": "Bearer abc.def.ghi",
        "nested": {"api_key": "sk-test-secret-value", "message": "ok"},
        "text": "prefix sk-test-secret-value suffix",
    }
    rendered = json.dumps(sanitize_mapping(payload))
    assert "sk-test-secret-value" not in rendered
    assert "Bearer abc" not in rendered
    assert "<redacted>" in rendered


def test_sanitize_mapping_redacts_bearer_tokens_with_base64_chars() -> None:
    payload = {"text": "prefix Bearer abc/def+ghi== suffix"}

    rendered = json.dumps(sanitize_mapping(payload))

    assert "Bearer abc/def+ghi==" not in rendered
    assert "def+ghi==" not in rendered
    assert "<redacted>" in rendered


def test_sanitize_mapping_redacts_short_sk_placeholders() -> None:
    payload = {"text": "prefix sk-test suffix"}

    rendered = json.dumps(sanitize_mapping(payload))

    assert "sk-test" not in rendered
    assert "<redacted>" in rendered


def test_deepseek_check_loads_local_env_without_printing_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-local-secret-value\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["deepseek-check"])
    assert result.exit_code == 0
    assert "api_key_configured" in result.output
    assert "sk-local-secret-value" not in result.output
    assert "DEEPSEEK_API_KEY" in result.output


def test_env_example_template_exists_and_contains_no_real_key() -> None:
    template = Path(".env.example")
    assert template.exists()
    text = template.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in text
    assert "https://api.deepseek.com" in text
    assert "sk-" not in text


def test_sanitize_mapping_keeps_usage_token_counters():
    from openagent_harness.env import sanitize_mapping

    sanitized = sanitize_mapping({"usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}})

    assert sanitized["usage"]["prompt_tokens"] == 12
    assert sanitized["usage"]["completion_tokens"] == 3
    assert sanitized["usage"]["total_tokens"] == 15


def test_llm_usage_parser_falls_back_for_redacted_counters():
    from openagent_harness.llm import ChatMessage, OpenAICompatibleClient

    client = OpenAICompatibleClient(api_key="sk-test")
    usage = client._parse_usage(
        {"usage": {"prompt_tokens": "<redacted>", "completion_tokens": "<redacted>", "total_tokens": "<redacted>"}},
        [ChatMessage("user", "hello")],
        "world",
    )

    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
