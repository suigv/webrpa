# webrpa

一个可独立运行的 Web/RPA 自动化平台，提供：

- 设备与拓扑管理（多设备、多云机端口映射）
- 任务调度与控制（优先级、定时、重试、取消、SSE 事件流）
- 插件化执行引擎（YAML 工作流 + 动作注册）
- 浏览器自动化与拟人化交互（可配置移动/点击/输入节奏）
- Web 控制台入口与日志 WebSocket 路由（`/web` + `/ws/logs`）
- **Binding Master**: 可视化 UI 特征蒸馏工具，提供 AI 驱动的状态识别建议与代码生成。
- **Account Store (SQLite)**: 账号池全面迁移至 SQLite (BaseStore)，支持高并发原子化抽号与状态管理。
- 云机详情页提供 AI 对话入口，可用自然语言下发 `agent_executor` 任务。

---

## 主要功能

### 1) API 服务

- `GET /health`：健康检查（含 `task_policy` 运行策略快照）
- `POST /api/runtime/execute`：debug/internal-only 直跑入口；同步执行 runtime payload，不创建 `/api/tasks` 托管任务、重试、取消、SSE 事件或指标
- `POST /api/binding/analyze`：捕获 UI XML 并由 AI 建议识别特征与状态 ID
- `POST /api/binding/draft`：汇总多条 UI 记录并生成 Python 探测代码
- 其他控制面 API（配置/账号池/诊断等）详见 `docs/HTTP_API.md`，或启动后访问 `/docs` 查看 OpenAPI。
- `GET /web`：控制台静态入口页面（smoke-backed）

### 2) 设备管理（`/api/devices`）

- 列表、详情、状态查询
- 设备启动/停止（runtime_stub 模式）
- 返回云机分配信息（api/rpa/sdk 端口）

### 3) 任务系统（`/api/tasks`）

- 创建任务（支持 `priority` / `run_at` / `max_retries` / `retry_backoff_seconds`）
- 新增托管 `agent_executor` 任务模式，继续复用同一 `/api/tasks` 创建、重试、取消、SSE 事件与指标链路
- 查询任务列表/详情
- 取消任务
- 清理未成功任务：`POST /api/tasks/cleanup_failed`（兼容 `DELETE`）
- 任务目录：`GET /api/tasks/catalog`
- 任务事件流（SSE）：`GET /api/tasks/{task_id}/events`
- 任务指标：`GET /api/tasks/metrics`（JSON）与 `GET /api/tasks/metrics/prometheus`（Prometheus 抓取格式）
- 任务控制面内部已拆分为 façade + service：`core/task_control.py` 只保留入口编排，执行循环在 `core/task_execution.py`，终态/重试规则在 `core/task_finalizer.py`，指标聚合与导出在 `core/task_metrics.py`
- `api/mappers/task_mapper.py` 统一承接 `TaskRecord` -> API DTO 映射，避免在 route 中散落时间/targets 转换逻辑
- 显式 target 已成为任务控制面的正式字段：route / store / mapper / execution / runtime 统一围绕 `targets` 工作，不再依赖把控制面元数据塞回 `payload`
- `agent_executor` 采用 structured-state-first 观察，只有主观察不足时才显式回退到 XML、截图或 browser HTML 等补充模态；执行环必须带 step budget、stagnant-state circuit breaker，并把完整模型轨迹单独追加到 `config/data/traces/` JSONL，而不是塞进任务生命周期事件

#### 3.1) 任务请求/响应契约摘要

`POST /api/tasks/` 请求体：

```json
{
  "task": "device_reboot",
  "payload": {
    "device_ip": "192.168.1.2",
    "name": "cloud-1"
  },
  "targets": [
    { "device_id": 1, "cloud_id": 2 }
  ],
  "priority": 50,
  "max_retries": 0,
  "retry_backoff_seconds": 2,
  "run_at": null
}
```

说明：
- `task` 与 `payload` 是异步任务的主入口
- 托管任务提交必须显式提供 `targets` 或兼容输入 `devices`；两者都缺失时请求会被拒绝
- `targets` 是推荐目标声明方式；每项为 `{device_id, cloud_id}`
- `devices` 仍可作为兼容输入，但控制面内部会归一到显式 `targets`
- HTTP 调用方应以 `Content-Type: application/json` 发送该请求体；前端共享提交入口已按此契约对齐
- `script` 仅用于匿名脚本直提交流程；常规插件任务优先使用 `task + payload`

