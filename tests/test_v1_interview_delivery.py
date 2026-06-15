from __future__ import annotations

import json
from pathlib import Path

from openagent_harness.context import ContextBuilder
from openagent_harness.runner import HarnessRunner
from openagent_harness.schema import TaskSpec


def _load_task(path: Path) -> TaskSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["repo"] = str(Path(data["repo"]).resolve())
    return TaskSpec.from_dict(data)


def test_realistic_benchmarks_are_registered_and_well_formed() -> None:
    task_paths = sorted(Path("benchmarks_realistic").glob("*/task.json"))
    assert len(task_paths) == 3

    task_ids = []
    for task_path in task_paths:
        data = json.loads(task_path.read_text(encoding="utf-8"))
        task_ids.append(data["id"])
        repo = Path(data["repo"])
        assert repo.exists(), f"missing repo for {task_path}"
        assert data["allowlist"], f"empty allowlist for {task_path}"
        assert data["acceptance"], f"empty acceptance for {task_path}"

    assert task_ids == ["config-loader-real", "fastapi-error-handler-real", "retry-429-real"]


def test_run_report_contains_interview_sections(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (repo / "check.py").write_text("from app import divide\nassert divide(1, 0) is None\n", encoding="utf-8")
    spec = TaskSpec(
        id="T-report-sections",
        repo=str(repo),
        goal="Return None when divide receives zero denominator.",
        allowlist=["app.py"],
        acceptance=["python check.py"],
        budget={"context_summary_files": 8},
    )
    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")
    assert result.gate.status == "pass"
    report = (result.run_dir / "report.html").read_text(encoding="utf-8")
    for section in [
        "Task Goal",
        "Selected Context",
        "Tool Calls Timeline",
        "Permission Decisions",
        "Patch Diff",
        "Test Output",
        "Cost Estimate",
        "Scorecard",
        "Failure Analysis",
    ]:
        assert section in report
    assert (result.run_dir / "task_spec.json").exists()
    assert (result.run_dir / "context_summary.json").exists()


def test_context_builder_prioritizes_realistic_task_files() -> None:
    spec = _load_task(Path("benchmarks_realistic/config-loader-real/task.json"))
    selected = ContextBuilder(Path(spec.repo)).candidate_files(spec.goal, limit=8)
    selected_paths = {item.path for item in selected}
    assert "config_loader.py" in selected_paths
    assert "test_config_loader.py" in selected_paths
