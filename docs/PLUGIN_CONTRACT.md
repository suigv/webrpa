---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
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

## Payload 边界

- `payload` 只承载插件声明过的业务输入。
- `targets` 承载目标设备/云机上下文。
- `task_id`、`device_ip`、端口、运行时 trace 等信息不应作为未声明特权字段继续混入插件业务 `payload`。
- `app_id` 只有在插件显式声明该输入时，才应进入 `payload`。

## 前端和 API 约束

- `GET /api/tasks/catalog` 是当前插件目录发现入口。
- 前端任务表单应从 catalog 的 `inputs` 渲染，而不是手写字段表。
- `POST /api/tasks/` 的常规插件路径应使用 `task + payload + targets`。
- `script` 仍是匿名脚本路径，不是常规插件任务主入口。

## 蒸馏相关字段

当前 manifest 里仍可看到与蒸馏相关的字段，例如 `distillable`。  
是否应该开启蒸馏，取决于插件是否代表可复用的稳定工作流，而不是一次性设备编排或随机化流程。
