# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。
> 说明：本文件同时包含“当前能力摘要”和“按日期追加的历史变更日志”。涉及当前契约、当前里程碑状态与当前接口语义时，以 `docs/README.md`、`docs/STATUS.md`、`docs/ROADMAP.md`、`docs/HTTP_API.md`、`docs/PLUGIN_CONTRACT.md` 为准；下方较早日期的条目应按历史记录理解，不应直接视为当前实现清单。

## 1. 当前阶段

- 阶段：**Web Console Productization & Navigation Engine Hardening**
- 核心状态：API、任务系统、插件执行、账号池全面可用；Web 控制台完成产品化改造；导航引擎具备自愈与锚点机制；AI 执行引擎接入托管链路。
- 设备接管页当前已支持“截图预览 + 轻控制”：点击截图触发轻触，并提供返回/Home/Enter/退格键、固定方向滑动以及单行文本发送，所有控制仍经由项目 API 转发，不要求浏览器直连设备。
- 已登记未来目标：设备接管页将从“轮询截图预览”演进到“截图预览 + WebRTC 实时接管”双模式，但当前仅作为规划项，尚未进入实现阶段。
- 该目标的前置条件已明确：后端统一下发 WebRTC 访问参数、补齐 WebRTC 端口公式与 helper、发布 `web/webplayer` 静态资源、确认浏览器到设备的网络可达性，并补上访问控制/审计边界。
- 最近重点 (2026-03-17):
  - **Inventory / Selector / Generator 初始化能力落地 (2026-03-19)**：
    - 新增 `core.device_profile_inventory`、`core.device_profile_selector`、`core.device_profile_generator` 三层服务，统一承接“先获取再选择”与“本地随机生成”两类场景。
    - 新增 `inventory.get_phone_models` / `inventory.refresh_phone_models`、`selector.select_phone_model`、`generator.generate_fingerprint` / `generator.generate_contact` / `generator.generate_env_bundle` 动作，插件层可以直接 `save_as` 后复用，不再需要把机型筛选和随机规则硬编码进 YAML。
    - 新增 `selector.resolve_cloud_container` 与 `profile.apply_env_bundle` 动作，插件可从当前 runtime target 自动反查 SDK 容器名，并把语言、指纹、Google ID、联系人、摇一摇、截图等一组环境写入收敛成一次复用动作。
    - 新增 `/api/inventory/phone-models/*`、`/api/selectors/phone-model`、`/api/generators/*` HTTP API；机型库存会缓存到 `config/data/.../inventory/`，默认按需获取，前端也可显式预热。
    - 设备初始化类插件已收敛为 `plugins/one_click_new_device/`；旧的 `mytos_device_setup`、重启、探针等样例插件已从插件库移除，避免目录里同时存在多条重叠能力链路。
    - `plugins/one_click_new_device/` 作为面向运营的“一键新机”插件，用户可在任务面板直接选择机型来源、地区模板、联系人/Google ID/截图等策略项。
    - `manifest.inputs` 已扩展 UI 元数据（`label` / `description` / `advanced` / `widget` / `options`），`/api/tasks/catalog` 会透传这些元数据，Web 任务面板现可按插件声明动态渲染下拉、复选框和数字输入，不再只支持文本框。
    - Web 端插件提交入口已统一追加 manifest 白名单过滤，`one_click_new_device` 不再被设备页/任务页/账号页误注入 `device_ip`、`package`、`app_id` 或账号字段，避免严格模式下触发 `unknown input parameter(s)`。
    - `one_click_new_device` 的运行时目标解析已收敛到 `runtime.target`：环境写入动作会读取当前云机的 `device_ip/api_port`，容器列表接口 `503` 时可按 `cloud_id -> android-XX` 降级解析容器名，避免首步因 SDK 列表瞬时不可用而直接失败。
    - 机型选择新增来源降级：当首选在线/本地库存为空、接口异常或筛选后无候选时，选择器会自动尝试另一来源，并把 `requested_source/source/fallback_used/inventory_attempts` 写回结果，避免一键新机因单侧库存波动直接失败。
    - Web 前端任务弹窗已升级为“提交即拉起、终态自动总结”的任务报告面板；执行完成后左侧会展示汇总结论和目标级结果明细。设备卡片也恢复展示云机机型、状态和控制端口等关键信息，不再只在详情弹窗中可见。
    - `one_click_new_device` 现会默认避开当前机型：当用户不填 `seed` 时，机会从库存中自动随机；插件同时会把切换前机型、选中机型、切换后机型以及环境写入结果汇总，前端弹窗在任务结束后展示报告而不是仅显示运行追踪。
    - 插件契约新增 `distillable`：设备初始化、环境编排、随机化、运维类插件可显式声明 `distillable: false`，目录/指标接口会透出该标记，蒸馏接口也会直接拒绝这类插件；`one_click_new_device` 已按不可蒸馏处理。
    - 插件契约新增 `visible_in_task_catalog`：像 `one_click_new_device` 这类明确不适合客户在任务列表里直接蒸馏/复用的内部编排型插件，默认会从 `/api/tasks/catalog` 隐藏；如需运维排查或管理端查看，可通过 `include_hidden=true` 显式拉取。
    - 任务运行时产物新增自动清理策略：`TaskController.cleanup_runtime_artifacts()` 会按隐藏任务保留天数、事件保留天数、trace 保留天数、事件总行数上限和 trace 总体积上限，自动裁剪 `task_events` 与 `config/data/traces/`；同时暴露 `POST/DELETE /api/tasks/cleanup_runtime` 供人工触发清理，避免非蒸馏型任务长期堆积日志与截图。
    - Web 任务面板与单机执行面板新增“任务说明卡”：选中插件后会直接显示任务用途、默认行为和可调参数标签；`/api/tasks/catalog` 也同步透出插件 `description`，便于客户理解像“一键新机”这类任务可以改哪些参数。
    - Web 设备页进一步补齐参数化体验：单机执行面板的“配置高级属性”现在只控制 manifest 中声明为 `advanced` 的字段，切换任务后会自动复位展开状态；底部批量分发条也新增任务说明卡、参数表单和高级参数展开，批量下发不再只能发空 payload。
    - **冗余与回退治理 (2026-03-19)**：
      - 新增 `core.device_control`，统一直连设备控制链路里的 RPC 目标校验、连接、分辨率发现、归一化坐标换算和截图字节校验；`/api/devices/*` 轻控制路由与 `ui_touch_actions` 现在复用同一套设备控制 helper，不再各自维护 `wm size` 解析和坐标缩放逻辑。
      - **任务终态出口继续收敛**：`TaskAttemptFinalizer` 新增内部 helper，统一承接 retry 事件、terminal 事件和 workflow draft 终态更新；`TaskExecutionService` 的子进程强制取消退出路径也改为复用 finalizer，不再旁路直写 `mark_cancelled + append_event`。
      - **强制取消回归保护**：新增测试固定 `TaskExecutionService._handle_process_exit()` 的 forced-cancel 行为，确保统一走 finalizer 后仍保留 `task.dispatch_result -> task.cancelled(reason=forced_cancel)` 的观测契约。
      - **Native state action 重复骨架收口**：`state_actions.py` 新增局部 helper，统一 `follow_visible_targets/extract_follow_targets` 与 `open_first_unread_dm/extract_unread_dm_targets` 这两组 action 的 XML 提取、默认值回退和候选解析流程，重复逻辑继续留在文件内收敛，不向跨模块抽象扩散。
      - **Action Registry 装配拆分**：`register_defaults()` 已拆成 browser/core/ui/android 四段私有注册函数，保留原有动作名和注册顺序语义不变，同时把后续新增动作的改动面从单个超长函数收敛到对应能力分区。
      - **Agent Executor 主循环瘦身**：`AgentExecutorRuntime.run()` 已把“单步观察”和“单步规划”两段厚逻辑下沉为类内私有 helper，保留原有 planner / trace / 事件契约不变，主循环开始从“超长顺序脚本”收敛成显式步骤状态机。
      - **Selector 包装层去机械重复**：`_ui_selector_support.py` 中 `MytSelector` 的 `addQuery_*` 包装已收敛为统一动态分发，保留 `execQuery* / clear / free` 显式出口不变，减少几十个一行转发方法继续堆积。
      - **RpcNode 字符串 getter 收口**：`_ui_selector_support.py` 中 `RpcNode` 已把 `text/id/class/package/desc/json` 这组完全同型的 handle/object 双路径读取逻辑统一到文件内私有 helper，保留原有返回值、fallback 顺序与公开方法名不变，继续把选择器支持层控制在局部、小步、可回滚的收敛范围内。
      - **RpcNode 通用 helper 继续收敛**：`_ui_selector_support.py` 中 `RpcNode` 进一步统一了 handle 调用入口、带参数的节点方法安全调用和 bounds 归一化逻辑；`parent/child/child_count/bound` 这些分支现在共用文件内 helper，但 `click` 这类返回语义不完全同型的路径仍保持原状，避免低风险重构越界成行为调整。
      - **Android API 动作局部重复收口**：`android_api_actions.py` 中 `background_keepalive` 这一组 package 型动作与 `google_id/adid` 读取动作已统一复用文件内 client 包装和参数解析 helper，减少“同一套校验 + 同一套 `_from_api` 包装”在后续修功能时重新堆回大文件的概率；同时补了小范围回归测试，固定这组动作的调用路径与缺参返回契约。
      - **Android API 零参数 wrapper 收口**：`android_api_actions.py` 中 `get_clipboard/query_proxy/stop_proxy/refresh_location/get_container_info/get_version/get_app_bootstart_list/get_root_allowed_apps` 这批纯透传动作已统一改为复用 `_with_client(...)`，把反复复制的“拿 client -> 判空 -> `_from_api`”样板从动作定义里移走；同时补充定向测试，固定这些 wrapper 仍然逐个命中原有 client 方法。
      - **Android API 别名动作继续收口**：`android_api_actions.py` 中 `backup/export` 与 `restore/import` 这两对别名动作已统一复用共享的路径解析与 client 包装 helper，避免后续再把相同的参数别名处理和 `_from_api` 样板复制回文件；同时补充回归测试，固定别名参数仍映射到原有 `backup_app/restore_app` client 调用。
      - **防回弹约束已固化到仓库**：`AGENTS.md` 新增大文件回填防线，明确要求在 `android_api_actions.py`、`_ui_selector_support.py`、`_state_detection_support.py`、`agent_executor.py`、`task_execution.py` 这类热点文件中，新增逻辑前必须先检查是否只是重复既有 helper 模式；对零参数 wrapper、package 型动作和 alias 动作，禁止再复制整段 handler。
      - **State detection DM 提取骨架收口**：`_state_detection_support.py` 中 inbound/outbound DM 最后一条消息提取已统一复用共享 helper，保留“按左右边界筛选 + 取最靠下消息”的原有契约不变，同时补充定向测试固定方向阈值、末条选择和解析失败日志。
      - **State detection 列表目标提取继续收口**：`_state_detection_support.py` 中 `extract_follow_targets_from_xml` 与 `extract_unread_dm_targets_from_xml` 已统一复用共享的 XML 解析、package 过滤、bounds/center 计算、去重和排序 helper，保留各自的匹配条件与返回结构不变；同时补充定向测试，固定按钮/未读目标提取和解析失败日志契约。
      - **任务取消原因语义对齐**：`TaskAttemptFinalizer.finalize_result_attempt()` 在“结果路径里遇到 cancel_requested”时，`task.cancelled` 事件原因已从误导性的 `user_exception_path` 收敛回 `user`；同时补充回归测试，固定 forced-cancel 与 result-path cancel 两条取消出口的 reason 契约。
      - **State action 转发壳去除**：`state_actions.py` 已移除一层对 `_state_detection_support.py` 的纯转发 wrapper，跟进把 DM 提取、follow/unread 目标提取、候选提取直接接到 support 实现，减少 support 层与 action 层之间的双处同步点；`android_api_actions.py` 中未使用的 `_ok()` helper 也一并清理。
      - **Agent Executor 规划失败出口收口**：`agent_executor.py` 中 planner 错误、fallback 空动作重试耗尽、非法动作选择这三条失败分支已统一复用类内 helper 生成 terminal trace 和失败结果，减少主循环里重复拼装同型 `failed_runtime_error` 终态的样板代码，保留原有 code/message/checkpoint 与 trace 契约不变。
      - **防回潮约束继续加固**：`AGENTS.md` 已进一步明确热点文件的“第二次重复即收口”规则，要求在 `agent_executor.py`、`task_execution.py` 及几类 action/support 大文件中，遇到同型 result/trace/event/参数归一化骨架时优先扩展局部 helper；同时禁止新增纯透传 wrapper 作为默认写法，避免后续修功能时再次把样板代码和空壳层写回热点文件。
      - **前端任务/草稿契约对齐**：任务详情弹窗现已直接消费 `workflow_draft` 的进度、失败建议与 `continue/distill` 能力，前端不再只把草稿当作一条只读 message；同时 SSE 也会跟进刷新 `workflow_draft.updated` 事件，减少后端已切到 Workflow Draft 主链路而前端仍停留在旧插件蒸馏心智的错位。
      - **前端任务上下文与 AI 能力源修复**：任务提交前的 payload 白名单裁剪现在会显式保留 `app_id/app` 这类运行时上下文字段，避免应用选择器在前端被自己裁空；设备页 AI 对话框的可选动作也改为优先读取 `/api/engine/skills` 元数据渲染，并支持附加自定义状态 ID，降低动作列表/状态集合继续手写漂移的风险。
      - **后端前端兼容点审查**：当前确认仍存在少量为旧前端/旧交互模型保留的兼容入口，例如旧的 `/api/tasks/distill/{plugin_name}` 插件蒸馏路由，以及 RPC bootstrap 在 runtime target 缺少 `device_ip` 时回退读取 payload 的兜底逻辑；本轮先完成前端主路径对齐，兼容入口暂不贸然删除，避免影响存量调用。
      - **指标页旧蒸馏心智继续收口**：`metrics.js` 现不再把插件蒸馏结果路径写死为 `plugins/<name>_distilled/`，而是直接显示后端返回的 `output_dir`；同时会把 `visible_in_task_catalog=false` 的插件明确标成“内部”，避免隐藏任务在指标页继续伪装成普通可见目录任务。
      - **连接参数取值规则局部收口**：新增 `engine/actions/_context_value_support.py`，把 `sdk_actions.py`、`android_api_actions.py`、`profile_actions.py` 中散落的 `params/payload/runtime.target/runtime` 取值逻辑统一收敛到共享 helper，同时保留各模块原有优先级顺序不变；额外补充定向测试，固定 SDK 风格、Android API 风格和 runtime target 优先的取值契约，减少后续为了兼容旧入口而在多个 action 文件里重复手写 `device_ip/api_port/sdk_port` 回退链。
      - **旧插件蒸馏兼容口显式化**：`task_routes.py` 中保留的 `/api/tasks/distill/{plugin_name}` legacy 路由，已把“不支持蒸馏”和“未达到门槛”这两段兼容返回骨架下沉为私有 helper，并补充定向测试固定返回契约；现阶段仍保留旧入口以兼容指标页/存量调用，但兼容逻辑不再直接堆在路由体里。
      - **`device_ip` payload 兼容链显式化**：`_rpc_bootstrap.py` 和 `interpreter.py` 里原本内联的 payload `device_ip` 回退已改成具名 legacy helper，并补充回归测试固定“runtime.target 缺少 `device_ip` 时仍兼容读取 payload”的现有语义；本轮不删除兼容，只把兼容边界从隐式条件收口成可见契约，方便后续继续缩小依赖面。
      - Web 端新增共享任务表单 UI helper，任务主面板、单机执行面板和批量下发条统一复用“说明卡 + 字段渲染 + 高级参数展开”逻辑，减少前端重复实现继续漂移。
      - 收紧若干过度静默回退：WebSocket 事件轮询/广播、账号失败反馈持久化、浏览器 selector 轮询 fallback 现在都会保留可观测错误信息；浏览器 cookie 注入对不支持的 backend 会明确返回失败，而不再伪装成成功。
      - Native 状态兼容继续收口：`ui_state_actions` 和 `navigation_actions` 仍兼容读取 legacy `binding_id` 入口，但内部传递、路由探测与执行热路径统一只使用 `state_profile_id`，避免新逻辑继续向内层传播双字段。
      - Planner 迁移继续推进：`StructuredPlanner` 现在直接调用 `engine.planners.plan_structured_step()`，不再反向依赖旧的 `_plan_next_step` dict 接口；`agent_executor_planning._plan_next_step` 已降级为薄兼容包装层，保留旧 trace/测试兼容的同时把 structured planner 主逻辑收口到 `planners.py`。
      - 设备页继续瘦身：新增 `web/js/features/device_task_panel.js`，把单机任务表单渲染、单机提交和批量分发从 `devices.js` 中拆出；设备页主文件继续聚焦设备列表、接管和详情展示，避免任务编排逻辑反复堆积。
      - 设备页 AI 对话弹窗也已独立：新增 `web/js/features/device_ai_dialog.js`，统一承接默认提示词加载、账号注入和 `agent_executor` 任务下发，`devices.js` 不再继续堆放 AI 对话表单读写与 payload 组装逻辑。
      - 设备页继续去热点：新增 `web/js/features/device_detail_modal.js` 与 `web/js/features/device_unit_detail.js`，把设备详情弹窗、接管页截图轮询、轻控制和详情页进入/退出逻辑从 `devices.js` 中拆出，设备页主文件继续收口为数据加载、卡片渲染和表单绑定入口。
      - 设备页剩余通用逻辑继续分层：新增 `web/js/features/device_accounts.js`、`web/js/features/device_system_modal.js`、`web/js/features/device_plugin_catalog.js`，把接管页账号池加载、系统状态/浏览器诊断弹窗、插件目录分组下拉渲染从 `devices.js` 中进一步拆出，减少页面主控脚本继续承担跨域状态。
      - Selector / 状态识别 support 模块补齐恢复性日志：`_ui_selector_support.py` 与 `_state_detection_support.py` 现在会对 selector 清理失败、节点方法回退、XML 解析失败、截断 XML 回补等路径输出 debug 日志，不再静默吞掉根因。
      - 新增 `tests/test_state_detection_support.py`，固定 XML 属性扫描回退、候选提取解析失败以及 bounds 解析失败的日志与返回契约，防止后续再次退回“无声 fallback”。
      - Native state 兼容入口继续收口：`binding_id -> state_profile_id` 的解析与 identity 组装已统一下沉到 `engine/ui_state_native_bindings.py`，`ui_state_actions`、`navigation_actions` 与 `NativeUIStateAdapter` 不再各自维护一套兼容分支；内部统一走 `state_profile_id`，仅在结构化结果边界保留 legacy alias。
      - 任务熔断器补齐启动窗口保护：`ActiveTargetCircuitBreaker` 与子进程目标监控现在只认“目标启动后的新 probe 快照”，不再因为任务启动前缓存的一次 `unavailable/timed out` 快照而在起跑瞬间误熔断；针对该行为已补充单测，覆盖启动前旧快照忽略与启动后新快照生效两条路径。
  - **MYTOS API 新能力接入 (2026-03-19)**：
    - `AndroidApiClient` 与 `android.*` / `mytos.*` 动作已补齐新版 `task=snap` 截图、`modifydev?cmd=7` 指纹更新、`modifydev?cmd=17` 摇一摇开关。
    - `mytos.screenshot` 现兼容 `level=1/2/3`，可直接走新版截图接口；同时新增 `mytos.set_fingerprint` / `mytos.update_fingerprint` / `mytos.set_shake`。
  - **执行器热点继续拆分 (2026-03-18)**：
    - **`agent_executor` 主循环瘦身**：将类型定义、通用辅助、规划链路、trace/证据链分别下沉到 `engine/agent_executor_types.py`、`engine/agent_executor_support.py`、`engine/agent_executor_planning.py`、`engine/agent_executor_trace.py`，`engine/agent_executor.py` 收口为更薄的运行时编排层。
    - **兼容面显式保留**：保留 `engine.agent_executor.time` monkeypatch 入口以及 `_build_history_digest` 等现有导出路径，确保现有测试与外部调用不因内部拆分而断裂。
    - **`sdk_actions` 目录化拆分**：`engine/actions/sdk_action_catalog.py` 接管 SDK/MYTOS 动作绑定目录与参数构造，`engine/actions/sdk_actions.py` 保留 registry 对外入口、运行时包装器与共享存储/配置/业务 façade，降低继续堆积为单文件热点的风险。
    - **进度快照统计纠偏**：`tools/update_project_progress.py` 已同步改为统计 `sdk_actions.py + sdk_action_catalog.py`，避免文档快照因目录拆分而误报动作绑定数量。
  - **Agent Executor 登录推进稳态化 (2026-03-18)**：
    - **提交后过渡观察收紧**：`agent_executor` 在 `ui.key_press(key="enter")` 成功后，优先使用 `ui.observe_transition` 观察“离开当前页”的状态迁移，而不是接受包含当前页在内的宽松等待结果。
    - **弱证据输入门槛**：在 `account/password/two_factor` 这类文本输入阶段，弱证据状态下不再允许跨页面直接 `ui.input_text`；必须先在同一状态里完成输入框点击或其他就绪动作。
    - **回退状态抗抖动**：当密码/2FA 提交后的弱回退证据错误回跳到 `account/login_entry` 时，执行器会稳定保持较晚阶段，避免因 UI XML 误判把流程错误拉回前页。
    - **前端日志可读性增强**：`task.observation` 事件新增 `state_certainty/state_source`，Web 控制台可直接区分 authoritative 观察与 fallback 推断。
  - **Ruff 规范基线收敛（排除 vendor）**：
    - `pyproject.toml` 统一 Ruff 配置（迁移至 `[tool.ruff.lint]`），并通过 `exclude=["vendor"]` 明确不对 vendored 第三方源码做 lint/format。
    - 核心目录（`api/ core/ engine/ ...`）`ruff format` 与 `ruff check` 全通过；同时补齐若干 legacy re-export（`ui_actions` metadata/close hooks）以保持 action registry 与测试兼容。
  - **前端构建链引入 (Vite + TypeScript)**：
    - `web/` 目录升级为 Vite 工程（支持 `npm run dev/build/typecheck`），后端收敛为 API-only。
    - 建议生产由 Nginx 同机反代部署（静态前端 + `/api`/`/ws` 反代），详见 `docs/FRONTEND.md`。
  - **Agent Executor 通用观察契约修复 (Framework Neutrality Hardening)**：
    - **unknown 不再伪装成成功观察**：`agent_executor` 现把 `state_id=unknown` / `confidence=0.0` 统一视为需要 fallback 的低置信观察，不再因为 `ok=true` 就关闭截图/VLM 证据链。
    - **观测日志去混淆**：`observed_state_ids` 不再混入 `expected_state_ids`，任务日志只展示真实观察结果，避免把目标状态误写成已观测状态。
    - **动作闭环增强**：`ai.locate_point` 成功后会向 Planner 注入后续点击提示；`ui.swipe` 失败时新增 `effect_uncertain` 语义，提醒执行器先观察页面变化而不是盲目假设动作未生效。
    - **登录阶段回退推断**：当结构化观察仍为 `unknown` 时，执行器会从 fallback XML 中通用推断 `login_entry/account/password/two_factor/home` 提示，恢复账号/密码/2FA 输入后的通用推进与自动提交能力，无需 app-specific `stage_patterns`。
