# `sdk_actions` follow-up assessment

更新时间：2026-03-08

## 结论

**Verdict: Split recommended later**

当前 `engine/actions/sdk_actions.py` 已经明显超出“单一 action 集合”的舒适区间，但还没有像此前的 `ui_actions` 那样，出现 selector/node 子系统、RPC 生命周期治理、独立 helper 已经成型却仍被强塞在 facade 中的即时拆分信号。

这次更适合保留为观察结论，而不是直接在本任务里做运行时代码抽离。原因有两点：

- 当前热点已经从 shared-store 破损修复，转成“多类纯函数与配置读取继续堆积在同一文件”的维护风险，参考 `engine/actions/sdk_actions.py:589`、`engine/actions/sdk_actions.py:823`、`engine/actions/sdk_actions.py:978`
- 已落地文档对 `sdk_actions` 的口径仍是“继续观察，但不是当前阻塞项”，参考 `docs/current_main_status.md:18`、`docs/reference/功能原子化修复结果.md:124`

## 评估范围

- 主模块：`engine/actions/sdk_actions.py:1`
- 相邻 helper / adapter：`hardware_adapters/myt_client.py:173`、`core/data_store.py:37`
- 已完成对照模式：`engine/actions/ui_actions.py:6`、`engine/actions/state_actions.py:6`、`engine/actions/_rpc_bootstrap.py:1`、`engine/actions/_ui_selector_support.py:1`、`engine/actions/_state_detection_support.py:1`
- 现有 watchpoint 文档：`docs/current_main_status.md:18`、`docs/reference/atomicity_architecture_review.md:49`、`docs/reference/功能原子化问题分类说明.md:79`、`docs/reference/功能原子化修复结果.md:124`
- 就近测试：`tests/test_sdk_actions_runtime.py:47`、`tests/test_sdk_complete.py:22`、`tests/test_hezi_sdk_probe_plugin.py:4`
- 覆盖规模侧写：`docs/project_progress.md:64`

## 当前复杂度切面

### 1. SDK 绑定与分发

`engine/actions/sdk_actions.py` 仍承担完整的 SDK facade 入口：

- `_sdk_client()` 负责从 payload/params 拼接客户端连接参数，见 `engine/actions/sdk_actions.py:37`
- `_invoke()` 负责统一 client method 查找、参数展开、异常转 `ActionResult`，见 `engine/actions/sdk_actions.py:47`
- `ACTION_BUILDERS` 维持 `sdk.*` 与 `mytos.*` 的大表绑定，见 `engine/actions/sdk_actions.py:445`
- `get_sdk_action_bindings()` 作为动态注册出口，见 `engine/actions/sdk_actions.py:580`

这一层本身是合理 facade，但它和后面的共享状态、配置读取、策略选择仍然处在同一文件。

### 2. 参数构造

参数构造是当前文件里最显眼的体量来源之一。

- `sdk_actions.py` 里有 `54` 个 `_args_*` builder，统计见 `engine/actions/sdk_actions.py:156`
- 这些 builder 横跨云机、镜像、备份、代理、触控、文件传输、系统能力多个能力族，终点统一汇入 `ACTION_BUILDERS`，见 `engine/actions/sdk_actions.py:445`
- `docs/project_progress.md:64` 记录当前已注册 `131` 个 SDK action binding，说明这里已经是高扇出入口，不是少量帮助函数

这部分现在主要是“长表 + 轻量 builder”。问题不是单个函数复杂，而是数量和能力族都在增长。

### 3. Shared-state 持久化

shared-store 热点已经从“脆弱实现”变成“集中在单文件维护”。

