# AI 项目指南（webrpa）

本文档只保留当前 AI 相关的最小事实，详细契约请读 `docs/` 顶层文档。

## 先读哪些文档

1. `docs/README.md`
2. `docs/STATUS.md`
3. `docs/HTTP_API.md`
4. `docs/PLUGIN_CONTRACT.md`
5. `docs/CONFIGURATION.md`

## 当前 AI 事实

- `agent_executor` 通过 `/api/tasks` 托管执行。
- 当前仓库存在 AI 对话入口：`/api/ai_dialog/planner` 与 `/api/ai_dialog/history`。
- 当前动作目录存在 AI-facing skill 发现接口：`/api/engine/skills`。
- AI 相关执行和蒸馏仍服务于插件化工作流，而不是替代插件边界。

## 写文档时的限制

- 不要把未来规划写成当前能力。
- 不要引用已经移除的 `docs/governance/`、`docs/strategy/`、`docs/reference/`、`docs/ops/`。
- 任何 AI 能力说明都应能回到当前代码路径或当前验证命令上。