- **默认提示词收敛**：`config/strategies/prompt_templates.yaml` 已收敛为单一默认模板，保留通用状态门禁和原子动作约束，移除按场景拆分的具体执行策略。
    - **动作参数兼容性**：`ai.locate_point` 现兼容 `description` 作为 `prompt` 别名，避免 Planner 返回自然语言描述字段时白白损失一步预算。
    - **前端硬编码清理**：
      - `web/js/features/devices.js`：移除对 `social_x` 模板的 `com.twitter.android` 硬编码注入。
      - `web/index.html`：移除下拉菜单中硬编码的 "X (Twitter)" 选项及风险提示中的平台特定文案。
      - `config/apps/x.yaml`：精简为最小骨架（仅保留 version 和 package_name），不再包含 app-specific selectors。
    - **Live 验证通过**：X 登录任务 (task_id: `56f6adf1-8ec2-4cda-ac65-d4386ef42fea`) 成功演示了 30 步执行链：AI 正确使用 fallback XML 推断登录阶段、定位输入框、点击、输入账号、找到 Next 按钮。框架现在能在无 app-specific 硬编码辅助下完成通用登录流程。
  - **Learning Hook 闭环落地 (Architecture 2.0 Phase 1)**：
    - **在线学习回写**：新增 `core/trace_learner.py` 与 `core/app_config_writer.py`，成功 trace 会在完成后提取稳定 `resource_id` 并按阈值回写到 `config/apps/<app>.yaml`。
    - **配置边界收敛**：`config/apps/<app>.yaml` 新增 `stage_patterns` 作为应用级感知记忆库；`selectors` 重新收口为通用 UI selector；`config/strategies/login_stage_patterns.yaml` 保持 framework 级默认规则，不参与在线自动写入。
    - **运行时兼容迁移**：`core.detect_app_stage` 现优先读取 `stage_patterns`，同时兼容旧的 stage-like selector 结构，避免存量 app 配置立即失效。
  - **从“辅助 AI”转向“解放 AI”的架构共识 (Architecture 2.0 Strategic Alignment)**：
    - **打破辅助悖论**：明确了 1.0 中“严格感知”对 AI 自主能力的束缚。2.0 将 AI 从规则的“被动工具”转变为“主动大脑”。
    - **演进生命周期**：确立了从“自主探索 (AI Bootstrapping)”到“原生数据执行 (Native Mode)”再到“终极 YAML 插件 (Master YAML)”的漏斗模型。
    - **文档体系同步**：更新了 `PROJECT_GOALS.md` 与 `architecture_2_0.md`，将“YAML 插件交付”确立为项目最终的工程化北极星目标。
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
- 最近重点 (2026-03-17)：
  - **安全清理工具落地**：新增 `tools/clean_workspace.py`，默认 dry-run，只清理本地缓存/构建产物；旧 trace 清理需要显式传入 retention 参数，避免误删当前运行数据。
  - **UI 状态命名收敛**：新增 `state_profile_id` 作为 `ui.match_state` / `ui.navigate_to` 的推荐参数名，运行时继续兼容 legacy `binding_id`，逐步收口旧术语。
  - **Native State Profile 内部继续收口**：`NativeUIStateAdapter` 主路径已改为优先解析 `state_profile_id`，`NativeStateProfile` 同时接受 `state_profile_id` / `binding_id` 构造入参，兼容字段统一由共享 helper 输出，减少后续重复维护成本。
  - **导航动作兼容边界集中化**：`ui.navigate_to` 对 route profile 的解析与 probe 身份字段输出已抽到共享 helper，主路径统一围绕 `state_profile_id`，同时显式保留 `binding_id` 兼容透传，减少动作层重复拼装旧字段的风险。
  - **UI State 入口参数标准化**：`ui.match_state` / `ui.wait_until` / `ui.observe_transition` 在 native 模式下会先把 `state_profile_id` / `binding_id` 归一成一致的双字段后再创建 adapter，确保新旧入口在后续动作链里观察到的是同一份稳定参数。
  - **移除 Binding 工坊（历史链路下线）**：删除 Web 控制台中的 Binding Master 入口、`/api/binding/*` 路由、`engine/binding_distiller.py` 与 `tools/distill_binding.py`，正式收口到自动学习主链路（`agent_executor -> trace -> config/apps/*.yaml`），减少人工预热路径。该条记录描述的是旧 binding 工坊链路的下线，不代表当前仍存在独立 binding 子系统。

