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
- `plugins/x_mobile_login/script.yaml` 已做定向 fallback-chain 压缩，复用现有 composite action 去掉登录主路径中的重复点击/输入回退编排，但没有把插件改写成全新结构
- `/api/runtime/execute` 已明确为 debug/internal-only 同步直跑入口，并有回归测试保证它不参与 `/api/tasks` 托管任务记录、事件、重试、取消或指标产物
- 原子化相关中文复盘文档已迁入 `docs/reference/`，参考审查文档与 README 入口均已同步
- `MYT_ENABLE_RPC=0` 启动与 `/health` 契约已验证通过

## 部分完成

- `sdk_actions` 经过 facade + helper 拆分后，体量与职责边界仍值得继续观察，但已不属于当前阻塞项

## 下一步优先级

1. 按提交边界整理已完成的 follow-up 文档与监控产物，补齐 commit / PR 证据链
2. 将 `docs/monitoring_rollout.md` 与渲染监控配置落到外部 Prometheus / Alertmanager 环境
3. 按 `docs/stale_running_recovery_tuning.md` 在真实部署里校准 `MYT_TASK_STALE_RUNNING_SECONDS`
4. 继续观察 `sdk_actions`、shared JSON store 与 `x_mobile_login` 在定向压缩后的 watchpoint 触发条件

## 参考文档

- `docs/reference/功能原子化问题分类说明.md`
- `docs/reference/功能原子化修复结果.md`
- `docs/reference/atomicity_architecture_review.md`