- `_shared_path()`、`_exclusive_shared_lock()`、`_update_store()` 负责路径、进程内锁、跨进程文件锁和原子写入，见 `engine/actions/sdk_actions.py:589`、`engine/actions/sdk_actions.py:600`、`engine/actions/sdk_actions.py:627`
- 底层原子写由 `core/data_store.py:37` 的 `write_json_atomic()` 提供
- 面向 workflow 的状态动作集中在 `save_shared()`、`load_shared_optional()`、`append_shared_unique()`、`increment_shared_counter()`，见 `engine/actions/sdk_actions.py:662`、`engine/actions/sdk_actions.py:685`、`engine/actions/sdk_actions.py:699`、`engine/actions/sdk_actions.py:754`
- 回归测试已把共享 JSON 的有效性和并发更新固定下来，见 `tests/test_sdk_actions_runtime.py:101`、`tests/test_sdk_actions_runtime.py:112`、`tests/test_sdk_actions_runtime.py:139`

这里说明 shared-store 本身已经不再是“立刻要救火的坏味道”。如果后续要拆，更像是为了边界清晰，而不是为了修 correctness。

### 4. 配置加载

当前文件还承担了三组配置装载责任：

- UI 配置路径与文档读取，见 `engine/actions/sdk_actions.py:823`、`engine/actions/sdk_actions.py:836`
- nurture keyword 策略读取，见 `engine/actions/sdk_actions.py:847`、`engine/actions/sdk_actions.py:860`
- interaction text 模板读取，见 `engine/actions/sdk_actions.py:871`、`engine/actions/sdk_actions.py:887`

这类逻辑本质上已经不属于 SDK binding。它们更接近“workflow support config access”。

### 5. 策略 / 业务辅助逻辑

当前文件的后半段还混有多类轻策略动作：

- 云机轮询策略：`wait_cloud_status()`，见 `engine/actions/sdk_actions.py:93`
- 日计数规则：`check_daily_limit()`、`increment_daily_counter()`，见 `engine/actions/sdk_actions.py:930`、`engine/actions/sdk_actions.py:957`
- nurture 关键词与黑名单策略：`pick_weighted_keyword()`、`is_text_blacklisted()`，见 `engine/actions/sdk_actions.py:978`、`engine/actions/sdk_actions.py:1023`
- DM / quote 模板生成：`generate_dm_reply()`、`generate_quote_text()`，见 `engine/actions/sdk_actions.py:1057`、`engine/actions/sdk_actions.py:1080`
- blogger candidate 选择与资料派生：`pick_candidate()`、`derive_blogger_profile()`、`save_blogger_candidates()`，见 `engine/actions/sdk_actions.py:1179`、`engine/actions/sdk_actions.py:1282`、`engine/actions/sdk_actions.py:1303`
- UI selector / scheme 配置查询：`load_ui_value()`、`load_ui_selector()`、`load_ui_scheme()`，见 `engine/actions/sdk_actions.py:1393`、`engine/actions/sdk_actions.py:1410`、`engine/actions/sdk_actions.py:1443`

这些函数大多是纯函数或轻 I/O 包装，所以风险没有 `ui_actions` 当时那么尖锐，但职责边界已经混杂得很明显。

## 与 `ui_actions` / `state_actions` 已完成拆分的对比

### 已完成拆分长什么样

当前主分支里，`ui_actions` / `state_actions` 的收敛模式已经很清楚：

- facade 文件只保留稳定入口与 monkeypatch surface，见 `engine/actions/ui_actions.py:20`、`engine/actions/state_actions.py:20`
- 共享 RPC bootstrap 已抽到 `engine/actions/_rpc_bootstrap.py:1`
- selector/node 子系统已下沉到 `engine/actions/_ui_selector_support.py:1`
- state detection / XML candidate parsing 已下沉到 `engine/actions/_state_detection_support.py:1`
- 成果文档明确把这组变化定义为“facade 拆分已完成”，见 `docs/reference/功能原子化修复结果.md:44`

### `sdk_actions` 有没有跨过同一阈值

**已经接近，但还没有完全跨过 `ui_actions` 当时的同类阈值。**

相同点：

- 都是大文件，且混合多类职责，`docs/reference/atomicity_architecture_review.md:28` 早就把它列为热点
- 都保留稳定 facade 价值，不适合直接拆碎 action namespace
- 都存在“如果继续把新逻辑堆进去，之后只会更难拆”的趋势

