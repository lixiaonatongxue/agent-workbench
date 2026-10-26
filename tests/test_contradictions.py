"""Contradiction detection tests."""

from app.doctor.contradictions import detect_contradictions


def block(text, path, agents, repo=None, line=1):
    return {"text": text, "path": path, "repo": repo, "agents": agents,
            "start_line": line, "end_line": line}


def test_package_manager_conflict_within_agent():
    blocks = [
        block("统一使用 pnpm 安装依赖，不要混用其他工具。", "D:/a/CLAUDE.md", '["claude-code"]', repo="D:/a"),
        block("Always use npm install for this repository.", "D:/a/AGENTS.md", '["claude-code"]', repo="D:/a"),
    ]
    groups = detect_contradictions(blocks)
    assert any(g["topic"] == "package-manager" and
               {v["value"] for v in g["values"]} == {"pnpm", "npm"}
               for g in groups)


def test_global_vs_repo_conflict():
    blocks = [
        block("回答使用中文，保持简洁。", "C:/Users/x/.claude/CLAUDE.md", '["claude-code"]', repo=None),
        block("Always respond in English with technical terms.", "D:/a/CLAUDE.md", '["claude-code"]', repo="D:/a"),
    ]
    groups = detect_contradictions(blocks)
    assert any(g["topic"] == "answer-language" and g["scope"] == "agent" for g in groups)


def test_no_conflict_for_single_value():
    blocks = [
        block("统一使用 pnpm 安装依赖。", "D:/a/CLAUDE.md", '["claude-code"]'),
        block("Run tests with pnpm before commit.", "D:/a/AGENTS.md", '["codex"]'),
    ]
    assert detect_contradictions(blocks) == []


def test_prose_mentions_ignored_without_directive():
    blocks = [
        block("The npm registry hosts pnpm metadata for browsing.", "D:/a/CLAUDE.md", '["claude-code"]'),
    ]
    assert detect_contradictions(blocks) == []


def test_python_version_conflict():
    blocks = [
        block("必须使用 Python 3.11 运行本项目。", "D:/a/AGENTS.md", '["codex"]'),
        block("使用 Python 3.8 以兼容旧环境。", "D:/b/AGENTS.md", '["codex"]'),
    ]
    groups = detect_contradictions(blocks)
    assert any(g["topic"] == "python-version" and
               {v["value"] for v in g["values"]} == {"3.11", "3.8"}
               for g in groups)


def test_different_agents_do_not_conflict():
    blocks = [
        block("统一使用 pnpm。", "D:/a/CLAUDE.md", '["claude-code"]'),
        block("Always use yarn.", "D:/a/.windsurfrules", '["windsurf"]'),
    ]
    assert detect_contradictions(blocks) == []
