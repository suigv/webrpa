# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**Web Console Productization & Navigation Engine Hardening**
- 核心状态：API、任务系统、插件执行、账号池全面可用；Web 控制台完成产品化改造，支持全生命周期任务与账号管理；导航引擎引入“自愈”与“锚点”机制，具备极强的环境噪声抗性；实时日志流打通 Action 级反馈链路
- 最近重点：
  - **Web 控制台产品化 (2026-03-10)**：
    - 实时显示 `MYT_ENABLE_RPC` 运行状态（开启/关闭/未知）。
    - 资源仓库支持账号**全字段编辑**（含 Token、邮箱等）及**状态一键重置**接口。
    - 任务流水支持**全局停止**、清空历史及单任务精准控制；前端渲染优先使用中文 `display_name`。
    - 设备集群支持**单机/全量初始化**，并植入“高危操作风险说明”、“二次确认”与“手动输入验证”逻辑。
  - **反馈与监控体系升级**：
    - 全系统反馈语重构，由生硬的技术术语转向业务化的产品描述。
    - 实时执行日志流实现**跨线程 WebSocket 异步广播**，Action 执行结果（✅成功/❌失败）即时可视化。
  - **导航引擎鲁棒性强化 (ISA 兼容)**：
    - 引入 **“UI 清道夫” (Global Interstitial Handler)**，底层自动识别并静默排除同步联系人、升级引导等干扰项。
    - 引入 **“语义锚点判定” (Anchor-Based Navigation)**，支持在 ID 缺失或变更环境下通过底部导航选中态进行多语言定位。
    - 建立自愈轨迹记录，确保引擎层介入的自救动作在日志中透明，为后续视觉模型任务蒸馏保留高质量的噪声处理轨迹。
  - **参数自动剥离与注入**：
    - UI 自动剥离 `device_ip`、`package` 等冗余参数，下发任务时自动从选中的云机节点实时注入，实现业务参数与环境参数解耦。
  - GPT executor MVP 已接到现有 `/api/tasks` 托管链路，任务名为 `gpt_executor`，继续走既有创建、取消、重试、SSE 事件与终态规则
  - 当前 MVP 观察策略是 structured-state-first，优先消费 `ui.match_state` 的结构化状态；只有主观察不足时才记录并使用 XML tree、截图或 browser HTML 等 fallback 模态
  - GPT 执行环的 circuit breaker 是 MVP 硬要求，不是可选优化：必须限制 step budget，并在结构化状态连续停滞时显式中止
  - 原始模型轨迹已单独落到 `config/data/traces/` append-only JSONL，和任务 lifecycle events 分开，供后续 Golden Run 蒸馏读取
  - Golden Run MVP 蒸馏保持离线工具路径，当前从一条成功的 `gpt_executor` JSONL 轨迹生成可审阅的 `manifest.yaml` + `script.yaml` 草稿；实际使用链路是先通过 `/api/tasks` 跑出成功 trace，再用 `tools/distill_golden_run.py --task-id --run-id --target-label --attempt-number --output-dir` 生成草稿，且不会自动写入 `plugins/`
  - 当前 usability gate 已定死为 parse + replay smoke。蒸馏草稿只有在现有 parser、manifest input 检查、PluginLoader 和 Runner replay smoke 都通过后才算 usable
  - SoM overlays、shadow healing、multi-run consensus extraction 和更广的恢复系统仍明确留在 v1 之外
  - 保留 `UIStateService` rollout 基线，继续沿用统一状态结果形状与 thin action wrapper，不把 recovery 或 fallback 逻辑塞进 service
  - 收紧 `wait_until` 轮询语义，并补齐 success-before-timeout、timeout 文案、`on_timeout goto`、`on_fail` fallback、取消返回与动态重轮询回归覆盖
  - 收口 `UIStateService` 共享语义：结果构造、timing 与 browser polling 改走共享 helper，native binding 注册拆到独立模块，减少 browser/native 的平行演化面
  - 落地 `ExecutionContext.session.defaults` 最小任务级接缝，明确覆盖顺序为显式 action 参数优先，其次 session defaults，最后才回退到原始 payload
  - 保守扩展 UI-state 观察覆盖，新增 `timeline_candidates`、`follow_targets` 绑定与集合首项别名，不改顶层观察结果形状
  - 补齐有界页面级 composite helper，`ui.navigate_to` 与 `ui.fill_form` 现在用于导航和表单驱动，不把它们写成工作流级恢复系统
  - 保留此前 `home` / `x_mobile_login` 工作流迁移基线，其中 `x_mobile_login` 已验证可通过 manifest 输入默认值与 `_target` 派生的 session defaults 收口重复 runtime 接线；当前只明确覆盖 `device_ip` 去重和相关步骤不再显式重复声明 `package`，同时不改变状态与消息契约
  - 最新验证波次已覆盖定向登录工作流测试、运行时接线 smoke，以及既有 `pytest tests -q`、`check_no_legacy_imports.py`、`MYT_ENABLE_RPC=0` 启动与 `/health` 验证结论
  - 既有 RPA/RPC remediation、`sdk_actions` facade + helper 分层、`/api/runtime/execute` debug/internal-only 契约、监控接线文档与 stale-running 调优文档仍保持有效

