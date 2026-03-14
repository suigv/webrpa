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
- [ ] **GPTExecutor 直接调用 ActionRegistry（解耦缺失）**：`agent_executor.py:403` 直接调用 `self._registry.resolve(action_name)(action_params, context)`，绕过 Interpreter 统一生命周期。若未来需要全局限流、统一审计或动作拦截，需同时改两处。改进方向：抽象 `ActionDispatcher` 统一分发入口。低优先级。
- [ ] **Interpreter wait_until 阻塞式轮询**：`interpreter.py:251` 使用 `time.sleep(min(interval_s, 1.0))`，最大 1s 盲等。即使设备状态已就绪也无法即时唤醒。改进方向：引入 `anyio.Event` 通知机制，需整个执行栈异步化，改动量大。低优先级。
- [ ] **设备快照缓存无 TTL**：`DeviceManager.get_devices_snapshot()` 返回内存快照，若 `CloudProbeService` 停止运行或异常，快照可能长期过期。改进方向：加 TTL 判断，超过阈值时强制刷新或标记数据陈旧。低优先级。
- [x] **任务队列 Aging 机制**：已实现，默认每等待 120s 提升 10 点优先级，可通过 `MYT_QUEUE_AGING_INTERVAL` / `MYT_QUEUE_AGING_BOOST` 环境变量调整（仅 InMemoryQueue）。
- [ ] **CloudProbeService → DeviceManager 耦合脆弱**：通过 `hasattr` 调用私有方法 `_update_probe_cache` / `_refresh_device_snapshots`，无正式接口契约。修复方向：定义 `DeviceProbeReceiver` Protocol。低优先级。
- [ ] **设备状态伪实时**：`CloudProbeService` 后台探测结果写入 `DeviceManager` 快照，但任务执行时 RPC 超时才能感知设备离线，无法提前熔断。改进方向：发布-订阅模式，探测状态变动即时推送给活跃 `ExecutionContext`。改动量大，低优先级。
- [x] **ConfigLoader 类型冗余**：已修复。`ConfigLoader.load()` 现在直接返回 `ConfigStore` 强类型对象，访问器全部改为直接读取属性，`_to_int`/`_to_bool` 防御性转换已从访问器层移除。

---

**治理结论**：WebRPA 现已具备支撑工业级业务负载的底座能力。
