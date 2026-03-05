# 迁移矩阵（Legacy `tmp/` → Current `new/`）

本矩阵用于 Task 1：把 `tmp/tasks/*.py` 与 `tmp/app/core/workflow_engine.py` 的能力，映射到当前项目 `engine/actions/*`、`plugins/*`、`core/*`。

## 拓扑复用结论（硬约束）

- **复用同一设备体系**：旧项目与当前项目共享同类设备控制链路（RPA/API/SDK）。
- **端口规则不变**：继续使用 `core/port_calc.py` 中 cloud_index 决定端口的计算方式，不新增端口换算逻辑。

## 旧任务到新架构映射

| 旧任务文件 | 核心能力 | 目标落点（新架构） | 迁移类型 | 风险 | 备注 |
|---|---|---|---|---|---|
| `tmp/tasks/task_reboot_device.py` | 重启云机、恢复检查 | `plugins/device_reboot/*` + `engine/actions/sdk_actions.py` | 可直接迁移 | 低 | 已有 `restart_android/get_cloud_status` 能力 |
| `tmp/tasks/task_soft_reset.py` | 清理应用/账号、云机切换 | `plugins/device_soft_reset/*` + 新增高阶 `app.*` actions | 需新增 action | 中 | 依赖旧 `BotAgent` 高阶流程 |
| `tmp/tasks/task_login.py` | 登录、2FA、状态判定 | `plugins/x_mobile_login/*` + `engine/actions/ui_actions.py` | 需新增分支脚本 | 中高 | 需抽离硬编码坐标与页面分支 |
| `tmp/tasks/task_scrape_blogger.py` | 搜索采集博主池 | `plugins/blogger_scrape/*` + `core/data_store.py` | 需新增数据契约 | 中 | 采集冷却与去重规则需结构化 |
| `tmp/tasks/task_clone_profile.py` | 仿冒资料、图片处理 | `plugins/profile_clone/*` + `engine/actions/*` + `core/data_store.py` | 需拆分两阶段插件 | 高 | 含 `from app.core.data_store` 旧耦合 |
| `tmp/tasks/task_follow_followers.py` | 粉丝页关注截流 | `plugins/follow_intercept/*` + 复用 scrape/clone 输出 | 需组合迁移 | 高 | 依赖 `task_scrape_blogger` / `task_clone_profile` |
| `tmp/tasks/task_home_interaction.py` | 主页浏览与互动策略 | `plugins/home_interaction/*` | 需新增策略层 | 中高 | 需将策略参数化到配置 |
| `tmp/tasks/task_quote_intercept.py` | 搜索回复并引用 | `plugins/quote_intercept/*` + `core/data_store.py` | 需组合迁移 | 高 | 依赖已引用用户状态与博主池 |
| `tmp/tasks/task_reply_dm.py` | 私信读取 + AI 回复 | `plugins/reply_dm/*` + `ai_services/*` | 需新增服务适配 | 高 | AI provider/消息解析耦合较强 |
| `tmp/tasks/task_nurture.py` | 养号计数与策略浏览 | `plugins/nurture/*` + `core/data_store.py` | 需新增状态模型 | 中高 | 旧版使用 TXT/JSON 混合状态 |

## 共享依赖映射（跨任务）

| 旧依赖 | 新目标 |
|---|---|
| `common.bot_agent` | `engine/actions/ui_actions.py` + 新增高阶 app 生命周期 action |
| `common.box_api` | `hardware_adapters/myt_client.py` / `sdk_actions` |
| `common.blogger_manager` | `core/data_store.py` + blogger schema |
| `common.account_handler` | `core/data_store.py` + account schema |
| `common.ai_providers` | `ai_services/*` |
| `tasks.*` 互相调用 | 插件间通过显式数据契约串联（禁止直接 import） |

## 优先级与波次建议

1. **Wave A（低风险）**：`reboot_device` → `soft_reset`
2. **Wave B（关键链路）**：`login` → `scrape_blogger`
3. **Wave C（高耦合）**：`clone_profile/follow/quote/reply_dm/nurture/home_interaction`

## Guardrail 对齐

- 禁止新增 `from tasks` / `import tasks` / `from app.` / `import app.`。
- 禁止把 `tmp/` 目录当运行时依赖。
- 插件运行入口统一走 `engine/runner.py` + `engine/plugin_loader.py`。
