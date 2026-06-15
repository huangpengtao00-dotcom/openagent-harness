from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

_IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "runs"}


@dataclass(frozen=True)
class Workspace:
    source: Path
    path: Path
    strategy: str


class WorkspaceManager:
    """Creates isolated candidate workspaces.

    The implementation uses copy isolation by default because it works without requiring the input
    repository to be a git checkout. The class boundary leaves room for git-worktree isolation later.
    """

    def create(self, source_repo: Path, target_dir: Path, *, strategy: str = "copy") -> Workspace:
        source_repo = source_repo.resolve()
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_repo, target_dir, ignore=self._ignore)
        return Workspace(source=source_repo, path=target_dir, strategy=strategy)

    def _ignore(self, directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in _IGNORED_DIRS}
