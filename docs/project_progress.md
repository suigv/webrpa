# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**Post-remediation follow-ups documented and aligned**
- 核心状态：API、任务系统、插件执行、账号池、Web 控制台、配置管理、适配器降级均可用；RPA/RPC 控制层 remediation 已完成，后续 watchpoint、监控 rollout、stale-running 调优与交接流程文档已同步落地
- 最近重点：
  - 完成 RPA/RPC 控制层 remediation：selector 热路径清理、解释器退出 safety net、共享 RPC helper、`mytRpc` 原生边界 hardening、`TaskController` 业务反馈抽离
  - 新增 contract-focused regression coverage，固定 shared bootstrap 契约、cleanup 顺序与 `/health` 的 `rpc_enabled=false` 行为
  - 完成 `MYT_ENABLE_RPC=0` 启动烟测与全量 `pytest tests -q` 门禁
  - 完成 post-remediation follow-up 文档收口：`sdk_actions`、shared JSON store、`x_mobile_login` compression watchpoint 均已有独立评估文档
  - 新增 `docs/monitoring_rollout.md` 与 `config/monitoring/rendered/single-node-example/`，明确 Prometheus/Alertmanager 外部接线基线
  - 新增 `docs/stale_running_recovery_tuning.md`，把 `MYT_TASK_STALE_RUNNING_SECONDS` 调优规则与 `/health`、`task.recovered_stale_running`、`NewTaskStaleRunningRecovered` 串成同一验证链
  - 原位于仓库根目录的中文原子化复盘文档已迁入 `docs/reference/`

## 2. 已实现功能清单

### 2.1 API 与控制面

- 健康检查、运行时执行、Web 控制台入口（`api/server.py`）
- 设备管理：列表/详情/状态/启停（`api/routes/devices.py`）
- 任务管理：创建/列表/详情/取消 + SSE 事件流（`api/routes/task_routes.py`）
- 配置管理：读取/更新系统配置与 humanized 配置（`api/routes/config.py`）
- 数据接口：账号/位置/网站读写与账号导入解析（`api/routes/data.py`）
- 日志 WebSocket 推送（`api/routes/websocket.py`）

### 2.2 引擎与插件

- Runner + Interpreter 工作流执行（`engine/runner.py`, `engine/interpreter.py`）
- 条件、跳转、等待、失败策略（`engine/conditions.py`, `engine/models/*`）
- 插件扫描与加载（`engine/plugin_loader.py`）
- 已内置插件：`x_mobile_login`、`mytos_device_setup`、`device_reboot`、`device_soft_reset`、`blogger_scrape`、`profile_clone` 及互动类插件

### 2.3 适配器与动作

- 浏览器动作：open/input/click/exists/wait/check_html/close（`engine/actions/browser_actions.py`）
- 账号凭据动作：`credentials.load`（`engine/actions/credential_actions.py`）
- UI/RPC 动作：点击、滑动、输入、按键、截图、节点查询等（`engine/actions/ui_actions.py`）
- SDK 动作绑定（`engine/actions/sdk_actions.py`）
- BrowserClient 拟人化与降级兜底（`hardware_adapters/browser_client.py`）
- MytRpc 跨平台动态库选择（`hardware_adapters/mytRpc.py`）

### 2.4 前端控制台

- **架构重构**：移除单体 `app.js`，采用 ES Modules 模块化设计 (`web/js/features/*`, `web/js/state/*`, `web/js/utils/*`)
- **交互增强**：引入全局 Toast 通知系统，替代原生 Alert/Console 日志；增加设备列表快捷控制（启动/停止/扫描）
- **账号与调度**：账号池支持导入预览、库存状态展示、ready 账号批量分派；云机大厅支持单机下发与批量选机下发
- **实际公开 UI**：当前公开页为云机大厅、账号池、配置；`web/js/features/tasks.js` 已实现任务管理逻辑，但 `web/index.html` 尚未暴露独立任务页入口，属于部分接线状态

### 2.5 质量保障

- 关键门禁脚本：`tools/check_no_legacy_imports.py`
- 测试覆盖：API、任务、配置迁移、插件、适配器、Web smoke、跨平台库选择等（`tests/`）

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 28 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 12 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 131 |
| Test files (`tests/test_*.py`) | 53 |
| Test functions (`def test_*`) | 197 |
<!-- AUTO_PROGRESS_SNAPSHOT:END -->

## 4. 维护方式（实时更新建议）

每次“有意义变更”后执行：

```bash
./.venv/bin/python tools/update_project_progress.py
```

推荐在以下时机执行：

1. 合并功能分支前
2. 每次完成测试与验证后
3. 发布前（用于生成最新项目快照）

## 5. 下一步建议（滚动）

1. 提交与 PR 打包：把已完成的 follow-up 文档/监控产物整理成可审阅的提交批次，并按 `docs/HANDOFF.md` 补齐证据链。
2. 外部 Prometheus / Alertmanager 实际部署联调：将 `docs/monitoring_rollout.md` 和 `config/monitoring/rendered/single-node-example/` 落到真实环境。
3. stale-running 线上阈值校准：按 `docs/stale_running_recovery_tuning.md` 的规则在目标环境确认常态值、演练值与告警响应。
4. 持续观察 watchpoint：定期复查 `docs/reference/sdk_actions_followup_assessment.md`、`docs/reference/shared_json_store_watchpoint.md`、`docs/reference/x_mobile_login_compression_watchpoint.md` 是否命中新触发条件。
