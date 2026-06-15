import json
from pathlib import Path

from typer.testing import CliRunner

from openagent_harness.cli import app


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
