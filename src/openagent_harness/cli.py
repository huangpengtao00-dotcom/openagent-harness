from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import typer

from .code_index import build_code_index
from .context import ContextBuilder
from .eval import run_eval
from .llm import ChatMessage, OpenAICompatibleClient
from .env import load_env_file, safe_env_status
from .portfolio import PortfolioRunner
from .runner import HarnessRunner
from .schema import RunMode, TaskSpec
from .policy import PermissionPolicy
from .tool_registry import LocalToolRegistry

app = typer.Typer(help="OpenAgent Harness: coding-agent loop, quality gate, trace, and benchmark runner.")


def _load_spec(path: Path) -> TaskSpec:
    return TaskSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to a task spec JSON file."),
    runs: Path = typer.Option(Path("runs"), "--runs", help="Directory where run artifacts are written."),
    mode: RunMode = typer.Option("local", "--mode", help="local uses deterministic patches; api uses guarded LLM tool loop."),
    model: str = typer.Option("deepseek-v4-flash", "--model", help="OpenAI-compatible model name."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-compatible base URL."),
    allow_llm_calls: bool = typer.Option(False, "--allow-llm-calls", help="Actually call the configured model API."),
) -> None:
    """Run a task through either the offline scripted path or the guarded API agent path."""
    load_env_file()
    result = HarnessRunner(mode=mode, model=model, base_url=base_url, allow_llm_calls=allow_llm_calls).run_task(
        _load_spec(spec), runs
    )
    typer.echo(f"run_id={result.run_id}")
    typer.echo(f"status={result.gate.status}")
    typer.echo(f"failure_type={result.gate.failure_type}")
    typer.echo(f"artifacts={result.run_dir}")


