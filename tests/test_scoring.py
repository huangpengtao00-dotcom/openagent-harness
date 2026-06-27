import json
from pathlib import Path

from openagent_harness.schema import GateResult
from openagent_harness.scoring import score_run


def test_score_preserves_partial_credit_when_hygiene_blocks_verified_patch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "patch.diff").write_text("diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n", encoding="utf-8")
    (run_dir / "test_result.json").write_text(
        json.dumps({"tests_ran": True, "tests_passed": True, "results": []}),
        encoding="utf-8",
    )
    gate = GateResult(
        has_diff=True,
        tests_ran=True,
        tests_passed=True,
        scope_ok=True,
        report_exists=True,
        status="fail",
        failure_type="ArtifactHygieneViolation",
        artifact_hygiene_ok=False,
    )

    scorecard = score_run(run_dir, gate)

    assert scorecard.status == "fail"
    assert scorecard.failure_type == "ArtifactHygieneViolation"
    assert scorecard.tests_passed is True
    assert scorecard.score >= 20
