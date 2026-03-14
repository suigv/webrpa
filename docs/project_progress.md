# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**Web Console Productization & Navigation Engine Hardening**
- 核心状态：API、任务系统、插件执行、账号池全面可用；Web 控制台完成产品化改造；导航引擎具备自愈与锚点机制；AI 执行引擎接入托管链路。
- 最近重点 (2026-03-11)：
  - **工业级稳固性与运维增强 (2026-03-11)**：
    - **跨平台拟真引擎全集成**：建立统一的 `HumanizedHelper`，拟人化偏移与打字节奏已成功注入 **Android Native 动作 (RPC)**，实现全端一致的风险控制。
    - **数据库架构统合 (BaseStore)**：彻底消除了 SQLite 实现碎片化，所有 Store 模块统一继承 `BaseStore`，全面启用 WAL 模式与 30s 统一忙时重试。
    - **Web 控制台全能化升级**：
      - **节点中心**：支持云机详情穿透、紧急停止、以及针对服务端环境（8001/Redis/浏览器驱动）的一键诊断。
      - **库存中心**：实现账号状态一键标记（✅/❌/⛔/❓）与全字段在线编辑。
      - **洞察中心**：任务流水支持 **SSE 实时事件流追踪**，可视化展示 AI 的每一步 Thought 与仿真证据。
      - **全量设置**：支持在线修改 host_ip、device_ips (JSON) 以及业务文本 (Location/Website)。
    - **运行环境优化**：
      - **测试隔离**：强制测试环境重定向至临时路径，保护生产账号数据。
      - **取消响应**：`wait_until` 解释器层实现 2s 级短脉冲轮询，大幅提升任务取消的灵敏度。
  - **架构收敛与重构**：
    - `TaskController` 已完成职责拆分，下放至 `TaskExecutionService`、`TaskMetricsService` 等子服务。
    - `engine/actions/sdk_actions.py` 已完成职责纠偏，拆分出共享存储、业务辅助等独立支持模块。
    - 统一了全局路径管理 (`core/paths.py`)，消除了多处根路径解析冗余。
    - **插件加载一致性**：`get_shared_plugin_loader` 已实现真正的全局单例，API 层刷新与后台执行引擎物理同步。
  - **Web 控制台产品化 (2026-03-10)**：
    - 实时显示 `MYT_ENABLE_RPC` 运行状态。
    - 资源仓库支持账号全字段编辑及状态一键重置。
    - 任务流水支持全局停止、清空历史及单任务精准控制。
    - 实时执行日志流实现 WebSocket 异步广播，Action 结果可视化。
  - **导航引擎鲁棒性强化**：
    - 引入“UI 清道夫”自动排除升级引导等干扰项。
    - 引入“语义锚点判定”支持无 ID 环境下的多语言定位。
  - **AI 执行引擎 (GPT Executor)**：
    - 已接入 `/api/tasks` 托管链路，支持创建、取消、重试及 SSE 事件。
    - 默认采用 `structured-state-first` 观察策略，仅在必要时回退至视觉模态。
    - 原始模型轨迹独立持久化至 `config/data/traces/`。