- 最近重点 (2026-03-19)：
  - **Workflow Draft 控制面落地**：新增 `workflow_drafts` 持久化层与 `WorkflowDraftService`，把客户中文任务名、成功样本门槛、最近成功快照、失败建议和蒸馏状态从单次任务中抽离为稳定草稿对象。
  - **任务提交流程减负**：`POST /api/tasks/` 新增 `display_name` / `draft_id` / `success_threshold`，AI 任务首次成功后只提示“继续验证”，不再要求客户重复输入提示词。
  - **失败建议结构化**：终态失败时自动生成 `latest_failure_advice`，包含失败摘要、缺失信息、建议补充项和推荐提示词；任务详情、草稿详情和 `workflow_draft.updated` SSE 事件都可直接消费。
  - **自动续跑验证**：新增 `POST /api/tasks/drafts/{draft_id}/continue`，复用最近一次成功快照自动创建后续验证任务。
  - **草稿级离线蒸馏**：新增 `POST /api/tasks/drafts/{draft_id}/distill`，达到门槛后从最近成功 golden run 离线生成 YAML 草稿，默认输出到 `plugins/.drafts/<plugin_name>_draft/`，避免未审核草稿被自动当作正式插件加载。
  - **Workflow Draft 身份/清理加固**：`draft_id` 现在会校验 `task_name` / `display_name` / `success_threshold` 一致性，防止跨任务串组；pending 取消、失败清理与 `clear_all` 会同步修正或删除草稿引用；已蒸馏草稿不再继续提示重复 distill；成功快照会固化最近一次成功 trace context，蒸馏优先使用这份上下文而不是临时目录扫描猜测。

