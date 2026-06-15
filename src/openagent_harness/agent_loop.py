from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .context import ContextBuilder
from .llm import ChatMessage, LLMClient, ModelUsage
from .policy import PermissionPolicy
from .schema import TaskSpec
from .tool_registry import LocalToolRegistry

_SYSTEM_PROMPT = """You are an autonomous coding agent inside OpenAgent Harness.
Return exactly one JSON object per turn. Do not use Markdown.
You must use local tools through JSON actions. Prefer edit_file over write_file.
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
class AgentRunOutcome:
    changed_paths: list[Path]
    steps: list[AgentStep]
    total_usage: ModelUsage
    finished: bool
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "changed_paths": [str(path) for path in self.changed_paths],
            "steps": [asdict(step) for step in self.steps],
            "total_usage": self.total_usage.to_dict(),
            "finished": self.finished,
            "summary": self.summary,
        }


class JsonActionCodingAgent:
    """Guarded loop: model -> JSON action -> registry tool -> observation -> repeat."""

    def __init__(self, client: LLMClient, *, max_steps: int = 8, prompt_char_budget: int = 40_000) -> None:
        self.client = client
        self.max_steps = max_steps
        self.prompt_char_budget = prompt_char_budget

    def apply(self, repo_dir: Path, spec: TaskSpec) -> AgentRunOutcome:
        policy = PermissionPolicy(repo_dir, spec.allowlist, spec.budget)
        timeout_seconds = float(spec.budget.get("tool_timeout_seconds", 30.0))
        registry = LocalToolRegistry(repo_dir, policy, timeout_seconds=timeout_seconds)
        context = ContextBuilder(repo_dir).render_context(spec.goal, max_chars=self.prompt_char_budget)
        messages = [
            ChatMessage("system", _SYSTEM_PROMPT),
            ChatMessage(
                "user",
                "Task goal:\n"
                f"{spec.goal}\n\n"
                f"Allowlist: {spec.allowlist}\n"
                f"Acceptance commands: {spec.acceptance or ['pytest']}\n\n"
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

        for index in range(1, self.max_steps + 1):
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
        )

    def _parse_action(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {"action": "invalid", "error": "No JSON object found."}
            try:
                data = json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                return {"action": "invalid", "error": str(exc)}
        if not isinstance(data, dict):
            return {"action": "invalid", "error": "JSON action must be an object."}
        return data
