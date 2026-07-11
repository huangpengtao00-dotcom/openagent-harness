from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .ignore_rules import IGNORED_DIR_NAMES, IGNORED_FILE_NAMES, IGNORED_SUFFIXES


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
        ignored: set[str] = set()
        for name in names:
            path = Path(directory) / name
            if name in IGNORED_DIR_NAMES or name in IGNORED_FILE_NAMES or path.suffix in IGNORED_SUFFIXES:
                ignored.add(name)
        return ignored
