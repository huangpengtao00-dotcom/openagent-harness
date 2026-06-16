from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .code_index import build_code_index
from .ignore_rules import IGNORED_DIR_NAMES, should_ignore_repo_path


_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".csv",
}
_CONTEXT_FILES = ["AGENTS.md", "CLAUDE.md", "README.md", "pyproject.toml"]


@dataclass(frozen=True)
class RepoFile:
    path: str
    size_bytes: int
    score: int = 0


@dataclass(frozen=True)
class RepoIndex:
    files: list[RepoFile]
    skipped: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "files": [file.__dict__ for file in self.files],
            "skipped": self.skipped,
            "total_bytes": self.total_bytes,
        }


class ContextBuilder:
    """Deterministic context compaction for coding-agent prompts."""

    def __init__(self, repo_dir: Path, *, max_file_bytes: int = 12_000, max_files: int = 20) -> None:
        self.repo_dir = repo_dir
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def build_index(self, goal: str = "") -> RepoIndex:
        files: list[RepoFile] = []
        skipped: list[str] = []
        total_bytes = 0
        for path in sorted(self.repo_dir.rglob("*")):
            if not path.is_file() or should_ignore_repo_path(path, self.repo_dir):
                continue
            relative = path.relative_to(self.repo_dir).as_posix()
            if path.suffix and path.suffix not in _TEXT_SUFFIXES:
                skipped.append(relative)
                continue
            size = path.stat().st_size
            total_bytes += size
            files.append(RepoFile(relative, size, self._score_path(relative, goal)))
        return RepoIndex(files=sorted(files, key=lambda f: (-f.score, f.path)), skipped=skipped, total_bytes=total_bytes)

    def candidate_files(self, goal: str, limit: int | None = None) -> list[RepoFile]:
        cap = limit or self.max_files
        return self.build_index(goal).files[:cap]

    def render_context(self, goal: str, *, max_chars: int = 40_000) -> str:
        parts: list[str] = []
        index = self.build_index(goal)
        parts.append("# Repository Map\n")
        for repo_file in index.files[: self.max_files]:
            parts.append(f"- {repo_file.path} ({repo_file.size_bytes} bytes, score={repo_file.score})\n")
        parts.append("\n# Symbol Map\n")
        try:
            code_index = build_code_index(self.repo_dir)
            for symbol in code_index.search_symbols(goal, limit=20) or code_index.symbols[:20]:
                parts.append(f"- {symbol.kind} {symbol.name} at {symbol.path}:{symbol.line} {symbol.signature}\n")
        except Exception as exc:  # noqa: BLE001 - context must be best-effort.
            parts.append(f"- <symbol indexing failed: {exc}>\n")
        parts.append("\n# Project Instructions\n")
        for name in _CONTEXT_FILES:
            path = self.repo_dir / name
            if path.exists() and path.is_file() and not should_ignore_repo_path(path, self.repo_dir):
                parts.append(f"\n## {name}\n")
                parts.append(self._read_limited(path))
        parts.append("\n# Candidate File Contents\n")
        used = len("".join(parts))
        for repo_file in index.files[: self.max_files]:
            if used >= max_chars:
                break
            path = self.repo_dir / repo_file.path
            content = self._read_limited(path)
            chunk = f"\n## {repo_file.path}\n```\n{content}\n```\n"
            remaining = max_chars - used
            if len(chunk) > remaining:
                chunk = chunk[: max(0, remaining - 80)] + "\n...<context truncated>\n"
            parts.append(chunk)
            used += len(chunk)
        return "".join(parts)

    def _read_limited(self, path: Path) -> str:
        raw = path.read_bytes()[: self.max_file_bytes]
        text = raw.decode("utf-8", errors="replace")
        if path.stat().st_size > self.max_file_bytes:
            text += "\n...<file truncated>\n"
        return text

    def _score_path(self, relative: str, goal: str) -> int:
        name = Path(relative).name.lower()
        lowered = relative.lower()
        tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+|[\u4e00-\u9fff]+", goal.lower()))
        score = 0
        if name in {"readme.md", "agents.md", "claude.md"}:
            score += 5
        if name.startswith("test_") or name.endswith("_test.py"):
            score += 4
        if relative.endswith(".py"):
            score += 3
        for token in tokens:
            if token and token in lowered:
                score += 8
        return score
