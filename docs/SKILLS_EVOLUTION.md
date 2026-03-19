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
- **系统技能**：当前插件库已收敛为 `one_click_new_device` 这一条代表性设备初始化技能链路。
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

### 阶段三：成熟度漏斗与终极蒸馏 (Current Focus)
- **自主探索 (AI Bootstrapping)**：打破硬编码规则枷锁，允许 AI 在 `unknown` 状态下利用 VLM 视觉直觉进行测绘。
- **数据驱动演进 (Data-Driven Intermediary)**：自动从 Trace 中提取 Resource ID 等稳态特征，将任务从昂贵的推理模式平滑转入低成本的原生匹配模式。
- **YAML 插件大师模式 (Master YAML Distillation)**：当数据足够稳定后，系统自动“编译”出脱离 AI 依赖、全量结构化、极速执行的终极 YAML 插件脚本。

---

## 5. 结论
WebRPA 的 **“Skills化”框架已经稳固**。通过近期引入的 **Planner 抽象层 (BasePlanner)** 和 **旁路蒸馏 (LLMDraftRefiner)**，系统已成功实现了决策层与执行层的物理隔离，并具备了对抗外部大模型波动的“防波堤”。

### 阶段四：智能体自反思加固 (Completed)
- **短期记忆注入 (History Digest)**：实现了执行历史的滑动窗口摘要传递，模型现可感知过去 5 步的决策后果，减少了盲目重试。
- **闭环失败反馈 (Failure-Aware)**：动作执行结果实时回流至 Planner，失败后的 prompt 会自动包含反思块与修正引导。
- **动作指纹与重复熔断**：建立了基于 (Action, Params) 的指纹追踪机制，有效识别并阻断了逻辑陷阱导致的死循环。

### 阶段五：业务内容填充与 OmniVision 演进 (Pending)
下一阶段的工作重心应从“基底开发”转向 **“业务内容填充”**。系统已完全准备好无缝接入更强大的新一代模型（如 OmniVision 架构），以支撑更大规模的 AI 自主自动化，不再在此产生架构技术债。
