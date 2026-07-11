from __future__ import annotations

import html
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .runner import HarnessRunner
from .schema import RunMode, TaskSpec


@dataclass(frozen=True)
class ModelProfile:
    name: str
    mode: RunMode
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    wire_api: str | None = None
    reasoning_effort: str | None = None
    disable_response_storage: bool | None = None
    budget_overrides: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelProfile":
        mode = str(data.get("mode", "api"))
        if mode not in {"local", "api"}:
            raise ValueError(f"profile {data.get('name', '<unknown>')} has unsupported mode={mode!r}")
        budget_overrides = data.get("budget_overrides")
        if budget_overrides is not None and not isinstance(budget_overrides, dict):
            raise ValueError("profile.budget_overrides must be an object when provided")
        return cls(
            name=str(data["name"]),
            mode=mode,  # type: ignore[arg-type]
            model=str(data.get("model") or data["name"]),
            base_url=str(data["base_url"]).rstrip("/") if data.get("base_url") else None,
            api_key_env=str(data["api_key_env"]) if data.get("api_key_env") else None,
            wire_api=str(data["wire_api"]) if data.get("wire_api") else None,
            reasoning_effort=str(data["reasoning_effort"]) if data.get("reasoning_effort") else None,
            disable_response_storage=(
                bool(data["disable_response_storage"]) if "disable_response_storage" in data else None
            ),
            budget_overrides=budget_overrides,
        )

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key_env"] = self.api_key_env
        data["api_key_configured"] = bool(self.api_key_env and os.getenv(self.api_key_env))
        return data


@dataclass(frozen=True)
class CompareCellResult:
    profile: str
    task_id: str
    status: str
    score: int
    tests_passed: bool
    failure_type: str | None
    patch_lines: int
    changed_files: int
    tokens: int
    estimated_cost_usd: float
    duration_seconds: float
    run_dir: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompareProfileSummary:
    profile: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_score: float
    tokens: int
    total_cost_usd: float
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompareSummary:
    profiles: list[dict[str, Any]]
    total_tasks: int
    total_runs: int
    profile_summaries: list[CompareProfileSummary]
    results: list[CompareCellResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profiles": self.profiles,
            "total_tasks": self.total_tasks,
            "total_runs": self.total_runs,
            "profile_summaries": [summary.to_dict() for summary in self.profile_summaries],
            "results": [result.to_dict() for result in self.results],
        }


def load_profiles(path: Path) -> list[ModelProfile]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_profiles = data.get("profiles", data) if isinstance(data, dict) else data
    if not isinstance(raw_profiles, list):
        raise ValueError("profiles file must be a list or an object with a profiles list")
    profiles = [ModelProfile.from_dict(item) for item in raw_profiles]
    if not profiles:
        raise ValueError("profiles file did not define any profiles")
    return profiles


