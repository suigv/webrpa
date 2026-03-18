# WebRPA 文档中心

# WebRPA 是一个基于 **“行为编译器 (Behavior Compiler)”** 理念构建的下一代 RPA 自动化平台。它不依赖于僵化的硬编码规则，而是利用 AI (VLM/LLM) 的原生视觉直觉进行自主探索，并自动将探索出的行为路径转化为高性能、零 AI 依赖的工业级 YAML 插件。

### 核心演进逻辑：成熟度漏斗 (Maturity Funnel)
系统通过以下三个阶段实现任务的闭环演进：
1.  **AI 自主探索 (Bootstrapping)**：打破规则枷锁，实现 0-1 的视觉寻路。
2.  **数据驱动执行 (Native Mode)**：自动沉淀感知记忆，将经验转化为确定性数据，平滑提效。
3.  **终极插件蒸馏 (YAML Mastery)**：编译生成高可确定、脱离大模型依赖的生产级插件脚本。

欢迎使用 WebRPA 开发文档。本文档库旨在提供项目现状、开发规范及架构设计的单一事实来源。

---

## 🚀 Quick Start
- **[AI 会话必读指南 (AI Onboarding Guide)](AI_ONBOARDING.md)**: 开启新会话或新 AI 介入时，请优先引导其阅读此文档以同步项目上下文。

## 最新变更
- `agent_executor` 已进一步拆成 runtime/planning/trace/support/types 多文件结构；`sdk_actions` 也已拆为 façade + catalog，降低两个热点文件继续膨胀的风险。
- 设备/云机可用性现在支持提前熔断：活跃 target 连续 probe 失败达到 unavailable 阈值后，任务会直接以 `failed_circuit_breaker` / `target_unavailable` 终止，而不是等后续 RPC 超时。
- 相关背景与实现记录见 `docs/TECHNICAL_DEBT.md`、`docs/project_progress.md`；运行参数见 `docs/CONFIGURATION.md`。

## 文档索引 (Index)
- **[架构演进 2.0 (Architecture 2.0)](architecture_2_0.md)**：项目灵魂，描述了从寻找路径到自动固化再到生成 YAML 的进化漏斗。
- **[项目进度看板 (Project Progress)](project_progress.md)**：实时变动日志。
- **[北极星目标 (Project Goals)](PROJECT_GOALS.md)**：双阶段演进与 YAML 大师战略。
- **[AI Onboarding 必读](AI_ONBOARDING.md)**：新会话启动指南。
- **[AI 工作流设计清单 (AI Workflow Checklist)](ai_workflow_design_checklist.md)**  
  设计基于 LLM/VLM 的自主智能体流程时的关键考量点。

---

## 🛠 开发指南 (Core Contracts)
- **[插件开发与输入规范 (Plugin Contract)](PLUGIN_CONTRACT.md)**  
  当前运行时 YAML 插件契约（`manifest.api_version: v1` / `script.version: v1`）的核心语法、输入参数声明及变量插值规则。
- **[AI 工作流设计清单 (AI Workflow Checklist)](ai_workflow_design_checklist.md)**  
  设计基于 LLM/VLM 的自主智能体流程时的关键考量点。

---

## 📡 API 参考
- **[WebRPA HTTP API（本服务）](HTTP_API.md)**  
  FastAPI 暴露的控制面接口（任务/设备/账号池/蒸馏/Schema 等），以及 `/web` 与 `/ws/logs`。
- **[盒子内 SDK API（8000）](MYT_SDK_API.md)**  
  设备级 SDK 接口（云机容器、镜像、备份、VPC 等）。
- **[MYTOS Android API (api_port)](MYTOS_API.md)**  
  云机级 Android HTTP API（剪贴板、代理、文件、系统配置等）。
- **[Android RPA SDK (rpa_port)](ANDROID_RPA_SDK.md)**  
  RPA 控制 SDK（触控、UI 节点、截图、视频流等）。

---

## 🏗 架构与设计 (Architecture)
- **[技术债与治理报告 (Technical Debt)](TECHNICAL_DEBT.md)**  
  记录系统级的设计缺陷、冗余及后续重构计划。
- **[系统交接文档 (Handoff Guide)](HANDOFF.md)**  
  深度架构解析、依赖拓扑及核心组件（Runner, Interpreter, Controller）的运行机制。
- **[Skills化演进与架构评估 (Skills Evolution)](SKILLS_EVOLUTION.md)**  
  评估项目“技能化”进度，分析架构阻力并指明 AI 自动合成技能的演进方向。
- **[自主学习与感知记忆系统 (Architecture 2.0)](architecture_2_0.md)**  
  设计目标：解决冷启动悖论，通过感知记忆消除硬编码，实现 AI 自主进化。

---

## ⚙️ 运维与调优
- **[配置与环境变量参考 (Configuration)](CONFIGURATION.md)**  
  全量环境变量说明、默认值及典型启动场景。
- **[监控部署指南 (Monitoring Rollout)](monitoring_rollout.md)**  
  Prometheus 采集、告警配置及面板渲染说明。
- **[僵尸任务恢复调优 (Stale Running Tuning)](stale_running_recovery_tuning.md)**  
  关于 `MYT_TASK_STALE_RUNNING_SECONDS` 的校准与演练建议。

---

## 📚 规划与目标 (Goals & Roadmap)
- **[项目目标 (Project Goals)](PROJECT_GOALS.md)**：北极星目标、成功标准与蒸馏门槛定义。
- **[里程碑规划 (Roadmap)](ROADMAP.md)**：M0-M4 里程碑状态与下一步证据行动。
- **[当前状态矩阵 (Status)](STATUS.md)**：功能完成度的 done/not-done 视图。
