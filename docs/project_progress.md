# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**UIStateService unified rollout completed and documented**
- 核心状态：API、任务系统、插件执行、账号池、Web 控制台、配置管理、原生/RPC 与浏览器观察链路均可用；`UIStateService` 已作为统一只读状态契约落地，并完成插件迁移与验证收口
- 最近重点：
  - 完成 `UIStateService` 统一契约，收敛原生端与浏览器端的状态识别结果形状，同时保留各自证据细节
  - 完成 native/mobile 与 browser/web 双适配器接线，保持旧行为兼容，不把 recovery 或 fallback 逻辑塞进 service
  - 完成 thin action wrapper 与动作注册接线，保留 legacy action 兼容面，工作流侧可经统一状态边界消费能力
  - 完成 interpreter / condition 集成，沿用现有 YAML 模型与 cleanup 语义，不引入新的 DSL
  - 完成 `x_mobile_login`、`dm_reply`、`nurture` 定向迁移，并对 `profile_clone` 做了目标明确的状态观察收口
  - 完成 rollout 验证波次，覆盖 service、native adapter、browser adapter、state actions、插件运行时、全量 `pytest tests -q`、`check_no_legacy_imports.py`、`MYT_ENABLE_RPC=0` 启动与 `/health`
  - 既有 RPA/RPC remediation、`sdk_actions` facade + helper 分层、`/api/runtime/execute` debug/internal-only 契约、监控接线文档与 stale-running 调优文档仍保持有效

## 2. 已实现功能清单

### 2.1 API 与控制面

- 健康检查、debug/internal-only 运行时直跑入口、Web 控制台入口（`api/server.py`）
- 设备管理：列表/详情/状态/启停（`api/routes/devices.py`）
- 任务管理：创建/列表/详情/取消 + SSE 事件流（`api/routes/task_routes.py`）
- 配置管理：读取/更新系统配置与 humanized 配置（`api/routes/config.py`）
- 数据接口：账号/位置/网站读写与账号导入解析（`api/routes/data.py`）
- 日志 WebSocket 推送（`api/routes/websocket.py`）

### 2.2 引擎与插件

- Runner + Interpreter 工作流执行（`engine/runner.py`, `engine/interpreter.py`）
- 条件、跳转、等待、失败策略，且已接入 `UIStateService` 支持统一状态观察与等待（`engine/conditions.py`, `engine/models/*`）
- 插件扫描与加载（`engine/plugin_loader.py`）
- 已内置插件：`x_mobile_login`、`mytos_device_setup`、`device_reboot`、`device_soft_reset`、`blogger_scrape`、`profile_clone` 及互动类插件，其中 `x_mobile_login`、`dm_reply`、`nurture` 已完成 UIStateService 定向迁移

### 2.3 适配器与动作

- 浏览器动作：open/input/click/exists/wait/check_html/close（`engine/actions/browser_actions.py`）
- 账号凭据动作：`credentials.load`（`engine/actions/credential_actions.py`）
- UI/RPC 动作：点击、滑动、输入、按键、截图、节点查询等（`engine/actions/ui_actions.py`）
- `UIStateService` 统一状态契约、native/browser adapters、thin wrappers 与兼容动作入口已落地（相关实现位于 `engine/actions/` 与 `engine/conditions.py`）
- SDK 动作绑定 facade + `sdk_*_support.py` helper 分层（`engine/actions/sdk_actions.py`）
- BrowserClient 拟人化与降级兜底（`hardware_adapters/browser_client.py`）
- MytRpc 跨平台动态库选择（`hardware_adapters/mytRpc.py`）

### 2.4 前端控制台

- **架构重构**：移除单体 `app.js`，采用 ES Modules 模块化设计 (`web/js/features/*`, `web/js/state/*`, `web/js/utils/*`)
- **交互增强**：引入全局 Toast 通知系统，替代原生 Alert/Console 日志；增加设备列表快捷控制（启动/停止/扫描）
- **账号与调度**：账号池支持导入预览、库存状态展示、ready 账号批量分派；云机大厅支持单机下发与批量选机下发
- **实际公开 UI**：当前公开页为云机大厅、账号池、配置；`web/js/features/tasks.js` 已实现任务管理逻辑，但 `web/index.html` 尚未暴露独立任务页入口，属于部分接线状态

### 2.5 质量保障

- 关键门禁脚本：`tools/check_no_legacy_imports.py`
- 测试覆盖：API、任务、配置迁移、插件、适配器、Web smoke、跨平台库选择，以及 `/api/runtime/execute` 非托管任务语义回归（`tests/`）

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 28 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 12 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 131 |
| Test files (`tests/test_*.py`) | 54 |
| Test functions (`def test_*`) | 207 |
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

1. 保持 `UIStateService` rollout 后观察，重点看新增插件是否继续复用统一状态边界，而不是回退到重复的插件内状态梯子。
2. 将 `docs/monitoring_rollout.md` 和 `config/monitoring/rendered/single-node-example/` 落到真实环境，完成外部 Prometheus / Alertmanager 联调。
3. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`，补齐常态值与演练值证据。
4. 持续复查 `docs/reference/sdk_actions_followup_assessment.md`、`docs/reference/shared_json_store_watchpoint.md`、`docs/reference/x_mobile_login_compression_watchpoint.md` 等 watchpoint 是否触发新的拆分或收口条件。
