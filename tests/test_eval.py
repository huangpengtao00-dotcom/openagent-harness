import json
from pathlib import Path

from openagent_harness.eval import EvalSummary, run_eval


def _write_calc_task(root: Path) -> None:
    task_dir = root / "benchmarks" / "calc-py"
    repo = task_dir / "repo"
    repo.mkdir(parents=True)
    (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_divide_zero_returns_none():\n"
        "    assert divide(4, 0) is None\n",
        encoding="utf-8",
    )
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "T1-calc-div-zero",
                "repo": "benchmarks/calc-py/repo",
                "goal": "Return None when divide receives zero denominator.",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"max_steps": 8},
            }
        ),
        encoding="utf-8",
    )


def test_run_eval_discovers_tasks_and_writes_summary(tmp_path: Path) -> None:
    _write_calc_task(tmp_path)

    summary = run_eval(tmp_path / "benchmarks", tmp_path / "runs", project_root=tmp_path)

    assert isinstance(summary, EvalSummary)
    assert summary.total == 1
    assert summary.passed == 1
    assert summary.pass_rate == 1.0
    summary_json = json.loads((tmp_path / "runs" / "eval_summary.json").read_text(encoding="utf-8"))
    assert summary_json["results"][0]["task_id"] == "T1-calc-div-zero"
    assert summary_json["results"][0]["status"] == "pass"
