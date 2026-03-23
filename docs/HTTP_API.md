# HTTP API（WebRPA 自身服务）

本文件只描述 **webrpa 服务本身**暴露的 HTTP / WebSocket API（FastAPI）。设备 SDK（8000）、MYTOS Android API（api_port）与 RPA SDK（rpa_port）请分别参考：
- `docs/reference/MYT_SDK_API.md`
- `docs/reference/MYTOS_API.md`
- `docs/reference/ANDROID_RPA_SDK.md`

> 交互式 OpenAPI：启动服务后访问 `/docs`。

---

## 1) 基础与控制台

- `GET /health`：健康检查，返回运行策略快照与已加载插件列表。
- `GET /web`：控制台入口（后端保留“入口路由”而不直接托管前端：若设置 `MYT_FRONTEND_URL` 则 307 重定向，否则返回 501 提示）。
- `WS /ws/logs`：实时日志流（WebSocket）。

### 鉴权（可选：JWT Bearer）

- 默认不启用鉴权；当设置 `MYT_AUTH_MODE=jwt` 时，后端会对 `/api/*` 强制要求 `Authorization: Bearer <token>`。
- SSE（`GET /api/tasks/{task_id}/events`）同样要求 `Authorization`；浏览器原生 `EventSource` 无法自定义请求头，前端已使用 `fetch()` 流式解析以携带 header。
- WebSocket（`/ws/logs`）在浏览器侧无法稳定携带 `Authorization` 头；推荐使用 `Sec-WebSocket-Protocol: bearer.<token>` 传递 token。

---

## 2) Runtime 直跑（debug/internal-only）

- `POST /api/runtime/execute`：同步执行 runtime payload，不进入 `/api/tasks` 托管链路（无重试/取消/SSE/指标）。

---

## 3) 配置读写（在线修改 `config/system.yaml` 相关项）

- `GET /api/config/`：读取当前运行配置视图（用于前端展示）。
- `PUT /api/config/`：更新配置（用于在线调参/修改 host_ip、device_ips、Location/Website 等）。
- `default_ai` 已从公开 `/api/config` 契约和默认仓库配置中移除；调用方不应再依赖该字段。

---

## 4) 数据与账号池（SQLite）

账号池与业务文本使用 `config/data/` 下的 SQLite 数据库/文件存储（详见 `docs/CONFIGURATION.md`）。

- `GET /api/data/accounts`：获取账号列表。
- `POST /api/data/accounts/import`：导入账号数据（可能触发从旧格式迁移）。`app_id` 现在是账号表一级字段，导入时需显式给出所属 app。
- `GET /api/data/accounts/parsed`：获取解析后的账号视图，可用 `?app_id=x` 直接按数据库列过滤。
- `POST /api/data/accounts/pop`：原子抽号（取一个可用账号）。传 `{"app_id":"x"}` 时会优先抽取该 app 账号，不存在时再回退到 `default` 池。
- `POST /api/data/accounts/reset`：重置账号池状态（运维/回归用途）。
- `POST /api/data/accounts/status`：更新账号状态（如 ready/blocked 等）。
- `POST /api/data/accounts/update`：更新账号字段。

- `GET /api/data/location` / `PUT /api/data/location`：读取/更新 Location 文本。
- `GET /api/data/website` / `PUT /api/data/website`：读取/更新 Website 文本。

---

## 5) 库存 / 选择器 / 生成器（设备初始化辅助）

这组接口用于承接“先获取再选择”与“本地随机生成”的两类能力，统一服务于插件编排、前端预热和设备初始化。

### 5.1 Phone Model Inventory

- `POST /api/inventory/phone-models/online/refresh?device_ip=...&sdk_port=8000`
  - 直连 SDK 刷新在线机型库存并写入 `config/data/.../inventory/` 缓存。
- `GET /api/inventory/phone-models/online?device_ip=...&sdk_port=8000&refresh=false`
  - 读取在线机型库存；若本地无缓存则自动回源刷新。
- `POST /api/inventory/phone-models/local/refresh?device_ip=...&sdk_port=8000`
  - 刷新本地机型库存缓存。
- `GET /api/inventory/phone-models/local?device_ip=...&sdk_port=8000&refresh=false`
  - 读取本地机型库存。

库存响应统一包含：
- `source`：`online` 或 `local`
- `device_ip` / `sdk_port`
- `count`
- `items`
- `refreshed_at`
- `from_cache`

### 5.2 Phone Model Selector

