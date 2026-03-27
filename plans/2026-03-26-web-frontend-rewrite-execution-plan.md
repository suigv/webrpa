# Web Frontend Rewrite Execution Plan

Status: execution-ready
Derived From: [Master Plan](/Users/chenhuien/webrpa/plans/2026-03-26-web-frontend-rewrite-plan.md)
Created: 2026-03-26

## Goal

以前端产品对象为起点，重构出：

- 更低心智负担的 operator 工作面
- 更清晰的 platform / marketplace 能力层
- 更统一的 canonical contracts
- 更易维护的前后端模块边界

## Frozen Decisions

### Product Layers

- `operator product`
  - `设备作战台`
  - `AI工作台`
  - `资产中心`
  - `偏好配置`
- `platform product`
  - auth
  - workspace
  - billing
  - admin
  - updates
- `marketplace`
  - plugin browse
  - purchase
  - submission
  - review
  - reward

### Top Navigation

1. `设备作战台`
2. `AI工作台`
3. `资产中心`
4. `偏好配置`

### AI Workspace Split

- `任务设计`
- `会话与草稿`
- `学习沉淀`

### Default Product Decisions

- 默认首页是 `设备作战台`
- `AI 快速发起` 保留在单设备详情，但只做快速入口
- 批量下发首版不做完整方案中心，只支持最近一次配置复用
- `业务策略文本` 归属 `任务资产`
- 系统资产主入口归属 `资产中心`
- 历史统计 / 成功率 / 错误趋势后置到低频层

## Core Object Tree

### Operator

- `DeviceSummary`
- `DeviceDetail`
- `TakeoverSession`
- `BatchDispatchSession`
- `TaskDraftDesign`
- `WorkflowDraft`
- `RunAsset`
- `LearningCandidate`
- `TaskAssetItem`
- `SystemAssetItem`

### Platform

- `UserIdentity`
- `Workspace`
- `WorkspaceMember`
- `RoleProfile`
- `PermissionPolicy`
- `CreditAccount`
- `BillingRule`
- `CreditTransaction`
- `RechargeOrder`
- `UpdateChannel`
- `UpdateJob`
- `AdminAction`

### Marketplace

- `PluginPackage`
- `PluginRelease`
- `PluginOwnership`
- `PluginPurchase`
- `PluginRewardTransaction`
- `PluginSubmission`
- `PluginReviewTask`
- `PluginInstallSession`

## Framework Decisions

- 后端继续保留 `FastAPI`
- 前端在 `Vite` 内重写为 `React + TypeScript`
- 交互模型保留 `REST + SSE + WebSocket`
- 新前端只接 canonical contracts
- 兼容层只保留在 adapter / boundary

## Isolation Strategy

### Branch

- 使用长期重构分支
- 旧主线不承担本次系统级重构开发

### Code Path

- 旧前端进入维护态
- 新前端在新代码路径中重建，例如 `web/src/*`

### Contracts

- 旧接口仅作为兼容层
- 新前端只接 canonical contracts

### Constraints

- 继续遵守 `AGENTS.md` / `$webrpa-dev` 的仓库底线约束
- 额外叠加本次 v2 重构约束：
  - 新代码按产品域组织
  - 新页面禁止继续消费历史 alias
  - 新旧页面不长期共享同一路径实现

## Canonical Contract Groups

### Operator

- `GET /operator/devices`
- `GET /operator/devices/{deviceKey}`
- `GET /operator/takeover/{taskId}`
- `POST /operator/batch-dispatch`
- `POST /operator/ai/design/plan`
- `GET /operator/ai/drafts`
- `GET /operator/ai/drafts/{draftId}`
- `GET /operator/ai/drafts/{draftId}/run-assets`
- `GET /operator/assets/task`
- `GET /operator/assets/system`

### Platform

- `GET /platform/workspaces`
- `GET /platform/workspaces/{workspaceId}`
- `GET /platform/workspaces/{workspaceId}/members`
- `GET /platform/workspaces/{workspaceId}/billing`
- `GET /platform/workspaces/{workspaceId}/transactions`
- `GET /platform/admin/audit-logs`
- `GET /platform/admin/update-jobs`

### Marketplace

- `GET /marketplace/plugins`
- `GET /marketplace/plugins/{pluginId}`
- `POST /marketplace/plugins/{pluginId}/purchase`
- `GET /marketplace/my/plugins`
- `POST /marketplace/submissions`
- `GET /marketplace/submissions`
- `POST /marketplace/admin/reviews/{reviewId}/approve`
- `POST /marketplace/admin/reviews/{reviewId}/reject`

## Implementation Waves

### Wave 0

- 冻结计划文档
- 产出开发约束文档
- 建立执行任务看板

### Wave 1

- auth 基础
- workspace 基础
- roles / permissions 基础
- admin / platform shell

### Wave 2

- operator canonical contracts
- platform canonical contracts
- marketplace canonical contracts
- mapper / adapter 层

### Wave 3

- 新前端模块树
- router / auth provider / workspace context
- query client / state stores / shell

### Wave 4

- 设备作战台
- 单设备详情
- 接管
- 批量下发

### Wave 5

- AI 工作台 / 任务设计
- AI 工作台 / 会话与草稿
- AI 工作台 / 学习沉淀

### Wave 6

- 任务资产
- 系统资产
- 导入与清洗

### Wave 7

- 积分账户
- 扣费与奖励规则
- 审计与风控
- 管理后台

### Wave 8

- 插件商店浏览
- 我的插件
- 上传与审核
- 交易与奖励

### Wave 9

- 在线更新
- API token
- webhook

## Acceptance Milestones

### M1 Platform Foundation

- 用户可登录并进入 active workspace
- 基础权限边界可用
- admin shell 可访问

### M2 Operator Core

- 设备作战台替代旧主工作面
- 单设备详情替代旧设备深页
- 接管链路可用
- 批量下发主路径可用

### M3 AI Core

- AI工作台三层结构可用
- `planner -> submit -> draft -> run asset -> save/distill` 主链路可用

### M4 Assets

- 任务资产和系统资产明确分离
- 导入与清洗链路可用

### M5 Billing/Admin

- 积分、规则、流水、审计、风控可用
- 管理后台具备基础治理能力

### M6 Marketplace

- 插件浏览、上传、审核、下载、奖励主链路可用

### M7 Updates/Integrations

- update job 可追踪
- rollback 可用
- token / webhook 基础可用

## Immediate Start Order

1. `Wave 0`
2. `Wave 1`
3. `Wave 2`
4. `Wave 3`
5. `Wave 4`

## Final Note

本文件用于执行，不再承担完整讨论背景。若执行中需要追溯原因，以 [Master Plan](/Users/chenhuien/webrpa/plans/2026-03-26-web-frontend-rewrite-plan.md) 为准。
