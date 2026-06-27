from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = {
    "secret_literal": re.compile(rb"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}"),
    "bearer_literal": re.compile(rb"Bearer\s+[A-Za-z0-9._-]{8,}"),
    "private_key_header": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}
_RUNTIME_CACHE_DIRS = {"__pycache__", ".pytest_cache"}
_SKIP_FILE_NAMES = {"artifact_hygiene.json", "evidence_summary.json", "evidence_summary.md"}


@dataclass(frozen=True)
class HygieneFinding:
    type: str
    path: str
    count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactHygieneResult:
    ok: bool
    findings: list[HygieneFinding]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def scan_run_artifacts(run_dir: Path, *, max_file_bytes: int = 2_097_152) -> ArtifactHygieneResult:
    findings: list[HygieneFinding] = []
    for path in sorted(run_dir.rglob("*")):
        relative = path.relative_to(run_dir).as_posix()
        if path.is_dir():
            if path.name in _RUNTIME_CACHE_DIRS:
                findings.append(HygieneFinding("runtime_cache", relative, 1))
            continue
        if path.name in _SKIP_FILE_NAMES:
            continue
        if not path.is_file() or path.stat().st_size > max_file_bytes:
            continue
        raw = path.read_bytes()
        for name, pattern in _SECRET_PATTERNS.items():
            count = len(pattern.findall(raw))
            if count:
                findings.append(HygieneFinding(name, relative, count))
    return ArtifactHygieneResult(ok=not findings, findings=findings)


def write_artifact_hygiene(run_dir: Path) -> ArtifactHygieneResult:
    result = scan_run_artifacts(run_dir)
    (run_dir / "artifact_hygiene.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def write_evidence_summary(run_dir: Path) -> dict[str, Any]:
    task = _read_json(run_dir / "task_spec.json")
    scorecard = _read_json(run_dir / "scorecard.json")
    test_result = _read_json(run_dir / "test_result.json")
    api_agent_run = _read_json(run_dir / "api_agent_run.json")
    hygiene = _read_json(run_dir / "artifact_hygiene.json")
    usage = api_agent_run.get("total_usage", {}) if isinstance(api_agent_run.get("total_usage"), dict) else {}
    summary = {
        "run_id": run_dir.name,
        "task_id": task.get("id"),
        "model_usage": usage,
        "status": scorecard.get("status"),
        "score": scorecard.get("score"),
        "failure_type": scorecard.get("failure_type"),
        "tests_ran": test_result.get("tests_ran"),
        "tests_passed": test_result.get("tests_passed"),
        "patch_lines": scorecard.get("patch_lines"),
        "changed_files": scorecard.get("changed_files"),
        "artifact_hygiene_ok": hygiene.get("ok", True),
        "artifact_hygiene_findings": hygiene.get("findings", []),
    }
    (run_dir / "evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "evidence_summary.md").write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def _render_markdown(summary: dict[str, Any]) -> str:
    usage = summary.get("model_usage") if isinstance(summary.get("model_usage"), dict) else {}
    findings = summary.get("artifact_hygiene_findings")
    finding_count = len(findings) if isinstance(findings, list) else 0
    return (
        "# Evidence Summary\n\n"
        f"- Run ID: {summary.get('run_id')}\n"
        f"- Task ID: {summary.get('task_id')}\n"
        f"- Status: {summary.get('status')}\n"
        f"- Score: {summary.get('score')}\n"
        f"- Failure type: {summary.get('failure_type')}\n"
        f"- Tests: ran={summary.get('tests_ran')} passed={summary.get('tests_passed')}\n"
        f"- Patch: lines={summary.get('patch_lines')} changed_files={summary.get('changed_files')}\n"
        f"- Usage: tokens={usage.get('total_tokens', 0)} cost_usd={usage.get('estimated_cost_usd', 0.0)}\n"
        f"- Artifact hygiene: ok={summary.get('artifact_hygiene_ok')} findings={finding_count}\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
