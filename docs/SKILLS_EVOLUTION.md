# WebRPA "Skills化" 演进报告与架构分析

## 1. 核心背景
在 WebRPA 体系中，“Skills化” 指的是将底层原子动作（Atomic Actions）通过声明式协议（YAML + Schema）封装为可感知、可编排、高鲁棒性的业务组件（Plugins/Skills），供 AI Agent 或自动化引擎消费。

---

## 2. 现状评估 (Current Progress)

### 2.1 基础设施 (Infrastructure) - **[90%]**
- **校验协议**：已建立严格的 `v1` 插件协议，通过 Pydantic 强制要求 `api_version`, `kind`, `inputs` 等元数据，确保了工具发现的确定性。
- **注册机制**：统一的 `ActionRegistry` 收集了超过 150 个原子动作，为 Skill 的构建提供了丰富的基石。
- **任务链路**：插件已作为 `/api/tasks` 的一等公民，支持优先级、重试、SSE 事件流和指标统计。

### 2.2 技能密度 (Skill Density) - **[40%]**
- **系统技能**：具备 `device_reboot`, `hezi_sdk_probe` 等维护技能。
- **业务技能**：处于起步阶段。虽然 AI 可以自主探索，但尚未大规模固化为稳定的业务插件（如“一键发推”、“自动关注”等）。
- **工具链**：`GoldenRunDistiller` 标志着具备了“技能自学习”能力，能从成功轨迹中提取选择器。

### 2.3 AI 协同 (AI Orchestration) - **[75%]**
- **协议注入**：`AI_SKILL.md` 明确了 AI Agent 的 SOP 和交互契约。
- **闭环系统**：AI 执行轨迹可以通过蒸馏回流至本地配置，实现了“探索 -> 总结 -> 技能化”的闭环。

---

## 3. 架构阻力分析 (Architectural Friction)

当前架构在向高度自动化“Skills化”演进时，存在以下四个核心摩擦点：

1.  **前置校验过于僵化**：
    `Runner` 在执行前进行严格的类型/动作校验。AI 生成的 YAML 若有微小格式偏差（如 `int` vs `float`），任务会直接熔断。
2.  **动作注册表缺乏自描述性**：
    `ActionRegistry` 仅映射函数，缺乏 JSON Schema 定义。AI 编写 Skill 时难以准确获知参数要求，只能依赖静态文档。
3.  **变量空间缺乏隔离（作用域）**：
    `context.vars` 为全局扁平结构。在复杂技能嵌套调用时，极易产生变量重名（Shadowing）冲突，阻碍了 Skill 的模块化复用。
4.  **异常处理缺乏全局钩子**：
    `on_fail` 仅限 Step 级。业务级 Skill 需要类似 `try...finally` 或全局 `on_error` 的回退机制（如登录失败后自动清理环境），目前只能靠大量冗长的 `goto` 模拟。

---

## 4. 演进方向与非破坏性方案

### 阶段一：降低摩擦 (Short-term)
- **注册表声明化**：在 `ActionRegistry` 中补全参数 Schema 定义，支持 `describe()` API。
- **宽容校验模式**：引入 `MYT_PERMISSIVE_VALIDATION` 开关，在 AI 合成模式下允许非关键类型自动转换。

### 阶段二：增强表达力 (Mid-term)
- **变量栈抽象**：将 `context.vars` 内部改造为支持层级作用域，支持局部变量定义。
- **脚本级生命周期钩子**：在 `WorkflowScript` 模型中增加 `finally:` 或 `on_error:` 块。

### 阶段三：自动化闭环 (Long-term)
- **无人值守蒸馏**：当 AI 成功完成高价值任务后，系统自动触发 `distill` 生成插件草稿。
- **语义化搜索**：通过 Embedding 对 `/api/tasks/catalog` 进行语义化扩展，帮助 AI 精准选词。

---

## 5. 结论
WebRPA 的 **“Skills化”框架已经稳固**。下一阶段的工作重心应从“基底开发”转向 **“业务内容填充”** 与 **“架构解耦增强”**，以支撑更大规模的 AI 自主自动化。
