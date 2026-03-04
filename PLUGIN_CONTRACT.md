# 插件契约 v2（`new/plugins/`）

## 目标
定义稳定的 **YAML 声明式插件契约**，让运行时可以执行业务工作流，而不耦合 API 路由或历史任务代码。

## 版本
- 当前契约：`v2`（仅 YAML）
- 历史版本：`v1`（JSON + handler.py）——**已弃用**

## 目录结构

每个插件位于 `new/plugins/` 下独立目录：

```text
new/plugins/<plugin_name>/
├── manifest.yaml    # 插件元信息与输入声明
└── script.yaml      # 声明式工作流步骤
```

两文件均为必需。插件不再使用 Python handler 入口。

## Manifest 模式（`manifest.yaml`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `api_version` | `"v1"` | 是 | 模式版本（固定 `v1`） |
| `kind` | `"plugin"` | 是 | 资源类型（固定 `plugin`） |
| `name` | string | 是 | 插件唯一标识（应与目录名一致） |
| `version` | string | 是 | 插件版本（建议 semver） |
| `display_name` | string | 是 | 展示名称 |
| `description` | string | 否 | 描述 |
| `entry_script` | string | 否 | 入口脚本名（默认 `script.yaml`） |
| `inputs` | list[PluginInput] | 否 | 输入参数声明 |

### PluginInput 模式

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 参数名 |
| `type` | `"string" \| "integer" \| "number" \| "boolean"` | 是 | 参数类型 |
| `required` | bool | 否 | 是否必填（默认 `true`） |
| `default` | any | 否 | 默认值 |

## Workflow 模式（`script.yaml`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `version` | `"v1"` | 是 | 脚本模式版本 |
| `workflow` | string | 是 | 工作流名称（建议与插件名一致） |
| `vars` | dict | 否 | 脚本级变量（支持插值） |
| `steps` | list[Step] | 是 | 有序步骤列表 |

### 变量插值

使用 `${namespace.path}` 语法：
- `${payload.key}`：来自运行时 payload
- `${vars.key}`：来自脚本变量或前置步骤结果
- `${vars.creds.field}`：点路径访问
- `${payload.url:-https://default.com}`：`:-` 后跟默认值

## 步骤原语（5 类）

### 1) `action`：执行已注册动作
关键字段：`action`、`params`、`save_as`、`on_fail`

### 2) `if`：条件分支
关键字段：`when`、`then`、`otherwise`

### 3) `wait_until`：轮询等待
关键字段：`check`、`interval_ms`、`timeout_ms`、`on_timeout`

### 4) `goto`：无条件跳转
关键字段：`target`

### 5) `stop`：结束工作流
关键字段：`status`（`success|failed`）、`message`

## 条件类型

| 类型 | 字段 | 说明 |
|---|---|---|
| `text_contains` | `text` | 页面 HTML 包含文本（忽略大小写） |
| `url_contains` | `text` | 当前 URL 包含文本 |
| `exists` | `selector` | DOM 中存在匹配元素 |
| `var_equals` | `var`, `equals` | 变量等值判断 |
| `result_ok` | — | 上一步动作结果为成功 |

## 失败策略（`on_fail`）

| 策略 | 字段 | 行为 |
|---|---|---|
| `abort` | — | 终止并返回错误（默认） |
| `skip` | — | 忽略失败，继续后续步骤 |
| `retry` | `retries`, `delay_ms` | 重试 N 次 |
| `goto` | `goto` | 失败后跳转到指定标签 |

## 内置动作（示例）

### 浏览器动作
- `browser.open`
- `browser.input`
- `browser.click`
- `browser.exists`
- `browser.check_html`
- `browser.wait_url`
- `browser.close`

### 凭据动作
- `credentials.load`

## 运行时执行流程

1. `PluginLoader.scan()` 发现 `plugins/*/manifest.yaml`
2. `Runner.run()` 按任务名匹配插件
3. `parse_script()` 解析并校验 `script.yaml`
4. `Interpreter.execute()` 执行工作流
5. 浏览器会话按需惰性创建
6. 解释器在 `finally` 中负责关闭浏览器会话
7. `max_transitions = 500` 防止跳转死循环
8. `wait_until` 强制受 `timeout_ms` 和引擎硬上限（120s）限制

## 安全与隔离规则

- 插件不得依赖旧命名空间（`tasks` / `app.*`）
- 插件不得包含 Python 逻辑（仅 YAML）
- 凭据必须通过 `credentials.load` 且路径受白名单约束
- 不允许执行 `new/` 范围外的破坏性文件操作

## 插件验收检查单

- [ ] `manifest.yaml` 可通过 `PluginManifest` 校验
- [ ] `script.yaml` 可通过 `WorkflowScript` 校验
- [ ] 引用标签全部存在
- [ ] 无重复标签
- [ ] 引用动作均已注册
- [ ] 失败分支（`on_fail`）有测试覆盖
- [ ] `check_no_legacy_imports.py` 通过
