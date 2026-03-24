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
- planner 返回当前已解析的 `intent`、`branch`、`execution`、`recommended_workflows`，用于前端展示任务意图、账号阻塞项和候选固定工作流。
- `POST /api/ai_dialog/annotations` 用于记录用户接管输入时声明的输入类型。
- `GET/POST /api/ai_dialog/drafts/{draft_id}/save_*` 用于列出并应用一次执行后的可选保存项，而不是强制落库全部运行时数据。
- `GET/PUT /api/ai_dialog/apps/{app_id}/branch_profiles` 用于读取和维护 app 级分支资料。
- `GET/POST /api/ai_dialog/apps/{app_id}/config_candidates*` 用于审核蒸馏候选后再写入共享 app 配置。

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
