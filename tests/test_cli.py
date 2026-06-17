import json
from pathlib import Path

from typer.testing import CliRunner

from openagent_harness.cli import app
from openagent_harness.llm import LLMResponse, ModelUsage


def test_cli_api_check_writes_configuration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec_path = tmp_path / "task.json"
    spec_path.write_text(
        json.dumps(
            {
                "id": "T-api",
                "repo": str(tmp_path),
                "goal": "Fix with model",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"max_steps": 3},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["api-check", str(spec_path), "--model", "gpt-4.1-mini"])

    assert result.exit_code == 0
    assert "status=missing_key" in result.output


def test_cli_eval_runs_discovered_benchmarks(tmp_path: Path) -> None:
    bench = tmp_path / "benchmarks" / "calc-py"
    repo = bench / "repo"
    repo.mkdir(parents=True)
    (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_divide_zero_returns_none():\n"
        "    assert divide(4, 0) is None\n",
        encoding="utf-8",
    )
    (bench / "task.json").write_text(
        json.dumps(
            {
                "id": "T1-calc-div-zero",
                "repo": str(repo),
                "goal": "Return None when divide receives zero denominator.",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"max_steps": 8},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["eval", "--benchmarks", str(tmp_path / "benchmarks"), "--runs", str(tmp_path / "runs")])

    assert result.exit_code == 0
    assert "total=1" in result.output
    assert "pass_rate=1.0" in result.output


def test_cli_api_check_ignores_task_enable_llm_calls_without_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec_path = tmp_path / "task.json"
    spec_path.write_text(
        json.dumps(
            {
                "id": "T-api-enabled",
                "repo": str(tmp_path),
                "goal": "Fix with model",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"enable_llm_calls": True, "max_steps": 3},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["api-check", str(spec_path), "--model", "deepseek-v4-flash", "--runs", str(tmp_path / "runs")])

    assert result.exit_code == 0
    assert "status=missing_key" in result.output
    assert "network_call=false" in result.output


def test_cli_api_check_reads_env_from_spec_directory_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / ".env").write_text("DEEPSEEK_API_KEY=sk-local-test-value\n", encoding="utf-8")
    spec_path = spec_dir / "task.json"
    spec_path.write_text(
        json.dumps(
            {
                "id": "T-api-local-env",
                "repo": str(tmp_path),
                "goal": "Fix with model",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"max_steps": 3},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["api-check", str(spec_path), "--model", "deepseek-v4-flash", "--runs", str(tmp_path / "runs")])

    assert result.exit_code == 0
    assert "status=ok" in result.output
    assert "api_key_configured=true" in result.output


def test_cli_deepseek_smoke_requires_explicit_allow_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-local-test-value\n", encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("chat should not run without explicit allow flag")

    monkeypatch.setattr("openagent_harness.llm.OpenAICompatibleClient.chat", fail_if_called)

    result = CliRunner().invoke(app, ["deepseek-smoke"])

    assert result.exit_code != 0
    assert "--allow-llm-calls" in result.output


def test_cli_deepseek_smoke_runs_when_explicitly_allowed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-local-test-value\n", encoding="utf-8")

    def fake_chat(self, messages, *, response_format_json=False):
        return LLMResponse(
            content='{"status":"ok"}',
            usage=ModelUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5, estimated_cost_usd=0.0000014),
            raw={"id": "fake"},
        )

    monkeypatch.setattr("openagent_harness.llm.OpenAICompatibleClient.chat", fake_chat)

    result = CliRunner().invoke(app, ["deepseek-smoke", "--allow-llm-calls", "--runs", str(tmp_path / "runs")])

    assert result.exit_code == 0
    assert "ok=true" in result.output
