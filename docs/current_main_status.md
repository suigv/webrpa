# Current Main Status

更新时间：2026-03-09

## 已完成

- `wait_until` 轮询语义已收紧，并补齐 success-before-timeout、超时文本、`on_timeout goto`、`on_fail`、取消态与动态重轮询回归覆盖
- `ExecutionContext.session.defaults` 已作为最小任务级接缝落地，运行时连接值可来自 payload、`_target` 与 manifest 默认值，同时保持显式 action 参数优先
- UI 状态观察覆盖已保守扩展到 `timeline_candidates`、`follow_targets` 与集合首项别名，不改变顶层观察结果形状
- `UIStateService` 的共享结果构造、timing 与 browser polling helper 已落地，browser 前置不可用错误改为 `attempt=0/samples=0`，native bindings 也已拆出独立 registry
- 有界页面辅助能力已补齐，`ui.navigate_to` 与 `ui.fill_form` 可用于页面级导航和表单驱动，不扩大为通用恢复系统
- `x_mobile_login` 已完成重复 runtime 接线收口：当前验证明确覆盖 `device_ip` 不再在步骤中重复传递，且相关步骤不再显式重复声明 `package`；既有 status / message 契约保持不变，相关登录工作流验证已通过
- `/web` 仍只在 smoke 范围内声明为静态控制台入口，`/ws/logs` 已补上专用 route 回归测试
- 运行时控制面验证波次已完成，包含定向测试、`MYT_ENABLE_RPC=0` 启动与 `/health` smoke

## 部分完成

- `sdk_actions` 拆分后的体量与职责边界仍值得继续观察，但不属于当前阻塞项

## 下一步优先级

1. 继续观察新旧插件是否稳定复用统一状态边界，避免重新长出插件内重复状态判断
2. 将 workflow-level conservative recovery 保持为 deferred watchpoint，仅在同一类有界有序链路跨多个 workflow 重复出现后再考虑上提
3. 将 `docs/monitoring_rollout.md` 与渲染监控配置落到外部 Prometheus / Alertmanager 环境
4. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`
5. 继续观察 `sdk_actions`、shared JSON store 与相关插件 watchpoint 的触发条件

## 参考文档

- `docs/reference/功能原子化问题分类说明.md`
- `docs/reference/功能原子化修复结果.md`
- `docs/reference/atomicity_architecture_review.md`
