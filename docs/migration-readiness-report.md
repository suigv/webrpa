# 迁移切换评估报告（Task 12）

## 可立即切换能力

- `device_reboot`（插件）
- `device_soft_reset`（插件）
- `x_mobile_login`（插件状态契约）
- `follow_interaction` / `home_interaction`（互动链路第一批）
- `blogger_scrape` + `profile_clone`（数据契约链路）
- `/api/tasks/catalog`（任务目录查询）

## 暂缓能力

- `quote_intercept` / `reply_dm` / `nurture` 的完整策略迁移（仍需业务细化与策略回归）

## 风险

1. `tmp/` 中仍保留旧实现，仅作为参考归档，不应被新运行时直接依赖。
2. 互动链路插件目前以契约优先，复杂策略需要后续增量增强。

## 回滚策略

- 插件级回滚：删除/禁用对应 `plugins/<name>` 目录即可停止该任务路由。
- 控制面回滚：`/api/tasks/catalog` 保留只读查询，不影响任务执行面。
- 门禁回滚：`tools/run_migration_gates.sh` 为统一验收入口，失败即阻断发布。
