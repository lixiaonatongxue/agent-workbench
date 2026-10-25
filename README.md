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

## Roadmap

- [x] v0.1-W1 扫描层 + 规则体检 A1-A4（计量 / 重复 / 陈旧 / 成本估算）
- [ ] v0.1-W2 会话适配器（ZCode、Claude Code）+ FTS5 全文搜索 + 时间线
- [ ] v0.1-W3 Markdown 导出 + 联调打磨 → 发布 v0.1
- [ ] v0.2 矛盾检测、Codex 适配器、项目视图、使用统计
- [ ] v1.0 一键渐进式披露重构、敏感信息打码导出、增量索引

## License

MIT
