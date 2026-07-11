from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .html_report import write_eval_html_report
from .runner import HarnessRunner
from .schema import TaskSpec


@dataclass(frozen=True)
class EvalTaskResult:
    task_id: str
    profile: str
    status: str
    score: int
    patch_lines: int
    changed_files: int
    tests_passed: bool
    failure_type: str | None
    tokens: int
    estimated_cost_usd: float
    duration_seconds: float
    run_dir: str


@dataclass(frozen=True)
class EvalSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_score: float
    total_patch_lines: int
    total_changed_files: int
    tests_passed: int
    failure_types: dict[str, int]
    tokens: int
    total_cost_usd: float
    duration_seconds: float
    results: list[EvalTaskResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "total_patch_lines": self.total_patch_lines,
            "total_changed_files": self.total_changed_files,
            "tests_passed": self.tests_passed,
            "failure_types": self.failure_types,
            "tokens": self.tokens,
            "total_cost_usd": self.total_cost_usd,
            "duration_seconds": self.duration_seconds,
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
        scorecard = _read_json(result.run_dir / "scorecard.json")
        test_result = _read_json(result.run_dir / "test_result.json")
        usage = _usage_from_trace(result.run_dir / "trace.jsonl")
        results.append(
            EvalTaskResult(
                task_id=spec.id,
                profile="scripted baseline",
                status=result.gate.status,
                score=int(scorecard.get("score") or (100 if result.gate.status == "pass" else 0)),
                patch_lines=int(scorecard.get("patch_lines") or 0),
                changed_files=int(scorecard.get("changed_files") or 0),
                tests_passed=bool(scorecard.get("tests_passed") or test_result.get("tests_passed") or False),
                failure_type="None" if result.gate.status == "pass" else result.gate.failure_type,
                tokens=int(usage.get("total_tokens") or 0),
                estimated_cost_usd=float(usage.get("estimated_cost_usd") or 0.0),
                duration_seconds=_test_duration_seconds(test_result),
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
        avg_score=round(sum(result.score for result in results) / total, 2) if total else 0.0,
        total_patch_lines=sum(result.patch_lines for result in results),
        total_changed_files=sum(result.changed_files for result in results),
        tests_passed=sum(1 for result in results if result.tests_passed),
        failure_types=dict(Counter(result.failure_type or "Unknown" for result in results)),
        tokens=sum(result.tokens for result in results),
        total_cost_usd=round(sum(result.estimated_cost_usd for result in results), 8),
        duration_seconds=round(sum(result.duration_seconds for result in results), 3),
        results=results,
    )
    (runs_root / "eval_summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_eval_html_report(runs_root)
    return summary


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _usage_from_trace(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    latest: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        observation = event.get("observation") or {}
        usage = observation.get("usage")
        if isinstance(usage, dict):
            latest = usage
    return latest


def _test_duration_seconds(test_result: dict[str, object]) -> float:
    results = test_result.get("results")
    if not isinstance(results, list):
        return 0.0
    return round(
        sum(float(result.get("duration_seconds") or 0.0) for result in results if isinstance(result, dict)),
        3,
    )
