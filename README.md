# Agent Workbench

> 给你的编码 Agent 生态做 **体检** 和 **归档** —— 100% 本地运行的 Web 应用。

**Rules Doctor + Session Explorer for Claude Code / ZCode / Codex / Cursor / ...**

- 🔥 **规则体检（Rules Doctor）**：扫描本机所有 git 仓库与用户目录里的 `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*` 等 agent 规则文件，告诉你「这个仓库每个会话固定注入多少 tokens」，检测跨仓库复制的重复规则、半年没人动的陈旧规则，并按你的用量估算年度上下文成本。
- 🗄️ **会话档案馆（Session Explorer)**：把散落在 Claude Code / ZCode / Codex 各自数据目录里的会话记录统一解析，全文搜索（SQLite FTS5）、时间线浏览、一键导出 Markdown。

## 为什么

- 规则文件越写越长，每个会话都被注入，token 在悄悄烧钱；跨项目复制粘贴、互相矛盾、半年没人看。
- 重度用户同时用 2-3 个编码 agent，「上次让它改的那个 nginx 配置在哪次对话」无法回答。

## 隐私边界

- 100% 本地运行、无遥测、无上传，所有网络代码可审计
- 只读为主；索引库一键清除
- 单元测试只使用合成数据，真实个人数据绝不进入仓库

## 快速开始

后端（Python 3.11+）：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m app.server              # http://127.0.0.1:8800
```

前端开发模式（Node 18+，可选；生产模式由后端直接伺服 `web/dist`）：

```bash
cd web
npm install
npm run dev                                       # http://127.0.0.1:8801
```

## Token 估算口径

中英文混合双系数加权：中文字符数 ÷ 1.8 + 其他字符数 ÷ 3.5，展示为「约 X tokens」。
系数可在设置页调整。该口径用于决策参考（误差 < 15%），不追求与官方 tokenizer 完全一致。

## 功能

**规则体检（Rules Doctor）**
- 扫描指定根目录下所有 git 仓库 + 用户目录，定位 8 家 agent 的规则文件（AGENTS.md / CLAUDE.md / .cursor/rules / GEMINI.md / copilot-instructions …，模式表外置可扩展）
- 同一文件被多个 agent 认领时自动合并（如 dify 的 CLAUDE.md 软链到 AGENTS.md → 三家共用）
- 计量：行数 / 字符 / token 估算（中英双系数），按 agent / 按仓库汇总「每次会话固定注入多少」
- 重复检测：规则块 simhash 相似度分组（跨文件 / 跨仓库复制的规则一眼现形，附内容预览）
- 矛盾检测：包管理器 / Python 版本 / 回答语言 / 默认分支等同主题相反指令，按文件与「同会话共注入」两个范围输出（启发式，供人工确认）
- 陈旧检测：规则文件半年未动 + 仓库仍活跃 → 疑似过时
- 成本估算：单价、会话频率可配，"一年烧多少钱" 直出

**会话档案馆（Session Explorer）**
- 适配器解析 ZCode（`~/.zcode/cli/db/db.sqlite`）、Claude Code（`~/.claude/projects/**.jsonl`）、Codex（`~/.codex/sessions/**.jsonl`）的本地会话存储，归一化为统一模型
- SQLite FTS5 全文索引（增量，按源文件 mtime 去重）
- 统一时间线：跨 agent 按时间排列，按 agent / 项目 / 关键词过滤
- 全文搜索：会话级 + 消息级两级命中，关键词高亮
- 一键导出排版良好的 Markdown（含工具调用摘要，可选敏感信息打码：API key / GitHub token / AWS AKIA / bearer …）

**使用统计**
- 近 12 个月会话活跃度（按 agent 堆叠）、各 agent 会话/消息/平均长度、最活跃项目排行

## Roadmap

- [x] v0.1-W1 扫描层 + 规则体检 A1-A4（计量 / 重复 / 陈旧 / 成本估算）
- [x] v0.1-W2 会话适配器（ZCode、Claude Code）+ FTS5 全文搜索 + 时间线 + Markdown 导出
- [x] v0.2 Codex 适配器、矛盾检测（A5）、使用统计页、消息级搜索、导出打码
- [ ] v0.3 联调打磨 → 发布 v0.1
- [ ] v1.0 一键渐进式披露重构（A6）、增量索引打磨、更多 agent 适配

## License

MIT
