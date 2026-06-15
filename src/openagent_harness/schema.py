from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


RunMode = Literal["local", "api"]


@dataclass(frozen=True)
class TaskSpec:
    id: str
    repo: str
    goal: str
    allowlist: list[str]
    acceptance: list[str]
    budget: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskSpec":
        return cls(
            id=str(data["id"]),
            repo=str(data["repo"]),
            goal=str(data["goal"]),
            allowlist=list(data.get("allowlist", [])),
            acceptance=list(data.get("acceptance", [])),
            budget=dict(data.get("budget", {})),
        )


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    task_id: str
    phase: str
    step: int
    message: str
    tool: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    has_diff: bool
    tests_ran: bool
    tests_passed: bool
    scope_ok: bool
    report_exists: bool
    status: Literal["pass", "fail"]
    failure_type: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    gate: GateResult