- `POST /api/selectors/phone-model`
  - 按 `source + filters + seed` 确定性选择一个机型。
  - 支持两种输入模式：
    - 传 `device_ip` / `sdk_port`，由后端自动读取库存
    - 直接传 `items`，对现有库存结果做本地选择

常用请求字段：
- `source`：`online` / `local`
- `device_ip`
- `sdk_port`
- `refresh_inventory`
- `seed`
- `filters`

`filters` 当前支持：
- `name_contains`
- `name_prefix`
- `name_regex`
- `ids`
- `names`
- 以及对 `status` / `sdk_ver` 等字段的精确匹配

响应中的 `apply` 已按 `sdk.switch_model` 对齐：
- `apply.model_id`
- `apply.local_model`
- `apply.model_name`

### 5.3 Random Generators

- `POST /api/generators/fingerprint`
  - 生成 `modifydev?cmd=7` 可直接使用的指纹对象。
- `POST /api/generators/contact`
  - 生成 `mytos.add_contact` 可直接使用的联系人数组。
- `POST /api/generators/env-bundle`
  - 一次生成语言/国家/时区、指纹、Google ADID、联系人等环境包，适合插件中 `save_as` 后复用。

当前内置国家配置：
- `jp_mobile`
- `us_mobile`

---

## 6) 设备与云机（拓扑与探测）

- `GET /api/devices/`：设备列表（包含云机端口映射信息）。
- `GET /api/devices/{device_id}`：设备详情。
- `GET /api/devices/{device_id}/status`：设备状态。
- `POST /api/devices/{device_id}/start`：启动设备（runtime_stub 模式下为占位实现）。
- `POST /api/devices/{device_id}/stop`：停止设备（runtime_stub 模式下为占位实现）。
- `POST /api/devices/discover`：局域网设备发现（当前也兼容 `POST /api/devices/discover/`）。
- `GET /api/devices/{device_id}/{cloud_id}/screenshot`：云机截图（`MYT_ENABLE_RPC=0` 时会返回 503）。
- `POST /api/devices/{device_id}/{cloud_id}/tap`：按像素坐标或归一化坐标点击云机屏幕。可附带 `trace_context`，把人工接管点击写入当前任务 trace。
- `POST /api/devices/{device_id}/{cloud_id}/swipe`：按像素坐标或归一化坐标滑动云机屏幕。可附带 `trace_context`。
- `POST /api/devices/{device_id}/{cloud_id}/key`：发送基础系统按键（`back` / `home` / `enter` / `recent` / `delete`）。可附带 `trace_context`。
- `POST /api/devices/{device_id}/{cloud_id}/text`：向当前焦点输入框发送单行文本，要求 `text` 非空且不包含换行。可附带 `trace_context`。

---

## 7) AI 对话入口

- `POST /api/ai_dialog/planner`：轻量 AI 对话 planner。输入 `goal`，可选再传 `app_id`、`selected_account`、`advanced_prompt`；返回 `display_name`、归一化后的 `resolved_payload`、账号策略和前端追问提示。
- `GET /api/ai_dialog/history`：列出 `source=ai_dialog` 的快捷历史卡片，包含最近 app/account 上下文、重放能力和关联的 workflow draft 摘要。

---

## 8) 任务系统（托管执行）

- `POST /api/tasks/`：创建任务（插件任务或匿名脚本任务）。
- `GET /api/tasks/`：任务列表。
- `GET /api/tasks/active?device_id=...&cloud_id=...&task_name=...`：按目标云机查询当前活跃任务；适合设备页恢复进行中的 AI 任务，不必扫整页任务列表。
- `GET /api/tasks/{task_id}`：任务详情（含 result / error）。
- `GET /api/tasks/{task_id}/events`：任务事件流（SSE）。

任务列表/详情响应额外字段（如存在则返回）：
- `started_at`：任务进入 running 的时间戳。
- `finished_at`：任务进入终态（completed/failed/cancelled）的时间戳。

`POST /api/tasks/` 额外支持：
- `display_name`：客户可见中文任务名，例如 `X 登录`。
- `draft_id`：把任务挂入已有 workflow draft。
- `success_threshold`：达到多少次成功样本后允许蒸馏，默认 `3`。
- 当 `task="_pipeline"` 时，`payload.steps` 应为有序步骤数组，每步包含 `plugin` 和可选 `payload`；并支持 `repeat` 与 `repeat_interval_ms`。

AI 托管任务提交契约（当前正式路径）：

```json
{
  "task": "agent_executor",
 "payload": {
    "goal": "dismiss login interstitial"
  },
  "targets": [
    {"device_id": 7, "cloud_id": 2}
  ],
  "priority": 50,
  "max_retries": 0,
  "retry_backoff_seconds": 2,
  "run_at": null,
  "idempotency_key": null
}
```

