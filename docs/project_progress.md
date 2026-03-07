# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**RPA/RPC remediation completed on worktree**
- 核心状态：API、任务系统、插件执行、账号池、Web 控制台、配置管理、适配器降级均可用；RPA/RPC 控制层已完成 selector 生命周期、共享 RPC bootstrap、native pointer ownership 与 task-control 边界收敛
- 最近重点：
  - 完成 RPA/RPC 控制层 remediation：selector 热路径清理、解释器退出 safety net、共享 RPC helper、`mytRpc` 原生边界 hardening、`TaskController` 业务反馈抽离
  - 新增 contract-focused regression coverage，固定 shared bootstrap 契约、cleanup 顺序与 `/health` 的 `rpc_enabled=false` 行为
  - 完成 `MYT_ENABLE_RPC=0` 启动烟测与全量 `pytest tests -q` 门禁

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
| Test files (`tests/test_*.py`) | 52 |
| Test functions (`def test_*`) | 184 |
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

1. 迁移闭环提交打包（commit/PR）：整理证据链、关联 `docs/HANDOFF.md` 与 `.sisyphus/evidence/*`，确保评审可一键复现门禁。
2. 将 Prometheus 抓取指标接入外部监控系统（抓取配置、告警规则与告警投递链路）。
   - 已完成仓内抓取/告警模板与参数化渲染工具；待完成外部 Prometheus/Alertmanager 实际部署与投递链路联调。
3. 线上化 stale-running 恢复策略：按环境调优 `MYT_TASK_STALE_RUNNING_SECONDS`，并联动外部监控确认恢复事件与重入行为符合预期。
4. 推进“拒绝未声明参数”落地：将 `docs/plugin_input_contract.md` 同步到调用方/部署手册，并完成各环境开关基线对齐与发布演练。
