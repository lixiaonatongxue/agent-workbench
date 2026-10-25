"""Locate and read agent rule files (AGENTS.md, CLAUDE.md, .cursor/rules/*, ...).

The pattern table lives in rules-patterns.json so new agents can be supported
without touching code. A single file can belong to multiple agents (AGENTS.md
is read by Codex, ZCode and friends) — the scanner merges agent ids per path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.doctor.simhash import simhash
from app.doctor.tokens import estimate_tokens
from app.scan.repos import RepoInfo, find_git_repos

PATTERNS_FILE = Path(__file__).with_name("rules-patterns.json")

# Files larger than this are almost certainly not rule files (or are hopeless ones).
MAX_FILE_SIZE = 5 * 1024 * 1024
# Blocks shorter than this (normalized chars) are noise for duplicate detection.
MIN_BLOCK_CHARS = 30


@dataclass
class RuleBlock:
    start_line: int  # 1-based inclusive
    end_line: int
    text: str
    tokens_est: int
    simhash: int
    norm_hash: str


@dataclass
class RuleFileInfo:
    path: str
    repo: str | None          # repo root path; None for user-global files
    repo_name: str | None
    agents: list[str] = field(default_factory=list)
    size: int = 0
    lines: int = 0
    chars: int = 0
    cjk_chars: int = 0
    tokens_est: int = 0
    mtime: float = 0.0
    content_hash: str = ""
    blocks: list[RuleBlock] = field(default_factory=list)
    error: str | None = None  # set when the file could not be read/parsed


ProgressFn = Callable[[str, int, int, str], None]  # phase, done, total, message


def _load_patterns(path: Path = PATTERNS_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    agents = data.get("agents", [])
    if not agents:
        raise ValueError(f"no agents defined in {path}")
    return agents


def _cjk_count(text: str) -> int:
    # same classes as doctor.tokens; counted separately for the report
    n = 0
    for ch in text:
        o = ord(ch)
        if (0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
                or 0xF900 <= o <= 0xFAFF or 0x3040 <= o <= 0x30FF
                or 0xAC00 <= o <= 0xD7AF):
            n += 1
    return n


def split_blocks(text: str) -> list[tuple[int, int, str]]:
    """Split into paragraph blocks on blank lines; drop tiny noise blocks."""
    lines = text.splitlines()
    blocks: list[tuple[int, int, str]] = []
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            blocks.append((start + 1, i, "\n".join(lines[start:i])))
            start = None
    if start is not None:
        blocks.append((start + 1, len(lines), "\n".join(lines[start:])))

    result = []
    for start_line, end_line, block_text in blocks:
        stripped = block_text.strip()
        if len(stripped.replace(" ", "").replace("\t", "")) >= MIN_BLOCK_CHARS:
            result.append((start_line, end_line, block_text))
    return result


def _read_rule_file(path: Path, repo: RepoInfo | None, agents: list[str]) -> RuleFileInfo:
    info = RuleFileInfo(
        path=str(path.resolve()),
        repo=repo.path if repo else None,
        repo_name=repo.name if repo else None,
        agents=agents,
    )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        info.error = f"read failed: {exc}"
        return info
    stat = path.stat()
    info.size = stat.st_size
    info.mtime = stat.st_mtime
    info.content_hash = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_FILE_SIZE:
        info.error = "file exceeds 5MB, skipped analysis"
        return info

    text = raw.decode("utf-8", errors="replace")
    info.lines = len(text.splitlines())
    info.chars = len(text)
    info.cjk_chars = _cjk_count(text)
    info.tokens_est = estimate_tokens(text)
    for start_line, end_line, block_text in split_blocks(text):
        norm = block_text.strip()
        info.blocks.append(RuleBlock(
            start_line=start_line,
            end_line=end_line,
            text=block_text,
            tokens_est=estimate_tokens(block_text),
            simhash=simhash(block_text),
            norm_hash=hashlib.sha256(
                "".join(norm.split()).lower().encode("utf-8")).hexdigest(),
        ))
    return info


class RuleScanner:
    def __init__(self, patterns_path: Path = PATTERNS_FILE):
        self.agents = _load_patterns(patterns_path)

    def agent_name(self, agent_id: str) -> str:
        for agent in self.agents:
            if agent["id"] == agent_id:
                return agent.get("name", agent_id)
        return agent_id

    def scan(
        self,
        roots: list[str],
        include_global: bool = True,
        user_home: str | None = None,
        max_depth: int = 4,
        progress: ProgressFn | None = None,
    ) -> tuple[list[RuleFileInfo], list[RepoInfo]]:
        """Scan repo roots (and optionally the user home) for rule files.

        Returns (files, repos). Read-only with respect to everything it touches.
        """
        def report(phase: str, done: int, total: int, message: str) -> None:
            if progress:
                progress(phase, done, total, message)

        report("repos", 0, 0, "discovering git repositories")
        repo_by_path: dict[str, RepoInfo] = {}
        for root in roots:
            for repo in find_git_repos(root, max_depth=max_depth):
                repo_by_path.setdefault(repo.path, repo)
        repos = list(repo_by_path.values())
        report("repos", len(repos), len(repos), f"found {len(repos)} repositories")

        found: dict[str, RuleFileInfo] = {}
        claim: dict[str, tuple[RepoInfo | None, list[str]]] = {}

        def claim_file(path: Path, repo: RepoInfo | None, agent_id: str) -> None:
            key = str(path.resolve())
            if key not in claim:
                claim[key] = (repo, [])
            agents_list = claim[key][1]
            if agent_id not in agents_list:
                agents_list.append(agent_id)

        for i, repo in enumerate(repos):
            report("files", i, len(repos), f"scanning {repo.name}")
            repo_path = Path(repo.path)
            for agent in self.agents:
                for pattern in agent.get("project_patterns", []):
                    try:
                        matches = sorted(repo_path.glob(pattern))
                    except (OSError, ValueError):
                        continue
                    for match in matches:
                        if match.is_file():
                            claim_file(match, repo, agent["id"])

        if include_global:
            home = Path(user_home) if user_home else Path.home()
            report("global", 0, len(self.agents), "scanning user home")
            for i, agent in enumerate(self.agents):
                for pattern in agent.get("global_patterns", []):
                    try:
                        matches = sorted(home.glob(pattern))
                    except (OSError, ValueError):
                        continue
                    for match in matches:
                        if match.is_file():
                            claim_file(match, None, agent["id"])
                report("global", i + 1, len(self.agents), f"{agent['name']} done")

        total = len(claim)
        for i, (key, (repo, agent_ids)) in enumerate(sorted(claim.items())):
            found[key] = _read_rule_file(Path(key), repo, agent_ids)
            report("read", i + 1, total, Path(key).name)

        return list(found.values()), repos
