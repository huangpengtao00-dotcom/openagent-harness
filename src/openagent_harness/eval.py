from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .html_report import write_eval_html_report
from .runner import HarnessRunner
from .schema import TaskSpec


@dataclass(frozen=True)
class EvalTaskResult:
    task_id: str
    status: str
    failure_type: str | None
    run_dir: str


@dataclass(frozen=True)
class EvalSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[EvalTaskResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "results": [asdict(result) for result in self.results],
        }


def run_eval(benchmarks_dir: Path, runs_root: Path, project_root: Path | None = None) -> EvalSummary:
    root = project_root or Path.cwd()
    runs_root.mkdir(parents=True, exist_ok=True)
    results: list[EvalTaskResult] = []

    for task_path in sorted(benchmarks_dir.glob("*/task.json")):
        data = json.loads(task_path.read_text(encoding="utf-8"))
        repo = Path(data["repo"])
        if not repo.is_absolute():
            data["repo"] = str(root / repo)
        spec = TaskSpec.from_dict(data)
        result = HarnessRunner(mode="local").run_task(spec, runs_root)
        results.append(
            EvalTaskResult(
                task_id=spec.id,
                status=result.gate.status,
                failure_type=result.gate.failure_type,
                run_dir=str(result.run_dir),
            )
        )

    passed = sum(1 for result in results if result.status == "pass")
    total = len(results)
    summary = EvalSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        pass_rate=round(passed / total, 4) if total else 0.0,
        results=results,
    )
    (runs_root / "eval_summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_eval_html_report(runs_root)
    return summary
