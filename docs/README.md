# WebRPA 文档中心

欢迎使用 WebRPA 开发文档。本文档库旨在提供项目现状、开发规范及架构设计的单一事实来源。

---

## 🚀 快速开始与现状
- **[项目进度看板 (Project Progress)](project_progress.md)**  
  当前可用能力、最近变更、各模块完成状态及下一步计划。

---

## 🛠 开发指南 (Core Contracts)
- **[插件开发与输入规范 (Plugin Contract)](PLUGIN_CONTRACT.md)**  
  YAML 插件模式 (v2) 的核心语法、输入参数声明及变量插值规则。
- **[AI 工作流设计清单 (AI Workflow Checklist)](ai_workflow_design_checklist.md)**  
  设计基于 LLM/VLM 的自主智能体流程时的关键考量点。

---

## 📡 API 参考
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