- 最近重点 (2026-03-15)：
  - **设备可用性提前熔断**：`DeviceManager` 新增 probe 订阅接口；任务执行链路会把当前 target 的 probe 离线信号并入取消判断，线程模式直接订阅，子进程模式由父进程监控活跃 target 并回传熔断理由，最终统一以 `failed_circuit_breaker` / `target_unavailable` 终止，而不是等待 RPC 超时。
  - **工具链根路径收敛**：`tools/*.py` 的仓库根目录解析已统一收口到共享 bootstrap + `core.paths`。
  - **框架去业务关键词 (Framework Neutrality)**：将登录阶段/关注/未读等默认 UI 识别 marker 从框架代码迁移到 `config/strategies/*.yaml`，框架层不再硬编码“首页/主页/关注”等业务词，支持按 action params/session defaults 覆盖。
  - **API 边界加固**：
    - `/api/tasks/distill/{plugin_name}`：加入 `plugin_name` 严格校验与输出目录边界约束（仅允许写入 `plugins/` 下），并将蒸馏门槛从插件 `manifest.yaml` 的 `distill_threshold` 读取，路由层不再硬编码。
    - `/api/devices/{device_id}/{cloud_id}/screenshot`：移除 `device_ip/rpa_port` 入参，改为从配置推导目标与端口公式计算，避免越权/SSRF 风险；`MYT_ENABLE_RPC=0` 时返回 503。
  - **WebSocket 事件桥接稳固性**：DB poller 改为可停止线程并移除私有 `_connect()` 依赖，避免 shutdown 后线程泄露。
  - **账号池架构升级 (SQLite & BaseStore Migration)**：完成了从 JSON 到 SQLite 的原子化迁移与自动平滑解。
  - **AI 术语与命名去硬编码 (Agent Executor)**：确立了厂商中立的智能体运行时架构。
  - **行为拟真引擎优化 (Behavioral Hardening)**：基于人类行为学研究优化了三档预设参数（延迟、停顿、按压时长），并在前端增加了全方位的「使用建议」引导，助力高风控平台（如 X/TikTok）的对抗能力。
  - **细节修正与系统稳固性 (本会话)**：修复了接管页参数丢失以及 VLM 客户端测试崩溃等隐患。
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
    - **蒸馏链路 Regex Fallback**：为 trace 特征提取引入了正则回退机制，确保在极端截断情况下仍能提取包名和核心特征。
    - **App 探测去硬编码重构**：彻底移除了框架中针对 X App 的硬编码字符串，支持通过 `config/apps/*.yaml` 动态加载。
    - **通用的 Native 状态观察**：旧常量名 `X_APP_STAGE_BINDING` 已收敛为全局通用的 `app_stage` 状态观察能力。
    - **X App 特征落地**：解析并集成 X App 首页特征。
    - **文档与系统一致性对齐**：全量审计并修复了 `docs/` 下的过期信息，包括多云机动态端口公式、任务控制面架构拆分描述、以及插件契约规范（补全 Pydantic 必填字段），并新增了 **[Skills化演进报告](SKILLS_EVOLUTION.md)**，确立了 AI 驱动技能化的架构演进方向。
  - **代码清理（本会话）**：删除 `common/env_loader.py`、`common/runtime_state.py`、`common/toolskit.py`（零引用旧产物）。