- 最近重点 (2026-03-12)：
  - **端口架构全面修正**：
    - 以官方三份文档为基准，建立三端口完全分离架构：8000（物理机级SDK）/ 30001（云机级Android API）/ 30002（RPA控制）。
    - 新建 `hardware_adapters/android_api_client.py`（`AndroidApiClient`，30001端口），实现 34 个云机级原子动作（剪贴板、S5代理、截图、文件操作、语言设置、定位、ADB权限、Google ID、联系人、模块管理等）。
    - 新建 `engine/actions/android_api_actions.py`，注册 `android.*` 命名空间（34个动作）。
    - `MytSdkClient`（8000端口）精简 ~400 行，移除所有混入的 30001 方法，回归物理机级职责（云机容器生命周期、镜像、备份、SSH、VPC）。
    - `mytos.*` 动作（50个）改为代理到 `android.*` 实现，不再走错误的 8000 端口。
  - **多轮成功率统计与蒸馏触发**：
    - 新增 `GET /api/tasks/metrics/plugins`，按插件统计累计成功次数及蒸馏进度。
    - 新增 `POST /api/tasks/distill/{plugin}`，一键触发多轮蒸馏生成 YAML 草稿。
    - 新增 `tools/distill_multi_run.py`，多 trace 聚合蒸馏工具。
    - 前端「运行洞察」新增「插件蒸馏进度」面板，带进度条和蒸馏按钮。
  - **VLM 屏幕元数据修复**：`capture_compressed` 从 JPEG/PNG 字节解析真实屏幕宽高，注入 trace 并传给 `VLMClient.predict()`，修复 VLM 坐标补偿精度。
  - **任务系统稳健性**：设备级排他锁（防幽灵任务）、子进程不做 availability 强制检查、多目标取消即时中断、`subscribe` 改为追加模式。
  - **前端系统**：账号选择器（接管页和AI对话框）、AI对话框改为勾选模式、设备上下线按钮、系统偏好页简化（移除 JSON 输入）、已发现设备数实时显示。

  - **AI 绑定蒸馏链路打通与稳定性增强 (X App)**：
    - **XML 截断原因调查与修复**：确认为 `dump_node_xml_ex` 存在 **4KB (4096字节)** 的 RPC 传输缓冲区硬限制。已在底层通过自愈重试机制解决。
    - **自愈式捕获逻辑 (Self-Healing)**：在 `_state_detection_support.py` 中实现了自动完整性校验，若检测到 `Ex` 模式截断，则自动重试标准 `dump_node_xml`（无此缓冲区限制），确保 AI 能获取完整 UI 树。
    - **蒸馏工具 Regex Fallback**：为 `tools/distill_binding.py` 引入了正则回退机制，确保在极端截断情况下仍能提取包名和核心特征。
    - **App 探测去硬编码重构**：彻底移除了框架中针对 X App 的硬编码字符串，支持通过 `config/apps/*.yaml` 动态加载。
    - **通用的 Native 状态观察**：`X_APP_STAGE_BINDING` 已重构为全局通用的 `app_stage` 绑定。
    - **X App 特征落地**：解析并集成 X App 首页特征。
    - **文档与系统一致性对齐**：全量审计并修复了 `docs/` 下的过期信息，包括多云机动态端口公式、任务控制面架构拆分描述、以及插件契约规范（补全 Pydantic 必填字段），并新增了 **[Skills化演进报告](SKILLS_EVOLUTION.md)**，确立了 AI 驱动技能化的架构演进方向。
  - **代码清理（本会话）**：删除 `common/env_loader.py`、`common/runtime_state.py`、`common/toolskit.py`（零引用旧产物）。

- 最近重点 (本会话)：
  - **App 配置统一架构**：删除 `config/bindings/` 目录，`xml_filter`/`states` 字段合并至 `config/apps/<app>.yaml`；GPT 执行器改为从 `config/apps/*.yaml` 按 `package_name` 加载 binding 参数；`sdk_config_support` 新增 `com.twitter.android → x` 映射。
  - **X app 配置**：新增 `config/apps/x.yaml`，含 `package_name`、`xml_filter`（max_text_len=60/max_desc_len=100，针对 X app 的合理截断），15 个 UI 状态描述，deep link scheme。
  - **蒸馏自动 selector merge**：`GoldenRunDistiller.distill()` 完成后自动扫描 script steps，提取 UI 定位 action（`ui.click` 等 8 种）的未参数化 `text`/`resource_id` 值，merge 写入对应 `config/apps/<app>.yaml` 的 `selectors` 字段；已有 selector 不覆盖。

- 最近重点 (本会话)：
  - **Skills-Driven 架构演进 (Phase 1 & 2)**：
    - **Action Registry 元数据增强**：`ActionRegistry` 现在支持 `ActionMetadata`，通过 Pydantic 模型定义每个动作的描述、参数 Schema (JSON Schema) 和返回值 Schema。
    - **自描述 API**：新增 `GET /api/engine/schema` 接口，全量暴露已注册动作的元数据，方便 AI 代理发现可用技能。
    - **非破坏性元数据富化**：为 `ui.*`、`app.*`、`core.*` (save/load shared) 以及 `ai.*` (llm/vlm/locate) 等高频核心动作补全了描述和参数规范。
    - **文档自愈机制**：在 `AGENTS.md` 中确立了“代码变更伴随文档同步”的强制规则，确保架构演进与文档保持物理对齐。
    - **AI 引导升级**：新建 `docs/AI_ONBOARDING.md` 作为 AI 进入项目的第一站，明确了知识检索优先级与职责边界。

