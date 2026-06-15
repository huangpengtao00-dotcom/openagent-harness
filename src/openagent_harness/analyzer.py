from __future__ import annotations

from .schema import GateResult


def classify_failure(gate: GateResult) -> str | None:
    if gate.status == "pass":
        return None
    if not gate.has_diff:
        return "NoPatch"
    if not gate.scope_ok:
        return "ScopeViolation"
    if gate.tests_ran and not gate.tests_passed:
        return "Regression"
    if not gate.tests_ran:
        return "Unverified"
    if not gate.report_exists:
        return "ReportMissing"
    return gate.failure_type or "Unknown"