- 最近重点 (本会话)：
  - **App 配置统一架构**：删除 `config/bindings/` 目录，`xml_filter`/`states` 字段合并至 `config/apps/<app>.yaml`；这里的 “GPT 执行器” 是旧称，现统一对应 `agent_executor`，并从 `config/apps/*.yaml` 按 `package_name` 加载原 binding 语义所承载的配置；`sdk_config_support` 新增 `com.twitter.android → x` 映射。
  - **X app 配置**：新增 `config/apps/x.yaml`，含 `package_name`、`xml_filter`（max_text_len=60/max_desc_len=100，针对 X app 的合理截断），15 个 UI 状态描述，deep link scheme。
  - **蒸馏自动 selector merge**：`GoldenRunDistiller.distill()` 完成后自动扫描 script steps，提取 UI 定位 action（`ui.click` 等 8 种）的未参数化 `text`/`resource_id` 值，merge 写入对应 `config/apps/<app>.yaml` 的 `selectors` 字段；已有 selector 不覆盖。

- 最近重点 (本会话)：
  - **Skills-Driven 架构演进 (Phase 1 & 2)**：
    - **Action Registry 元数据增强**：`ActionRegistry` 现在支持 `ActionMetadata`，通过 Pydantic 模型定义每个动作的描述、参数 Schema (JSON Schema) 和返回值 Schema。
    - **自描述 API**：`GET /api/engine/schema` 作为通用动作目录，全量暴露已注册动作的元数据并支持按 `tag` 过滤；`GET /api/engine/skills` 提供仅含 `skill` 标签动作的 AI 技能书。
    - **非破坏性元数据富化**：为 `ui.*`、`app.*`、`core.*` (save/load shared) 以及 `ai.*` (llm/vlm/locate) 等高频核心动作补全了描述和参数规范。
    - **文档自愈机制**：在 `AGENTS.md` 中确立了“代码变更伴随文档同步”的强制规则，确保架构演进与文档保持物理对齐。
    - **AI 引导升级**：新建 `docs/AI_ONBOARDING.md` 作为 AI 进入项目的第一站，明确了知识检索优先级与职责边界。

