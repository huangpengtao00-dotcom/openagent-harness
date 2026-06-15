from pathlib import Path

from openagent_harness.gate import QualityGate
from openagent_harness.schema import GateResult, TaskSpec


def test_gate_fails_when_patch_exists_but_no_tests_ran(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "patch.diff").write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")

    spec = TaskSpec(
        id="T-demo",
        repo="demo",
        goal="fix behavior",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 5},
    )

    result = QualityGate().check_run(run_dir, spec)

    assert isinstance(result, GateResult)
    assert result.has_diff is True
    assert result.tests_ran is False
    assert result.tests_passed is False
    assert result.scope_ok is True
    assert result.status == "fail"
    assert result.failure_type == "Unverified"


def test_gate_detects_scope_violation_from_patch_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "patch.diff").write_text(
        "diff --git a/app.py b/app.py\n"
        "diff --git a/secrets.txt b/secrets.txt\n",
        encoding="utf-8",
    )
    (run_dir / "test_result.json").write_text(
        '{"tests_ran": true, "tests_passed": true, "command": "pytest"}',
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-scope",
        repo="demo",
        goal="fix app only",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 5},
    )

    result = QualityGate().check_run(run_dir, spec)

    assert result.scope_ok is False
    assert result.status == "fail"
    assert result.failure_type == "ScopeViolation"


def test_gate_uses_same_glob_allowlist_semantics_as_permission_policy(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "patch.diff").write_text("diff --git a/src/app.py b/src/app.py\n", encoding="utf-8")
    (run_dir / "test_result.json").write_text(
        '{"tests_ran": true, "tests_passed": true, "command": "pytest"}',
        encoding="utf-8",
    )
    (run_dir / "final_report.md").write_text("ok", encoding="utf-8")
    spec = TaskSpec(
        id="T-glob-scope",
        repo="demo",
        goal="fix app only",
        allowlist=["src/*.py"],
        acceptance=["pytest"],
        budget={"max_steps": 5},
    )

    result = QualityGate().check_run(run_dir, spec)

    assert result.scope_ok is True
    assert result.status == "pass"
