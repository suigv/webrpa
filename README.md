# webrpa

一个可独立运行的 Web/RPA 自动化平台，提供：

- 设备与拓扑管理（多设备、多云机端口映射）
- 任务调度与控制（优先级、定时、重试、取消、SSE 事件流）
- 插件化执行引擎（YAML 工作流 + 动作注册）
- 浏览器自动化与拟人化交互（可配置移动/点击/输入节奏）
- Web 控制台与日志推送（`/web` + `/ws/logs`）
- 账号池导入/分配与状态回写（`/api/data/accounts*`）

## 项目介绍（整体架构）

`webrpa` 采用“API 控制面 + 核心调度层 + 插件执行引擎 + 适配器层 + Web 控制台”的分层结构，目标是在保持可扩展性的同时，让任务编排、设备管理和自动化执行解耦。

### 分层职责

- `api/`：对外 HTTP/WebSocket/SSE 入口，负责协议转换与参数校验，路由保持薄层。
- `core/`：控制面核心，负责配置加载、设备拓扑、LAN 发现、任务队列、任务存储、事件存储与调度循环。
- `engine/`：执行面核心，负责插件扫描、脚本解析、工作流解释执行、动作分发与执行期校验。
- `engine/actions/`：动作语义实现层，将 workflow 的 action 映射到具体能力（browser/sdk/ui/app/device 等）。
- `hardware_adapters/`：外部能力适配层，封装 Browser/SDK/MytRpc 等运行时依赖，并支持缺失时优雅降级。
- `plugins/`：业务插件层，每个插件由 `manifest.yaml`（输入契约）和 `script.yaml`（工作流）组成。
- `web/`：前端控制台，当前提供云机大厅、账号池、拟人化配置与日志实时查看。

### 任务执行主链路

1. 客户端通过 `POST /api/tasks` 提交任务（支持优先级、定时、重试、幂等键）。
2. `TaskController` 将任务写入持久化存储并入队，记录 `task.created` 事件。
3. Worker 出队后按 target（设备/云机）分发，调用 `Runner` 执行。
4. `Runner` 根据 `task` 选择插件，校验输入与动作白名单后交给 `Interpreter`。
5. `Interpreter` 按 YAML 步骤执行 `action/if/wait_until/goto/stop`，通过 Action Registry 调用具体动作。
6. 动作通过 adapter 访问浏览器或设备能力，结果回写任务状态，并持续产出事件与指标。

### 运行时总览

1. `api/server.py` 启动 FastAPI，并挂载 `/api/*`、`/web`、`/ws/logs`
2. 设备、配置、数据、任务请求分别进入 `api/routes/*`
3. 控制面能力下沉到 `core/*`，执行面能力下沉到 `engine/*`
4. 命名任务由 `engine/runner.py` 分发到 `plugins/*`
5. `engine/interpreter.py` 解释执行 YAML workflow
6. 浏览器、SDK、RPC 等外部能力统一经 `hardware_adapters/*` 访问

### 设计原则

- **插件优先**：新业务流程尽量以插件落地，避免把业务逻辑堆进 API 路由。
- **可恢复**：任务具备重试、取消、stale-running 恢复能力，控制器重启后可回收运行中任务。
- **可观测**：提供任务事件流（SSE）与指标接口（JSON/Prometheus）用于外部监控接入。
- **可降级**：当浏览器或 RPC 依赖不可用时，适配器返回明确错误，不阻断服务启动。

---

## 主要功能

### 1) API 服务

- `GET /health`：健康检查（含 `task_policy` 运行策略快照）
- `POST /api/runtime/execute`：直接执行 runtime payload
- `GET /api/diagnostics/browser`：浏览器适配器诊断
- `GET /web`：控制台页面

### 2) 设备管理（`/api/devices`）

- 设备列表、详情、状态查询
- LAN 发现与设备 IP 回写（`POST /api/devices/discover`）
- 设备逻辑启停（connection enabled/disabled）
- 返回云机分配信息与可用性探测结果（api/rpa/sdk 端口）

### 3) 任务系统（`/api/tasks`）

- 创建任务（支持 `priority` / `run_at` / `max_retries` / `retry_backoff_seconds`）
- 查询任务列表/详情
- 取消任务
- 任务事件流（SSE）：`GET /api/tasks/{task_id}/events`
- 任务指标：`GET /api/tasks/metrics`（JSON）与 `GET /api/tasks/metrics/prometheus`（Prometheus 抓取格式）

### 3.1) 外部监控接线资产

- Prometheus 抓取模板：`config/monitoring/prometheus/task_metrics_scrape.example.yml`
- 告警规则模板：`config/monitoring/prometheus/task_metrics_alerts.yml`（含 `NewTaskStaleRunningRecovered`）
- Alertmanager 路由模板：`config/monitoring/alertmanager/task_metrics_route.example.yml`
- 参数化渲染工具：`tools/render_task_metrics_monitoring.py`

### 4) 插件化执行引擎

- `Runner` 支持匿名脚本与命名任务分发
- YAML 插件通过 `engine/plugin_loader.py` 加载并交给解释器执行
- 内置动作注册器覆盖 `browser` / `credentials` / `core` / `ui` / `app` / `device` / `sdk` / `mytos` 命名空间

### 5) 账号池与数据接口（`/api/data`）

- 原始账号文本读取：`GET /api/data/accounts`
- 账号导入与高级解析：`POST /api/data/accounts/import`
- 账号状态回写：`POST /api/data/accounts/status`
- 原子化弹出 ready 账号：`POST /api/data/accounts/pop`
- 解析后账号列表：`GET /api/data/accounts/parsed`
- 文本型位置/站点数据读写：`/api/data/location`、`/api/data/website`

