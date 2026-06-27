from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .scoring import RunScorecard, score_run
from .schema import GateResult


def write_run_html_report(run_dir: Path, gate: GateResult) -> RunScorecard:
    scorecard = score_run(run_dir, gate)
    task_spec = _read_json(run_dir / "task_spec.json")
    context_summary = _read_json(run_dir / "context_summary.json")
    api_agent_run = _read_json(run_dir / "api_agent_run.json")
    patch = _read_text(run_dir / "patch.diff")
    test_result = _read_json(run_dir / "test_result.json")
    trace_lines = _read_text(run_dir / "trace.jsonl").splitlines()
    trace_events = [json.loads(line) for line in trace_lines if line.strip()]
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OpenAgent Harness Run Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; line-height: 1.45; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 16px 0; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }}
    .label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 20px; font-weight: 700; }}
    pre {{ background: #111827; color: #f9fafb; padding: 16px; border-radius: 8px; overflow-x: auto; max-height: 560px; }}
    code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 24px; }}
    td, th {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; vertical-align: top; }}
    .ok {{ color: #047857; font-weight: 700; }}
    .bad {{ color: #b91c1c; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>OpenAgent Harness Run Report</h1>
  <div class="grid">
    <div class="card"><div class="label">Status</div><div class="value">{html.escape(scorecard.status)}</div></div>
    <div class="card"><div class="label">Score</div><div class="value">{scorecard.score}</div></div>
    <div class="card"><div class="label">Changed files</div><div class="value">{scorecard.changed_files}</div></div>
    <div class="card"><div class="label">Patch lines</div><div class="value">{scorecard.patch_lines}</div></div>
  </div>

  <h2>Task Goal</h2>
  <p>{html.escape(str(task_spec.get('goal', '')))}</p>
  <table>
    <tr><th>Task ID</th><td>{html.escape(str(task_spec.get('id', '')))}</td></tr>
    <tr><th>Allowlist</th><td><code>{html.escape(json.dumps(task_spec.get('allowlist', []), ensure_ascii=False))}</code></td></tr>
    <tr><th>Acceptance</th><td><code>{html.escape(json.dumps(task_spec.get('acceptance', []), ensure_ascii=False))}</code></td></tr>
  </table>

  <h2>Selected Context</h2>
  <p>Total files: {html.escape(str(context_summary.get('total_files', '')))} | Total bytes: {html.escape(str(context_summary.get('total_bytes', '')))}</p>
  <table><tr><th>Path</th><th>Size</th><th>Score</th></tr>{_context_rows(context_summary)}</table>

  <h2>Tool Calls Timeline</h2>
  {_api_steps_table(api_agent_run)}
  <h3>Trace timeline</h3>
  <table><tr><th>Phase</th><th>Step</th><th>Message</th><th>Observation</th></tr>{''.join(_trace_row(event) for event in trace_events)}</table>

  <h2>Permission Decisions</h2>
  {_permission_table(api_agent_run)}

  <h2>Patch Diff</h2>
  <pre>{html.escape(patch[:30000])}</pre>

  <h2>Test Output</h2>
  <pre>{html.escape(json.dumps(test_result, ensure_ascii=False, indent=2)[:18000])}</pre>

  <h2>Cost Estimate</h2>
  {_cost_block(api_agent_run)}

  <h2>Scorecard</h2>
  <pre>{html.escape(json.dumps(scorecard.to_dict(), ensure_ascii=False, indent=2))}</pre>

  <h2>Failure Analysis</h2>
  <p>{html.escape(_failure_analysis(scorecard, gate, test_result))}</p>
</body>
</html>
"""
    (run_dir / "report.html").write_text(html_text, encoding="utf-8")
    (run_dir / "scorecard.json").write_text(json.dumps(scorecard.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return scorecard


def write_eval_html_report(runs_root: Path) -> None:
    summary = _read_json(runs_root / "eval_summary.json")
    rows = []
    for result in summary.get("results", []):
        run_dir = Path(str(result.get("run_dir", "")))
        scorecard = _read_json(run_dir / "scorecard.json")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(result.get('task_id', '')))}</td>"
            f"<td>{html.escape(str(result.get('status', '')))}</td>"
            f"<td>{html.escape(str(result.get('failure_type', '')))}</td>"
            f"<td>{html.escape(str(scorecard.get('score', '')))}</td>"
            f"<td>{html.escape(str(run_dir))}</td>"
            "</tr>"
        )
    html_text = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>OpenAgent Eval Summary</title>
<style>body{{font-family:Arial,sans-serif;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #e5e7eb;padding:8px;text-align:left}}</style></head>
<body><h1>OpenAgent Eval Summary</h1>
<p>Total: {summary.get('total', 0)} | Passed: {summary.get('passed', 0)} | Failed: {summary.get('failed', 0)} | Pass rate: {summary.get('pass_rate', 0)}</p>
<table><tr><th>Task</th><th>Status</th><th>Failure</th><th>Score</th><th>Run dir</th></tr>{''.join(rows)}</table>
</body></html>"""
    (runs_root / "eval_report.html").write_text(html_text, encoding="utf-8")


def _context_rows(context_summary: dict[str, Any]) -> str:
    rows = []
    for item in context_summary.get("selected_files", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('path', '')))}</td>"
            f"<td>{html.escape(str(item.get('size_bytes', '')))}</td>"
            f"<td>{html.escape(str(item.get('score', '')))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='3'>No context summary.</td></tr>"


def _api_steps_table(api_agent_run: dict[str, Any]) -> str:
    steps = api_agent_run.get("steps", [])
    if not steps:
        return "<p>No API agent steps recorded. Local/scripted runs still include the trace table below.</p>"
    rows = []
    for step in steps:
        observation = step.get("observation", {})
        ok_class = "ok" if observation.get("ok") else "bad"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(step.get('index', '')))}</td>"
            f"<td>{html.escape(str(step.get('action', '')))}</td>"
            f"<td><span class='{ok_class}'>{html.escape(str(observation.get('ok', '')))}</span></td>"
            f"<td><pre>{html.escape(json.dumps(step.get('args', {}), ensure_ascii=False, indent=2)[:4000])}</pre></td>"
            f"<td><pre>{html.escape(json.dumps(observation, ensure_ascii=False, indent=2)[:4000])}</pre></td>"
            "</tr>"
        )
    return "<table><tr><th>#</th><th>Action</th><th>OK</th><th>Args</th><th>Observation</th></tr>" + "".join(rows) + "</table>"


