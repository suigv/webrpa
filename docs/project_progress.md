# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**Web Console Productization & Navigation Engine Hardening**
- 核心状态：API、任务系统、插件执行、账号池全面可用；Web 控制台完成产品化改造；导航引擎具备自愈与锚点机制；AI 执行引擎接入托管链路。
- 最近重点 (2026-03-16):
  - **AgentExecutor 自反思能力增强 (Phase 4 - Self-Reflection Hardening)**：
    - **执行轨迹摘要 (History Digest)**：实现了基于滑动窗口（默认最近 5 步）的执行历史压缩注入，为 Planner 提供了必要的短期记忆，有效防止了在错误路径上的盲目循环。
    - **失败感知与自修正 (Failure-Aware Reflection)**：建立了动作执行结果的闭环反馈机制。当动作失败时，自动注入包含错误码、原因及修正建议的反思块，引导 Planner 动态调整策略。
    - **重复动作熔断机制 (Repeated Action Breaker)**：引入了动作指纹检测技术。针对连续重复同一 (action, params) 组合的行为进行识别并发出反思警告，从根本上杜绝了无效重试导致的预算浪费。
    - **观测指标富化**：Trace 记录现已完整包含反思元数据、历史摘要长度及重复计数，为后续离线蒸馏与热修复提供了精准的数据支撑。
  - **Skills-Driven 架构演进 (Phase 3 - UI 动作模块化与回归修复)**：
    - **UI 动作深度拆分**：彻底重构并解耦了 `ui_actions.py`，建立了 `ui_touch`, `ui_input`, `ui_selector`, `ui_app`, `ui_device` 五大专有子模块。
    - **RPC 链路对齐与一致性同步**：引入了基于装饰器的 monkeypatch 实时同步机制，解决了多进程/多环境下的 mock 逃逸问题，确保了 RPC 状态在全链路的一致性。
    - **回归测试 100% 达成**：修复了 `selector_click_one` 等核心动作的执行序列偏差，实现了对旧版测试套件 100% 的兼容性回归。
    - **硬件适配层稳固**：在 `MytRpc` 中补全了 PascalCase 别名，确保了硬件驱动接口与上层应用调用的精确匹配。
  - **任务执行鲁棒性加固 (Task Execution Resilience)**：针对自动化测试与本地开发环境，将 `ActiveTargetCircuitBreaker` 熔断机制改为基于 RPC 状态按需触发，解决了 `MYT_ENABLE_RPC=0` 模式下因网络探测失败导致的误报 FAILED 状态。
  - **RPC 特性开关一致性**：统一了系统与测试中对 `MYT_ENABLE_RPC` 环境变量的优先级处理，确保 Feature Flag 在全链路上严格生效。
  - **架构硬化验证完成**：完成了 `BaseStore` (SQLite)、`ConfigLoader` (Pydantic) 以及 `CloudProbeService` (Probing) 的全量集成验证，通过了 280+ 项测试用例的回归校验。
