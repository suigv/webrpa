# Current Main Status

更新时间：2026-03-08

## 已完成

- RPA/RPC remediation 已在当前工作树完成并通过全量验证
- selector 生命周期清理已补齐，解释器退出时会释放 selector-backed RPC 与 tracked node 资源
- shared RPC bootstrap 已统一抽取到 `engine/actions/_rpc_bootstrap.py`
- `ui_actions` / `state_actions` 已收敛为稳定 facade，selector/state internals 已拆到 helper 子模块
- `sdk_actions.py` 已保持稳定 facade，并把运行时、配置、shared-store、profile 与业务辅助逻辑下沉到 `sdk_*_support.py` helper 模块
- `core/task_control.py` 中的账号反馈策略已抽到 `core/account_feedback.py`
- `hardware_adapters/mytRpc.py` 已补齐 pointer ownership、timeout 透传与 failure-safe 保护
- `UIStateService` 统一只读状态契约已落地，native/mobile 与 browser/web 观察结果已收敛到共享 contract，并保留平台证据细节
- service-backed thin action wrappers 与动作注册已完成，legacy action 兼容面保持可用
- interpreter / condition 已接入统一状态观察与等待能力，保持现有 YAML 模型与 cleanup 语义，不引入新 DSL
- `plugins/x_mobile_login`、`dm_reply`、`nurture` 已完成定向 UIStateService 迁移，`profile_clone` 也完成了目标明确的状态观察收口
- `/api/runtime/execute` 已明确为 debug/internal-only 同步直跑入口，并有回归测试保证它不参与 `/api/tasks` 托管任务记录、事件、重试、取消或指标产物
- 原子化相关中文复盘文档已迁入 `docs/reference/`，参考审查文档与 README 入口均已同步
- `MYT_ENABLE_RPC=0` 启动与 `/health` 契约已验证通过
- UIStateService rollout 最终验证波次已完成，覆盖 service / adapters / wrappers / interpreter / plugins / 全量测试 / required startup checks

## 部分完成

- `sdk_actions` 经过 facade + helper 拆分后，体量与职责边界仍值得继续观察，但已不属于当前阻塞项

## 下一步优先级

1. 继续观察新旧插件是否稳定复用 `UIStateService` 统一状态边界，避免重新长出插件内重复状态判断
2. 将 `docs/monitoring_rollout.md` 与渲染监控配置落到外部 Prometheus / Alertmanager 环境
3. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`
4. 继续观察 `sdk_actions`、shared JSON store 与相关插件 watchpoint 的触发条件

## 参考文档

- `docs/reference/功能原子化问题分类说明.md`
- `docs/reference/功能原子化修复结果.md`
- `docs/reference/atomicity_architecture_review.md`
