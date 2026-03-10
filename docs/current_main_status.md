# Current Main Status

更新时间：2026-03-10

## 已完成

- `wait_until` 轮询语义已收紧，并补齐 success-before-timeout、超时文本、`on_timeout goto`、`on_fail`、取消态与动态重轮询回归覆盖
- 托管 `gpt_executor` 任务模式已接到既有 `/api/tasks` 控制面，继续沿用现有创建、取消、重试、SSE 事件和终态语义
- GPT executor MVP 当前按 structured-state-first 观察运行，只有主观察不足时才显式回退到 XML tree、截图或 browser HTML 等补充模态
- GPT executor 的 step budget、stagnant-state circuit breaker 和 distillation parameterization 都是 MVP 硬要求，不是后补优化
- 原始模型轨迹已独立持久化到 `config/data/traces/` append-only JSONL，和 task events 分离
- Golden Run 目前只支持离线蒸馏成可审阅 YAML 草稿，不会自动安装到 `plugins/`；草稿只有通过 parse + replay smoke 后才算 usable
- `ExecutionContext.session.defaults` 已作为最小任务级接缝落地，运行时连接值可来自 payload、`_target` 与 manifest 默认值，同时保持显式 action 参数优先
- UI 状态观察覆盖已保守扩展到 `timeline_candidates`、`follow_targets` 与集合首项别名，不改变顶层观察结果形状
- `UIStateService` 的共享结果构造、timing 与 browser polling helper 已落地，browser 前置不可用错误改为 `attempt=0/samples=0`，native bindings 也已拆出独立 registry
- 有界页面辅助能力已补齐，`ui.navigate_to` 与 `ui.fill_form` 可用于页面级导航和表单驱动，不扩大为通用恢复系统
- `x_mobile_login` 已完成重复 runtime 接线收口：当前验证明确覆盖 `device_ip` 不再在步骤中重复传递，且相关步骤不再显式重复声明 `package`；既有 status / message 契约保持不变，相关登录工作流验证已通过
- `/web` 仍只在 smoke 范围内声明为静态控制台入口，`/ws/logs` 已补上专用 route 回归测试
- 运行时控制面验证波次已完成，包含定向测试、`MYT_ENABLE_RPC=0` 启动与 `/health` smoke
- **Web 控制台产品化改造 (2026-03-10)**：
    - 实时显示 `MYT_ENABLE_RPC` 运行状态。
    - 资源仓库支持账号**全字段编辑**（Token、邮箱等）及**状态一键重置**接口。
    - 任务流水支持**全局停止**、清空历史及单任务精准控制。
    - 设备集群支持**单机/全量初始化**，并植入“高危操作风险说明”、“二次确认”与“手动输入确认”机制。
- **反馈与监控体系打通**：
    - 全系统反馈语重构，由生硬的技术术语转向业务化的产品描述。
    - 实时执行日志流实现**跨线程 WebSocket 异步广播**，Action 执行结果（✅成功/❌失败）即时可视化。
    - **日志体验深度优化 (2026-03-10)**：
        - 实现了全量 11 个内置插件脚本（YAML）的业务化标签汉化。
        - 引入前端**互斥渲染引擎**与后端**覆盖式订阅机制**，彻底解决热重载导致的日志重复问题。
        - 实现了自愈过程的“透明化”日志输出，消除由于环境清理导致的感知白屏。
- **导航引擎鲁棒性强化 (ISA 兼容)**：
    - 引入 **“UI 清道夫” (Global Interstitial Handler)**，底层自动识别并排除同步联系人、升级引导等干扰项。
    - 引入 **“语义锚点判定” (Anchor-Based Navigation)**，支持在 ID 缺失环境下通过底部导航选中态进行多语言定位。
    - 建立自愈轨迹记录，确保引擎层介入的自救动作在日志中透明，为后续视觉模型任务蒸馏保留噪声处理数据。
- **插件体系汉化**：全量 11 个内置插件脚本标签完成专业中文重构，确保日志输出完全业务化。

## 部分完成

- `sdk_actions` 拆分后的体量与职责边界仍值得继续观察，但不属于当前阻塞项
- GPT executor MVP 已完成最小闭环，但 SoM overlays、shadow healing、multi-run consensus extraction 与更广恢复系统仍是 deferred watchpoint，不在 v1

## 下一步优先级

1. 继续观察新旧插件是否稳定复用统一状态边界，避免重新长出插件内重复状态判断
2. 将 workflow-level conservative recovery 保持为 deferred watchpoint，仅在同一类有界有序链路跨多个 workflow 重复出现后再考虑上提
3. 将 `docs/monitoring_rollout.md` 与渲染监控配置落到外部 Prometheus / Alertmanager 环境
4. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`
5. 继续观察 `sdk_actions`、shared JSON store 与相关插件 watchpoint 的触发条件
6. 继续把 GPT executor 增强限制在 deferred watchpoint，等真实运行证据证明需要时，再评估 SoM overlays、shadow healing、multi-run consensus extraction 或更广恢复系统是否该上提。

## 参考文档

- `docs/reference/功能原子化问题分类说明.md`
- `docs/reference/功能原子化修复结果.md`
- `docs/reference/atomicity_architecture_review.md`
