import json
from pathlib import Path

import pytest

from artifacts import resolve_artifact_path, list_artifacts
from runs import query_runs, read_run_summary


def write_json(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def make_run(root: Path, name: str, *, status="pass", score=95, failure_type=None, tests_passed=True):
    run_dir = root / name
    run_dir.mkdir()
    write_json(run_dir / "scorecard.json", {"status": status, "score": score, "failure_type": failure_type})
    write_json(run_dir / "test_result.json", {"tests_passed": tests_passed})
    (run_dir / "patch.diff").write_text("diff --git a/x.py b/x.py\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text("{}", encoding="utf-8")
    (run_dir / "debug.tmp").write_text("ignore me", encoding="utf-8")
    return run_dir


def test_resolve_artifact_path_rejects_path_traversal(tmp_path: Path):
    root = tmp_path / "runs"
    run_dir = make_run(root, "run-1")

    assert resolve_artifact_path(root, "run-1", "patch.diff") == run_dir / "patch.diff"

    with pytest.raises(ValueError):
        resolve_artifact_path(root, "../outside", "patch.diff")
    with pytest.raises(ValueError):
        resolve_artifact_path(root, "run-1", "../secret.txt")
    with pytest.raises(ValueError):
        resolve_artifact_path(root, "run-1", "debug.tmp")


def test_list_artifacts_returns_only_known_files(tmp_path: Path):
    run_dir = make_run(tmp_path, "run-1")

    assert list_artifacts(run_dir) == ["patch.diff", "scorecard.json", "test_result.json", "trace.jsonl"]


def test_read_run_summary_tolerates_missing_optional_files(tmp_path: Path):
    run_dir = tmp_path / "run-missing"
    run_dir.mkdir()
    write_json(run_dir / "scorecard.json", {"status": "fail", "score": 20, "failure_type": "NoPatch"})

    summary = read_run_summary(run_dir)

    assert summary["run_id"] == "run-missing"
    assert summary["tests_passed"] is False
    assert summary["artifacts"] == ["scorecard.json"]


def test_query_runs_filters_and_paginates_deterministically(tmp_path: Path):
    root = tmp_path / "runs"
    make_run(root, "b-run", status="fail", score=40, failure_type="Regression", tests_passed=False)
    make_run(root, "a-run", status="pass", score=96)
    make_run(root, "c-run", status="fail", score=30, failure_type="NoPatch", tests_passed=False)

    failed = query_runs(root, status="fail", page=1, page_size=1)

    assert failed["total"] == 2
    assert [item["run_id"] for item in failed["items"]] == ["b-run"]
    second = query_runs(root, status="fail", page=2, page_size=1)
    assert [item["run_id"] for item in second["items"]] == ["c-run"]

    regression = query_runs(root, failure_type="Regression")
    assert regression["total"] == 1
    assert regression["items"][0]["run_id"] == "b-run"