- 最近重点 (本会话)：
  - **场景提示词模板服务化**：
    - 新建 `engine/prompt_templates.py`，集中定义 4 个模板常量（通用自动化、账号登录/切换、社交媒体 X/Twitter、内容采集/数据爬取），作为项目唯一数据源。
    - 新增 `GET /api/tasks/prompt_templates` 路由，动态返回模板列表（key/name/content）。
    - 前端 AI 对话框「场景提示词模板」select 改为动态拉取（`loadPromptTemplates()`），移除硬编码静态对象和静态 `<option>`，打开对话框时自动刷新。

- 最近重点 (本会话)：
  - **ai_type 去硬编码重构**：
    - 删除框架层所有 `volc`/`part_time` 业务判断分支（`sdk_business_support.py`）。
    - 候选人评分权重（`has_media_bonus`、`keyword_bonuses`）移入 `nurture_keywords.yaml` 的 `candidate_scoring` 字段，框架通用读取。
    - 搜索词（`#mytxx`/`#mytjz`）移入 `interaction_texts.yaml` 的 `search_query` section，框架从配置随机选取。
    - 删除 `models/device.py` 中的 `AIType` enum，`DeviceInfo.ai_type` 改为开放 `str`。
    - 删除 `core/device_manager.py` 中的 `parse_ai_type` 死代码函数。
    - 所有兜底值从 `"volc"` 改为 `"default"`，`nurture_keywords.yaml` 新增 `default` strategy section。
    - **新增模式只需改配置，零框架改动**。

- 下一步优先级：
  - [x] 提取数据库基类 (`BaseStore`)，消除 `TaskStore` 与 `TaskEventStore` 的重复代码（待验证）。
  - [x] 废弃 `common/config_manager.py`，全面收敛至 `core/config_loader.py`（待验证）。
  - [x] 引入 Pydantic 重构配置解析逻辑，替代手动 JSON 校验（待验证）。
  - [x] 拆分 `DeviceManager`，将云机探测逻辑移至独立服务（待验证）。
  - [x] 修复 AI 模块隐患：VLM 连接泄露处理及基于 `retryable` 标记的退避重试（待验证）。
  - **AI 对话架构改进 (2026-03-11)**：
    - **修复无 binding 场景下的 fingerprint 计算**：`gpt_executor` 在 `observation.ok=False` 时改用 UI XML 内容计算停滞 fingerprint，防止在无 binding 场景下错误触发死循环熔断。
    - **新增 binding 蒸馏工具** (`tools/distill_binding.py`)：从 trace jsonl 自动提取 UI 特征、归纳界面状态，生成 `NativeStateBinding` 代码草稿。
    - **前端 AI 对话修复**：`binding_id` 服务化、allowed_actions 注册名对齐、SSE 事件流稳定性修复。
    - **LLM 调用链路修复**：新增 `OpenAIChatProvider` 并通过 `.env` 注入 key，由于采用了标准 OpenAI 封装协议，系统现在能更稳健地连接到各类代理服务。

## 2. 已实现功能清单

### 2.1 API 与控制面
- 任务/设备/配置/数据全套 RESTful 接口。
- WebSocket 实时日志流 (`/ws/logs`)。
- 托管任务生命周期管理（创建/取消/重试/指标）。

### 2.2 引擎与插件
- Runner + Interpreter 声明式工作流引擎。
- 支持 YAML 插件模式（`v2` 契约）。
- 托管 `gpt_executor` 自主智能体运行时。
- 离线 Golden Run 蒸馏工具。

### 2.3 适配器与动作
- 统一 UI 状态观察层 (`UIStateService`)。
- 浏览器、原生 UI、SDK 动作绑定。
- 拟人化操作与降级回退机制。

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 35 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 4 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 154 |
| Test files (`tests/test_*.py`) | 50 |
| Test functions (`def test_*`) | 245 |
| Documentation files (`docs/*.md`) | 16 |
<!-- AUTO_PROGRESS_SNAPSHOT:END -->

## 4. 维护说明
每次有意义变更后执行 `./.venv/bin/python tools/update_project_progress.py` 以更新统计快照。
