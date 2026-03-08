# `sdk_actions` follow-up assessment

更新时间：2026-03-08

## 结论

**Verdict: Split landed, keep as watchpoint**

当前主分支已经完成 task 7 对应的内部拆分：`engine/actions/sdk_actions.py` 继续作为稳定 facade，对外保留 `sdk.*` / `mytos.*` action 绑定、registry 入口与 monkeypatch surface；运行时、配置、shared-store、profile 与业务辅助逻辑已经拆到 `sdk_*_support.py` helper 模块。

本 follow-up 文档的职责不再是说明“以后再拆”，而是记录拆分后的现状和后续观察点：

- 已落地形态是 `sdk_actions.py` facade + `sdk_runtime_support.py`、`sdk_config_support.py`、`sdk_shared_store_support.py`、`sdk_profile_support.py`、`sdk_business_support.py`
- 当前结论是“拆分已完成，但仍需继续观察 facade 是否再次吸收过多 workflow support 逻辑”

## 评估范围

- 主模块：`engine/actions/sdk_actions.py:1`
- 相邻 helper / adapter：`engine/actions/sdk_runtime_support.py`、`engine/actions/sdk_config_support.py`、`engine/actions/sdk_shared_store_support.py`、`engine/actions/sdk_profile_support.py`、`engine/actions/sdk_business_support.py`、`hardware_adapters/myt_client.py`、`core/data_store.py`
- 已完成对照模式：`engine/actions/ui_actions.py`、`engine/actions/state_actions.py`、`engine/actions/_rpc_bootstrap.py`
- 现有 watchpoint 文档：`docs/current_main_status.md`、`docs/reference/atomicity_architecture_review.md`、`docs/reference/功能原子化问题分类说明.md`、`docs/reference/功能原子化修复结果.md`
- 就近测试：`tests/test_sdk_actions_runtime.py:47`、`tests/test_sdk_complete.py:22`、`tests/test_hezi_sdk_probe_plugin.py:4`
- 覆盖规模侧写：`docs/project_progress.md:64`

## 已落地拆分形态

### 1. facade 仍保留稳定入口

`engine/actions/sdk_actions.py` 现在仍负责几类对外稳定面：

- `_sdk_client()` 与 `_invoke()` 维持统一 client 构造、方法查找与 `ActionResult` 包装
- `ACTION_BUILDERS` 和 `get_sdk_action_bindings()` 继续作为统一注册出口
- facade wrapper 继续保留便于测试 monkeypatch 的函数名，例如 `wait_cloud_status()`、`save_shared()`、`load_ui_selector()`、`pick_weighted_keyword()`

### 2. 内部 helper 已按职责下沉

- `sdk_runtime_support.py` 承担 `wait_cloud_status`、TOTP、daily counter、UI selector/value/scheme 等运行时辅助逻辑
- `sdk_config_support.py` 负责 UI、strategy、interaction text、daily counter 相关配置和文档读取
- `sdk_shared_store_support.py` 负责 shared-store 路径、锁、读写与 shared action 实现
- `sdk_profile_support.py` 负责 blogger profile 派生
- `sdk_business_support.py` 负责 keyword、blacklist、DM/quote、candidate 等轻业务辅助动作

这说明 task 7 的 repo-backed 结论已经从“建议 later split”变成“已按 facade + helper 形态落地”。

## 当前复杂度切面

### 1. SDK 绑定与分发

`engine/actions/sdk_actions.py` 仍承担完整的 SDK facade 入口：

- `_sdk_client()` 负责从 payload/params 拼接客户端连接参数
- `_invoke()` 负责统一 client method 查找、参数展开、异常转 `ActionResult`
- `ACTION_BUILDERS` 维持 `sdk.*` 与 `mytos.*` 的大表绑定
- `get_sdk_action_bindings()` 作为动态注册出口

这一层现在已经和后面的 shared-store、配置读取、策略选择解耦，剩余风险主要是 facade 未来是否再次把 helper 逻辑吸回单文件。

### 2. 参数构造

参数构造仍是 facade 里最显眼的体量来源之一。

- `sdk_actions.py` 里仍保留大量 `_args_*` builder
- 这些 builder 横跨云机、镜像、备份、代理、触控、文件传输、系统能力多个能力族，终点统一汇入 `ACTION_BUILDERS`
- `docs/project_progress.md:64` 记录当前已注册 `131` 个 SDK action binding，说明这里已经是高扇出入口，不是少量帮助函数

这部分现在主要是“长表 + 轻量 builder”。问题不是单个函数复杂，而是数量和能力族都在增长。

### 3. Shared-state 持久化

shared-store 热点已经从“集中在单文件维护”变成“helper 已拆出，但仍需继续看边界是否稳定”。

- `_shared_path()`、`_exclusive_shared_lock()`、`_update_store()` 这些 facade wrapper 现在委托给 `sdk_shared_store_support.py`
- 底层原子写由 `core/data_store.py:37` 的 `write_json_atomic()` 提供
- 面向 workflow 的状态动作仍由 `save_shared()`、`load_shared_optional()`、`append_shared_unique()`、`increment_shared_counter()` 暴露，但内部实现已在 helper 模块
- 回归测试已把共享 JSON 的有效性和并发更新固定下来，见 `tests/test_sdk_actions_runtime.py:101`、`tests/test_sdk_actions_runtime.py:112`、`tests/test_sdk_actions_runtime.py:139`

这里说明 shared-store 的 correctness 问题已收口，后续更多是观察 facade 和 helper 边界是否继续清晰。

### 4. 配置加载

当前 facade 仍保留配置读取入口，但实际装载责任已经下沉：

