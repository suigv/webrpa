---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-25
stale_after_days: 14
verification_method:
  - config tree audit
  - startup validation
  - /health snapshot inspection
---

# Configuration

本文件只保留当前仓库里仍然存在、且能从代码结构直接确认的配置面。

## 配置文件

- `config/system.yaml`
  - 系统级配置入口。
- `config/devices.json`
  - 设备与拓扑配置；仓库默认文件应保持中性模板，不提交真实局域网设备 IP。
- `config/apps/*.yaml`
  - 单应用配置；当前仓库里它是 app 相关配置的主入口。
- `config/data/`
  - 运行时数据目录。

## App 配置结构

`config/apps/*.yaml` 当前同时承载共享 app 身份、共享骨架能力和 app 内业务分支资料。当前代码已使用的字段包括：

- `app_id`、`display_name`、`aliases`
- `package_name`、`package_names`
- `default_branch`
- `branches`
- `xml_filter`
- `states`
- `stage_patterns`
- `schemes`
- `selectors`
- `agent_hint`

边界：

- `schemes` 仍属于人工维护的共享能力，不依赖蒸馏自动写入。
- app 级共享配置只应保留稳定、可复用的内容。
- AI 或蒸馏学习结果先进入审核候选，再决定是否 promotion 到共享 app YAML。
- 当前候选审核路径支持把 `selectors`、`states`、`stage_patterns`、`xml_filter`、`agent_hint` promotion 到共享 app YAML。

## 关键环境变量

这些变量直接影响当前运行形态：

- `MYT_LOAD_DOTENV`
  - 为 `1` 时允许从仓库根目录加载 `.env`。
- `MYT_ENABLE_RPC`
  - 为 `0` 时禁用 RPC 依赖，允许纯 Web / 无硬件开发路径。
- `MYT_ENABLE_VLM`
  - 控制视觉模型相关路径是否启用。
- `MYT_FRONTEND_URL`
  - 影响 `/web` 的跳转目标。
- `MYT_AUTH_MODE`
  - 设为 `jwt` 时启用 JWT 鉴权。
- `MYT_JWT_SECRET`
  - JWT 模式所需 secret。
- `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS`
  - 控制插件未声明输入是否被拒绝。
- `MYT_DATA_SUBDIR`
  - 将运行数据写入 `config/data/<subdir>/`。

## 当前配置边界

- 非敏感系统配置优先放在 `config/system.yaml`。
- 敏感信息优先通过环境变量注入，不写入仓库配置。
- 运行时数据必须留在 `config/data/` 下。
- app 相关静态配置统一落在 `config/apps/*.yaml`，不要把 app 特例塞回框架代码。

## 当前运行时数据

- 账号、任务等运行时数据继续落在 `config/data/`。
- workflow draft 蒸馏产物当前写入 `config/data/distilled_plugins/`，不再写入 `plugins/` 源码目录。
- app 配置审核候选当前使用独立数据存储，不直接把未审核学习结果写入 `config/apps/*.yaml`。
- 当 `config/devices.json` 中的 `discovery_enabled=true` 时，服务启动后会立即进行一次局域网设备扫描，之后按小时扫描一次。
- 自动扫描与手动 `POST /api/devices/discover` 都会把扫描结果回写到 `config/devices.json` 的 `discovered_device_ips` / `discovered_total_devices`。

## 当前可观察入口

- `/health` 会返回 `task_policy` 快照，可用于检查部分任务运行策略是否生效。
- `GET /api/config/` / `PUT /api/config/` 是当前配置读写 API。
