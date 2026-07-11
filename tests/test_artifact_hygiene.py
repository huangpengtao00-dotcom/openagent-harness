from pathlib import Path

from openagent_harness.artifact_hygiene import HygieneFinding, scan_run_artifacts, write_artifact_hygiene


def test_scan_run_artifacts_flags_secret_like_values_and_runtime_caches(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "trace.jsonl").write_text('{"error": "sk-live-secret-value"}\n', encoding="utf-8")
    (run_dir / "repo" / "__pycache__").mkdir(parents=True)

    result = scan_run_artifacts(run_dir)

    finding_types = {finding.type for finding in result.findings}
    assert result.ok is False
    assert "secret_literal" in finding_types
    assert "runtime_cache" in finding_types


def test_scan_run_artifacts_does_not_flag_dpsk_slug_as_secret(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "task_spec.json").write_text(
        '{"id": "dpsk-complex-policy-pipeline-20260623"}\n',
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text('{"error": "sk-live-secret-value"}\n', encoding="utf-8")

    result = scan_run_artifacts(run_dir)

    assert result.ok is False
    assert result.findings == [HygieneFinding("secret_literal", "trace.jsonl", 1)]


def test_write_artifact_hygiene_skips_its_own_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "patch.diff").write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")

    first = write_artifact_hygiene(run_dir)
    second = write_artifact_hygiene(run_dir)

    assert first.ok is True
    assert second.ok is True
