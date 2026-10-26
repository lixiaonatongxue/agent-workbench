"""Heuristic contradiction detection (A5): same topic, opposing directives.

Deliberately conservative output — everything here is "疑似矛盾，供人工确认".
Topics are small hand-written value packs; a mention only counts when the
block also carries directive-ish wording (use/prefer/always/never/用/使用…),
which keeps prose mentions ("npm scripts") out of the results.

Scopes compared:
- per file: two different values for one topic inside the same rule file
- per agent: two different values across files the same agent reads
  (global + repo files), i.e. what actually co-injects into one session
"""

from __future__ import annotations

import json
import re

DIRECTIVE_RE = re.compile(
    r"(?i)\b(use|prefer|always|never|install|run|统一|使用|采用|安装|执行|必须|不要)\b|用",
)

TOPICS: list[dict] = [
    {
        "id": "package-manager",
        "label": "包管理器",
        "values": {
            "pnpm": r"(?i)\bpnpm\b",
            "npm": r"(?i)\bnpm\b",
            "yarn": r"(?i)\byarn\b",
            "bun": r"(?i)\bbun\b",
        },
    },
    {
        "id": "python-version",
        "label": "Python 版本",
        "values": "version",  # dynamic: python 3.x
        "pattern": r"[Pp]ython\s*3\.(\d{1,2})",
    },
    {
        "id": "answer-language",
        "label": "回答语言",
        "values": {
            "中文": r"(?i)(中文回答|用中文|回复.*中文|answer in chinese|respond in chinese)",
            "English": r"(?i)(英文回答|用英文|回复.*英文|answer in english|respond in english)",
        },
    },
    {
        "id": "default-branch",
        "label": "默认分支",
        "values": {
            "main": r"(?i)\bmain\b\s*(分支|branch)|默认分支.*\bmain\b",
            "master": r"(?i)\bmaster\b\s*(分支|branch)|默认分支.*\bmaster\b",
        },
    },
]

MAX_GROUPS = 50
SENTENCE_SPLIT = re.compile(r"[。\n；;]")


def _sentence_brief(text: str, pos: int, limit: int = 90) -> str:
    start = max(text.rfind("。", 0, pos), text.rfind("\n", 0, pos), 0)
    segment = text[start:text.find("。", pos)] if text.find("。", pos) != -1 else text[start:]
    return brief_line(segment.strip() or text[max(0, pos - 40):pos + 50], limit)


def brief_line(s: str, limit: int) -> str:
    s = " ".join(s.split())
    return s[:limit] + ("…" if len(s) > limit else "")


def _mentions_for_block(block: dict) -> list[dict]:
    """Yield {topic, value, line, brief} mentions found in one rule block."""
    text = block.get("text") or ""
    if not text or not DIRECTIVE_RE.search(text):
        return []
    found = []
    for topic in TOPICS:
        if topic["values"] == "version":
            for m in re.finditer(topic["pattern"], text):
                found.append({
                    "topic": topic["id"], "label": topic["label"],
                    "value": f"3.{m.group(1)}",
                    "line": block["start_line"],
                    "brief": _sentence_brief(text, m.start()),
                })
                break  # one mention per block per topic is enough
        else:
            hit = None
            for value, pattern in topic["values"].items():
                m = re.search(pattern, text)
                if m:
                    hit = {
                        "topic": topic["id"], "label": topic["label"],
                        "value": value,
                        "line": block["start_line"],
                        "brief": _sentence_brief(text, m.start()),
                    }
                    break
            if hit:
                found.append(hit)
    return found


def detect_contradictions(blocks: list[dict]) -> list[dict]:
    """blocks: rule_blocks rows joined with path/repo/agents (agents = JSON)."""
    mentions: list[dict] = []
    for block in blocks:
        for m in _mentions_for_block(block):
            mentions.append({
                **m,
                "path": block["path"],
                "repo": block["repo"],
                "agents": json.loads(block["agents"]) if block.get("agents") else [],
            })
    if not mentions:
        return []

    groups: list[dict] = []

    def add_group(scope: str, scope_name: str, topic_id: str, label: str,
                  per_value: dict[str, list[dict]]) -> None:
        if len(per_value) < 2:
            return
        groups.append({
            "topic": topic_id, "label": label,
            "scope": scope, "scope_name": scope_name,
            "values": [
                {"value": value,
                 "mentions": [
                     {"path": mm["path"], "line": mm["line"], "brief": mm["brief"]}
                     for mm in ms[:3]]}
                for value, ms in sorted(per_value.items())
            ],
        })

    # scope: file
    by_file: dict[tuple, dict[str, dict[str, list[dict]]]] = {}
    for m in mentions:
        by_file.setdefault(m["path"], {}).setdefault(m["topic"], {}) \
                .setdefault(m["value"], []).append(m)
    for path, topics in by_file.items():
        for topic_id, per_value in topics.items():
            label = next(t["label"] for t in TOPICS if t["id"] == topic_id)
            add_group("file", path, topic_id, label, per_value)

    # scope: agent (files that agent reads: global + all repos)
    by_agent: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for m in mentions:
        for agent in m["agents"]:
            by_agent.setdefault(agent, {}).setdefault(m["topic"], {}) \
                    .setdefault(m["value"], []).append(m)
    for agent, topics in by_agent.items():
        for topic_id, per_value in topics.items():
            label = next(t["label"] for t in TOPICS if t["id"] == topic_id)
            # skip when the whole conflict already lives in one file
            paths = {mm["path"] for ms in per_value.values() for mm in ms}
            if len(paths) < 2:
                continue
            add_group("agent", agent, topic_id, label, per_value)

    groups.sort(key=lambda g: len(g["values"]), reverse=True)
    return groups[:MAX_GROUPS]
