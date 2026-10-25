"""Filesystem locations for local state (index db)."""

from __future__ import annotations

import os
from pathlib import Path


def data_home() -> Path:
    """Directory holding local state. Override with AGENT_WORKBENCH_HOME env."""
    env = os.environ.get("AGENT_WORKBENCH_HOME")
    if env:
        return Path(env)
    return Path.home() / ".agent-workbench"


def db_path() -> Path:
    return data_home() / "workbench.sqlite3"