### 6) 浏览器拟人化能力

- `models/humanized.py` 提供强类型配置（移动、点击、输入、fallback 策略）
- BrowserClient 集成几何感知目标点、节奏控制与降级回退

### 7) 已内置插件

- `plugins/x_mobile_login`
  - X 移动端登录工作流
  - 基于 UI/RPC 的状态识别、输入、2FA 生成与结果分支
- `plugins/mytos_device_setup`
  - MYTOS 设备初始化工作流
  - ADB 权限、语言国家、开机启动、root 授权等原子动作编排
- `plugins/device_reboot` / `plugins/device_soft_reset`
  - 设备重启与软重置
- `plugins/blogger_scrape` / `plugins/profile_clone`
  - 资料抓取与共享数据迁移/克隆链路
- `plugins/follow_interaction` / `plugins/home_interaction` / `plugins/quote_interaction` / `plugins/dm_reply`
  - 互动类插件契约与执行骨架

### 8) Web 控制台现状

- 已公开页面：云机大厅、账号池、拟人化配置、实时日志
- 支持单机任务下发、批量选机下发、账号池批量分派 `x_mobile_login`
- 代码中包含 `web/js/features/tasks.js` 的任务管理模块，但当前 `web/index.html` 未暴露独立任务页 DOM，任务管理 UI 仍属于“部分接线”状态

---

## 项目结构

```text
api/                # FastAPI 路由与服务入口
core/               # 配置、任务控制、队列、存储、设备管理
docs/               # 项目文档、契约、嵌入说明、进度记录
engine/             # 解析器、解释器、动作注册、插件加载
hardware_adapters/  # 浏览器/RPC 适配
models/             # Pydantic/Dataclass 模型
plugins/            # 业务插件（manifest + script）
scripts/            # 启动脚本与实验性辅助脚本
tests/              # 单元与集成测试
web/                # 控制台静态资源
tools/              # 校验脚本与工具
```

### 目录职责补充

- `api/server.py`：唯一应用入口、生命周期、静态资源挂载、健康检查
- `api/routes/task_routes.py`：任务目录、创建/查询/取消、SSE、指标导出
- `api/routes/data.py`：账号池、位置、站点数据接口
- `contracts/`：类型存根与契约辅助文件
- `core/task_control.py`：任务提交、队列、重试、取消、事件与指标
- `core/device_manager.py`：设备拓扑、云机分配、可用性探测
- `core/account_parser.py`：账号导入与归一化解析
- `engine/action_registry.py`：内置动作注册
- `engine/plugin_loader.py`：插件发现与加载
- `lib/`：原生 `mytRpc` 动态库文件
- `vendor/`：vendored 第三方依赖（当前为 `DrissionPage`）
- `hardware_adapters/myt_client.py` / `hardware_adapters/mytRpc.py` / `hardware_adapters/browser_client.py`：外部能力适配层

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

### 3) 健康检查

```bash
curl http://127.0.0.1:8001/health
```

### 4) 打开控制台

- 浏览器访问：`http://127.0.0.1:8001/web`

---

## 质量与验证

常用验证命令（在仓库根目录执行）：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
```

若在项目父目录执行，可使用等效命令：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
```

---

## 项目进度文档

- 进度与功能清单：`docs/project_progress.md`
- 文档索引：`docs/README.md`
- 跨对话交接模板：`docs/HANDOFF.md`
- 插件输入契约与灰度策略：`docs/plugin_input_contract.md`
- 插件结构与工作流契约：`docs/PLUGIN_CONTRACT.md`
- Web 嵌入桌面 GUI 指南：`docs/WEB_GUI_EMBED.md`
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

## 开发约定

### 技术栈

- Python 3.11+
- FastAPI + Uvicorn + Pydantic
- SQLite（`config/data/tasks.db`）+ JSON 配置/数据
- WebSocket（日志）+ SSE（任务事件流）
- Browser/RPA 适配器 + `ai_services/` 占位客户端

### 新增 API / 动作时的约定

- 新增 API 路由时，保持 `api/` 薄层，业务逻辑落到 `core/` 或 `engine/`
- 新增工作流能力时，优先放在 `plugins/`，避免把业务流程写进路由
- 新增原子能力时，在 `engine/actions/` 实现，并通过 `engine/action_registry.py` 注册
- 插件契约变更时，同步更新 `docs/PLUGIN_CONTRACT.md`

### 开发注意事项

- 不要直接操作 `config/data/tasks.db`，统一走任务控制面 / 存储层
- 不要引回 `tasks.*` 或 `app.*` 历史命名空间
- 浏览器与 RPC 适配器必须保持 failure-safe，缺失依赖时不能阻断服务启动
- 数据文件保持在 `config/data`

### 完成定义

- 静态门禁通过
- 测试通过
- `MYT_ENABLE_RPC=0` 启动成功
- `/health` 返回 200
- 未重新引入 legacy imports

### 端口架构

每个云机有 `api_port` 与 `rpa_port`，每台设备共享一个 `sdk_port`。

| Port | Formula | Role |
|---|---|---|
| `api_port` | `30000 + (cloud-1)*100 + 1` | 云机 HTTP API |
| `rpa_port` | `30000 + (cloud-1)*100 + 2` | MytRpc 控制通道 |
| `sdk_port` | `8000`（可配置） | 设备级控制 API |

示例（device IP `192.168.1.214`，10 台云机）：

```text
cloud 1  -> api 30001, rpa 30002
cloud 2  -> api 30101, rpa 30102
cloud 10 -> api 30901, rpa 30902
```

---

## License

如需开源许可，请在仓库中补充 `LICENSE` 文件并在此处声明。
