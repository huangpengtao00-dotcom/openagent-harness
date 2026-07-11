from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .schema import GateResult


@dataclass(frozen=True)
class RunScorecard:
    score: int
    status: str
    patch_lines: int
    changed_files: int
    tests_passed: bool
    failure_type: str | None
    artifact_hygiene_ok: bool
    rationale: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score_run(run_dir: Path, gate: GateResult) -> RunScorecard:
    patch = (run_dir / "patch.diff").read_text(encoding="utf-8") if (run_dir / "patch.diff").exists() else ""
    patch_lines = sum(1 for line in patch.splitlines() if line.startswith("+") or line.startswith("-"))
    changed_files = sum(1 for line in patch.splitlines() if line.startswith("diff --git"))
    test_data = _read_json(run_dir / "test_result.json")
    rationale: list[str] = []
    score = 0
    if gate.status == "pass":
        score += 70
        rationale.append("quality gate passed")
    else:
        rationale.append(f"quality gate failed: {gate.failure_type}")
    if gate.tests_passed:
        score += 15
        rationale.append("acceptance tests passed")
    if gate.scope_ok:
        score += 10
        rationale.append("patch stayed inside allowlist")
    if gate.artifact_hygiene_ok:
        rationale.append("artifacts passed hygiene scan")
    else:
        score -= 10
        rationale.append("artifact hygiene violation blocked release")
    if 0 < changed_files <= 3:
        score += 3
        rationale.append("small changed-file footprint")
    if 0 < patch_lines <= 80:
        score += 2
        rationale.append("compact patch")
    if any(result.get("timed_out") for result in test_data.get("results", [])):
        score -= 20
        rationale.append("timeout penalty")
    return RunScorecard(
        score=max(0, min(100, score)),
        status=gate.status,
        patch_lines=patch_lines,
        changed_files=changed_files,
        tests_passed=gate.tests_passed,
        failure_type=gate.failure_type,
        artifact_hygiene_ok=gate.artifact_hygiene_ok,
        rationale=rationale,
    )


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
