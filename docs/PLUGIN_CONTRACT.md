---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-26
stale_after_days: 14
verification_method:
  - manifest and script audit in plugins/*
  - task catalog contract audit
---

# Plugin Contract

当前运行时的插件协议是 `v1`。

## 目录结构

```text
plugins/<plugin_name>/
├── manifest.yaml
└── script.yaml
```

## `manifest.yaml`

当前仓库要求插件 manifest 至少表达这些信息：

- `api_version: v1`
- `kind: plugin`
- `name`
- `version`
- `display_name`
- `description`
- `inputs`

`inputs` 是插件业务输入的真源。前端和 API 都应以它为白名单生成和过滤 `payload`。

## `script.yaml`

当前脚本文件使用：

- `version: v1`
- `workflow`
- `steps`

步骤以声明式工作流方式组织，运行时通过 `engine/plugin_loader.py` 和解释器执行。

## 声明式单脚本 schema 草案

仓库当前还存在一份面向 AI 对话和后续探索/蒸馏链路的内部 schema 草案：

- `engine/models/declarative_script.py` 中的 `DeclarativeScriptV0`

它当前是声明层对象，不是插件运行时 `script.yaml` 的替代品。

当前用途：

- 约束 AI 对话产出的单脚本声明结构
- 表达 App 归属、输入、产出、阶段、终态、人工接管策略
- 作为 AI planner 到 `agent_executor` 的内部桥接对象，通过 `_planner_declarative_*` 字段把脚本摘要和阶段锚点带入探索执行
- 作为 workflow draft / run asset / distill 响应里的 `declarative_binding` 来源，标记一次探索样本绑定到了哪个声明脚本、最近停在什么阶段

当前边界：

- 不承载运行态快照
- 不直接承载 action 明细或 selector 细节
- 不等同于当前插件 `v1` 运行时协议
- 不是对外插件 payload 合约；`_planner_declarative_*` 仅属于 AI 对话内部运行时字段
- 阶段推进证据当前以 runtime trace / task event / workflow draft binding 形式暴露，还没有升级为插件 `script.yaml` 的正式阶段状态协议

## Payload 边界

- `payload` 只承载插件声明过的业务输入。
- `targets` 承载目标设备/云机上下文。
- `task_id`、`device_ip`、端口、运行时 trace 等信息不应作为未声明特权字段继续混入插件业务 `payload`。
- `app_id` 只有在插件显式声明该输入时，才应进入 `payload`。

## 业务分支与默认值

- 业务分支应优先通过显式声明的 `branch_id` 输入表达，而不是继续扩散历史别名字段。
- 如果插件允许任务级覆盖，覆盖字段也必须出现在 `manifest.inputs` 中，不能依赖隐式注入。
- 当任务没有显式填写分支类输入时，运行时可以回退到账号默认分支或 app 默认分支；这种默认解析不改变 `payload` 白名单边界。
- 共享资源隔离键、回复类型、关键词等业务参数如果需要任务级输入，同样必须由 manifest 明确声明。

## 前端和 API 约束

- `GET /api/tasks/catalog` 是当前插件目录发现入口。
- 前端任务表单应从 catalog 的 `inputs` 渲染，而不是手写字段表。
- `POST /api/tasks/` 的常规插件路径应使用 `task + payload + targets`。
- `script` 仍是匿名脚本路径，不是常规插件任务主入口。

## 蒸馏相关字段

当前 manifest 里仍可看到与蒸馏相关的字段，例如 `distillable`。  
是否应该开启蒸馏，取决于插件是否代表可复用的稳定工作流，而不是一次性设备编排或随机化流程。

当前 manifest 还支持 `distill_mode`，用于声明蒸馏产物类型和运行时依赖：

- `output_type`
  - `pure_yaml`
  - `yaml_with_ai`
  - `yaml_with_channel`
  - `human_assisted`
  - `context_only`
- `requires_ai_runtime`
- `requires_channel_runtime`

当前约束：

- 图形验证码、滑块验证码等 AI 参与型挑战，应进入 `yaml_with_ai`。
- 邮箱码、短信码等依赖收件箱/短信通道读取的挑战，应进入 `yaml_with_channel`。
- 人工补洞成功样本不应伪装成上述自动化产物，应进入 `human_assisted`。
- Golden run 直接蒸馏出的普通动作流，默认产物类型是 `pure_yaml`。

当前仓库已注册并接入第一版受控 challenge action contract：

- `ai.solve_captcha`
- `channel.read_email_code`
- `channel.read_sms_code`

当前边界：

- `ai.solve_captcha` 已支持通过 VLM/LLM 读取验证码图片并返回结构化结果；图像可来自当前截图或显式图片引用。
- `channel.read_email_code` 已支持运行时 hook 和基于 IMAP 的邮箱验证码轮询读取。
- `channel.read_sms_code` 已支持运行时 hook、显式短信正文或内存短信箱解析；当前没有通用设备短信收件箱适配器。
- 这些 action 仍属于受控节点，不等于任意自由 prompt 或所有通道都已平台化接入。

蒸馏产生的选择器、状态、阶段模式和 agent 提示等学习结果，不应直接改写共享 app YAML；当前路径是先进入候选池，待人工审核后再 promotion。

当前目录里的 `app_config_explorer` 属于通用建档/探索插件，它本身不可蒸馏；它的职责是触发一次受限探索，并把学习结果写入 app config 候选池。