- 最近重点 (本会话)：
  - **决策层完全解耦 (Architectural Decoupling)**：
    - **Planner 抽象层 (防波堤 1)**：新增 `engine/planners.py`，将 `AgentExecutorRuntime` 中的硬编码决策逻辑（LLM/VLM 调用、Prompt 组装）抽离为 `BasePlanner` 协议。引入 `StructuredPlanner`（生产基线）和 `OmniVisionPlanner`（实验性多模态，`MYT_EXPERIMENTAL_OMNIVISION=1` 开启）。执行器循环现在通过不可变的 `PlannerInput`/`PlannerOutput` 契约与决策大脑通信，实现物理隔离。
    - **旁路蒸馏增强 (防波堤 2)**：在 `core/golden_run_distillation.py` 中新增 `LLMDraftRefiner`。在启发式参数化完成后，通过可选的 LLM 旁路分析 YAML 寻找额外的硬编码业务参数并抽取为 `${payload.xxx}`。完全静默失败回退机制保证了核心蒸馏流程的绝对稳定性（新增 `--use-llm-refiner` CLI 支持）。

- 最近重点 (本会话)：
- **默认提示词服务化**：
- `engine/prompt_templates.py` 继续作为项目唯一提示词数据源，但当前仅暴露一个默认模板。
- `GET /api/tasks/prompt_templates` 仍返回模板列表（key/name/content），供前端拉取默认提示词内容。
- 前端 AI 对话框已移除场景模板选择，仅在打开时自动填充默认提示词，用户仍可手动微调。