## 2. 已实现功能清单

### 2.1 API 与控制面

- 健康检查、debug/internal-only 运行时直跑入口、`/web` 静态控制台入口（smoke-backed，`api/server.py`）
- 设备管理：列表/详情/状态/启停（`api/routes/devices.py`）
- 任务管理：创建/列表/详情/取消 + SSE 事件流（`api/routes/task_routes.py`）
- 任务响应映射边界：`api/mappers/task_mapper.py` 统一承接 `TaskRecord` -> `TaskResponse` / `TaskDetailResponse` 转换，路由层保持 thin HTTP coordination
- 配置管理：读取/更新系统配置与 humanized 配置（`api/routes/config.py`）
- 数据接口：账号/位置/网站读写与账号导入解析（`api/routes/data.py`）
- 日志 WebSocket 路由（`/ws/logs`，由 `tests/test_websocket_logs_route.py` 覆盖 ping/filter 广播路径；`api/routes/websocket.py`）

### 2.2 引擎与插件

- Runner + Interpreter 工作流执行（`engine/runner.py`, `engine/interpreter.py`）
- 托管 `gpt_executor` 运行时（`engine/gpt_executor.py`）已复用现有 task/runtime seam，按 structured-state-first 规划动作，并在需要时记录 fallback 模态
- 条件、跳转、等待、失败策略，且已接入 `UIStateService` 支持统一状态观察与等待；`wait_until` 已补齐动态重轮询、超时分支、失败回退与取消语义回归（`engine/conditions.py`, `engine/models/*`）
- 插件扫描与加载（`engine/plugin_loader.py`）
- 离线 Golden Run 蒸馏（`core/golden_run_distillation.py`, `tools/distill_golden_run.py`）会基于成功 JSONL 轨迹产出 reviewable YAML draft，并对 payload literals 做参数化映射
- 已内置插件：`x_mobile_login`、`mytos_device_setup`、`device_reboot`、`device_soft_reset`、`blogger_scrape`、`profile_clone` 及互动类插件；此前 `home` / `x_mobile_login` 迁移基线仍有效，其中 `x_mobile_login` 已完成 session-defaults 接线压缩验证

### 2.3 适配器与动作

- 浏览器动作：open/input/click/exists/wait/check_html/close（`engine/actions/browser_actions.py`）
- 账号凭据动作：`credentials.load`（`engine/actions/credential_actions.py`）
- UI/RPC 动作：点击、滑动、输入、按键、截图、节点查询等（`engine/actions/ui_actions.py`）
- `UIStateService` 统一状态契约、native/browser adapters、thin wrappers 与兼容动作入口已落地，且新增 `timeline_candidates` / `follow_targets` 观察绑定与集合首项别名（相关实现位于 `engine/actions/` 与 `engine/conditions.py`）
- `UIStateService` 的共享结果构造、timing 与 browser polling helper 已落地，native binding 注册已拆到独立模块，并补充了 helper/adapter 语义回归测试
- `ExecutionContext.session.defaults` 已作为最小任务级默认值接缝落地，RPC / package / credentials 消费侧可按显式参数 → session defaults → payload 的顺序取值
- 有界 composite helper `ui.navigate_to` 与 `ui.fill_form` 已可用于页面导航和表单驱动，范围仍限定在页面级封装
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
- GPT executor MVP 文档门禁已覆盖 `tools/check_doc_claims.py` 与 `tests/test_doc_claim_guard.py`；distilled draft 的可用性回归由 `tests/test_gpt_distillation.py` 里的 parse + replay smoke gate 约束

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 28 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 12 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 131 |
| Test files (`tests/test_*.py`) | 61 |
| Test functions (`def test_*`) | 282 |
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

1. 保持 `UIStateService` rollout 后观察，重点看新增插件以及既有 `home` / `x_mobile_login` 路线是否继续复用统一状态边界和 session defaults，而不是回退到重复的插件内状态梯子。
2. 将工作流级保守恢复明确维持在 **deferred**，继续观察是否真的在多个工作流里反复出现同一有界有序恢复链，再决定是否上提为共享策略。
3. 将 `docs/monitoring_rollout.md` 和 `config/monitoring/rendered/single-node-example/` 落到真实环境，完成外部 Prometheus / Alertmanager 联调。
4. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`，补齐常态值与演练值证据。
5. 持续复查 `docs/reference/sdk_actions_followup_assessment.md`、`docs/reference/shared_json_store_watchpoint.md`、`docs/reference/x_mobile_login_compression_watchpoint.md` 等 watchpoint 是否触发新的拆分或收口条件。
6. GPT executor 后续增强保持为 deferred，先不要把 SoM overlays、shadow healing、multi-run consensus extraction 或更广恢复系统写成 v1 已完成项。
