# 架构演进 2.0 (Architecture 2.0)

本文件描述 WebRPA 的核心架构愿景：将“AI 的探索轨迹”逐步沉淀为可复用、可审计、可脱离大模型的确定性执行资产（最终形态是 YAML 插件）。

它回答三个问题：
- 我们为什么要做“行为编译器 (Behavior Compiler)”？
- “成熟度漏斗 (Maturity Funnel)”三阶段分别交付什么？
- 工程上必须遵守哪些边界/不变量，才能让系统长期可演进？

> 相关的目标与成功标准请看 `docs/PROJECT_GOALS.md`；变更流水请看 `docs/project_progress.md`；代码拓扑与组件职责请看 `docs/HANDOFF.md`。

---

## 1) 核心理念：行为编译器 (Behavior Compiler)

WebRPA 不是一个“写死规则的脚本仓库”，而是一个把行为从“探索”编译到“确定性复用”的平台：

1. **AI 在真实界面中探索**（允许试错，但有预算与熔断）
2. **提取可复用的感知记忆**（例如 Resource ID、稳定 selector、登录阶段 patterns）
3. **将高成功率轨迹蒸馏为可复用资产**（最终落到 YAML 插件或可重放的确定性步骤）

平台的价值来自于“闭环”：每一次运行都能反哺下一次运行的稳定性与成本。

---

## 2) 成熟度漏斗 (Maturity Funnel)

### Phase A：AI 自主探索 (Bootstrapping / 2.0 模式)

目标：在缺少 UI 绑定/selector 的情况下，依然能完成 0→1 的任务执行，并产出“可用于学习”的证据。

典型特征：
- 以结构化观察为优先（state-first），必要时回退到 UI XML / 截图 / Browser HTML 等模态。
- 必须有 **Step/Token Budget** 与 **stagnant-state circuit breaker**，防止死循环与无意义试错。
- 产生的轨迹记录应归档到 `config/data/traces/`（用于后续分析与蒸馏门槛判定）。

### Phase B：数据驱动执行 (Native/Data Mode / 1.0 模式切入)

目标：把探索期得到的稳定信号沉淀为“便宜、快、可控”的数据驱动执行能力，并减少对大模型的依赖。

典型交付物：
- 应用级配置：`config/apps/*.yaml`（按 `package_name` 动态加载）
  - `states`：UI 状态集合（用于 `ui.match_state` 等）
  - `selectors`：稳定的 UI 元素定位（用于 selector/composite actions）
  - `stage_patterns`：登录阶段等感知记忆（在线学习回写仅限此处）
- 可复用的 composite actions（例如 selector 加载 + fallback 点击链），避免插件脚本重复搬运底层策略。

### Phase C：终极插件蒸馏 (YAML Mastery / Master YAML)

目标：当某个流程达到足够的成功次数/证据质量后，将其编译为“生产级 YAML 插件”（尽可能脱离 LLM/VLM 推理）。

关键点：
- 插件契约是约束边界：见 `docs/PLUGIN_CONTRACT.md`。
- 蒸馏门槛来自插件 `manifest.yaml` 的 `distill_threshold`（默认简单流程 3 次成功）。
- 蒸馏产物应该可审阅、可重放，且严格参数化输入（避免把一次性数据写死进脚本）。

---

## 3) 必须遵守的不变量 (Invariants)

这些约束是“可独立运行、可持续演进”的底线（也用于审查与 gate）：

- **入口统一**：`api/server.py` 是唯一 app entrypoint；`/web` 为默认控制台入口。
- **RPC 可禁用**：必须支持 `MYT_ENABLE_RPC=0` 启动与健康检查。
- **数据目录边界**：所有运行产物必须位于 `config/data/`（例如 `tasks.db`、`accounts.json.db`、`traces/`）。
- **禁止 legacy 依赖**：不得引入 `tasks` 或 `app.*` 的旧命名空间。
- **无 App 硬编码**：框架层（`engine/`, `core/`, `api/`）不得硬编码 app-specific 字符串；应用差异只能通过 `config/apps/*.yaml` 驱动。

---

## 4) “完成”是什么：证据优先

WebRPA 的“完成”不是“代码写了”，而是“证据存在”：
- gate（无 legacy import、pytest 通过）；
- 服务启动与 `/health` 为 200；
- 蒸馏/回填/执行等关键链路，至少具备可复盘的轨迹与指标（Prometheus/JSON 指标 + trace 文件）。

当前里程碑完成度请以 `docs/STATUS.md` 为准。

