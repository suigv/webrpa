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
| `expected_output` | object | (可选) 预期输出结果的结构化说明 |

### 输入参数 (Input)
| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 参数名（在脚本中通过 `${payload.name}` 引用） |
| `type` | string | `string` | `integer` | `number` | `boolean` |
| `required` | bool | 是否必填（默认 `true`） |
| `default` | any | 默认值 |

### 运行时验证策略
- **严格模式**：由 `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=1` 控制。若开启，插件将拒绝任何未在 `manifest.yaml` 中声明的输入参数（`task` 和 `_` 前缀参数除外）。
- **验证失败**：返回 `status=failed_config_error`, `checkpoint=dispatch`。

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
