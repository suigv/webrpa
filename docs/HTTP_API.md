---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
stale_after_days: 14
verification_method:
  - route audit via api/server.py and api/routes/*
  - startup and /docs smoke through uvicorn
---

# HTTP API

本文件只描述当前仓库里由 `api.server:app` 暴露的 HTTP / WebSocket 入口。  
完整请求模型和响应模型以运行中的 OpenAPI `/docs` 为准。

## 基础入口

- `GET /`：基础欢迎响应。
- `GET /web`：控制台入口；若配置 `MYT_FRONTEND_URL` 则重定向，否则返回前端部署提示。
- `GET /health`：健康检查。
- `POST /api/runtime/execute`：同步 runtime 调试入口。
- `GET /api/diagnostics/browser`：浏览器运行时诊断。
- `WS /ws/logs`：日志流。

## 配置

- `GET /api/config/`
- `PUT /api/config/`

## 数据与账号

- `GET /api/data/accounts`
- `POST /api/data/accounts/import`
- `POST /api/data/accounts/update`
- `POST /api/data/accounts/status`
- `POST /api/data/accounts/pop`
- `GET /api/data/accounts/parsed`
- `POST /api/data/accounts/reset`
- `GET /api/data/location`
- `PUT /api/data/location`
- `GET /api/data/website`
- `PUT /api/data/website`

### 账号导入与分配边界

- `POST /api/data/accounts/import` 当前支持同时提交 `app_id`、`app_display_name`、`package_name`、`default_branch`、`role_tags`。
- 导入时如果 app 尚不存在，后端会按当前输入补齐最小 app 配置，不要求先改代码。
- `POST /api/data/accounts/pop` 支持 `branch_id` 和 `accepted_role_tags`，其中标签匹配规则是任一命中即可。
- `GET /api/data/accounts/parsed` 支持按 `app_id`、`branch_id`、`role_tag` 过滤当前账号池视图。

## 设备与云机

- `GET /api/devices/`
- `POST /api/devices/discover`
- `GET /api/devices/{device_id}`
- `GET /api/devices/{device_id}/status`
- `POST /api/devices/{device_id}/start`
- `POST /api/devices/{device_id}/stop`
- `GET /api/devices/{device_id}/{cloud_id}/screenshot`
- `POST /api/devices/{device_id}/{cloud_id}/tap`
- `POST /api/devices/{device_id}/{cloud_id}/swipe`
- `POST /api/devices/{device_id}/{cloud_id}/key`
- `POST /api/devices/{device_id}/{cloud_id}/text`

## 任务系统

- `POST /api/tasks/`
- `GET /api/tasks/`
- `GET /api/tasks/active`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/events`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/pause`
- `POST /api/tasks/{task_id}/resume`
- `POST /api/tasks/{task_id}/takeover`
- `POST /api/tasks/device/{device_id}/stop`
- `POST /api/tasks/cleanup_failed`
- `DELETE /api/tasks/cleanup_failed`
- `POST /api/tasks/cleanup_runtime`
- `DELETE /api/tasks/cleanup_runtime`
- `DELETE /api/tasks/`
- `GET /api/tasks/catalog`
- `GET /api/tasks/catalog/apps`
- `GET /api/tasks/prompt_templates`
- `GET /api/tasks/metrics`
- `GET /api/tasks/metrics/prometheus`
- `GET /api/tasks/metrics/plugins`
- `GET /api/tasks/drafts`
- `GET /api/tasks/drafts/{draft_id}`
- `GET /api/tasks/drafts/{draft_id}/snapshot`
- `POST /api/tasks/drafts/{draft_id}/continue`
- `POST /api/tasks/drafts/{draft_id}/distill`
- `POST /api/tasks/plugins/{plugin_name}/distill`

### 任务提交边界

当前正式任务提交主路径是：

```json
{
  "task": "device_reboot",
  "payload": {},
  "targets": [{"device_id": 1, "cloud_id": 1}]
}
```

约束：

- `task`、`payload`、`targets` 是主契约。
- `targets` 是目标声明通道。
- `payload` 只承载插件 `manifest.inputs` 中声明的业务字段。
- 运行时上下文不应混入 `payload`。

### App Catalog

- `GET /api/tasks/catalog/apps` 返回当前共享 app 身份目录。
- 每个 app 条目当前包含 `id`、`name/display_name`、`aliases`、`package_name`、`package_names`。

## AI 对话

- `POST /api/ai_dialog/planner`
- `GET /api/ai_dialog/history`
- `POST /api/ai_dialog/annotations`
- `GET /api/ai_dialog/tasks/{task_id}/annotations`
- `GET /api/ai_dialog/drafts/{draft_id}/save_candidates`
- `POST /api/ai_dialog/drafts/{draft_id}/save_choices`
- `GET /api/ai_dialog/apps/{app_id}/branch_profiles`
- `PUT /api/ai_dialog/apps/{app_id}/branch_profiles`
- `GET /api/ai_dialog/apps/{app_id}/config_candidates`
- `POST /api/ai_dialog/apps/{app_id}/config_candidates/review`

### AI 对话边界

- `POST /api/ai_dialog/planner` 当前支持 `app_id`、`app_display_name`、`package_name`，用于已存在 app 选择和新 app 探索式启动。
- planner 返回当前已解析的 `intent`、`branch`、`execution`、`recommended_workflows`，以及新的 `guidance`、`control_flow`，用于前端展示任务意图、账号阻塞项、提示词补充建议和已识别的控制流线索。
- planner 额外返回 `memory`，用于描述近期同类 AI 运行资产的最近终态、蒸馏判定、可复用状态/动作、`reuse_priority`、`recommended_action` 和提示语。
- 当前 `intent` 与 `memory` 的业务语义优先来自插件 manifest 中声明的 `ai_hints`，而不是框架层写死的任务族表。
- planner 会从 `goal + advanced_prompt` 中抽取条件判断、等待、超时、成功标准等控制流提示，并写回 `resolved_payload._planner_control_flow_*`，供 `agent_executor` 运行时 planner artifact 和后续蒸馏链路复用。
- `POST /api/ai_dialog/annotations` 用于记录用户接管输入时声明的输入类型。
- `GET/POST /api/ai_dialog/drafts/{draft_id}/save_*` 用于列出并应用一次执行后的可选保存项，而不是强制落库全部运行时数据。
- `GET /api/ai_dialog/history` 返回的 AI 草稿历史当前会分别给出 `can_replay`、`can_edit`、`can_save`；failed/cancelled 但仍保留 `draft_memory` / `useful_trace` 的任务仍可进入“编辑后执行 / 保存可复用项”链路。
- `GET /api/ai_dialog/drafts/{draft_id}/save_candidates` 当前会优先读取最近 completed task 的 AI 输入标注；若没有 completed task，则回退到最近 terminal task，避免有价值但未完成的 AI run 无法沉淀数据。
- planner 的 `execution` 当前也会同步返回 `reuse_priority`、`reuse_action`、`distill_eligible`，供前端直接展示再次下发时的复用优先级与下一步出口。
- `GET/PUT /api/ai_dialog/apps/{app_id}/branch_profiles` 用于读取和维护 app 级分支资料。
- `GET/POST /api/ai_dialog/apps/{app_id}/config_candidates*` 用于审核蒸馏候选后再写入共享 app 配置。

### Workflow Draft / Run Asset

- `GET /api/tasks/drafts*` 返回的 workflow draft 摘要当前区分两类完成结果：
  - `success_count` 只统计通过蒸馏资格判定的 accepted 样本。
  - `latest_run_asset` 描述最近一次终态运行的 `business_outcome`、`distill_decision`、`distill_reason` 与 `retained_value`。
- workflow draft 摘要当前额外返回：
  - `latest_run_asset.value_profile`：本次运行的统一资格/价值判定结果。
  - `distill_assessment`：当前草稿是否可蒸馏、最近一次资格结论、当前阶段。
  - `exit`：当前统一出口动作，例如 `apply_suggestion`、`continue_validation`、`distill`、`review_distilled`。
- 当一次 AI 任务已经完成但不满足蒸馏资格时，系统仍会保留 replayable / useful trace 级别的 run asset，供后续 planner 与继续执行复用。
- failed/cancelled 终态只要保留了 `retained_value`，草稿也会生成 continuation snapshot，不再要求必须先有 completed snapshot 才能继续编辑。
- app 级 `agent_executor` 任务当前会使用更高的默认步数预算，并在最近步骤持续产生真实状态进展时按轮次延长预算；若连续出现无效运行时契约动作，则会提前以 circuit breaker 结束。

## 动作与技能目录

- `GET /api/engine/schema`
- `GET /api/engine/skills`

`/api/engine/schema` 支持 `?tag=...` 过滤；`/api/engine/skills` 只返回 `tags=["skill"]` 的动作。

## 库存、选择器、生成器

- `POST /api/inventory/phone-models/{source}/refresh`
- `GET /api/inventory/phone-models/{source}`
- `POST /api/selectors/phone-model`
- `POST /api/generators/fingerprint`
- `POST /api/generators/contact`
- `POST /api/generators/env-bundle`

## 鉴权

当前仓库支持可选 JWT 模式：

- `MYT_AUTH_MODE=jwt`
- `Authorization: Bearer <token>` 用于 HTTP
- `Sec-WebSocket-Protocol: bearer.<token>` 用于浏览器 WebSocket
