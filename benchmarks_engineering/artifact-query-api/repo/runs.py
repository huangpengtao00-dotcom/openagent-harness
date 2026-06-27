import json
from pathlib import Path

from artifacts import list_artifacts


def read_run_summary(run_dir):
    run_dir = Path(run_dir)
    scorecard = json.loads((run_dir / "scorecard.json").read_text())
    test_result = json.loads((run_dir / "test_result.json").read_text())
    return {
        "run_id": run_dir.name,
        "status": scorecard["status"],
        "score": scorecard["score"],
        "failure_type": scorecard.get("failure_type"),
        "tests_passed": test_result["tests_passed"],
        "artifacts": list_artifacts(run_dir),
    }


def query_runs(runs_root, *, status=None, failure_type=None, page=1, page_size=20):
    rows = []
    for run_dir in Path(runs_root).iterdir():
        if run_dir.is_dir():
            rows.append(read_run_summary(run_dir))
    if status:
        rows = [row for row in rows if row["status"] == status]
    if failure_type:
        rows = [row for row in rows if row["failure_type"] == failure_type]
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": len(rows), "items": rows[start:end]}
