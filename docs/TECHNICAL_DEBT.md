# WebRPA 技术债与设计缺陷治理报告 (2026-03-11 完结版)

**当前状态**：launch-readiness 阶段已完成一轮高价值收口与瘦身，热点文件的防回潮治理已显著加强；但结构债并未清零，当前剩余问题主要集中在前后端契约边界、兼容层和少数热点文件的持续瘦身。

---

## 🟢 治理里程碑 (已清偿)

### 1. 存储与性能 (Performance)
- [x] **全量异步 I/O 统合**：API 层对所有同步 Store/Service 调用完成了 `anyio.to_thread` 封装。特别是 **SSE 事件流** 已改造为异步生成器，彻底解决了多任务追踪下的 API 卡死风险。
- [x] **数据库架构统合**：`BaseStore` 作为唯一地基，开启 WAL 模式并统一事务管理。
- [x] **账号存储数据库化**：实现原子化 POP 逻辑，支持极高并发。

### 2. 运行时鲁棒性 (Robustness)
- [x] **深度取消支持**：`ui.click` 和 `browser.wait_until` 等长耗时动作已植入对 `stop_event` 的毫秒级感知。
- [x] **AI 执行韧性**：`AgentExecutor` 具备指数退避重试与动作指纹死循环熔断能力。
- [x] **连接池管理**：`VLMClient` 共享持久连接池，杜绝 FD 泄露。

### 3. 工程规范 (Refactoring)
- [x] **配置入口归一化**：彻底废弃 `ConfigManager` 残留，全量由 Pydantic 模型驱动。
- [x] **设备管理服务化**：探测逻辑解耦至 `CloudProbeService`。
- [x] **错误语义标准化**：引入全局 `ErrorType` 枚举。

---

## 🟡 持续观测项
- [ ] **任务 payload 契约仍需防回潮**：共享前端提交路径现已统一收口到 `web/js/features/task_service.js` 的 payload 预处理 helper；`accounts.js` 批量派发与 `device_ai_dialog.js` 的 `agent_executor` 提交不再把 `device_ip`/target 语义混入 payload，`tasks.js` 仍仅在插件显式声明 `app_id` 时注入该字段。当前剩余风险主要是后续新增入口绕过该 helper，或后端兼容层继续接受历史 runtime-only 字段。
  - 已完成：共享 helper 现在只组合业务 payload、可选账号注入、声明门控的 `app_id` 注入，并在需要时剥离 runtime-only 字段后再按 manifest 白名单过滤。
  - 剩余范围：后续新增的前端任务提交入口必须复用该 helper；本轮未处理后端 legacy `device_ip` 兼容分支。
  - 回归验收：`one_click_new_device` / `agent_executor` 等共享提交路径不再隐式发送 `device_ip`；存在 `app_id` 声明的插件仍可通过共享 helper 提交；保持前端契约测试覆盖该 seam。
- [ ] 随着设备数突破 1000 台，需评估 `ThreadPoolExecutor` 的线程池饱和度。
- [x] `navigation_actions.py` 通用化：移除业务残留，改为 routes/hops 驱动。
- [x] **ActionRegistry 调用点分散（需统一分发入口）**：历史上 `AgentExecutor/Interpreter` 存在 `registry.resolve(...)(...)` 的重复直呼，导致后续要加全局限流/审计/拦截需要改多处。现已引入 `engine/action_dispatcher.py:dispatch_action()` 统一动作分发入口（两条执行链路已收敛）。
- [x] **Interpreter wait_until 阻塞式轮询（已修复）**：wait_until 现采用 `wait_signal` + 背景轮询线程（`WAIT_UNTIL_POLL_MAX_S`/`WAIT_UNTIL_CANCEL_CHECK_S`），并在 Service wait 路径做了分片超时以确保取消响应，不再是 `time.sleep(1s)` 盲等。
- [x] **设备快照缓存无 TTL（已修复）**：`DeviceManager.get_devices_snapshot()` 现引入 TTL（环境变量 `MYT_DEVICE_SNAPSHOT_TTL_SECONDS`，默认 2s），过期自动重建快照，避免 probe worker 异常时 UI 长期显示陈旧数据。
- [x] **任务队列 Aging 机制**：已实现，默认每等待 120s 提升 10 点优先级，可通过 `MYT_QUEUE_AGING_INTERVAL` / `MYT_QUEUE_AGING_BOOST` 环境变量调整（仅 InMemoryQueue）。
- [x] **CloudProbeService → DeviceManager 耦合脆弱（已修复）**：移除 `hasattr`/私有方法兜底调用，统一使用 `DeviceManager.update_cloud_probe()` 与 `DeviceManager.refresh_device_snapshots()` 公共接口。
- [x] **设备状态伪实时 / 提前熔断（已修复）**：`DeviceManager` 现提供云机 probe 订阅接口，线程执行路径会把目标云机离线信号并入 `should_cancel`，子进程执行路径则由父进程监控当前活跃 target 并把熔断理由回传子进程；连续 probe 失败达到 unavailable 阈值后，任务会以 `failed_circuit_breaker` / `target_unavailable` 提前失败，不再只能等 RPC 动作超时后才感知离线。
- [x] **ConfigLoader 类型冗余**：已修复。`ConfigLoader.load()` 现在直接返回 `ConfigStore` 强类型对象，访问器全部改为直接读取属性，`_to_int`/`_to_bool` 防御性转换已从访问器层移除。

