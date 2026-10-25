"""Discover git repositories under given root directories."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Directories that never contain interesting repos and are huge to walk.
SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env", "__pycache__", ".git",
    "dist", "build", "target", ".tox", ".mypy_cache", ".pytest_cache",
    ".cache", ".npm", ".cargo", "site-packages", ".idea", ".vscode",
    "$RECYCLE.BIN", "System Volume Information",
}


@dataclass
class RepoInfo:
    path: str          # absolute repo root
    name: str
    last_activity: float | None  # unix ts of last commit (best effort)


def _last_commit_ts(repo: Path) -> float | None:
    """Best-effort last activity: git log, falling back to newest .git file mtime."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        newest = None
        for dirpath, _dirnames, filenames in os.walk(repo / ".git"):
            for fname in filenames:
                try:
                    m = os.path.getmtime(os.path.join(dirpath, fname))
                except OSError:
                    continue
                if newest is None or m > newest:
                    newest = m
        return newest
    except OSError:
        return None


def _make_repo_info(repo_path: Path) -> RepoInfo:
    return RepoInfo(
        path=str(repo_path.resolve()),
        name=repo_path.name,
        last_activity=_last_commit_ts(repo_path),
    )


def find_git_repos(root: str | os.PathLike, max_depth: int = 4) -> list[RepoInfo]:
    """Walk `root` (bounded depth, pruning SKIP_DIRS) and return every directory
    containing a `.git` entry. Does not descend into found repos."""
    root_path = Path(root).resolve()
    repos: list[RepoInfo] = []

    if (root_path / ".git").exists():
        return [_make_repo_info(root_path)]

    def walk(directory: Path, depth: int) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in SKIP_DIRS:
                continue
            path = Path(entry.path)
            if (path / ".git").exists():
                repos.append(_make_repo_info(path))
                continue  # do not descend into a found repo
            if depth < max_depth:
                walk(path, depth + 1)

    walk(root_path, 0)
    return repos