def _permission_table(api_agent_run: dict[str, Any]) -> str:
    rows = []
    for step in api_agent_run.get("steps", []):
        action = str(step.get("action", ""))
        observation = step.get("observation", {})
        if action in {"write_file", "edit_file", "run_command", "read_file"}:
            allowed = observation.get("ok")
            reason = observation.get("error") or "allowed by policy"
            rows.append(
                "<tr>"
                f"<td>{html.escape(action)}</td>"
                f"<td>{html.escape(str(step.get('args', {}).get('path') or step.get('args', {}).get('command') or ''))}</td>"
                f"<td>{html.escape(str(allowed))}</td>"
                f"<td>{html.escape(str(reason))}</td>"
                "</tr>"
            )
    if not rows:
        return "<p>No explicit policy decisions recorded for this run.</p>"
    return "<table><tr><th>Action</th><th>Target</th><th>Allowed</th><th>Reason</th></tr>" + "".join(rows) + "</table>"


def _cost_block(api_agent_run: dict[str, Any]) -> str:
    usage = api_agent_run.get("total_usage", {})
    if not usage:
        return "<p>No model usage recorded for local/scripted run.</p>"
    return "<pre>" + html.escape(json.dumps(usage, ensure_ascii=False, indent=2)) + "</pre>"


def _failure_analysis(scorecard: RunScorecard, gate: GateResult, test_result: dict[str, Any]) -> str:
    if gate.status == "pass":
        return "The run passed the quality gate: diff exists, acceptance ran, tests passed, scope stayed within the allowlist, and final_report.md exists."
    if gate.failure_type == "Regression":
        return "Acceptance failed. Inspect Test Output and Patch Diff first; the most likely cause is an incomplete or over-broad patch."
    if gate.failure_type == "ScopeViolation":
        return "The patch touched files outside the allowlist. Tighten the agent policy or task spec."
    if gate.failure_type == "ArtifactHygieneViolation":
        return "Run artifacts failed the hygiene scan. Inspect artifact_hygiene.json for secret-like values or runtime cache leftovers."
    if gate.failure_type == "NoPatch":
        return "No code change was produced. Check whether the agent had enough context and whether the task is supported by the selected mode."
    if any(result.get("timed_out") for result in test_result.get("results", [])):
        return "At least one acceptance command timed out. Reduce test scope or increase acceptance_timeout_seconds."
    return f"Quality gate failed with type: {gate.failure_type}."


def _trace_row(event: dict[str, object]) -> str:
    obs = event.get("observation")
    obs_text = json.dumps(obs, ensure_ascii=False)[:1000] if obs else ""
    return (
        "<tr>"
        f"<td>{html.escape(str(event.get('phase', '')))}</td>"
        f"<td>{html.escape(str(event.get('step', '')))}</td>"
        f"<td>{html.escape(str(event.get('message', '')))}</td>"
        f"<td>{html.escape(obs_text)}</td>"
        "</tr>"
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
