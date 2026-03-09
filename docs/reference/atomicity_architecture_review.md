# 功能原子化架构审查

更新时间：2026-03-09

## 已合入主分支的进展说明

以下建议已经以“收敛热点复杂度”的形式部分落地到 `main`：

- `engine/actions/ui_actions.py` 已补齐 selector 生命周期清理，并将 selector/node 细节下沉，保留稳定 facade
- `engine/actions/sdk_actions.py` 已收敛 shared-store 写入路径，补上原子写入、同进程锁与跨进程文件锁
- `core/data_store.py` 已改为原子 JSON 写入
- 任务控制面已拆为 `TaskController` façade、`TaskExecutionService`、`TaskAttemptFinalizer`、`TaskMetricsService`，执行生命周期、终态策略和指标导出不再继续堆进 `core/task_control.py`

以下建议在当前 `main` 上仍然应作为长期 watchpoint，但不再都属于未完成阻塞项：

- `core/task_control.py` 的 façade 边界继续保持稳定，避免执行/观测/补偿规则回流
- 插件层重复 fallback 的 composite action 收敛（当前主分支上的 `x_mobile_login` workflow 形态与最初审查时不同，因此未在本轮强行推进）

如果只关心“现在已经修了什么”和“哪些项只保留为 watchpoint”，请优先看：

- `docs/reference/功能原子化修复结果.md`
- `docs/reference/功能原子化问题分类说明.md`
- `docs/reference/sdk_actions_followup_assessment.md`
- `docs/reference/shared_json_store_watchpoint.md`
- `docs/reference/x_mobile_login_compression_watchpoint.md`

## 结论

- 当前主干架构仍然成立：`Runner -> Interpreter -> ActionRegistry -> Plugin Workflow` 的分层没有失效。
- 当前风险不在“架构方向错误”，而在“局部热点持续膨胀”。
- `engine/actions/ui_actions.py`、`engine/actions/sdk_actions.py` 仍然跨过舒适维护区间，开始表现出 God module / orchestration leakage 特征。
- `core/task_control.py` 的热点已经降级，但任务控制面整体仍需继续守住 service 边界。
- 插件层整体仍可用，但 `plugins/x_mobile_login/script.yaml` 已经成为明显异常值，说明缺少少量合适粒度的复合动作，导致工作流脚本承担了过多编排细节。

## 证据摘要

- `engine/actions/ui_actions.py`：约 1340 行
- `engine/actions/sdk_actions.py`：约 1177 行
- `core/task_control.py`：已收缩为 façade，执行/终态/指标逻辑已外移
- `plugins/x_mobile_login/script.yaml`：约 705 行
- `plugins/profile_clone/script.yaml`：约 234 行

这些数字本身不是问题，问题在于它们同时伴随职责混合。

## 分层判断

### 1. Action 层

现状：

- `engine/actions/browser_actions.py` 边界最清晰，基本保持“一个能力族，一个模块”。
- `engine/actions/ui_actions.py` 混合了 RPC 连接、点击/滑动/输入、app/device 帮助函数、截图能力，以及 selector/node 子系统。
- `engine/actions/sdk_actions.py` 混合了 SDK 绑定、参数构造、共享状态读写、UI 配置加载，以及一部分策略性逻辑。
- `engine/actions/state_actions.py` 与 `engine/actions/ui_actions.py` 存在重复的 RPC 连接/关闭模式。

问题：

- Action 本应是“稳定、可复用、单一职责”的能力入口，但当前部分模块已同时承担能力定义、连接管理、策略选择、参数拼装。
- 重复的 RPC 接入逻辑意味着后续任何连接策略变化都要改多处，容易漂移。
- `ui_actions` 的 selector/node 子系统已经接近一个独立小框架，不适合继续塞在同一个动作文件里。

判断：

- Action 注册机制是合理的。
- Action 模块边界已经开始失真，需要按能力族二次拆分。

### 2. Plugin 层

现状：

- 大多数插件仍然符合“单业务工作流”的方向。
- `plugins/profile_clone/script.yaml`、`plugins/dm_reply/script.yaml`、`plugins/quote_interaction/script.yaml` 体量偏大但仍处于可接受范围。
- `plugins/x_mobile_login/script.yaml` 体量明显过大，且包含大量重复性的 selector 加载、点击回退、输入回退、状态分支。

问题：