契约边界：
- **Canonical top-level fields**：`task`、`payload`、`targets`，以及已存在的调度/控制字段 `priority`、`max_retries`、`retry_backoff_seconds`、`run_at`、`idempotency_key`。
- **Compatibility-only top-level fields**：`display_name`、`draft_id`、`success_threshold`。
- `agent_executor` 在缺省情况下会自动从 app 上下文推断 `expected_state_ids` 与 `allowed_actions`；前端 AI 对话只需要提交 `goal`，可选再补 `app_id`、账号和 `advanced_prompt`。
- `ai_type` 若仍需提交，必须放在 `payload.ai_type`；顶层 `ai_type` 现在会被当作 misplaced field 直接拒绝。
- 顶层 `devices` 兼容入口已移除；任务提交必须显式提供 `targets`。
- **Anonymous script mode**：`script` 仍是独立的匿名脚本提交流程；不要把它当作 AI 托管任务的首选入口。

任务请求契约补充：
- `payload` 只承载插件在 `manifest.inputs` 中声明的业务输入。
- `targets` 是唯一目标声明通道；每项为 `{device_id, cloud_id}`。
- `device_id` / `cloud_id` / `device_ip` 属于目标/运行时元数据，必须通过 `targets` 或运行时信封提供，而不是顶层漂移字段或主业务 `payload`。
- `allowed_actions`、`expected_state_ids`、`app_id` 这类业务输入若需要提交，必须放在 `payload` 内；其中 `app_id` 只有在目标插件显式声明该输入时才允许出现。
- `_runtime_profile`、`_runtime`、`_llm`、`_vlm` 属于私有运行时覆写，不属于主业务 payload 契约；它们可以作为内部/兼容路径存在，但调用方不应把它们当作公开业务输入。
- 当 `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=1` 时，未声明字段会在 dispatch 阶段直接以 `failed_config_error` 拒绝。
- 当前仍保留少量 deprecated 兼容：某些旧调用路径在 `runtime.target` 缺少 `device_ip` 时，执行层仍会回退读取 payload 中的 legacy `device_ip`。这不是推荐契约，后续会继续收敛。

当任务附带 `display_name`，或属于自然语言驱动的 AI 执行任务（如 `agent_executor`）时，后端会自动创建 / 复用 workflow draft，并在任务响应与 `workflow_draft.updated` SSE 事件里附带：
- 当前成功样本数与剩余验证次数
- 失败建议与推荐提示词
- 推荐下一步动作（`apply_suggestion` / `continue_validation` / `distill`）

### 8.1 任务取消与清理
- `POST /api/tasks/{task_id}/cancel`：取消任务（等价于“更显式”的取消入口）。
- `POST /api/tasks/{task_id}/pause`：暂停任务。pending 任务会直接进入 `paused`；running 任务会进入协作式 `pause_requested` 流程。响应中的 `paused` 仅在任务已实际进入 `paused` 时为 `true`，`pause_requested` 表示请求已接受但仍在等待 worker 协作停下。
- `POST /api/tasks/{task_id}/resume`：恢复任务。`paused` 任务会重新排队；running + `pause_requested` 会清除暂停请求。响应中的 `resumed` 表示已从 `paused` 重新排队，`resume_requested` 表示已对运行中的任务撤销暂停请求。
- `POST /api/tasks/{task_id}/takeover`：发起显式 operator takeover 请求，可附带 `run_id` / `owner`。
- `POST /api/tasks/cleanup_failed`：清理 failed/cancelled 任务及相关运行产物（兼容 `DELETE`）。
- `POST /api/tasks/cleanup_runtime`：按保留期/上限裁剪任务事件与 trace（兼容 `DELETE`）。
- `DELETE /api/tasks/`：清空任务（运维用途，谨慎使用）。
- `POST /api/tasks/device/{device_id}/stop`：停止某设备的所有活跃任务（运维用途）。

`POST /api/tasks/cleanup_runtime` / `DELETE /api/tasks/cleanup_runtime` 支持以下 query 参数：
- `hidden_task_retention_days`
- `event_retention_days`
- `trace_retention_days`
- `max_event_rows`
- `max_trace_bytes`

### 8.2 任务目录与模板
- `GET /api/tasks/catalog`：插件/任务目录（用于前端下拉与校验）。
- `GET /api/tasks/catalog/apps`：已发现的 app 配置列表（来自 `config/apps/*.yaml`）。
- `GET /api/tasks/prompt_templates`：默认提示词列表（当前收敛为单一默认模板，来自 `engine/prompt_templates.py`）。

