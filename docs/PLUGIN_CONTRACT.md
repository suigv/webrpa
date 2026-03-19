# 插件契约与输入规范 (运行时 v1)

## 1. 目标与结构
定义稳定的 **YAML 声明式插件契约**，实现业务流与执行引擎的解耦。
当前运行时代码要求 `manifest.yaml` 使用 `api_version: v1`，`script.yaml` 使用 `version: v1`。

> [!NOTE]
> 仓库里曾出现过“插件契约 (v2)”的文档命名，但它并没有对应到一个独立落地的运行时解析版本。就当前代码而言，插件运行时只有 `v1` 这一套实际生效的 schema；此前的 “v2” 更接近文档分代或设计语义，而不是 `api_version: v2` 这样的可执行协议版本。

> [!IMPORTANT]
> **终极演进目标**：在 Architecture 2.0 的“成熟度漏斗”中，YAML 插件是系统的终极产物（Master YAML）。它代表了经过 AI 探索和数据固化后，能够脱离 LLM/VLM 依赖的极致性能与确定性脚本。

### 目录结构
```text
plugins/<plugin_name>/
├── manifest.yaml    # 插件元信息与输入声明
└── script.yaml      # 声明式工作流步骤
```

---

## 2. 输入声明规范 (`manifest.yaml`)

### 核心字段
| 字段 | 类型 | 说明 |
|---|---|---|
| `api_version` | string | 固定填 `v1` |
| `kind` | string | 固定填 `plugin` |
| `name` | string | 插件唯一标识（须与目录名一致） |
| `version` | string | 插件版本号 |
| `display_name` | string | 插件显示名称 |
| `category` | string | 插件分类（默认 `其他`） |
| `description` | string | 插件功能描述（用于 AI 发现） |
| `inputs` | list[Input] | 输入参数声明 |
| `distillable` | bool | 是否适合进入“AI 执行后蒸馏”链路（默认 `true`） |
| `expected_output` | object | (可选) 预期输出结果的结构化说明 |

### 输入参数 (Input)
| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 参数名（在脚本中通过 `${payload.name}` 引用） |
| `type` | string | `string` | `integer` | `number` | `boolean` |
| `required` | bool | 是否必填（默认 `true`） |
| `default` | any | 默认值 |
| `label` | string | 前端展示名称（可选） |
| `description` | string | 字段说明（可选） |
| `placeholder` | string | 前端占位提示（可选） |
| `advanced` | bool | 是否归入“高级参数”区域（默认 `false`） |
| `system` | bool | 是否由系统注入、默认不在 UI 渲染（默认 `false`） |
| `widget` | string | 推荐控件：`text` / `number` / `checkbox` / `select` / `hidden` |
| `options` | list[Option] | 下拉候选项，适用于 `select` |

### Option
| 字段 | 类型 | 说明 |
|---|---|---|
| `value` | any | 真实提交值 |
| `label` | string | 用户可见名称 |
| `description` | string | 选项说明（可选） |

### 运行时验证策略
- **严格模式**：由 `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=1` 控制。若开启，插件将拒绝任何未在 `manifest.yaml` 中声明的输入参数（`task` 和 `_` 前缀参数除外）。
- **验证失败**：返回 `status=failed_config_error`, `checkpoint=dispatch`。
- **目录接口透传**：`GET /api/tasks/catalog` 会把 `inputs` 元数据原样透传给前端，任务面板可据此渲染文本框、数字框、复选框和下拉框。
- **蒸馏适用性**：`distillable: false` 的插件会在目录与指标接口中明确标记为“不可蒸馏”；`POST /api/tasks/distill/{plugin_name}` 会直接拒绝这类插件。
- **目录可见性**：`visible_in_task_catalog: false` 的插件默认不会出现在 `GET /api/tasks/catalog`；如需运维查看，可显式调用 `GET /api/tasks/catalog?include_hidden=true`。
- **前端提交约束**：Web 端派发插件任务时，会按 `inputs` 白名单过滤 payload，只提交 `manifest.yaml` 已声明字段；`device_ip`、`package`、`app_id`、账号注入字段等系统侧上下文不再默认混入插件入参。

### 哪些插件不适合蒸馏

以下类型应显式设置 `distillable: false`：

- 设备初始化、环境重置、运维编排类插件
- 主要依赖 SDK / HTTP API，而不是稳定 UI 路径的插件
- 含有随机生成、库存选择、重启回线、状态探测的插件
- 每次执行结果天然应该不同的插件

典型例子：

- `one_click_new_device`
- 指纹更新 / 代理切换 / 联系人注入 / 清缓存 / 重置环境

如果这些插件也不希望客户在常规任务目录中直接看到，应同时设置：

