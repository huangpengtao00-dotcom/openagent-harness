from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .context import ContextBuilder
from .llm import ChatMessage, LLMClient, ModelUsage
from .policy import PermissionPolicy
from .schema import TaskSpec
from .tool_registry import LocalToolRegistry

_SYSTEM_PROMPT = """You are an autonomous coding agent inside OpenAgent Harness.
Return exactly one JSON object per turn. Do not use Markdown.
You must use local tools through JSON actions. Prefer edit_file over write_file.
Example valid action:
{"action":"read_file","path":"solution.py"}
Rules:
- Diagnose first with search_repo, inspect_symbols, or read_file when needed.
- Modify only task allowlist files.
- Prefer a minimal patch-level edit_file action with exact old_text/new_text.
- Run acceptance tests before finish.
- Finish only after a successful verification command.
"""


@dataclass(frozen=True)
class AgentStep:
    index: int
    action: str
    args: dict[str, Any]
    observation: dict[str, Any]
    usage: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class LoopStrategy:
    tier: Literal["simple", "standard", "deep"]
    max_steps: int
    prompt_char_budget: int
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRunOutcome:
    changed_paths: list[Path]
    steps: list[AgentStep]
    total_usage: ModelUsage
    finished: bool
    summary: str
    strategy: LoopStrategy = field(
        default_factory=lambda: LoopStrategy("standard", 8, 40_000, ["legacy fixed loop budget"])
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "changed_paths": [str(path) for path in self.changed_paths],
            "steps": [asdict(step) for step in self.steps],
            "total_usage": self.total_usage.to_dict(),
            "finished": self.finished,
            "summary": self.summary,
            "strategy": self.strategy.to_dict(),
        }