内置目录项：
- `_pipeline`：任务级编排入口。后端会顺序执行 `payload.steps` 中声明的子插件，并在每个子步骤结束时发出 `pipeline.step_done` SSE 事件。

`GET /api/tasks/catalog` 当前返回：
- `task`
- `display_name`
- `category`
- `description`
- `distillable`
- `visible_in_task_catalog`
- `required`
- `defaults`
- `example_payload`
- `inputs`

其中 `inputs` 会携带插件 `manifest.yaml` 中声明的 UI 元数据：
- `name` / `type` / `required` / `default`
- `label` / `description` / `placeholder`
- `advanced` / `system`
- `widget`
- `options`

前端任务面板会基于这些元数据自动渲染下拉、复选框和数字输入，而不再把所有字段都退化成普通文本框。
前端提交层也必须以这些 `inputs` 作为 payload 白名单，而不是额外注入页面私有字段。

说明：
- 默认 `GET /api/tasks/catalog` 不返回 `visible_in_task_catalog: false` 的内部插件。
- 运维或管理端可通过 `GET /api/tasks/catalog?include_hidden=true` 显式查看隐藏插件。

### 8.3 指标
- `GET /api/tasks/metrics`：JSON 指标。
- `GET /api/tasks/metrics/prometheus`：Prometheus 抓取格式。
- `GET /api/tasks/metrics/plugins`：按插件聚合的成功次数与蒸馏进度；返回中包含 `distillable` 与 `visible_in_task_catalog`，用于区分“不支持蒸馏”“默认隐藏”和“尚未达到蒸馏门槛”。

### 8.4 Workflow Draft
- `GET /api/tasks/drafts`：列出 workflow drafts（按更新时间倒序）。
- `GET /api/tasks/drafts/{draft_id}`：获取草稿状态、样本计数、失败建议和蒸馏进度。
- `GET /api/tasks/drafts/{draft_id}/snapshot`：获取最近一次成功快照（用于“编辑并重放”将历史参数预填到任务表单）。
- `POST /api/tasks/drafts/{draft_id}/continue`：复用最近一次成功快照继续自动验证。
- `POST /api/tasks/drafts/{draft_id}/distill`：当成功样本达到门槛后离线蒸馏最近一次成功 golden run，生成 YAML 草稿，并额外输出 `report_path` 指向的蒸馏报告（包含 `source` 汇总与 `human_guided` 步骤标注）。
- AI 对话入口会把自然语言任务额外标记为 `source=ai_dialog`，供 `/api/ai_dialog/history` 聚合成快捷历史卡片。

Workflow draft 蒸馏默认写入：
- `plugins/.drafts/<plugin_name>_draft/`

这样既满足“写入边界仍在 `plugins/` 下”，又不会被当前插件加载器误判为正式插件。

Workflow draft 约束：
- `draft_id` 一旦创建，会绑定首个任务的 `task_name`、`display_name` 与 `success_threshold`。
- 后续续跑或重试必须沿用同一业务身份；若传入不一致的值，接口会返回 400，避免把不相关运行误并到同一个草稿。
- `cleanup_failed` / `clear_all` 会同步清理 workflow draft 中已经失效的任务引用，避免草稿状态残留到已删除任务。
- 最近成功快照会固化 replay identity（例如解析后的 `app_id`、显式 `credentials_ref` 来源类型与账号名），用于“编辑并重放”保持更稳定的身份边界。

### 8.5 插件蒸馏
- `POST /api/tasks/plugins/{plugin_name}/distill`：触发插件蒸馏（受 `distill_threshold` 与目录边界约束）。

说明：
- 当插件 `manifest.yaml` 声明 `distillable: false` 时，该接口会直接返回 `code=distillation_not_supported`。
- 这类插件通常属于设备初始化、环境编排、随机化或运维流程，不应把一次 AI / API 运行样本固化成蒸馏模板。
- 蒸馏成功后后端会清空共享 plugin loader cache；只有**后续 lookup**（例如新的 catalog 请求、后续任务分发）会看到新插件，当前运行中的任务不承诺热更新。

---

## 9) Engine 自描述（Action Schema）

- `GET /api/engine/schema`：动作元数据目录（默认返回完整 metadata，可用 `?tag=skill` 等参数过滤）。
- `GET /api/engine/skills`：AI-facing 技能书，仅返回带 `skill` 标签的动作集合。

---

## 10) 浏览器诊断

- `GET /api/diagnostics/browser`：浏览器能力/依赖诊断（DrissionPage/CDP 可用性等）。
