# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**Legacy capability extraction closed（Tasks 1-12 + F1/F2/F3/F4）**
- 核心状态：API、任务系统、插件执行、Web 控制台、配置管理、适配器降级均可用，且旧项目核心能力已按插件化路径迁移收敛
- 最近重点：
  - 完成旧能力迁移闭环与证据链（F1/F2/F3/F4）
  - 补齐 selector 查询链 not-found 语义与设备 HostPort 异常防护
  - 增加任务调度→执行链路可观测事件（`task.dispatching` / `task.dispatch_result`）
  - 增加任务事件聚合指标接口：`GET /api/tasks/metrics`（状态分布、事件类型计数、终态结果计数）
  - 在任务指标接口补齐阈值告警判定能力：支持失败率/取消率阈值与最小样本门槛，输出 `rates` 与 `alerts` 决策块
  - 新增 Prometheus 指标抓取出口：`GET /api/tasks/metrics/prometheus`，输出任务状态/事件/终态/速率/告警指标（与 JSON 指标查询参数保持一致）
  - 增加外部监控接线资产：`config/monitoring/prometheus/task_metrics_scrape.example.yml`、`config/monitoring/prometheus/task_metrics_alerts.yml`，并新增渲染工具 `tools/render_task_metrics_monitoring.py`
  - 增加跨控制器重启的幂等去重回归测试：验证 pending 任务在持久化 DB 场景下仍可按 `idempotency_key` 去重
  - 继续补齐跨进程幂等语义回归：新增 running/retry 窗口去重测试，验证控制器重启后 duplicate submit 仍返回原任务
  - 补齐 stale-running 启动恢复：控制器启动前自动回收超时 running 任务并重新入队，新增 `MYT_TASK_STALE_RUNNING_SECONDS` 阈值配置与回归测试
  - 完成插件 manifest 输入完整性审计基线：新增 `tools/check_plugin_manifest_inputs.py`，并将其纳入 `tools/run_migration_gates.sh` 一键门禁
  - 补齐插件输入声明覆盖：修复 `blogger_scrape`、`follow_interaction`、`home_interaction`、`quote_interaction`、`dm_reply`、`x_auto_login` 的 payload 引用与 manifest 声明一致性
  - 在 runtime 严格拒绝未声明参数：`engine/runner.py` 对插件 payload 新增 unknown-key 拦截（保留 `task` 保留字段），并复用 `invalid_params` 失败语义
  - 为严格 unknown-key 校验增加灰度开关：新增环境变量 `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS`（默认开启，可按环境关闭）
  - 增加运行策略可观测性：`GET /health` 新增 `task_policy`（`strict_plugin_unknown_inputs` / `stale_running_seconds`）用于环境基线核验
  - 新增对外契约文档：`docs/plugin_input_contract.md`（校验规则、灰度开关基线与发布策略）
  - 补齐 Alertmanager 接线资产：新增模板 `config/monitoring/alertmanager/task_metrics_route.example.yml`，并扩展 `tools/render_task_metrics_monitoring.py` 可渲染 `task_metrics_alertmanager.yml`
  - 增加 stale-running 恢复告警规则：`task_metrics_alerts` 新增 `NewTaskStaleRunningRecovered`，用于提示已发生启动恢复行为
  - 修复执行上下文与测试稳定性问题：新增 `sitecustomize.py`、`pytest.ini(testpaths=tests)`，并修复 `check_plugin_manifest_inputs.py` 直跑导入路径；任务控制面相关 SQLite 测试切换为 `tmp_path` 隔离，消除共享 `config/data` 导致的偶发 `no such table` / `disk I/O error`
  - 稳定幂等去重回归测试隔离性：duplicate-submit 用例改为独立临时 DB，避免共享历史导致的分页/顺序耦合波动
  - 收紧插件分发安全边界：动作命名空间白名单 + manifest 输入参数必填/类型前置校验（失败码显式化）
  - 强化任务可靠性/幂等：支持 `idempotency_key` 防重复提交（原子化去重），补齐 body/header 冲突校验，并修复取消请求在异常路径下的状态一致性
  - 完成前端重构与组件化：拆分 `app.js` 为 ES Modules，引入 Toast 状态反馈与 Loading 交互，解决长连接日志渲染性能瓶颈
  - 增强设备与任务控制面：新增设备启停/扫描快捷操作，任务编辑器集成常用动作模板，降低 JSON 编写错误率

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
- 示例插件：`plugins/x_auto_login`（manifest + script）

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
- **效率工具**：任务提交页新增“动作模板”选择器，降低 JSON 手写成本；日志视窗增加行数限制与性能优化
- **功能完备**：多 Tab 控制台（监控、任务、账号、配置）、拟人化参数可视化编辑、实时状态流监听

### 2.5 质量保障

- 关键门禁脚本：`tools/check_no_legacy_imports.py`
- 测试覆盖：API、任务、配置迁移、插件、适配器、Web smoke、跨平台库选择等（`tests/`）

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Last generated (UTC): `2026-03-05T17:15:05.699533+00:00`
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 26 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 10 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 44 |
| Test files (`tests/test_*.py`) | 48 |
| Test functions (`def test_*`) | 151 |
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