class JsonActionCodingAgent:
    """Guarded loop: model -> JSON action -> registry tool -> observation -> repeat."""

    def __init__(
        self,
        client: LLMClient,
        *,
        max_steps: int = 8,
        prompt_char_budget: int = 40_000,
        adaptive: bool = False,
    ) -> None:
        self.client = client
        self.max_steps = max_steps
        self.prompt_char_budget = prompt_char_budget
        self.adaptive = adaptive

    def apply(self, repo_dir: Path, spec: TaskSpec, *, failure_context: str | None = None) -> AgentRunOutcome:
        strategy = self._select_strategy(repo_dir, spec, failure_context=failure_context)
        policy = PermissionPolicy(repo_dir, spec.allowlist, spec.budget)
        timeout_seconds = float(spec.budget.get("tool_timeout_seconds", 30.0))
        registry = LocalToolRegistry(repo_dir, policy, timeout_seconds=timeout_seconds)
        context = ContextBuilder(repo_dir).render_context(spec.goal, max_chars=strategy.prompt_char_budget)
        failure_context_section = ""
        if failure_context:
            failure_context_section = (
                "\n\nPrevious failed run evidence:\n"
                f"{failure_context}\n\n"
                "Use the evidence above to diagnose the next attempt. "
                "Do not repeat the previous failed patch blindly. "
                "The task allowlist and acceptance commands remain authoritative."
            )
        messages = [
            ChatMessage("system", _SYSTEM_PROMPT),
            ChatMessage(
                "user",
                "Task goal:\n"
                f"{spec.goal}\n\n"
                f"Allowlist: {spec.allowlist}\n"
                f"Acceptance commands: {spec.acceptance or ['pytest']}\n\n"
                f"{failure_context_section}\n\n"
                "Loop strategy:\n"
                f"{json.dumps(strategy.to_dict(), ensure_ascii=False)}\n\n"
                "Available tools, each invoked by setting the JSON action field to the tool name:\n"
                f"{registry.specs_json()}\n\n"
                "Finish action schema: {\"action\":\"finish\",\"summary\":\"what changed and why\"}\n\n"
                f"Repository context:\n{context}",
            ),
        ]
        steps: list[AgentStep] = []
        changed_paths: list[Path] = []
        total_prompt = 0
        total_completion = 0
        total_estimated_cost = 0.0
        summary = ""
        finished = False
        verified = False

        for index in range(1, strategy.max_steps + 1):
            response = self.client.chat(messages, response_format_json=True)
            total_prompt += response.usage.prompt_tokens
            total_completion += response.usage.completion_tokens
            total_estimated_cost += response.usage.estimated_cost_usd
            action = self._parse_action(response.content)
            action_name = str(action.get("action", "")).strip()

            if action_name == "finish":
                summary = str(action.get("summary", ""))
                observation = {"ok": verified, "summary": summary}
                finished = verified
                if not verified:
                    observation["error"] = "finish blocked until a verification command succeeds"
            elif action_name == "invalid":
                observation = {
                    "ok": False,
                    "error": (
                        "Your previous response was not a valid JSON action object. "
                        "Return exactly one object such as "
                        '{"action":"read_file","path":"solution.py"} or '
                        '{"action":"run_command","command":"python -m pytest -q"}.'
                    ),
                    "parse_error": str(action.get("error", "invalid JSON action")),
                }
            else:
                observation = registry.dispatch(action_name, action).to_observation()
                if action_name in {"edit_file", "write_file"} and observation.get("ok"):
                    path = str(observation.get("path", ""))
                    if path:
                        changed_paths.append((repo_dir / path).resolve())
                if action_name == "run_command" and observation.get("ok"):
                    verified = True

            step = AgentStep(
                index=index,
                action=action_name,
                args={k: v for k, v in action.items() if k not in {"content", "old_text", "new_text"}},
                observation=observation,
                usage=response.usage.to_dict(),
            )
            steps.append(step)
            messages.append(ChatMessage("assistant", response.content))
            messages.append(ChatMessage("user", "Observation:\n" + json.dumps(observation, ensure_ascii=False)))
            if finished:
                break

        return AgentRunOutcome(
            changed_paths=sorted(set(changed_paths)),
            steps=steps,
            total_usage=ModelUsage(
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                total_tokens=total_prompt + total_completion,
                estimated_cost_usd=round(total_estimated_cost, 8),
            ),
            finished=finished,
            summary=summary,
            strategy=strategy,
        )

    def _parse_action(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            if start == -1:
                return {"action": "invalid", "error": "No JSON object found."}
            try:
                data, _ = json.JSONDecoder().raw_decode(content[start:])
            except json.JSONDecodeError as exc:
                return {"action": "invalid", "error": str(exc)}
        if not isinstance(data, dict):
            return {"action": "invalid", "error": "JSON action must be an object."}
        return data

    def _select_strategy(self, repo_dir: Path, spec: TaskSpec, *, failure_context: str | None = None) -> LoopStrategy:
        configured_steps = int(spec.budget.get("max_steps", self.max_steps))
        configured_budget = int(spec.budget.get("prompt_char_budget", self.prompt_char_budget))
        if not self.adaptive:
            return LoopStrategy(
                tier="standard",
                max_steps=configured_steps,
                prompt_char_budget=configured_budget,
                rationale=["explicit fixed loop budget"],
            )

        files = _text_files(repo_dir)
        test_files = [path for path in files if path.name.startswith("test_") or path.name.endswith("_test.py")]
        allowlist_size = len(spec.allowlist)
        goal_size = len(spec.goal)
        rationale: list[str] = []
        complexity = 0
        if len(files) <= 3 and allowlist_size <= 1 and len(test_files) <= 1 and goal_size <= 500 and not failure_context:
            rationale.append("small repo, one editable file, short goal")
        else:
            complexity += 1
            rationale.append("multi-file or larger task context")
        if allowlist_size >= 3 or len(test_files) >= 3 or len(files) >= 12:
            complexity += 2
            rationale.append("broad edit/test surface")
        if failure_context:
            complexity += 2
            rationale.append("retry has failure context to diagnose")
        if any(token in spec.goal.lower() for token in ["refactor", "race", "concurrent", "cache", "security", "multi", "async"]):
            complexity += 1
            rationale.append("goal contains higher-complexity engineering terms")

        if complexity == 0:
            return LoopStrategy(
                tier="simple",
                max_steps=min(configured_steps, 4),
                prompt_char_budget=min(configured_budget, 16_000),
                rationale=rationale,
            )
        if complexity >= 3:
            return LoopStrategy(
                tier="deep",
                max_steps=max(configured_steps, 10),
                prompt_char_budget=max(configured_budget, 60_000),
                rationale=rationale,
            )
        return LoopStrategy(
            tier="standard",
            max_steps=configured_steps,
            prompt_char_budget=configured_budget,
            rationale=rationale,
        )


def _text_files(repo_dir: Path) -> list[Path]:
    return [
        path
        for path in repo_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".csv"}
    ]
