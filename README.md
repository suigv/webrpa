# webrpa

一个可独立运行的 Web/RPA 自动化平台，提供：

- 设备与拓扑管理（多设备、多云机端口映射）
- 任务调度与控制（优先级、定时、重试、取消、SSE 事件流）
- 插件化执行引擎（YAML 工作流 + 动作注册）
- 浏览器自动化与拟人化交互（可配置移动/点击/输入节奏）
- Web 控制台与日志推送（`/web` + `/ws/logs`）

---

## 主要功能

### 1) API 服务

- `GET /health`：健康检查（含 `task_policy` 运行策略快照）
- `POST /api/runtime/execute`：直接执行 runtime payload
- `GET /web`：控制台页面

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

### 5) 浏览器拟人化能力

- `models/humanized.py` 提供强类型配置（移动、点击、输入、fallback 策略）
- BrowserClient 集成几何感知目标点、节奏控制与降级回退

### 6) 已内置插件示例

- `plugins/x_auto_login`
  - X/Twitter 登录工作流
  - 账号密码输入、2FA 处理、captcha 检测、结果判定

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

> 当前代码以包名 `new.*` 组织；默认在仓库根目录（本目录）执行，亦支持在父目录按 `new/...` 路径执行。

### 1) 创建环境并安装依赖（在仓库根目录执行）

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

### 2) 启动服务（禁用 RPC，在仓库根目录执行）

```bash
MYT_NEW_ROOT=$(pwd) MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001
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
./new/.venv/bin/python new/tools/check_no_legacy_imports.py
./new/.venv/bin/python -m pytest new/tests -q
```

---

## 项目进度文档

- 进度与功能清单：`new/docs/project_progress.md`
- 跨对话交接模板：`new/docs/HANDOFF.md`
- 插件输入契约与灰度策略：`new/docs/plugin_input_contract.md`
- 自动刷新快照（建议每次有意义变更后执行）：

```bash
./.venv/bin/python tools/update_project_progress.py
```

若在项目父目录执行：

```bash
./new/.venv/bin/python new/tools/update_project_progress.py
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
