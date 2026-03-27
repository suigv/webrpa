# Web Frontend Rewrite Development Rules

Status: active
Derived From: [Master Plan](/Users/chenhuien/webrpa/plans/2026-03-26-web-frontend-rewrite-plan.md)
Created: 2026-03-26

## Purpose

约束本次重构及后续新增功能，避免系统重新长回旧式堆叠结构。

## Core Principles

1. 先定产品对象，再定接口，再写页面。
2. 新前端只接 canonical contracts。
3. 兼容逻辑只留在边界，不进入页面层。
4. 正确的底层能力不推翻，只重做对象装配和产品入口。
5. 每完成一类新主路径，就尽快淘汰对应旧入口。

## Frontend Structure Rules

### Module Tree

前端按以下顶层组织：

- `app`
- `pages`
- `features`
- `entities`
- `shared`

### Layer Responsibilities

- `app`
  - 路由入口、providers、shell、guard
- `pages`
  - 页面级组装
- `features`
  - 页面内完整交互能力块
- `entities`
  - canonical objects、mappers、query keys、稳定 UI 片段
- `shared`
  - 通用 UI、API client、工具、稳定公共类型

### Hard Rules

- `pages` 不直接写原始 API 兼容逻辑
- `features` 不跨域依赖内部实现
- `entities` 不承载页面流程
- `shared` 不放业务专属逻辑

## Type And Mapping Rules

### Canonical Types

同一对象只允许一套主类型定义，例如：

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

### Mapping

- 页面只消费 canonical types
- 原始响应必须先过 mapper / adapter
- 历史 alias 不得进入新页面代码

## State Management Rules

- 服务端真状态：`TanStack Query`
- 前端会话状态：`Zustand`
- 页面局部临时状态：组件内部

禁止：

- 把远程数据和 UI 控件状态塞进同一全局 store
- 多个页面各自复制一套筛选与选择逻辑

## Backend Contract Rules

- route 不写业务规则
- 聚合对象逻辑必须落到 service / domain
- 新 contract 优先按产品对象设计
- 兼容 alias 只能保留在 boundary / ingestion 层

## Permission And Security Rules

- 页面守卫不是最终权限判断
- 所有敏感 API 必须服务端鉴权
- 多租户查询与写入都必须显式带 workspace 边界
- 所有敏感操作必须写审计日志
- 计费、奖励、积分调整全部以后端为准

## Billing Rules

- 扣费只由后端统一结算
- 奖励只由后端统一结算
- 每笔账务都保留规则快照
- 每笔账务都必须可回溯

## Marketplace Rules

- 插件上传必须进入 submission
- 审核通过后才可 published
- 下载 / 购买 / 奖励全部入账
- 风险插件必须支持下架与冻结

## Update Rules

- 更新必须生成 update job
- 必须保留状态、日志、失败记录
- 必须保留 rollback 路径

## Naming Rules

- 页面名按产品对象或主流程命名
- 类型名按 canonical object 命名
- mapper 名与对象名一一对应
- 技术来源名不得直接作为产品对象名

## Review Checklist

每个功能 PR 至少检查：

1. 是否落在正确产品域
2. 是否新增了 canonical type 或复用了已有 type
3. 是否通过 mapper 层接入
4. 是否绕过了权限 / workspace 边界
5. 是否引入了新的历史 alias 扩散
6. 是否需要审计 / 风控 / 安全规则补充

## Default Rule

如果某个新增功能无法快速判断该怎么落：

1. 先判断它属于 `operator / platform / marketplace` 哪一层
2. 再判断它对应哪个主对象
3. 再决定页面与 contract

若无法通过这三步明确归属，则默认不能直接编码。