不同点：

- `ui_actions` 当时已经有 selector/node 子系统和 RPC 生命周期问题，拆分直接对应资源释放与契约稳定收益，见 `docs/reference/功能原子化修复结果.md:13`、`docs/reference/功能原子化修复结果.md:28`
- `sdk_actions` 当前的复杂度更偏“多族群纯函数共居”，而不是“正在失控的运行时子系统”
- `sdk_actions` 的 shared-store correctness 已由原子写和并发测试兜住，近期没有证据表明这里还存在像 selector 生命周期那样的即时报错面，见 `tests/test_sdk_actions_runtime.py:101`
- 现有插件和映射文档仍把 `engine/actions/sdk_actions.py` 当成统一 SDK/MYTOS facade 使用，见 `docs/reference/hezi_sdk_atomic_mapping.md:8`、`docs/reference/pdf_feature_usability_checklist.md:46`

所以，`sdk_actions` 已经跨过“值得持续看守”的阈值，但还没有出现“必须现在拆，否则当前 runtime 风险持续外溢”的证据。

## 现阶段最值得记录的 concern clusters

按后续最可能的拆分方向看，当前可以清楚分成五组：

1. **SDK bindings / dispatch**: `_sdk_client()`、`_invoke()`、`ACTION_BUILDERS`、`get_sdk_action_bindings()`，见 `engine/actions/sdk_actions.py:37`、`engine/actions/sdk_actions.py:445`
2. **parameter builders**: `_args_*` 系列，见 `engine/actions/sdk_actions.py:156`
3. **shared-state persistence**: `_shared_path()` 到 `increment_shared_counter()`，见 `engine/actions/sdk_actions.py:589`
4. **config loading**: `_ui_config_paths()`、`_strategy_config_paths()`、`_interaction_text_config_paths()` 及各自 loader，见 `engine/actions/sdk_actions.py:823`
5. **strategy / policy helpers**: `wait_cloud_status()`、nurture / DM / blogger / UI lookup 系列，见 `engine/actions/sdk_actions.py:93`、`engine/actions/sdk_actions.py:978`

如果未来要拆，最自然的方式不是改 action 名称，而是保持 facade，先把这些内部族群下沉到 helper 子模块。

## 为什么这次不建议立刻拆

- 当前证据更多指向“维护面偏宽”，不是“已有运行时子系统故障正在持续发生”
- shared-store、客户端映射、插件探针都有测试兜底，见 `tests/test_sdk_actions_runtime.py:47`、`tests/test_sdk_complete.py:22`、`tests/test_hezi_sdk_probe_plugin.py:4`
- 现有文档已经把 `sdk_actions` 定位成 watchpoint，而不是 remediation blocker，见 `docs/current_main_status.md:18`、`docs/reference/功能原子化修复结果.md:124`
- 直接在这个 follow-up 任务里开拆，会把“评估”变成“隐式重构”，不符合当前计划边界

## 会触发重新排期的信号

后续如果出现以下任一信号，就该把 split 从 backlog 提到当前工作：

- `sdk_actions.py` 再新增一整组配置读取或 shared-state 规则，继续把 workflow support 堆进 facade
- `_args_*` builder 数继续上升，且新增 builder 已经需要按能力族分段维护
- 新测试开始不得不大量 monkeypatch `sdk_actions` 内部 helper，而不是只替换 `MytSdkClient`
- 文档或插件开始依赖更多非 SDK 的 `sdk_actions` 辅助动作，说明 facade 正在吸收越来越多业务支持逻辑
- 需要为 shared-store、策略读取、UI 配置读取分别引入不同的缓存、隔离或错误契约

## 最终判断

- 当前判断：**Split recommended later**
- 当前动作：继续保持 `engine/actions/sdk_actions.py` 为稳定 facade，不在这次任务里做代码拆分
- 后续建议：若再新增一组 config/policy/shared-state 能力，优先做内部 helper 下沉，目标形态参考 `ui_actions` / `state_actions` 已完成的 facade + helper 模式