- 最近重点 (2026-03-15)：
  - **设备可用性提前熔断**：`DeviceManager` 新增 probe 订阅接口；任务执行链路会把当前 target 的 probe 离线信号并入取消判断，线程模式直接订阅，子进程模式由父进程监控活跃 target 并回传熔断理由，最终统一以 `failed_circuit_breaker` / `target_unavailable` 终止，而不是等待 RPC 超时。
  - **工具链根路径收敛与 Binding 草稿降欠账**：`tools/*.py` 的仓库根目录解析已统一收口到共享 bootstrap + `core.paths`，`tools/distill_binding.py` 生成的 NativeStateBinding 草稿改为输出可直接运行的启发式 detector，不再留 `NotImplementedError` 占位。
  - **框架去业务关键词 (Framework Neutrality)**：将登录阶段/关注/未读等默认 UI 识别 marker 从框架代码迁移到 `config/strategies/*.yaml`，框架层不再硬编码“首页/主页/关注”等业务词，支持按 action params/session defaults 覆盖。
  - **API 边界加固**：
    - `/api/tasks/distill/{plugin_name}`：加入 `plugin_name` 严格校验与输出目录边界约束（仅允许写入 `plugins/` 下），并将蒸馏门槛从插件 `manifest.yaml` 的 `distill_threshold` 读取，路由层不再硬编码。
    - `/api/devices/{device_id}/{cloud_id}/screenshot`：移除 `device_ip/rpa_port` 入参，改为从配置推导目标与端口公式计算，避免越权/SSRF 风险；`MYT_ENABLE_RPC=0` 时返回 503。
  - **WebSocket 事件桥接稳固性**：DB poller 改为可停止线程并移除私有 `_connect()` 依赖，避免 shutdown 后线程泄露。
  - **账号池架构升级 (SQLite & BaseStore Migration)**：完成了从 JSON 到 SQLite 的原子化迁移与自动平滑解。
  - **AI 辅助 Binding 工坊集成 (Binding Master)**：内置 UI 特征提取、AI 绑定生成及前端可视化集成。
  - **AI 术语与命名去硬编码 (Agent Executor)**：确立了厂商中立的智能体运行时架构。
  - **行为拟真引擎优化 (Behavioral Hardening)**：基于人类行为学研究优化了三档预设参数（延迟、停顿、按压时长），并在前端增加了全方位的「使用建议」引导，助力高风控平台（如 X/TikTok）的对抗能力。
  - **细节修正与系统稳固性 (本会话)**：修复了 Binding 工坊前端 Typo、接管页参数丢失、以及 VLM 客户端测试崩溃等隐患。
  - **坐标分辨率精准化与动作语义演进 (Coordinate & Semantic Hardening)**：
    - **云机分辨率动态感知**：重构了 `_resolve_coords` 逻辑，实现了基于 RPC 现场的 `wm size` 自动探测与缓存，解决了云机（如 720p 镜像）分辨率覆盖导致的点击偏移问题。
    - **UI 运行时类型加固**：全面清理了 `ui_actions` 及 `runtime.py` 中的潜在崩溃风险，补齐了跨环境 RPC 实例的 `None` 检查和二进制截图数据的字节显式断言。
    - **Selector 动作富感知与对齐升级**：完全重写了 `ui.selector_click_one`。现支持自动提取目标节点的物理边界 (`bounds`)，并通过新增的 `align` 参数（如 `bottom_right`）实现节点内的精准相对位移点击。同时将点击步骤降级代理给 `ui.click`，从而无缝承接拟人化指纹，并返回附带 `node_text` / `node_bounds` 的富感知 (Rich Perception) 结果，大幅增强了 AI 智能体“闭环反思”能力。
    - **运行上下文修复**：修正了 `ExecutionContext` 中 `device_id` 的提取路径（从 `runtime.target` 提取），确保分辨率自动发现机制在生产链路下能正确触发。
    - **全量动作同步**：同步更新了 `click`, `touch`, `swipe`, `long_click` 等 6 类核心动作，全面支持归一化坐标 (`nx`, `ny`) 在跨分辨率环境下的像素级精准转换。

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
  - **AI 执行引擎 (Agent Executor)**：
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
  - **VLM 视觉坐标完美映射补偿 (2026-03-14)**：
    - **物理分辨率感知 (Physical Resolution Awareness)**：在 `DeviceManager` 中引入物理宽高追踪，并在 `capture_compressed` 中集成 `wm size` 自动探测与缓存机制，彻底解决 VLM 观察分辨率与执行分辨率不匹配的点击偏移。
    - **坐标换算加固**：重构 `ai.locate_point` 逻辑，强制优先使用探测到的物理分辨率进行 `norm_1000` 坐标强制转换，确保模型在大屏幕或缩放屏幕下的定位精度。
    - **规划器同步校准**：同步更新 `agent_executor` 的 VLM 决策逻辑及证据采集链路，确保端到端的视觉坐标一致性。
    - **验证体系**：新增 `tests/test_coordinate_mapping.py` 覆盖不同屏幕比例下的缩放补偿逻辑。
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
  - **决策层完全解耦 (Architectural Decoupling)**：
    - **Planner 抽象层 (防波堤 1)**：新增 `engine/planners.py`，将 `AgentExecutorRuntime` 中的硬编码决策逻辑（LLM/VLM 调用、Prompt 组装）抽离为 `BasePlanner` 协议。引入 `StructuredPlanner`（生产基线）和 `OmniVisionPlanner`（实验性多模态，`MYT_EXPERIMENTAL_OMNIVISION=1` 开启）。执行器循环现在通过不可变的 `PlannerInput`/`PlannerOutput` 契约与决策大脑通信，实现物理隔离。
    - **旁路蒸馏增强 (防波堤 2)**：在 `core/golden_run_distillation.py` 中新增 `LLMDraftRefiner`。在启发式参数化完成后，通过可选的 LLM 旁路分析 YAML 寻找额外的硬编码业务参数并抽取为 `${payload.xxx}`。完全静默失败回退机制保证了核心蒸馏流程的绝对稳定性（新增 `--use-llm-refiner` CLI 支持）。

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