- UI 配置路径与文档读取通过 `sdk_config_support.py`
- nurture keyword 策略读取通过 `sdk_config_support.py` + `sdk_business_support.py`
- interaction text 模板读取通过 `sdk_config_support.py`

这类逻辑本质上已经从 SDK binding facade 中抽离到 support 层，当前只保留显式转发面。

### 5. 策略 / 业务辅助逻辑

当前 facade 后半段仍暴露多类轻策略动作，但实现也已分散到 helper：

- 云机轮询策略：`sdk_runtime_support.py`
- 日计数规则：`sdk_runtime_support.py`
- nurture 关键词与黑名单策略、DM / quote、candidate 逻辑：`sdk_business_support.py`
- blogger profile 派生：`sdk_profile_support.py`
- UI selector / scheme 配置查询：`sdk_runtime_support.py` + `sdk_config_support.py`

这些函数大多是纯函数或轻 I/O 包装，所以拆分后的主要风险不再是“当前 runtime 已失控”，而是未来继续加功能时是否守住 helper 边界。

## 与 `ui_actions` / `state_actions` 已完成拆分的对比

### 已完成拆分长什么样

当前主分支里，`ui_actions` / `state_actions` 的收敛模式已经很清楚：

- facade 文件只保留稳定入口与 monkeypatch surface，见 `engine/actions/ui_actions.py:20`、`engine/actions/state_actions.py:20`
- 共享 RPC bootstrap 已抽到 `engine/actions/_rpc_bootstrap.py:1`
- selector/node 子系统已下沉到 `engine/actions/_ui_selector_support.py:1`
- state detection / XML candidate parsing 已下沉到 `engine/actions/_state_detection_support.py:1`
- 成果文档明确把这组变化定义为“facade 拆分已完成”，见 `docs/reference/功能原子化修复结果.md:44`

### `sdk_actions` 有没有跨过同一阈值

**已经跨过需要内部拆分的阈值，而且当前主分支已经完成第一轮拆分。**

相同点：

- 都是大文件，且混合多类职责，`docs/reference/atomicity_architecture_review.md:28` 早就把它列为热点
- 都保留稳定 facade 价值，不适合直接拆碎 action namespace
- 都存在“如果继续把新逻辑堆进去，之后只会更难拆”的趋势

不同点：

- `ui_actions` 当时更偏 selector/node 子系统和 RPC 生命周期风险，`sdk_actions` 更偏多族群纯函数与 support 逻辑混居
- `sdk_actions` 的 shared-store correctness 已由原子写和并发测试兜住
- 现有插件和映射文档仍把 `engine/actions/sdk_actions.py` 当成统一 SDK/MYTOS facade 使用

所以，repo-backed 的结论已经不是“要不要拆”，而是“拆分已经落地，后续继续看 facade 是否再次膨胀”。

## 现阶段最值得记录的 concern clusters

按后续最可能的拆分方向看，当前可以清楚分成五组：

1. **SDK bindings / dispatch**: `_sdk_client()`、`_invoke()`、`ACTION_BUILDERS`、`get_sdk_action_bindings()`，见 `engine/actions/sdk_actions.py:37`、`engine/actions/sdk_actions.py:445`
2. **parameter builders**: `_args_*` 系列，见 `engine/actions/sdk_actions.py:156`
3. **shared-state persistence**: `_shared_path()` 到 `increment_shared_counter()`，见 `engine/actions/sdk_actions.py:589`
4. **config loading**: `_ui_config_paths()`、`_strategy_config_paths()`、`_interaction_text_config_paths()` 及各自 loader，见 `engine/actions/sdk_actions.py:823`
5. **strategy / policy helpers**: `wait_cloud_status()`、nurture / DM / blogger / UI lookup 系列，见 `engine/actions/sdk_actions.py:93`、`engine/actions/sdk_actions.py:978`

本次落地正是沿用这条路径，保持 action 名称不变，先把内部族群下沉到 helper 子模块。

## 为什么现在仍保留 watchpoint

- shared-store、客户端映射、插件探针都有测试兜底，见 `tests/test_sdk_actions_runtime.py:47`、`tests/test_sdk_complete.py:22`、`tests/test_hezi_sdk_probe_plugin.py:4`
- 但 facade 里仍保留大量 `_args_*` builder 和统一绑定大表，后续继续增长时仍可能把 support 边界拉回单文件
- 当前最合理的 repo-backed 口径是“split completed, keep observing”, 而不是再把它说成 deferred

## 会触发重新排期的信号

后续如果出现以下任一信号，就该把 split 从 backlog 提到当前工作：

- `sdk_actions.py` 再新增一整组配置读取或 shared-state 规则，继续把 workflow support 堆进 facade
- `_args_*` builder 数继续上升，且新增 builder 已经需要按能力族分段维护
- 新测试开始不得不大量 monkeypatch `sdk_actions` 内部 helper，而不是只替换 `MytSdkClient`
- 文档或插件开始依赖更多非 SDK 的 `sdk_actions` 辅助动作，说明 facade 正在吸收越来越多业务支持逻辑
- 需要为 shared-store、策略读取、UI 配置读取分别引入不同的缓存、隔离或错误契约

## 最终判断

- 当前判断：**Split landed, keep as watchpoint**
- 当前动作：继续保持 `engine/actions/sdk_actions.py` 为稳定 facade，新增 support 逻辑优先下沉到现有 `sdk_*_support.py` 模块
- 后续建议：若再新增一组 config/policy/shared-state 能力，优先沿现有 facade + helper 模式扩展，而不是把实现重新堆回 `sdk_actions.py`
