import json
from pathlib import Path

from openagent_harness.agent_loop import JsonActionCodingAgent
from openagent_harness.context import ContextBuilder
from openagent_harness.llm import OpenAICompatibleClient, ReplayLLMClient, estimate_cost_usd, estimate_tokens_from_text
from openagent_harness.policy import PermissionPolicy
from openagent_harness.schema import TaskSpec


def test_deepseek_client_defaults_are_openai_compatible(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = OpenAICompatibleClient()
    config = client.configuration_note()

    assert config["model"] == "deepseek-v4-flash"
    assert config["base_url"] == "https://api.deepseek.com"
    assert config["api_key_configured"] is True


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

    assert policy.check_write_path("app.py").allowed is True
    assert policy.check_write_path("secrets.txt").allowed is False
    assert policy.check_shell_command("rm -rf .").allowed is False
    assert policy.check_shell_command("python -m pytest -q").allowed is True


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
