# AI Agent 上传/会话读取指南 (Onboarding Guide)

为了让新会话的 AI 能够快速理解项目现状并保持架构一致性，建议在新会话开始时，引导其按以下优先级读取文档。

---

## 🟢 第一级：必读上下文 (Essential Context)
**用途**：理解“我们在做什么”以及“现在做到了哪里”。

- **[项目进度看板 (Project Progress)](project_progress.md)**  
  *实时更新的变更日志。* 重点看“最近变动”和“当前状态统计”，避免 AI 建议已废弃的模块。
- **[Skills化演进报告 (Skills Evolution)](SKILLS_EVOLUTION.md)**  
  *项目的核心战略。* 描述了从 AI 驱动转向 Skills 驱动的架构蓝图、当前阻力点及演进阶段。
- **[项目核心目标 (Project Goals)](PROJECT_GOALS.md)**  
  *决策锚点。* 定义了 North Star 指标和 Core Goals（如：AI 自主执行、技能蒸馏）。

---

## 🟡 第二级：技术规范 (Technical Specs)
**用途**：理解“怎么写代码”以及“接口契约是什么”。

- **[插件契约规范 (Plugin Contract)](PLUGIN_CONTRACT.md)**  
  *YAML 编写指南。* AI 生成 Skills (YAML) 时必须遵循的 Pydantic 字段规范。
- **[设备与多云架构 (Android RPA SDK)](ANDROID_RPA_SDK.md)**  
  *环境定义。* 描述了多云机隔离、端口计算公式 (`30001/30002`) 以及 RPA 通讯机制。
- **[系统状态矩阵 (Status Matrix)](STATUS.md)**  
  *里程碑核对。* 快速了解 M0-M4 各个阶段的 Verified（已验证）vs Planned（规划中）情况。

---
---

## 🛠️ AI 行为守则 (Agent Responsibilities)
- **文档自愈 (Self-Documenting)**：根据 `AGENTS.md` 规范，AI 在完成任何功能开发、Action 新增或重构后，**必须**同步更新相关文档（包括但不限于 `/docs` 目录、`ActionMetadata` 声明以及 `project_progress.md`）。
- **校验为先**：必须在提交前执行 `check_no_legacy_imports.py` 和 `pytest`。

## 🔵 第三级：架构深潜 (Deep Architecture)
**用途**：理解“代码库的解耦逻辑”以及“核心组件职责”。

- **[系统交接文档 (Handoff Guide)](HANDOFF.md)**  
  *“活地图”。* 深度解析 `Runner`, `Interpreter`, `TaskController` 之间的调用拓扑。
- **[脚本执行路线图 (Roadmap)](ROADMAP.md)**  
  *长期规划。* 明确后续重构和功能开发的具体路径。

---

## 💡 AI 引导建议 (Prompt Suggestion)
在新会话的第一条指令中，您可以直接发送：
> “请先按优先级读取 `docs/AI_ONBOARDING.md` 中定义的**必读上下文**，确保你了解最新的重构进度（如 ActionRegistry 增强）和 Skills 演进路线后，再开始处理 [您的具体需求]。”
