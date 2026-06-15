import json
from pathlib import Path

from openagent_harness.analyzer import classify_failure
from openagent_harness.schema import GateResult, TraceEvent
from openagent_harness.trace import JsonlTraceStore


def test_trace_store_appends_jsonl_events(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    store = JsonlTraceStore(trace_path)

    store.append(
        TraceEvent(
            run_id="run-1",
            task_id="T1",
            phase="act",
            step=1,
            message="ran pytest",
            tool={"name": "pytest", "args": ["-q"]},
            observation={"exit_code": 0},
        )
    )

    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["phase"] == "act"
    assert rows[0]["tool"]["name"] == "pytest"


def test_analyzer_classifies_regression_before_unverified() -> None:
    gate = GateResult(
        has_diff=True,
        tests_ran=True,
        tests_passed=False,
        scope_ok=True,
        report_exists=True,
        status="fail",
        failure_type=None,
    )

    assert classify_failure(gate) == "Regression"