`GET /api/tasks/` 列表项核心字段：

```json
{
  "task_id": "...",
  "task_type": "script",
  "task_name": "device_reboot",
  "devices": [1],
  "targets": [{ "device_id": 1, "cloud_id": 2 }],
  "status": "pending",
  "created_at": "2026-03-09T01:02:03Z",
  "retry_count": 0,
  "max_retries": 0,
  "retry_backoff_seconds": 2,
  "next_retry_at": null,
  "priority": 50,
  "run_at": null
}
```

`GET /api/tasks/{task_id}` 在列表字段基础上额外返回：

```json
{
  "result": {},
  "error": null
}
```

说明：
- 前端列表页应使用 `task_name`，不是旧的 `display_name`
- 任务详情页应消费 `result` / `error`，不是旧的 `payload` / `message`
- SSE 事件流用于生命周期追踪；详情接口本身不承担事件聚合职责

### 3.2) 外部监控接线资产

- Prometheus 抓取模板：`config/monitoring/prometheus/task_metrics_scrape.example.yml`
- 告警规则模板：`config/monitoring/prometheus/task_metrics_alerts.yml`（含 `NewTaskStaleRunningRecovered`）
- Alertmanager 路由模板：`config/monitoring/alertmanager/task_metrics_route.example.yml`
- 参数化渲染工具：`tools/render_task_metrics_monitoring.py`

### 4) 插件化执行引擎

- `Runner` 支持匿名脚本与命名任务分发
- YAML 插件通过 `engine/plugin_loader.py` 加载并交给解释器执行
- 运行时与 `GET /api/tasks/catalog` 共用同一插件缓存视图；catalog 的显式 refresh 会同步更新现有 runtime 视图
- 内置动作注册器（浏览器动作、凭据动作等）
- 复用的 selector workflow 已收口到 composite actions（如 `core.load_ui_selectors`、`ui.selector_click_with_fallback`），避免脚本重复加载/点击逻辑
- Golden Run 离线蒸馏工具 `tools/distill_golden_run.py` 会从一条成功轨迹生成可审阅的 `manifest.yaml` + `script.yaml` 草稿，要求保留参数化输入；草稿不会自动安装到 `plugins/`，只有通过 parse + replay smoke 后才算可用
- `wait_until` 已补齐 success-before-timeout、`on_timeout goto`、`on_fail`、取消态与动态重轮询语义
- `ExecutionContext.session.defaults` 已作为最小任务级默认值接缝落地，保持显式 action 参数优先，其次 session defaults，最后回退到原始 payload
- `ExecutionContext.runtime` 已承接任务运行时信封；target / task_id / cloud_target_label 等控制面信息不再通过 payload 私有字段注入
- 任务可通过 payload `_runtime_profile` / `_runtime` / `_llm` / `_vlm` 覆写运行时配置；profile 文件放在 `config/<name>.json`
- `agent_executor` 的 VLM 路径默认关闭；需要时在 `config/system.yaml` 中设置 `enable_vlm: true` 并在 `fallback_modalities` 中显式启用
- 新增 `ai.locate_point` 动作：输入截图+提示词，返回点击坐标（支持像素/归一化坐标换算）
- `UIStateService` 的结果构造、timing 与 browser polling 语义已收口到共享 helper；native bindings 也已拆到独立 registry，降低 browser/native 平行演化风险

### 5) 浏览器拟人化能力

- `models/humanized.py` 提供强类型配置（移动、点击、输入、fallback 策略）
- BrowserClient 集成几何感知目标点、节奏控制与降级回退
- UI 状态观察覆盖已扩展到 `timeline_candidates`、`follow_targets` 与集合首项别名，不改变顶层结果形状
- 有界 helper `ui.navigate_to` 与 `ui.fill_form` 可用于页面级导航和表单驱动，未上提为工作流级恢复系统

### 6) RPA/RPC 控制层（已完成 remediation）

