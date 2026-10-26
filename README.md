<div align="center">

# Agent Workbench

**Rules Doctor + Session Explorer for your coding agents**

[简体中文](README.zh-CN.md) | **English**

*100% local. No telemetry. No cloud.*

</div>

---

Is your `AGENTS.md` quietly burning tokens on every single session? Lost track of "which conversation was it where I asked about that nginx config?" — across Claude Code, ZCode and Codex?

Agent Workbench is a local web app that answers both:

- 🩺 **Rules Doctor** — scans every git repo (and your home dir) for agent rule files, measures what each one costs per session, finds duplicated and contradictory rules, estimates yearly spend.
- 🗄️ **Session Explorer** — parses the local session stores of Claude Code / ZCode / Codex into one searchable archive: unified timeline, full-text search (SQLite FTS5), Markdown export.

## Highlights

**Rules Doctor**

- Locates rule files for 8 agents (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*`, `GEMINI.md`, `.github/copilot-instructions.md`, …) — pattern table is a JSON file, easy to extend
- Files claimed by multiple agents are merged automatically (e.g. a `CLAUDE.md` symlink to `AGENTS.md` counts once)
- Metering: lines / chars / token estimate (dual-ratio for CJK+latin), aggregated per agent and per repo — "this repo injects ~8.2k tokens into every session"
- Duplicate detection: 64-bit simhash over normalized blocks groups near-duplicate rules across files and repos (threshold calibrated empirically)
- Contradiction detection (heuristic): same topic, opposing directives — package manager, Python version, answer language, default branch — flagged both within a file and across "rules that co-inject into one session"
- Staleness detection: rule file untouched for months while its repo is still active
- Cost estimate: configurable price & sessions/day → "you burn ~¥437/year on this"

**Session Explorer**

- Adapters for ZCode (`~/.zcode/cli/db/db.sqlite`), Claude Code (`~/.claude/projects/**.jsonl`) and Codex (`~/.codex/sessions/**.jsonl`), normalized to one model — read-only, tolerant of unknown fields
- Incremental FTS5 index (per-source mtime), safe to re-run any time
- Unified timeline across agents; filter by agent / project / keyword
- Two-level search: session hits with snippets + message-level hits, keyword highlighted
- One-click Markdown export with tool-call summaries, optional secret masking (API keys, `ghp_…`, AKIA, bearer headers, …)

**Usage Stats**

- 12-month activity chart (stacked by agent), sessions/messages/avg length per agent, top projects

## Privacy

- Everything runs on your machine. The server binds `127.0.0.1` only, there is no telemetry and no outbound call — the code is small enough to audit.
- Indexes live in `~/.agent-workbench/` (override with `AGENT_WORKBENCH_HOME`) and can be wiped from the Settings page or `DELETE /api/data`.
- Tests use synthetic data only; no personal data is committed to this repo.

## Quick start

Backend (Python 3.11+):

```bash
git clone https://github.com/lixiaonatongxue/agent-workbench.git
cd agent-workbench
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m app.server              # http://127.0.0.1:8800
```

Frontend (Node 18+, optional — the built SPA is served by the backend):

```bash
cd web
npm install
npm run dev                                     # dev server on http://127.0.0.1:8801
```

Then open **http://127.0.0.1:8800**, point the scanner at your projects root (e.g. `D:\projects`), hit **Scan**, and switch to the Sessions tab to index your history.

## Token estimation

Mixed CJK/latin dual-ratio: CJK chars ÷ 1.8 + other chars ÷ 3.5 (both configurable in Settings). It is a decision-grade estimate (±15%), not a billing-grade one — the exact ratios and assumptions are shown in every report.

## How it works

```
agent-workbench/
├── app/
│   ├── scan/          # repo discovery + rule-file location (rules-patterns.json)
│   ├── doctor/        # token metering, simhash duplicates, contradictions, report
│   ├── sessions/      # adapters (zcode/claude_code/codex), FTS5 indexer,
│   │                  # search, markdown export, stats
│   └── server.py      # FastAPI, 127.0.0.1:8800
├── web/               # Vue3 + Vite SPA (doctor / sessions / stats / settings)
└── tests/             # synthetic-data unit tests (pytest)
```

Adding an agent = one adapter file + a few lines in `rules-patterns.json`.

## Roadmap

- [x] v0.1 — scan layer + rules doctor (metering / duplicates / staleness / cost)
- [x] v0.2 — session adapters (ZCode, Claude Code) + FTS5 search + timeline + export
- [x] v0.3 — Codex adapter, contradiction detection, usage stats, message-level search, masked export
- [ ] v1.0 — one-click progressive-disclosure refactor for bloated AGENTS.md, more agents

## License

[MIT](LICENSE)
