# webrpa

一个可独立运行的 Web/RPA 自动化平台，提供：

- 设备与拓扑管理（多设备、多云机端口映射）
- 任务调度与控制（优先级、定时、重试、取消、SSE 事件流）
- 插件化执行引擎（YAML 工作流 + 动作注册）
- 浏览器自动化与拟人化交互（可配置移动/点击/输入节奏）
- Web 控制台入口与日志 WebSocket 路由（`/web` + `/ws/logs`）

---

## 主要功能

### 1) API 服务

- `GET /health`：健康检查（含 `task_policy` 运行策略快照）
- `POST /api/runtime/execute`：debug/internal-only 直跑入口；同步执行 runtime payload，不创建 `/api/tasks` 托管任务、重试、取消、SSE 事件或指标
- `GET /web`：控制台静态入口页面（smoke-backed）

### 2) 设备管理（`/api/devices`）

- 列表、详情、状态查询
- 设备启动/停止（runtime_stub 模式）
- 返回云机分配信息（api/rpa/sdk 端口）

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
- 内置动作注册器（浏览器动作、凭据动作等）
- `wait_until` 已补齐 success-before-timeout、`on_timeout goto`、`on_fail`、取消态与动态重轮询语义
- `ExecutionContext.session.defaults` 已作为最小任务级默认值接缝落地，保持显式 action 参数优先，其次 session defaults，最后回退到原始 payload

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

- `plugins/x_mobile_login`
  - 当前主分支内置的 X/Twitter 移动端登录工作流
  - 负责登录阶段状态判定与运行时接线验证
  - 已验证可通过 manifest 输入默认值与 `_target` 派生的 session defaults 收口重复 runtime 接线；当前回归只明确覆盖 `device_ip` 无需在步骤里重复传递，且相关步骤不必再显式重复声明 `package`，同时保持既有 status / message 契约
- `plugins/hezi_sdk_probe`
  - SDK 能力探测与基础连通性验证
- `plugins/mytos_device_setup`
  - 设备准备与运行时初始化类流程

---

## 项目结构

```text
api/                # FastAPI 路由与服务入口
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

- 进度与功能清单：`docs/project_progress.md`
- 当前 main 已完成/未完成事项：`docs/current_main_status.md`
- 跨对话交接模板：`docs/HANDOFF.md`
- 插件输入契约与灰度策略：`docs/plugin_input_contract.md`
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