- `engine/actions/ui_actions.py` 与 `engine/actions/state_actions.py` 保持稳定 facade，对外动作名与常见错误码契约不变
- 共享 RPC 启动/关闭逻辑已收敛到 `engine/actions/_rpc_bootstrap.py`
- selector/node 子系统与状态提取逻辑已拆到内部 helper，避免动作模块继续膨胀
- `core/task_control.py` 中的账号反馈策略已下沉到 `core/account_feedback.py`
- `hardware_adapters/mytRpc.py` 已补齐 pointer ownership / timeout / failure-safe 处理，且 `MYT_ENABLE_RPC=0` 启动路径已验证

### 7) 已内置插件示例

- `plugins/hezi_sdk_probe`
  - SDK 能力探测与基础连通性验证
- `plugins/mytos_device_setup`
  - 设备准备与运行时初始化类流程
- `plugins/device_reboot`
  - 设备硬件重启
- `plugins/device_soft_reset`
  - 设备软件复位（需显式提供 `package`）

---

## 项目结构

```text
api/                # FastAPI 路由、DTO mapper 与服务入口
core/               # 配置、任务控制、队列、存储、设备管理
engine/             # 解析器、解释器、动作注册、插件加载
hardware_adapters/  # 浏览器/RPC 适配
models/             # Pydantic/Dataclass 模型
plugins/            # 业务插件（manifest + script）
tests/              # 单元与集成测试
web/                # 控制台静态资源
tools/              # 校验脚本与工具
```

---

## 快速开始

> 当前代码以包名 `*` 组织；默认在仓库根目录（本目录）执行，亦支持在父目录按 `...` 路径执行。

### 1) 创建环境并安装依赖（在仓库根目录执行）

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

### 2) 启动服务（禁用 RPC，在仓库根目录执行）

```bash
 MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

说明：全局非敏系统配置（如 Redis, LLM URL 等）统一在 `config/system.yaml` 中维护。如需注入敏感信息（如 API Key）或进行环境变量覆盖，可在根目录创建 `.env`，并设置 `MYT_LOAD_DOTENV=1` 后启动服务。

### 3) 健康检查

```bash
curl http://127.0.0.1:8001/health
```

### 4) 打开控制台

- 浏览器访问：`http://127.0.0.1:8001/web`

### 5) (可选) 桌面工作站启动器 (pywebview)

仓库根目录的 `main.py` 提供一个桌面壳（内嵌浏览器 + 一键启动服务），适合本地运维/演示。

```bash
./.venv/bin/python -m pip install pywebview
./.venv/bin/python main.py
```

---

## 质量与验证

常用验证命令（在仓库根目录执行）：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

若在项目父目录执行，可使用等效命令：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
```

---

## 项目进度文档

- 文档层级约定，单点可判定：
  - `README.md` = entrypoint / summary only
  - `docs/project_progress.md` + `docs/project_progress.md` = canonical status / progress
  - `docs/HANDOFF.md` = continuation / runbook / evidence workflow
  - `docs/README.md` = optional index, not canonical

- 进度与功能清单：`docs/project_progress.md`
- 当前 main 已完成/未完成事项：`docs/project_progress.md`
- 跨对话交接模板：`docs/HANDOFF.md`
- 插件输入契约与灰度策略：`docs/PLUGIN_CONTRACT.md`
- 历史/辅助文档归档：`docs/archive/`
- 原子化问题分类：`docs/reference/功能原子化问题分类说明.md`
- 原子化修复结果：`docs/reference/功能原子化修复结果.md`
- 自动刷新快照（建议每次有意义变更后执行）：

```bash
./.venv/bin/python tools/update_project_progress.py
```

若在项目父目录执行：

```bash
./.venv/bin/python tools/update_project_progress.py
```

- CI 自动校验：`.github/workflows/project-progress-sync.yml`
  - 在 PR / push(main/master) 时自动运行快照刷新
  - 若 `docs/project_progress.md` 未同步更新则检查失败

---

## 约束与设计原则

- 不引入 legacy 命名空间依赖（`tasks` / `app.*`）
- 路由保持薄层，业务逻辑优先下沉到 `core/` 与 `engine/`
- 新业务流程优先插件化（`plugins/`）
- 适配器能力缺失时需可降级、可恢复

---

## License

如需开源许可，请在仓库中补充 `LICENSE` 文件并在此处声明。
