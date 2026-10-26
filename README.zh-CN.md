<div align="center">

# Agent Workbench

**给你的编码 Agent 做体检和归档的本地工作台**

**简体中文** | [English](README.md)

*100% 本地运行 · 无遥测 · 不联网*

</div>

---

你的 `AGENTS.md` 是不是每个会话都在悄悄烧 token？“上次让它改的那个 nginx 配置在哪次对话来着”——横跨 Claude Code、ZCode、Codex 就是找不到？

Agent Workbench 是一个本地 Web 应用，一个产品解决两件事：

- 🩺 **规则体检（Rules Doctor）**：扫描所有 git 仓库和用户目录里的 agent 规则文件，计量每个会话的固定注入成本，找出重复与矛盾的规则，估算年度开销。
- 🗄️ **会话档案馆（Session Explorer）**：把 Claude Code / ZCode / Codex 散落各处的本地会话记录统一解析成一座档案馆——时间线、全文搜索（SQLite FTS5）、Markdown 导出。

## 功能亮点

**规则体检**

- 定位 8 家 agent 的规则文件（`AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*` / `GEMINI.md` / `.github/copilot-instructions.md` …），模式表外置 JSON，加新工具零代码
- 多家 agent 共用的文件自动合并（如 `CLAUDE.md` 软链到 `AGENTS.md` 只计一次）
- 计量：行数 / 字符 / token 估算（中英双系数），按 agent、按仓库汇总——"这个仓库每个会话固定注入 ≈8.2k tokens"
- 重复检测：规范化后 64 位 simhash 聚组，跨文件、跨仓库复制的规则一眼现形（阈值经实测校准）
- 矛盾检测（启发式）：同主题相反指令——包管理器、Python 版本、回答语言、默认分支——覆盖"同一文件内"和"同会话共注入"两个范围
- 陈旧检测：规则文件半年没动而仓库仍然活跃 → 疑似过时
- 成本估算：单价与会话频率可配，"一年白烧 ¥437" 直出

**会话档案馆**

- 适配器解析 ZCode（`~/.zcode/cli/db/db.sqlite`）、Claude Code（`~/.claude/projects/**.jsonl`）、Codex（`~/.codex/sessions/**.jsonl`），归一化为统一模型——只读解析、未知字段容错
- FTS5 增量索引（按源文件 mtime），随时重跑都安全
- 跨 agent 统一时间线；按 agent / 项目 / 关键词过滤
- 两级搜索：会话级命中（带片段）+ 消息级命中，关键词高亮
- 一键导出排版良好的 Markdown（含工具调用摘要），可选敏感信息打码（API key、`ghp_…`、AKIA、bearer 头…）

**使用统计**

- 近 12 个月活跃度图表（按 agent 堆叠）、各 agent 会话/消息/平均长度、最活跃项目排行

## 隐私边界

- 全程本机运行：服务只绑 `127.0.0.1`，无遥测、无外呼，代码量小到可以亲自审计
- 索引库在 `~/.agent-workbench/`（可用 `AGENT_WORKBENCH_HOME` 覆盖），设置页或 `DELETE /api/data` 一键清除
- 单元测试只用合成数据，本仓库不含任何个人数据

## 快速开始

后端（Python 3.11+）：

```bash
git clone https://github.com/lixiaonatongxue/agent-workbench.git
cd agent-workbench
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m app.server              # http://127.0.0.1:8800
```

前端（Node 18+，可选——构建产物由后端直接伺服）：

```bash
cd web
npm install
npm run dev                                     # 开发模式 http://127.0.0.1:8801
```

打开 **http://127.0.0.1:8800**，把扫描根目录指向你的项目目录（如 `D:\projects`），点「开始体检」，再到「会话档案馆」索引历史记录。

## Token 估算口径

中英混合双系数：中文字符 ÷ 1.8 + 其他字符 ÷ 3.5（设置页可调）。这是决策级估算（±15%），不是计费级——每个报告都标注口径与假设。

## 项目结构

```
agent-workbench/
├── app/
│   ├── scan/          # 仓库发现 + 规则文件定位（rules-patterns.json）
│   ├── doctor/        # token 计量、simhash 重复、矛盾检测、报告
│   ├── sessions/      # 适配器（zcode/claude_code/codex）、FTS5 索引、
│   │                  # 搜索、Markdown 导出、统计
│   └── server.py      # FastAPI，127.0.0.1:8800
├── web/               # Vue3 + Vite SPA（体检 / 档案馆 / 统计 / 设置）
└── tests/             # 合成数据单元测试（pytest）
```

新增一个 agent = 新增一个适配器文件 + `rules-patterns.json` 几行。

## Roadmap

- [x] v0.1 — 扫描层 + 规则体检（计量 / 重复 / 陈旧 / 成本）
- [x] v0.2 — 会话适配器（ZCode、Claude Code）+ FTS5 搜索 + 时间线 + 导出
- [x] v0.3 — Codex 适配器、矛盾检测、使用统计、消息级搜索、导出打码
- [ ] v1.0 — 一键渐进式披露重构（臃肿 AGENTS.md 瘦身）、更多 agent 适配

## License

[MIT](LICENSE)