def run_compare(
    benchmarks_dir: Path,
    profiles_path: Path,
    runs_root: Path,
    *,
    project_root: Path | None = None,
    parallel: int = 2,
    allow_llm_calls: bool = False,
) -> CompareSummary:
    root = project_root or Path.cwd()
    profiles = load_profiles(profiles_path)
    specs = _load_specs(benchmarks_dir, root)
    runs_root.mkdir(parents=True, exist_ok=True)

    results: list[CompareCellResult] = []
    max_workers = max(1, int(parallel))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for spec in specs:
            for profile in profiles:
                futures.append(
                    executor.submit(
                        _run_one_cell,
                        spec,
                        profile,
                        runs_root,
                        allow_llm_calls,
                    )
                )
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: (item.profile, item.task_id))
    summary = CompareSummary(
        profiles=[profile.to_public_dict() for profile in profiles],
        total_tasks=len(specs),
        total_runs=len(results),
        profile_summaries=_summarize_by_profile(results),
        results=results,
    )
    (runs_root / "comparison_summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_compare_html_report(runs_root, summary)
    return summary


def _load_specs(benchmarks_dir: Path, root: Path) -> list[TaskSpec]:
    specs: list[TaskSpec] = []
    for task_path in sorted(benchmarks_dir.glob("*/task.json")):
        data = json.loads(task_path.read_text(encoding="utf-8"))
        repo = Path(str(data["repo"]))
        if not repo.is_absolute():
            data["repo"] = str(root / repo)
        specs.append(TaskSpec.from_dict(data))
    return specs


def _run_one_cell(spec: TaskSpec, profile: ModelProfile, runs_root: Path, allow_llm_calls: bool) -> CompareCellResult:
    started = time.monotonic()
    cell_root = runs_root / _safe_name(profile.name) / _safe_name(spec.id)
    spec_for_profile = _apply_budget_overrides(spec, profile)
    result = HarnessRunner(
        mode=profile.mode,
        model=profile.model,
        base_url=profile.base_url,
        api_key=os.getenv(profile.api_key_env) if profile.api_key_env else None,
        allow_llm_calls=allow_llm_calls,
        wire_api=profile.wire_api,
        reasoning_effort=profile.reasoning_effort,
        disable_response_storage=profile.disable_response_storage,
    ).run_task(spec_for_profile, cell_root)
    scorecard = _read_json(result.run_dir / "scorecard.json")
    test_result = _read_json(result.run_dir / "test_result.json")
    usage = _usage_from_run(result.run_dir)
    return CompareCellResult(
        profile=profile.name,
        task_id=spec.id,
        status=result.gate.status,
        score=int(scorecard.get("score") or (100 if result.gate.status == "pass" else 0)),
        tests_passed=bool(scorecard.get("tests_passed") or test_result.get("tests_passed") or False),
        failure_type="None" if result.gate.status == "pass" else result.gate.failure_type,
        patch_lines=int(scorecard.get("patch_lines") or 0),
        changed_files=int(scorecard.get("changed_files") or 0),
        tokens=int(usage.get("total_tokens") or 0),
        estimated_cost_usd=float(usage.get("estimated_cost_usd") or 0.0),
        duration_seconds=round(time.monotonic() - started, 3),
        run_dir=str(result.run_dir),
    )


def _apply_budget_overrides(spec: TaskSpec, profile: ModelProfile) -> TaskSpec:
    if not profile.budget_overrides:
        return spec
    budget = dict(spec.budget)
    budget.update(profile.budget_overrides)
    return TaskSpec(
        id=spec.id,
        repo=spec.repo,
        goal=spec.goal,
        allowlist=spec.allowlist,
        acceptance=spec.acceptance,
        budget=budget,
    )


def _summarize_by_profile(results: list[CompareCellResult]) -> list[CompareProfileSummary]:
    profiles = sorted({result.profile for result in results})
    summaries: list[CompareProfileSummary] = []
    for profile in profiles:
        rows = [result for result in results if result.profile == profile]
        total = len(rows)
        passed = sum(1 for row in rows if row.status == "pass")
        summaries.append(
            CompareProfileSummary(
                profile=profile,
                total=total,
                passed=passed,
                failed=total - passed,
                pass_rate=round(passed / total, 4) if total else 0.0,
                avg_score=round(sum(row.score for row in rows) / total, 2) if total else 0.0,
                tokens=sum(row.tokens for row in rows),
                total_cost_usd=round(sum(row.estimated_cost_usd for row in rows), 8),
                duration_seconds=round(sum(row.duration_seconds for row in rows), 3),
            )
        )
    return summaries


def _usage_from_run(run_dir: Path) -> dict[str, Any]:
    api_run = _read_json(run_dir / "api_agent_run.json")
    usage = api_run.get("total_usage")
    return usage if isinstance(usage, dict) else {}


def _write_compare_html_report(runs_root: Path, summary: CompareSummary) -> None:
    summary_rows = []
    for item in summary.profile_summaries:
        summary_rows.append(
            "<tr>"
            f"<td>{html.escape(item.profile)}</td>"
            f"<td>{item.passed}/{item.total}</td>"
            f"<td>{item.pass_rate}</td>"
            f"<td>{item.avg_score}</td>"
            f"<td>{item.tokens}</td>"
            f"<td>{item.total_cost_usd}</td>"
            f"<td>{item.duration_seconds}</td>"
            "</tr>"
        )
    detail_rows = []
    for item in summary.results:
        detail_rows.append(
            "<tr>"
            f"<td>{html.escape(item.profile)}</td>"
            f"<td>{html.escape(item.task_id)}</td>"
            f"<td>{html.escape(item.status)}</td>"
            f"<td>{item.score}</td>"
            f"<td>{html.escape(str(item.failure_type))}</td>"
            f"<td>{item.patch_lines}</td>"
            f"<td>{item.changed_files}</td>"
            f"<td>{item.tokens}</td>"
            f"<td>{item.estimated_cost_usd}</td>"
            f"<td>{html.escape(item.run_dir)}</td>"
            "</tr>"
        )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OpenAgent Model Comparison</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 28px; }}
    th, td {{ border: 1px solid #d8dee9; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f6f8; }}
    code {{ background: #f3f6f8; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>OpenAgent Model Comparison</h1>
  <p>Tasks: {summary.total_tasks} | Runs: {summary.total_runs}</p>
  <h2>Profile Summary</h2>
  <table>
    <tr><th>Profile</th><th>Passed</th><th>Pass rate</th><th>Avg score</th><th>Tokens</th><th>Cost USD</th><th>Duration seconds</th></tr>
    {''.join(summary_rows)}
  </table>
  <h2>Task Matrix</h2>
  <table>
    <tr><th>Profile</th><th>Task</th><th>Status</th><th>Score</th><th>Failure</th><th>Patch lines</th><th>Changed files</th><th>Tokens</th><th>Cost USD</th><th>Run dir</th></tr>
    {''.join(detail_rows)}
  </table>
</body>
</html>
"""
    (runs_root / "comparison_report.html").write_text(html_text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    return cleaned[:80] or "profile"
