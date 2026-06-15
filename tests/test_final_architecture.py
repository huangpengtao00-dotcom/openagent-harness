import json
from pathlib import Path

from typer.testing import CliRunner

from openagent_harness.cli import app
from openagent_harness.code_index import build_code_index, grep_repo
from openagent_harness.policy import PermissionPolicy
from openagent_harness.portfolio import PortfolioRunner
from openagent_harness.schema import TaskSpec
from openagent_harness.tool_registry import LocalToolRegistry


def test_code_index_extracts_symbols_and_searches_text(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        "class PaymentService:\n"
        "    def charge(self, amount):\n"
        "        return amount\n",
        encoding="utf-8",
    )

    index = build_code_index(tmp_path)
    names = {symbol.name for symbol in index.symbols}
    hits = grep_repo(tmp_path, "charge")

    assert "PaymentService" in names
    assert "charge" in names
    assert hits[0].path == "service.py"


def test_tool_registry_supports_patch_level_edit(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def ok():\n    return False\n", encoding="utf-8")
    registry = LocalToolRegistry(tmp_path, PermissionPolicy(tmp_path, allowlist=["app.py"]))

    result = registry.dispatch(
        "edit_file",
        {
            "path": "app.py",
            "old_text": "    return False\n",
            "new_text": "    return True\n",
            "expected_replacements": 1,
        },
    )

    assert result.ok is True
    assert "return True" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_tool_registry_blocks_ambiguous_patch_anchor(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    registry = LocalToolRegistry(tmp_path, PermissionPolicy(tmp_path, allowlist=["app.py"]))

    result = registry.dispatch("edit_file", {"path": "app.py", "old_text": "x = 1\n", "new_text": "x = 2\n"})

    assert result.ok is False
    assert result.data["matches"] == 2


def test_portfolio_runner_writes_selection_summary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_zero():\n"
        "    assert divide(1, 0) is None\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-portfolio",
        repo=str(repo),
        goal="Return None when divide receives zero denominator.",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = PortfolioRunner().run(spec, tmp_path / "runs")
    summary = json.loads((tmp_path / "runs" / "portfolio_summary.json").read_text(encoding="utf-8"))

    assert result.best is not None
    assert result.best.scorecard.status == "pass"
    assert summary["best"]["scorecard"]["score"] >= 90


def test_cli_index_and_tools_commands(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    runner = CliRunner()

    index_result = runner.invoke(app, ["index", str(tmp_path), "--query", "hello"])
    tools_result = runner.invoke(app, ["tools", str(tmp_path)])

    assert index_result.exit_code == 0
    assert "hello" in index_result.output
    assert tools_result.exit_code == 0
    assert "edit_file" in tools_result.output
