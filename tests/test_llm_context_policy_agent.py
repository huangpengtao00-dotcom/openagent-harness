import json
import io
import urllib.error
from pathlib import Path

from openagent_harness.agent_loop import JsonActionCodingAgent
from openagent_harness.context import ContextBuilder
from openagent_harness.llm import OpenAICompatibleClient, ProviderTransientError, ReplayLLMClient, estimate_cost_usd, estimate_tokens_from_text
from openagent_harness.policy import PermissionPolicy
from openagent_harness.schema import TaskSpec


def test_deepseek_client_defaults_are_openai_compatible(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAGENT_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = OpenAICompatibleClient()
    config = client.configuration_note()

    assert config["model"] == "deepseek-v4-flash"
    assert config["base_url"] == "https://api.deepseek.com"
    assert config["api_key_configured"] is True


def test_openai_key_defaults_to_openai_base_url(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    client = OpenAICompatibleClient(model="gpt-5.5")
    config = client.configuration_note()

    assert config["base_url"] == "https://api.openai.com/v1"
    assert config["base_url_source"] == "openai_default"
    assert config["api_key_source"] == "OPENAI_API_KEY"


def test_openai_model_prefers_openai_key_when_deepseek_key_also_exists(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_BASE_URL", raising=False)

    client = OpenAICompatibleClient(model="gpt-5.5", base_url="http://43.106.115.130:8080/v1")
    config = client.configuration_note()

    assert config["api_key_source"] == "OPENAI_API_KEY"
    assert client.api_key == "openai-key"


def test_openagent_key_override_still_has_highest_priority(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAGENT_API_KEY", "override-key")

    client = OpenAICompatibleClient(model="gpt-5.5", base_url="http://43.106.115.130:8080/v1")
    config = client.configuration_note()

    assert config["api_key_source"] == "OPENAGENT_API_KEY"
    assert client.api_key == "override-key"


def test_openai_responses_configuration(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = OpenAICompatibleClient(
        model="gpt-5.5",
        base_url="http://127.0.0.1:8080/v1",
        wire_api="responses",
        reasoning_effort="high",
        disable_response_storage=True,
    )
    config = client.configuration_note()

    assert config["base_url"] == "http://127.0.0.1:8080/v1"
    assert config["wire_api"] == "responses"
    assert config["reasoning_effort"] == "high"
    assert config["disable_response_storage"] is True


def test_responses_usage_parser_accepts_input_output_tokens(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = OpenAICompatibleClient(model="gpt-5.5", wire_api="responses")

    usage = client._parse_usage(
        {"usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}},
        [],
        "{}",
    )

    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 4
    assert usage.total_tokens == 14


def test_cost_estimate_uses_known_deepseek_price_table() -> None:
    assert estimate_tokens_from_text("hello") > 0
    assert estimate_cost_usd("deepseek-v4-flash", 1_000_000, 1_000_000) == 0.42


def test_context_builder_prioritizes_relevant_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("demo", encoding="utf-8")
    (tmp_path / "payment.py").write_text("def charge(): pass", encoding="utf-8")
    (tmp_path / "test_payment.py").write_text("def test_charge(): pass", encoding="utf-8")

    candidates = ContextBuilder(tmp_path).candidate_files("fix payment charge bug", limit=2)

    assert candidates[0].path in {"payment.py", "test_payment.py"}
    assert all(candidate.score > 0 for candidate in candidates)


def test_permission_policy_blocks_out_of_scope_write_and_risky_shell(tmp_path: Path) -> None:
    policy = PermissionPolicy(tmp_path, allowlist=["app.py"])
    (tmp_path / "check_custom.py").write_text("print('ok')\n", encoding="utf-8")

    assert policy.check_write_path("app.py").allowed is True
    assert policy.check_write_path("secrets.txt").allowed is False
    assert policy.check_shell_command("rm -rf .").allowed is False
    assert policy.check_shell_command("python -m pytest -q").allowed is True
    assert policy.check_shell_command("python check_custom.py").allowed is True
    assert policy.check_shell_command("python -c \"import os\"").allowed is False
    assert policy.check_shell_command("python -m http.server").allowed is False


def test_json_action_agent_edits_allowed_file_and_runs_test(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_zero():\n"
        "    assert divide(1, 0) is None\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-agent",
        repo=str(tmp_path),
        goal="Return None on zero denominator.",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 4},
    )
    client = ReplayLLMClient(
        [
            json.dumps(
                {
                    "action": "write_file",
                    "path": "app.py",
                    "content": "def divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n",
                }
            ),
            json.dumps({"action": "run_command", "command": "python -m pytest -q"}),
            json.dumps({"action": "finish", "summary": "zero denominator handled"}),
        ]
    )

    outcome = JsonActionCodingAgent(client, max_steps=4).apply(tmp_path, spec)

    assert outcome.finished is True
    assert len(outcome.steps) == 3
    assert "if b == 0" in (tmp_path / "app.py").read_text(encoding="utf-8")
    assert outcome.steps[1].observation["exit_code"] == 0


def test_json_action_agent_includes_failure_context_in_prompt(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def ok():\n    return False\n", encoding="utf-8")
    spec = TaskSpec(
        id="T-agent-retry-context",
        repo=str(tmp_path),
        goal="Fix ok.",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 1},
    )
    client = ReplayLLMClient([json.dumps({"action": "read_file", "path": "app.py"})])

    JsonActionCodingAgent(client, max_steps=1).apply(
        tmp_path,
        spec,
        failure_context="Previous run failed because test_result stderr contained AssertionError: expected True.",
    )

    prompt = "\n".join(message.content for message in client.calls[0])
    assert "Previous failed run evidence" in prompt
    assert "AssertionError: expected True" in prompt
    assert "Do not repeat the previous failed patch blindly" in prompt


def test_adaptive_agent_loop_uses_simple_strategy_for_small_task(tmp_path: Path) -> None:
    (tmp_path / "solution.py").write_text("def clamp(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text(
        "from solution import clamp\n\n"
        "def test_clamp():\n"
        "    assert clamp(-1) == 0\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-agent-simple-strategy",
        repo=str(tmp_path),
        goal="Clamp value at zero.",
        allowlist=["solution.py"],
        acceptance=["python -m pytest -q"],
        budget={"max_steps": 8, "prompt_char_budget": 40_000},
    )
    client = ReplayLLMClient(
        [
            json.dumps({"action": "read_file", "path": "solution.py"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
        ]
    )

    outcome = JsonActionCodingAgent(client, max_steps=8, prompt_char_budget=40_000, adaptive=True).apply(tmp_path, spec)

    assert outcome.strategy.tier == "simple"
    assert outcome.strategy.max_steps == 4
    assert outcome.strategy.prompt_char_budget == 16_000
    prompt = "\n".join(message.content for message in client.calls[0])
    assert '"tier": "simple"' in prompt


def test_adaptive_agent_loop_uses_deep_strategy_for_retry_context(tmp_path: Path) -> None:
    for index in range(4):
        (tmp_path / f"module_{index}.py").write_text(f"def f{index}():\n    return False\n", encoding="utf-8")
        (tmp_path / f"test_module_{index}.py").write_text(f"from module_{index} import f{index}\n", encoding="utf-8")
    spec = TaskSpec(
        id="T-agent-deep-strategy",
        repo=str(tmp_path),
        goal="Refactor async cache behavior across multiple files.",
        allowlist=[f"module_{index}.py" for index in range(4)],
        acceptance=["python -m pytest -q"],
        budget={"max_steps": 6, "prompt_char_budget": 20_000},
    )
    client = ReplayLLMClient(
        [
            json.dumps({"action": "search_repo", "query": "cache"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
            json.dumps({"action": "finish", "summary": "strategy checked"}),
        ]
    )

    outcome = JsonActionCodingAgent(client, max_steps=6, prompt_char_budget=20_000, adaptive=True).apply(
        tmp_path,
        spec,
        failure_context="Previous run failed with AssertionError in cache expiry tests.",
    )

    assert outcome.strategy.tier == "deep"
    assert outcome.strategy.max_steps == 10
    assert outcome.strategy.prompt_char_budget == 60_000
    assert "retry has failure context to diagnose" in outcome.strategy.rationale


def test_json_action_agent_accepts_nested_parameters_payload(tmp_path: Path) -> None:
    (tmp_path / "solution.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text(
        "from solution import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-agent-nested-params",
        repo=str(tmp_path),
        goal="Fix add so it returns the sum.",
        allowlist=["solution.py"],
        acceptance=["python -m pytest -q"],
        budget={"max_steps": 4},
    )
    client = ReplayLLMClient(
        [
            json.dumps(
                {
                    "action": "edit_file",
                    "parameters": {
                        "path": "solution.py",
                        "old_text": "def add(a, b):\n    return a - b\n",
                        "new_text": "def add(a, b):\n    return a + b\n",
                        "expected_replacements": 1,
                    },
                }
            ),
            json.dumps({"action": "run_command", "parameters": {"command": "python -m pytest -q"}}),
            json.dumps({"action": "finish", "summary": "sum bug fixed"}),
        ]
    )

    outcome = JsonActionCodingAgent(client, max_steps=4).apply(tmp_path, spec)

    assert outcome.finished is True
    assert outcome.steps[0].observation["ok"] is True
    assert outcome.steps[1].observation["exit_code"] == 0
    assert "return a + b" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_json_action_agent_gives_recoverable_feedback_for_non_json_response(tmp_path: Path) -> None:
    (tmp_path / "solution.py").write_text("def ok():\n    return False\n", encoding="utf-8")
    spec = TaskSpec(
        id="T-agent-invalid-json",
        repo=str(tmp_path),
        goal="Fix ok.",
        allowlist=["solution.py"],
        acceptance=["python -m pytest -q"],
        budget={"max_steps": 1},
    )
    client = ReplayLLMClient(["I will inspect the file first."])

    outcome = JsonActionCodingAgent(client, max_steps=1).apply(tmp_path, spec)

    assert outcome.finished is False
    assert outcome.steps[0].action == "invalid"
    assert "not a valid JSON action object" in outcome.steps[0].observation["error"]
    assert "Unknown action" not in outcome.steps[0].observation["error"]


def test_json_action_parser_accepts_first_json_object_with_trailing_text() -> None:
    agent = JsonActionCodingAgent(ReplayLLMClient([]))

    action = agent._parse_action('{"action":"read_file","path":"solution.py"}\n{"note":"extra"}')

    assert action == {"action": "read_file", "path": "solution.py"}


def test_json_action_agent_blocks_unsafe_write(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    spec = TaskSpec(
        id="T-agent-block",
        repo=str(tmp_path),
        goal="Do not touch secrets.",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 1},
    )
    client = ReplayLLMClient([json.dumps({"action": "write_file", "path": "secrets.txt", "content": "leak"})])

    outcome = JsonActionCodingAgent(client, max_steps=1).apply(tmp_path, spec)

    assert outcome.finished is False
    assert outcome.steps[0].observation["ok"] is False
    assert not (tmp_path / "secrets.txt").exists()


def test_openai_client_retries_transient_http_errors(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    attempts = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"output_text":"{}","usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}'

    def fake_urlopen(request, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b'{"error":"temporary"}'))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    client = OpenAICompatibleClient(model="gpt-5.5", wire_api="responses", provider_max_retries=1)
    response = client.chat([], response_format_json=True)

    assert attempts["count"] == 2
    assert response.raw["_provider_retry"] == {"attempts": 2}


def test_openai_client_raises_provider_transient_after_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b''))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    client = OpenAICompatibleClient(model="gpt-5.5", wire_api="responses", provider_max_retries=1)
    try:
        client.chat([], response_format_json=True)
    except ProviderTransientError as exc:
        assert exc.status_code == 502
        assert exc.attempts == 2
    else:
        raise AssertionError("expected ProviderTransientError")
