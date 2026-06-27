from pathlib import Path


KNOWN_ARTIFACTS = {
    "patch.diff",
    "gate.json",
    "scorecard.json",
    "test_result.json",
    "trace.jsonl",
    "report.html",
}


def resolve_artifact_path(runs_root, run_id, artifact_name):
    path = Path(runs_root) / run_id / artifact_name
    return path


def list_artifacts(run_dir):
    return sorted(path.name for path in Path(run_dir).iterdir() if path.is_file())
