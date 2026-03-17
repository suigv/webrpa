# 系统交接文档 (Handoff Guide)

本文件为 WebRPA 架构的深度技术解析，旨在帮助后续开发者快速理解核心组件的拓扑结构与运行机制。

---

## 1. 整体架构 (High-Level Architecture)

WebRPA 采用三层架构模型，其核心愿景是作为一个 **“行为编译器 (Behavior Compiler)”**，通过“成熟度漏斗 (Maturity Funnel)”将 AI 的探索轨迹编译为确定性的 YAML 插件。

1.  **控制面 (Control Plane)**：基于 FastAPI 提供的 REST 接口，负责任务持久化、状态机管理和指标统计。
2.  **执行引擎 (Execution Engine)**：负责解释并运行工作流。支持从“自主探索 (AI Bootstrapping)”到“原生数据执行 (Native/Data Mode)”再到“终极插件蒸馏 (Master YAML)”的演进。
3.  **驱动/硬件层 (Driver/Hardware Layer)**：通过三端口协议操作云机：
    - `sdk_port`: 8000（物理机级 SDK，负责容器/镜像/备份）。
    - `api_port`: 30000 + (cloud-1)*100 + 1（Android API，负责系统/剪贴板/文件）。
    - `rpa_port`: 30000 + (cloud-1)*100 + 2（RPA 控制，负责触控/UI 节点/截图）。
    - 浏览器通过 DrissionPage/CDP 操作。

---

## 2. 核心组件解析

### 2.1 任务、存储与异步化 (Task, Persistence & Async)
- **核心组件**：
  - `TaskController`：负责任务的提交与整体生命周期流程。
  - `TaskExecutionService`：负责任务的执行编排与分发。
  - `TaskMetricsService`：负责指标聚合。
  - `TaskAttemptFinalizer`：负责任务重试与清理策略。
- **存储架构**：全量模块统一继承自 `BaseStore`，使用 SQLite WAL 模式。
- **异步安全**：API 路由全面采用 `anyio.to_thread` 封装，确保同步 Store 操作不阻塞事件循环。

### 2.2 解释器与 AI 韧性 (Interpreter & AI Agent)
- **Runner**：双轨分发。
- **Interpreter**：支持 2s 级短脉冲取消检测。
- **AI 韧性**：`AgentExecutor` 自带指数退避重试与动作死循环熔断。
- **BindingDistiller**：由 AI 驱动的 UI 特征蒸馏服务，支持实时界面分析与识别代码生成。

### 2.3 设备管理服务化 (Device Management)
- **DeviceManager**：纯粹的状态 Registry，负责快照生成。
- **CloudProbeService**：独立的后台服务，负责云机在线探测与型号映射。
- **LanDeviceDiscovery**：负责网络层 IP 扫描。

---

## 3. 错误与日志标准 (Observability)
- **ErrorType**：全系统统一的错误语义类别（ENV, BUSINESS, AUTH, TIMEOUT）。
- **仿真证据**：Action 自动上报拟人化执行细节至事件流。


### 3.1 变量作用域 (Variable Scopes)
1.  **Task Payload** (`${payload.xxx}`)：任务不可变参数。
2.  **Internal Vars** (`${vars.xxx}`)：运行时临时状态。
3.  **Humanized Config**：自动下发至 `ExecutionContext.humanized` 的仿真参数。

---

## 4. 关键路径 (Key Paths)

- **主数据库**：`config/data/tasks.db`
- **账号池**：`config/data/accounts.json.db`（SQLite 格式，原 `accounts.json` 自动迁移）
- **AI 决策轨迹**：`config/data/traces/`
- **插件目录**：`plugins/`
- **场景提示词模板**：`engine/prompt_templates.py`（`PROMPT_TEMPLATES` 列表常量，`GET /api/tasks/prompt_templates` 路由对外暴露，前端动态拉取）
- **UI 配置**：`config/apps/*.yaml`（默认 `config/apps/default.yaml`，可通过 `MYT_DEFAULT_APP` 指定回退配置）
- **UI 状态绑定**：`config/apps/*.yaml`（按 `package_name` 动态加载，`xml_filter`/`states` 与选择器统一存放，缺失时走 binding-free 观察）
- **驱动库 (SO/DLL)**：`lib/`（libmytrpc，支持 macOS/Linux/Windows）
- **临时浏览器 Profile**：`/tmp/webrpa_browser_profiles/`，`close()` 时自动删除，启动时清理残留。

---

## 5. 已知约束与设计原则
- **无状态插件**：YAML 插件不应包含任何本地文件系统操作，所有持久化应通过 `shared_json_store` 动作完成。
- **幂等性**：建议通过 `X-Idempotency-Key` 提交任务，防止由于网络重试导致的重复操作。
- **UI 鲁棒性**：优先使用文本或语义锚点定位，而非脆弱的坐标或完整 XPath。

---

## 6. UI 路由导航 (Route Navigation)
- `ui.navigate_to` 为通用路由导航动作，不绑定任何单一 App。
- 必须显式提供 `routes` 与 `hops`（可通过 `params` 或 session defaults），并使用 `ui.match_state` 做状态探测。
- 设计原则：路由定义稳定、跳转动作最小化、每步执行后立即验证到达状态。