- `visible_in_task_catalog: false`

原因：

- 这类任务的价值在于“参数化编排”，不是“复刻一次 AI 操作轨迹”
- 蒸馏会错误固化随机结果、库存状态或某次环境快照
- 即使执行成功，也不应把一次运行样本当作可复用的业务 YAML 模板

---

## 3. 工作流脚本规范 (`script.yaml`)

### 变量插值
- `${payload.key}`：引用外部输入。
- `${vars.key}`：引用脚本内部变量或步骤结果（通过 `save_as` 保存）。
- `${payload.url:-default_val}`：支持默认值语法。

### 核心结构
| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | string | 固定填 `v1` |
| `workflow` | string | 工作流名称描述 |
| `steps` | list[Step] | 步骤列表 |

### 核心指令 (Step)
每个步骤必须包含 `kind` 字段作为类型鉴别器。

1.  **action** (`kind: action`)：执行原子动作（如 `ui.click`, `browser.open`）。
2.  **if** (`kind: if`)：基于条件（`when`, `then`, `otherwise`）的分支跳转。
3.  **wait_until** (`kind: wait_until`)：轮询等待特定状态达成。
4.  **goto** (`kind: goto`)：标签跳转。
5.  **stop** (`kind: stop`)：显式终止并返回成功或失败。

> **说明**：如需跨页面导航，请使用 `ui.navigate_to`，并在 `params` 或 session defaults 提供 `routes` 与 `hops`（路由定义 + 跳转动作）。该动作基于 `ui.match_state` 校验到达状态，避免隐式硬编码路径。对 native/browser 状态观察，推荐使用 `state_profile_id`；运行时继续兼容旧参数名 `binding_id`。

### 推荐编排模式：Inventory / Selector / Generator

当插件需要处理“设备初始化 / 防封环境配置 / 随机资料注入”时，推荐遵循下面的职责分层：

- `inventory.*`
  - 负责“必须先从上游拉取”的数据，如在线机型、本地机型、国家码、镜像列表。
  - 当前已提供：`inventory.get_phone_models` / `inventory.refresh_phone_models`
- `selector.*`
  - 负责对库存做筛选和确定性选择，避免把筛选逻辑散落在 YAML 中。
  - 当前已提供：`selector.select_phone_model`
- `generator.*`
  - 负责本地可合成的数据，如指纹、联系人、环境包。
  - 当前已提供：`generator.generate_fingerprint` / `generator.generate_contact` / `generator.generate_env_bundle`

推荐脚本模式：

```yaml
steps:
  - kind: action
    action: selector.select_phone_model
    save_as: selected_model
    params:
      source: online
      device_ip: "${payload.device_ip}"
      seed: "${payload.seed}"

  - kind: action
    action: generator.generate_env_bundle
    save_as: env_bundle
    params:
      country_profile: jp_mobile
      seed: "${payload.seed}"

  - kind: action
    action: sdk.switch_model
    params:
      name: "${payload.cloud_name}"
      model_id: "${vars.selected_model.apply.model_id:-}"
      localModel: "${vars.selected_model.apply.local_model:-}"

  - kind: action
    action: mytos.set_fingerprint
    params:
      data: "${vars.env_bundle.fingerprint}"
```

这样做的目的：
- 先获取的数据与随机生成的数据边界清晰
- API、插件、前端预热可共用同一套服务
- `save_as` 后的输出结构稳定，便于后续动作直接消费

---

## 4. 失败处理策略 (`on_fail`)
- **abort**：立即终止（默认）。
- **skip**：忽略错误继续。
- **retry**：配置 `retries` 和 `delay_ms` 进行局部重试。
- **goto**：跳转到指定的异常处理标签。

---

## 5. 开发者检查单
- [ ] `manifest.yaml` 的 `name` 与目录名一致。
- [ ] `manifest.yaml` 包含 `api_version: v1` 和 `kind: plugin`。
- [ ] `script.yaml` 包含 `version: v1` 和 `workflow` 名称。
- [ ] 脚本中每个步骤都包含 `kind` 鉴别器（如 `kind: action`）。
- [ ] 所有 `action` 引用的动作均已在系统中注册。
- [ ] 步骤中引用的 `${payload.xxx}` 均在 `manifest` 中有对应声明。
- [ ] 关键步骤配置了合理的 `on_fail` 策略。
- [ ] 复杂跳转逻辑已通过 `max_transitions`（硬上限 500）压力测试。
- [ ] 对“获取后选择”和“随机生成”两类数据，优先复用 `inventory.*` / `selector.*` / `generator.*`，避免在 YAML 中重复堆条件和随机规则。