- 这不是单纯“插件太长”，而是 action 粒度过低，导致工作流被迫显式展开大量重复细节。
- 当插件脚本开始重复“同一业务意图的多个低层 fallback 组合”时，说明应该新增复合动作，而不是继续堆 YAML。

判断：

- Plugin as workflow 的方向仍然正确。
- 需要控制插件脚本增长，避免插件层承担本应下沉到 action/composite action 的复杂性。

### 3. Core 调度层

现状：

- `core/task_store.py`、`core/task_queue.py`、`core/task_events.py` 的职责总体清晰。
- `core/task_control.py` 现在主要保留提交、查询、取消入口和 façade 编排。
- `core/task_execution.py` 负责 worker 生命周期、stale recovery、pending 重入队和执行 fan-out。
- `core/task_finalizer.py` 负责 retry/cancel/fail 的终态收敛和 failure feedback hook。
- `core/task_metrics.py` 负责指标聚合和 Prometheus 文本导出。

问题：

- 任务控制面虽然已经拆开，但 `TaskExecutionService` 仍是后续最容易继续膨胀的新热点。
- dispatch runtime 接线和终态事件契约需要继续保持在独立 service 内，不要回流到 façade。
- 后续如果增加新的补偿或观测规则，仍然有再次形成控制面热点的风险。

判断：

- Core 的三分结构是对的。
- 当前主要风险已经从 `TaskController` 本身转为“是否继续守住 execution/finalizer/metrics 的 service 边界”。

## 当前最不合理的设计点

按优先级排序：

1. `engine/actions/ui_actions.py` 将 RPC 基础能力与 selector/node 子系统塞在同一模块
2. `engine/actions/sdk_actions.py` 将 SDK 绑定、参数装配、共享状态和策略逻辑混在一起
3. `engine/actions/state_actions.py` 与 `engine/actions/ui_actions.py` 存在重复 RPC 接入模式
4. `plugins/x_mobile_login/script.yaml` 作为单插件工作流已经过长，且重复模式太多
5. 任务控制面新增需求如果绕过 service 边界，仍可能重新长回总控制器

## 建议优先拆分的切口

### 第一优先级

- 提取统一 RPC helper，供 `engine/actions/ui_actions.py` 与 `engine/actions/state_actions.py` 共用
- 守住任务控制面的 façade/service 边界，避免执行/观测/补偿逻辑回流到 `core/task_control.py`

### 第二优先级

- 将 `engine/actions/ui_actions.py` 拆成两层：基础 UI/RPC 动作、selector/node 子系统
- 将 `engine/actions/sdk_actions.py` 拆成内部子模块：SDK 绑定、参数构造、共享状态、配置装载

### 第三优先级

- 为 `plugins/x_mobile_login/script.yaml` 增加少量复合动作，减少重复 fallback 编排
- 对超长插件建立脚本长度与重复模式审查机制

## 这次不建议做的事

- 不建议重写 workflow engine
- 不建议推翻现有 plugin contract
- 不建议一次性重命名大批 action namespace
- 不建议把所有复杂逻辑都继续上推到 plugin 层

## 项目约束建议

建议把以下约束写入项目规则：

- API route 保持薄层，不接业务策略
- `TaskController` 仅负责 orchestration，不直接承载业务补偿/业务反馈规则
- 任务执行循环、终态策略、指标导出分别落在独立 service，不得重新合并回一个控制器类
- 新 action 优先复用共享连接 helper，禁止复制 RPC 接入模板
- 当单个 action 模块开始同时包含“连接管理 + 参数策略 + 业务逻辑 + mini framework”时，必须拆分
- 当插件 workflow 开始重复 3 次以上相同 fallback 组合时，应新增复合 action，而不是继续复制 YAML
- 对超长脚本和超长动作模块做架构复核，不以“功能能跑”作为唯一通过标准

## 建议的下一步

1. 继续做 action 层低风险整理：提取共享 RPC helper
2. 再做一次边界清理：拆分 `ui_actions` 与 `sdk_actions` 的内部职责
3. 最后针对 `x_mobile_login` 做收敛：新增 2-3 个复合动作，压缩脚本长度和重复段

## 适用范围

本结论用于指导：

- 后续 action 新增方式
- plugin workflow 规模控制
- core 调度层的职责边界
- `AGENTS.md` 中的项目级复杂度约束