### 防回潮 / 反膨胀治理准则
说明：仓库已经明确“第二次重复即收口”的原则，后续治理重点不是大改写，而是防止热点文件在小修小补中重新回膨。

- 第二次出现同型 result/trace/event/参数归一化/兼容回退骨架时，就地收口到局部 helper 或共享 helper，不等第三次、第四次再补救。
- 优先做文件内、小步、可回滚的瘦身，不做跨模块大改写；默认选择局部 helper、薄包装、重复分支折叠，而不是新抽象层扩散。
- alias、legacy route、兼容字段只能保留为薄包装，必须与主实现相邻并复用同一 helper/service，不允许分叉出第二套行为。
- `core/task_execution.py`、`engine/agent_executor.py` 这类主流程热点不得继续追加重复的终态、取消、trace、事件分支；新增行为若只是复写既有骨架，先扩展附近 helper。
- `engine/actions/android_api_actions.py`、`engine/actions/_ui_selector_support.py`、`engine/actions/_state_detection_support.py` 这类热点 support/action 文件，新增逻辑前先检查是否只是已有 bootstrap、wrapper、bounds、XML 过滤、fallback 链的重复；若是，直接收口，不再复制 handler。
- 运行时上下文属于 `targets` 或 dedicated runtime envelope，不属于插件 payload；前端、路由、运行时都不得把 `app_id`、`device_ip`、target metadata 当作通用隐式输入继续注回 payload。
- 插件脚本若第三次出现同一 fallback 序列，应上提为 composite action，而不是继续复制 YAML。

### 剩余高优先级结构债, 按当前证据排序
1. **前端 payload / runtime-context 边界仍未完全收口**  
   后果：多入口提交仍可能把 `app_id`、`device_ip`、账号别名或 target 元数据带回 payload，继续制造 strict 校验不一致和兼容分支。  
   最小下一步：补一层共享前端提交断言，统一验证“仅 manifest 声明字段进入 payload，runtime context 只进 `targets` / runtime envelope”，并补多入口契约测试。
2. **`api/routes/task_routes.py` 仍承担过多兼容装配**  
   后果：目录、统计、蒸馏兼容口和历史字段拼装继续把 route 变成结构债汇合点。  
   当前进展：`create_task()` 已进一步把 body/header 幂等键对齐与 request→script payload 归一化提取到 route-local helper，保持 `script` 与 `task + payload` 提交语义不变。  
   最小下一步：继续做 route-local 收口，把目录/统计/蒸馏兼容响应骨架压到就近 helper，保持 route 薄层，但不要误报为已完全收敛。
3. **`core/task_execution.py` 仍是执行主链热点**  
   后果：任务终态、取消、重试、target 可用性和进程退出规则容易再次堆回主流程。  
   当前进展：`_execute_task()` 内异常路径与结果路径共享的 post-run terminalization（finalize outcome → conditional retry enqueue → `time.sleep(0)`）已收口到邻近 file-local helper，减少一处重复骨架且不改变重试/取消语义。  
   最小下一步：继续只抽离下一处重复的终态/事件骨架到邻近 helper，避免把新策略直接追加进主执行循环；`_handle_process_exit()` 仍保持原样，热点未闭环。
4. **`engine/agent_executor.py` 仍需持续瘦身**  
   后果：虽然已拆出 planning/trace/support/types，但 run-loop 仍容易重新吸附空动作延迟、失败出口、history/trace 组装等 fix-forward 分支。  
   最小下一步：继续按单步语义切片，把下一组同型 per-step 失败或 defer 分支下沉到私有 helper，保持 `run()` 只表达状态推进。
5. **`engine/actions/android_api_actions.py` 仍有回膨风险**  
   后果：package 型动作、零参数 wrapper、alias 动作最容易在新增能力时重新复制 `_from_api`、参数解析和 client 包装样板。  
   最小下一步：每次新增动作先复用现有 `_with_client` / 参数 helper；若再出现第二组同型样板，立即就地合并，不新增新层级。
6. **`engine/actions/_ui_selector_support.py` 仍是 support 热点**  
   后果：query dispatch、node getter、handle 清理、bounds 归一化等逻辑若继续混写，选择器支持层会再次膨胀。  
   最小下一步：优先沿既有 companion/helper seam 继续局部提取重复查询或节点读取骨架，同时保持 facade 和 teardown 顺序不变。
7. **`engine/actions/_state_detection_support.py` 仍有结构性重复压力**  
   后果：XML 解析、package 过滤、bounds/center 计算、列表提取与日志回退路径仍可能在新 state helper 中重新复制。  
   最小下一步：新增 state 提取逻辑时强制复用现有 XML/helper 骨架，只补能力差异，不再复制一整段解析流程。

---
 
 ## 🟠 架构演进债 (Architecture 2.0 Transition)
 - [ ] **解除前置感知枷锁**：1.0 模式下的 `detect_login_stage` 过于死板，需重构为非阻塞式探测，支持在 `unknown` 状态下自动触发 AI 视觉探索。
 - [ ] **感知记忆持久化抽象**：需建立统一的 `PerceptionMemory` 存储层，替换散落在 `config/apps/*.yaml` 中的半自动固化数据。
 - [ ] **自动化蒸馏评价体系**：目前缺乏对生成 YAML 质量的自动评分机制。
 
 **治理结论**：WebRPA 已完成一轮高价值治理，launch-readiness 所需的主要契约与热点防线已经成形；下一阶段重点不是大拆大建，而是继续按“收口、瘦身、薄兼容包装、防回潮”把剩余结构债一点点压平。
