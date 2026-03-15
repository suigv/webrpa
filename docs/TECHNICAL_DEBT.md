# WebRPA 技术债与设计缺陷治理报告 (2026-03-11 完结版)

**当前状态**：全量 P0/P1 架构债已清偿。系统已升级为全异步 I/O 架构，进入高性能稳定运行期。

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
- [ ] 随着设备数突破 1000 台，需评估 `ThreadPoolExecutor` 的线程池饱和度。
- [x] `navigation_actions.py` 通用化：移除业务残留，改为 routes/hops 驱动。
- [x] **ActionRegistry 调用点分散（需统一分发入口）**：历史上 `AgentExecutor/Interpreter` 存在 `registry.resolve(...)(...)` 的重复直呼，导致后续要加全局限流/审计/拦截需要改多处。现已引入 `engine/action_dispatcher.py:dispatch_action()` 统一动作分发入口（两条执行链路已收敛）。
- [x] **Interpreter wait_until 阻塞式轮询（已修复）**：wait_until 现采用 `wait_signal` + 背景轮询线程（`WAIT_UNTIL_POLL_MAX_S`/`WAIT_UNTIL_CANCEL_CHECK_S`），并在 Service wait 路径做了分片超时以确保取消响应，不再是 `time.sleep(1s)` 盲等。
- [x] **设备快照缓存无 TTL（已修复）**：`DeviceManager.get_devices_snapshot()` 现引入 TTL（环境变量 `MYT_DEVICE_SNAPSHOT_TTL_SECONDS`，默认 2s），过期自动重建快照，避免 probe worker 异常时 UI 长期显示陈旧数据。
- [x] **任务队列 Aging 机制**：已实现，默认每等待 120s 提升 10 点优先级，可通过 `MYT_QUEUE_AGING_INTERVAL` / `MYT_QUEUE_AGING_BOOST` 环境变量调整（仅 InMemoryQueue）。
- [x] **CloudProbeService → DeviceManager 耦合脆弱（已修复）**：移除 `hasattr`/私有方法兜底调用，统一使用 `DeviceManager.update_cloud_probe()` 与 `DeviceManager.refresh_device_snapshots()` 公共接口。
- [x] **设备状态伪实时 / 提前熔断（已修复）**：`DeviceManager` 现提供云机 probe 订阅接口，线程执行路径会把目标云机离线信号并入 `should_cancel`，子进程执行路径则由父进程监控当前活跃 target 并把熔断理由回传子进程；连续 probe 失败达到 unavailable 阈值后，任务会以 `failed_circuit_breaker` / `target_unavailable` 提前失败，不再只能等 RPC 动作超时后才感知离线。
- [x] **ConfigLoader 类型冗余**：已修复。`ConfigLoader.load()` 现在直接返回 `ConfigStore` 强类型对象，访问器全部改为直接读取属性，`_to_int`/`_to_bool` 防御性转换已从访问器层移除。

---

**治理结论**：WebRPA 现已具备支撑工业级业务负载的底座能力。