- 最近重点 (本会话)：
  - **共享存储作用域解析收敛**：
    - `engine/actions/sdk_shared_store_support.py` 将 `device/task/cloud` 三类 shared key 默认作用域值解析收敛到单一 helper，移除散落在 `resolve_shared_key()` 内的分支拼装。
    - 保持 `device -> payload.device_ip`、`task -> context.task_id`、`cloud -> context.cloud_target_label / payload.name` 的既有优先级不变，只把兼容入口集中，降低后续补丁继续把同类回退逻辑写散的概率。
    - 补充 `tests/test_sdk_shared_store_support.py`，覆盖现有默认作用域契约以及缺少动态上下文字段时的安全降级，避免后续结构收敛误伤 shared store 键空间。

- 最近重点 (本会话)：
  - **API 生命周期订阅兼容分支收敛**：
    - `api/server.py` 将任务事件订阅的现代 `subscribe_events()` 路径与旧 `_events.subscribe()` 兼容路径抽成 `_subscribe_task_events()`，让 `lifespan()` 回到只负责启动顺序编排。
    - 新增现代控制器入口与不支持订阅时的显式失败测试，保留旧测试替身路径不变，避免后续再把兼容分支直接塞回应用启动主流程。

- 最近重点 (本会话)：
  - **前后端蒸馏入口对齐**：
    - `api/routes/task_routes.py` 新增明确的当前插件蒸馏入口 `/api/tasks/plugins/{plugin_name}/distill`，并把旧 `/api/tasks/distill/{plugin_name}` 收敛为兼容别名，共用同一后端处理函数。
    - 指标页蒸馏按钮已切换到新入口，避免前端继续把 legacy route 当成主契约；同时保留旧路由，降低已有外部调用或脚本的迁移风险。
    - 补充新旧路由对不可蒸馏插件的一致性测试，锁住兼容别名与主入口的行为对齐。

