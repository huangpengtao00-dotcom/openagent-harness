from __future__ import annotations

import json
import re
from pathlib import Path

from .policy import is_path_allowed_by_patterns
from .schema import GateResult, TaskSpec


_DIFF_PATH_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")


class QualityGate:
    def check_run(self, run_dir: Path, spec: TaskSpec) -> GateResult:
        patch_path = run_dir / "patch.diff"
        test_result_path = run_dir / "test_result.json"
        report_path = run_dir / "final_report.md"

        has_diff = patch_path.exists() and patch_path.read_text(encoding="utf-8").strip() != ""
        changed_paths = self._changed_paths(patch_path) if has_diff else set()
        scope_ok = all(is_path_allowed_by_patterns(path, spec.allowlist) for path in changed_paths) if changed_paths else True

        tests_ran = False
        tests_passed = False
        if test_result_path.exists():
            data = json.loads(test_result_path.read_text(encoding="utf-8"))
            tests_ran = bool(data.get("tests_ran"))
            tests_passed = bool(data.get("tests_passed"))

        report_exists = report_path.exists() and report_path.read_text(encoding="utf-8").strip() != ""
        status = "pass" if has_diff and tests_ran and tests_passed and scope_ok and report_exists else "fail"
        failure_type = None if status == "pass" else self._failure_type(has_diff, tests_ran, tests_passed, scope_ok, report_exists)
        return GateResult(has_diff, tests_ran, tests_passed, scope_ok, report_exists, status, failure_type)

    def _changed_paths(self, patch_path: Path) -> set[str]:
        changed: set[str] = set()
        for line in patch_path.read_text(encoding="utf-8").splitlines():
            match = _DIFF_PATH_RE.match(line)
            if match:
                changed.add(match.group(2).replace("\\", "/"))
        return changed

    def _failure_type(
        self,
        has_diff: bool,
        tests_ran: bool,
        tests_passed: bool,
        scope_ok: bool,
        report_exists: bool,
    ) -> str:
        if not has_diff:
            return "NoPatch"
        if not scope_ok:
            return "ScopeViolation"
        if tests_ran and not tests_passed:
            return "Regression"
        if not tests_ran:
            return "Unverified"
        if not report_exists:
            return "ReportMissing"
        return "Unknown"