- 最近重点 (2026-03-15)：
  - **账号池架构升级 (SQLite & BaseStore Migration)**：
    - 针对账号库抽号并发与一致性隐患，完成了从 JSON 文本到 SQLite 的全面迁移。
    - 引入 `AccountStore` 模块实现原子化 `pop_account` 与事务级状态更新。
    - 实现从 `accounts.json` 到 SQLite 的自动平滑解迁移机制。
  - **AI 辅助 Binding 工坊集成 (Binding Master)**：
    - 将 `binding_observer.py` 逻辑提取为 `engine/binding_distiller.py` 核心服务并在 Web 控制台前端实现 UI 集成。
    - 提供实时 UI 节点特征分析与 AI 驱动的 Python 绑定代码生成。
  - **AI 术语与命名去硬编码 (Agent Executor)**：
    - 全量重命名 `GPT Executor` -> `Agent Executor`，确立厂商中立的运行时架构。
  - **VLM 架构通用化重构**：
    - 废弃 UI-TARS 专有逻辑，建立通用的 `VLMProvider` 协议，支持多厂商插件化接入。
  - **细节修正与系统稳固性 (本会话)**：
    - 修复了 `binding.js` 中的 `json.stringify` 拼写错误。
    - 修复了接管页面 `currentDeviceId` 丢失导致的采集参数缺失问题。
    - 修正了 `AccountStore.pop_ready_account` 在 SQLite 事务中的返回对象缺陷。
    - 修复了 `test_llm_client.py` 中因 `VLMClient` 构造函数变更引起的测试崩溃。

- 最近重点 (2026-03-14)：
  - **VLM 架构对齐 (VLM Architecture Alignment)**：
    - **多服务商注册制**：重构了 `vlm_client.py`，引入 `VLMProvider` 协议，使 VLM 架构与 LLM 保持完全一致。
    - **配置标准化**：`VLMSettings` 现在也支持 `providers` 字典，消除了对 UI-TARS 的硬编码依赖。
    - **API Key 隔离**：支持 `MYT_VLM_API_KEY_{PROVIDER}` 环境变量，实现了安全的密钥管理。
  - **LLM 多服务商支持 (Multi-Provider Registry)**：
    - **配置解耦**：重构了 `system.yaml` 结构，支持在 `services.llm.providers` 下预设多个厂商配置（DeepSeek, OpenAI, SiliconFlow 等）。
    - **API Key 分级注入**：增强了 `get_llm_api_key`，支持 `MYT_LLM_API_KEY_DEEPSEEK` 这种特定前缀的 Key，确立了“特定服务商 -> 全局兜底”的密钥查找优先级。
    - **动态协议解析**：`LLMClient` 现支持根据配置的 `provider_type` 动态下发任务，消除了对 OpenAI 协议的硬编码依赖。
  - **视觉坐标系统与稳定性加固 (Hardening)**：
    - **VLM 坐标映射修正**：彻底解决了 `ai.locate_point` 中因物理尺寸与截图尺寸混淆导致的点击偏移。确立了“原图坐标系空间观察 -> 物理屏幕空间映射”的标准转换链路，完美支持像素模式与横屏动态补偿。
    - **任务取消灵敏度优化**：为 `agent_executor` 引入了 `_interruptible_sleep` 机制，将 Planner 级退避重试改为短脉冲轮询，确保在 8s 级重试回退期间仍能实现 2s 内的任务取消响应。
    - **架构解耦 (App Config)**：建立了核心层 `core/app_config.py` (AppConfigManager)，将应用配置发现、骨架生成从 `agent_executor` 与 `sdk_config_support` 中抽离，消除了执行层对动作辅助模块的反向依赖。
    - **性能底座优化**：在 `ExecutionContext` 中引入了物理分辨率会话级缓存，将 `wm size` 的 RPC 调用开销降至最低。
  - [x] 提取数据库基类 (`BaseStore`)，消除 `TaskStore` 与 `TaskEventStore` 的重复代码。
- [x] 废弃 `common/config_manager.py`，全面收敛至 `core/config_loader.py`。
- [x] 引入 Pydantic 重构配置解析逻辑，替代手动 JSON 校验。
- [x] 拆分 `DeviceManager`，将云机探测逻辑移至独立服务。
- [x] 修复 AI 模块隐患：VLM 连接泄露处理及基于 `retryable` 标记的退避重试。
  - **AI 对话架构改进 (2026-03-11)**：
    - **修复无 binding 场景下的 fingerprint 计算**：`agent_executor` 在 `observation.ok=False` 时改用 UI XML 内容计算停滞 fingerprint，防止在无 binding 场景下错误触发死循环熔断。
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
- 托管 `agent_executor` 自主智能体运行时。
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
| API route decorators (`api/routes`) | 41 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 4 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 154 |
| Test files (`tests/test_*.py`) | 55 |
| Test functions (`def test_*`) | 270 |
<!-- AUTO_PROGRESS_SNAPSHOT:END -->

## 4. 维护说明
每次有意义变更后执行 `./.venv/bin/python tools/update_project_progress.py` 以更新统计快照。