- 最近重点 (本会话)：
  - **Agent Executor 登录字段命名对齐**：
    - AI 对话框提交账号信息时改用更明确的 `account/password/twofa_secret` 外部字段名，不再把 `acc/pwd/fa2_secret` 当作前端主契约。
    - `engine/agent_executor_support.py` 将这些外部字段统一归一化到现有内部 planner 输入键，旧别名仍兼容，但兼容逻辑集中到单一入口，避免继续在前端扩散历史命名。
    - 补充归一化测试，锁住 canonical 字段与旧内部键空间之间的映射关系。

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
  - **AI 术语与命名去硬编码 (Agent Executor)**：
    - 全量重命名 `GPT Executor` -> `Agent Executor`，确立厂商中立的运行时架构。
  - **VLM 架构通用化重构**：
    - 废弃 UI-TARS 专有逻辑，建立通用的 `VLMProvider` 协议，支持多厂商插件化接入。
  - **细节修正与系统稳固性 (本会话)**：
    - 修复了历史前端 binding 工具页面中 `binding.js` 的 `json.stringify` 拼写错误。
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
    - **修复无旧 binding 配置场景下的 fingerprint 计算**：`agent_executor` 在 `observation.ok=False` 时改用 UI XML 内容计算停滞 fingerprint，防止在缺少旧 binding 预热配置时错误触发死循环熔断。
    - **新增 binding 蒸馏链路（历史表述）**：支持从 trace jsonl 自动提取 UI 特征并归纳界面状态；该能力后续已收口到当前自动学习主链路。
    - **前端 AI 对话修复**：历史字段 `binding_id` 完成服务化，随后相关 binding 工具链已逐步退场；同时对齐 `allowed_actions` 注册名并修复 SSE 事件流稳定性。
    - **LLM 调用链路修复**：新增 `OpenAIChatProvider` 并通过 `.env` 注入 key，由于采用了标准 OpenAI 封装协议，系统现在能更稳健地连接到各类代理服务。
    - **统一入口 `.env` 加载**：`api.server` 现在会在 `MYT_LOAD_DOTENV!=0` 时主动加载项目根目录 `.env`，避免直接 `uvicorn api.server:app` 与 `run_webrpa.sh` 的环境行为不一致。
    - **登录执行器约束增强**：`agent_executor` 不再把 `ui.observe_transition` 暴露给 planner 直接决策；当 `account/password/two_factor` 处于弱匹配且尚未确认输入框聚焦时，会强制 `ai.locate_point` 优先寻找输入框而非提交按钮。
    - **加载态预算修复**：`agent_executor` 现在会在成功交互后检测通用 loading/progress 过渡层，并先内部等待状态稳定再重新规划，避免把“正在载入…”这类瞬态页面白白消耗成一个独立步骤。
    - **尾部动态续步**：`agent_executor` 在用尽 `max_steps` 时不再一律硬失败；若最近观察仍显示明显推进、且未接近停滞/重复死循环，会自动一次性追加少量尾部预算，用于完成首页判定或收口动作。
    - **观测抖动与探测稳定性修复 (2026-03-19)**：`agent_executor` 现在会识别“弱观察 + planner 空动作”的组合场景，将其视为短暂观测不可靠并执行受限延迟重试；只有在观察已可用时仍返回空动作，才继续按 `invalid_action_selection` 处理。同时统一云机探测快照 `last_checked_at` 为带时区的 UTC 时间，避免本地时区字符串被按 UTC 误解后触发误熔断；为 RPA 端口探测补上一轮轻量重试，并在任务熔断前对当前目标追加一次同步确认探测，降低瞬时 `Host is down` / `timed out` 抖动导致的错误熔断。对于账号/密码/2FA 这些弱观察阶段，若 planner 已明确在寻找“下一步/继续/登录”类提交按钮，运行时也不再把视觉定位意图强行改写成“只找输入框”。

## 2. 已实现功能清单

### 2.1 API 与控制面
- 任务/设备/配置/数据全套 RESTful 接口。
- WebSocket 实时日志流 (`/ws/logs`)。
- 托管任务生命周期管理（创建/取消/重试/指标）。

### 2.2 引擎与插件
- Runner + Interpreter 声明式工作流引擎。
- 支持 YAML 插件模式（当前运行时契约为 `v1`）。
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
| API route decorators (`api/routes`) | 57 |
| App-level route decorators (`api/server.py`) | 5 |
| Plugin count (`plugins/*/manifest.yaml`) | 1 |
| SDK action bindings (`engine/actions/sdk_actions.py` + `engine/actions/sdk_action_catalog.py`) | 158 |
| Test files (`tests/test_*.py`) | 72 |
| Test functions (`def test_*`) | 399 |
<!-- AUTO_PROGRESS_SNAPSHOT:END -->

## 4. 维护说明
每次有意义变更后执行 `./.venv/bin/python tools/update_project_progress.py` 以更新统计快照。