@app.command("api-check")
def api_check(
    spec: Path = typer.Argument(..., help="Path to a task spec JSON file."),
    model: str = typer.Option("deepseek-v4-flash", "--model", help="OpenAI-compatible model name."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-compatible base URL."),
    runs: Path = typer.Option(Path("runs"), "--runs", help="Directory where check artifacts are written."),
) -> None:
    """Validate API configuration without making a network call.

    This command never enters the agent loop and never spends tokens. It only
    verifies that local .env / shell configuration can be resolved and writes a
    sanitized api_check.json artifact for debugging.
    """
    load_env_file()
    loaded_spec = _load_spec(spec)
    client = OpenAICompatibleClient(model=model, base_url=base_url)
    run_hash = hashlib.sha256(f"{loaded_spec.id}|{model}|{client.base_url}".encode("utf-8")).hexdigest()[:8]
    safe_task_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in loaded_spec.id)[:64]
    run_id = f"api-check-{safe_task_id}-{run_hash}"
    run_dir = runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "status": "ok" if client.is_configured() else "missing_key",
        "network_call": False,
        "task_id": loaded_spec.id,
        "model": model,
        "configuration": client.configuration_note(),
        "env_status": safe_env_status(["DEEPSEEK_API_KEY", "OPENAGENT_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_BASE_URL", "OPENAGENT_BASE_URL"]),
        "note": "api-check is a dry run; use deepseek-smoke or run --allow-llm-calls for real API calls.",
    }
    (run_dir / "api_check.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"run_id={run_id}")
    typer.echo(f"status={artifact['status']}")
    typer.echo(f"api_key_configured={str(client.is_configured()).lower()}")
    typer.echo(f"artifacts={run_dir}")
    typer.echo("network_call=false")


@app.command("deepseek-check")
def deepseek_check(
    model: str = typer.Option("deepseek-v4-flash", "--model", help="DeepSeek model name."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Override DeepSeek/OpenAI-compatible base URL."),
) -> None:
    """Print DeepSeek/OpenAI-compatible client configuration without calling the API."""
    load_env_file()
    client = OpenAICompatibleClient(model=model, base_url=base_url)
    note = client.configuration_note()
    note["env_status"] = safe_env_status(["DEEPSEEK_API_KEY", "OPENAGENT_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_BASE_URL", "OPENAGENT_BASE_URL"])
    typer.echo(json.dumps(note, ensure_ascii=False, indent=2))


@app.command("deepseek-smoke")
def deepseek_smoke(
    model: str = typer.Option("deepseek-v4-flash", "--model", help="DeepSeek/OpenAI-compatible model name."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Override DeepSeek/OpenAI-compatible base URL."),
    runs: Path = typer.Option(Path("runs_deepseek_smoke"), "--runs", help="Directory where smoke artifacts are written."),
    prompt: str = typer.Option(
        "Return a compact JSON object with fields status and message saying OpenAgent Harness API smoke test passed.",
        "--prompt",
        help="Small prompt used for a real API smoke test.",
    ),
) -> None:
    """Make one real API call and write a sanitized smoke-test artifact. Never writes the API key."""
    load_env_file()
    client = OpenAICompatibleClient(model=model, base_url=base_url, max_tokens=256, timeout_seconds=30.0)
    if not client.is_configured():
        raise typer.BadParameter("No API key configured. Put DEEPSEEK_API_KEY in a local .env file or export it in the shell.")
    response = client.chat(
        [
            ChatMessage("system", "You are a minimal API connectivity tester. Return JSON only."),
            ChatMessage("user", prompt),
        ],
        response_format_json=True,
    )
    runs.mkdir(parents=True, exist_ok=True)
    artifact = {
        "configured": client.configuration_note(),
        "response_content": response.content,
        "usage": response.usage.to_dict(),
        "raw": response.raw,
    }
    out = runs / "deepseek_smoke.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"ok=true")
    typer.echo(f"artifact={out}")
    typer.echo(json.dumps({"usage": response.usage.to_dict(), "content_preview": response.content[:300]}, ensure_ascii=False, indent=2))


@app.command("context")
def context(
    repo: Path = typer.Argument(..., help="Repository directory to compact."),
    goal: str = typer.Argument(..., help="Natural-language task goal."),
    max_chars: int = typer.Option(20_000, "--max-chars", help="Maximum rendered context characters."),
) -> None:
    """Render deterministic compact context for a coding-agent prompt."""
    typer.echo(ContextBuilder(repo).render_context(goal, max_chars=max_chars))




@app.command("index")
def index(
    repo: Path = typer.Argument(..., help="Repository directory to index."),
    query: Optional[str] = typer.Option(None, "--query", help="Optional symbol query."),
    limit: int = typer.Option(30, "--limit", help="Maximum symbols to print."),
) -> None:
    """Build a Python AST symbol index for repo understanding."""
    code_index = build_code_index(repo)
    symbols = code_index.search_symbols(query, limit=limit) if query else code_index.symbols[:limit]
    typer.echo(
        json.dumps(
            {
                "files_indexed": code_index.files_indexed,
                "errors": code_index.errors,
                "symbols": [symbol.to_dict() for symbol in symbols],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("tools")
def tools(
    repo: Path = typer.Argument(Path("."), help="Repository directory used only for policy construction."),
) -> None:
    """Print the local tool registry schemas exposed to the coding agent."""
    registry = LocalToolRegistry(repo, PermissionPolicy(repo, allowlist=["*"]))
    typer.echo(registry.specs_json())


@app.command("portfolio")
def portfolio(
    spec: Path = typer.Argument(..., help="Path to a task spec JSON file."),
    runs: Path = typer.Option(Path("runs_portfolio"), "--runs", help="Directory where portfolio artifacts are written."),
) -> None:
    """Run candidate agents and select the best verified patch by scorecard."""
    result = PortfolioRunner().run(_load_spec(spec), runs)
    typer.echo(f"candidates={len(result.candidates)}")
    if result.best:
        typer.echo(f"best={result.best.name}")
        typer.echo(f"score={result.best.scorecard.score}")
        typer.echo(f"run_dir={result.best.run_dir}")
    typer.echo(f"summary={runs / 'portfolio_summary.json'}")


@app.command()
def replay(run_dir: Path = typer.Argument(..., help="Run artifact directory containing trace.jsonl.")) -> None:
    """Print a compact replay from trace.jsonl."""
    trace_path = run_dir / "trace.jsonl"
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        typer.echo(f"[{event['phase']}] step={event['step']} {event['message']}")


@app.command()
def eval(
    benchmarks: Path = typer.Option(Path("benchmarks"), "--benchmarks", help="Directory containing benchmark task folders."),
    runs: Path = typer.Option(Path("runs_eval"), "--runs", help="Directory where eval artifacts are written."),
) -> None:
    """Run every benchmark task and write eval_summary.json."""
    summary = run_eval(benchmarks, runs, project_root=Path.cwd())
    typer.echo(f"total={summary.total}")
    typer.echo(f"passed={summary.passed}")
    typer.echo(f"failed={summary.failed}")
    typer.echo(f"pass_rate={summary.pass_rate}")
    typer.echo(f"summary={runs / 'eval_summary.json'}")
    typer.echo(f"html_report={runs / 'eval_report.html'}")


if __name__ == "__main__":
    app()
