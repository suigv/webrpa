# Frontend-Led System Refactor Plan

Status: frozen-by-default
Created: 2026-03-26
Owner: Codex + user discussion
Scope: 以前端需求、页面树、产品交互和用户心智模型为牵引，对 `web/`、前后端 contract、能力暴露层、部分后端接口收口方式进行联合重构规划

## Derived Docs

为方便执行，本 master plan 已派生出两份压缩文档：

- [Execution Plan](/Users/chenhuien/webrpa/plans/2026-03-26-web-frontend-rewrite-execution-plan.md)
- [Development Rules](/Users/chenhuien/webrpa/plans/2026-03-26-web-frontend-rewrite-development-rules.md)

使用建议：

- 本文档保留完整背景、判断与长期依据
- `Execution Plan` 用于实际排期与开工
- `Development Rules` 用于编码期约束与 review

## Version Isolation Strategy

本次重构若要真正成为“独立版本”，不能只靠口头约定，必须同时做三层隔离：

### 1. Git Branch 隔离

默认建议：

- 必须开长期重构分支

建议分支命名：

- `rewrite/operator-platform-v1`
  或
- `feat/frontend-led-system-v2`

原因：

- 这次不是普通功能改动，而是系统级重构
- 若直接在主线零散提交，旧结构与新结构会相互污染

结论：

- 对这次重构来说，开分支不是可选项，而是默认必需项

### 2. Code Path 隔离

仅有 git 分支还不够，还必须做代码路径隔离。

默认建议：

- 旧前端进入维护态
- 新前端在新代码路径中重建

前端建议：

- 保留旧 `web/js/*` 仅用于过渡维护
- 新前端放到新的模块化目录，例如：
  - `web/src/*`

后端建议：

- 旧接口保留为兼容边界
- 新前端只接新的 canonical contracts / 聚合层

结论：

- 独立版本的关键不是“另起一个分支名”，而是“新代码不继续长在旧结构里”

### 3. Contract 隔离

这次要保证独立版本，最关键的是新前端不能继续直接消费旧式历史 contract。

默认要求：

- 旧 contract：
  - 仅作为兼容层存在
- 新 contract：
  - 只围绕 canonical objects 建立

也就是说：

- 旧前端可以继续吃旧接口
- 新前端只能吃 canonical contracts

这样才能保证：

- 新版本不再被旧字段别名和错误分层拖住

## Constraint Inheritance Decision

### 1. 是否继续受 `$webrpa-dev` / `AGENTS.md` 约束

结论：

- `继续受约束`
- 但本次重构应在其基础上增加一层“v2 重构约束”

原因：

- `webrpa-dev` / `AGENTS.md` 里有很多仍然必须保留的仓库级硬约束：
  - 不引入旧 repo 依赖
  - 保持数据路径边界
  - route 薄层
  - 任务系统和插件系统边界
  - RPC 开关兼容
- 这些不是旧架构负担，而是仓库基本纪律

但本次还需要新增的 v2 约束包括：

- 新前端只接 canonical contracts
- 新代码按产品域组织
- 兼容 alias 不得进入新页面
- 新旧页面不长期混用同一主路径

结论：

- 正确做法不是“摆脱 webrpa-dev 约束”
- 而是“保留仓库底线约束，再叠加本次重构约束”

## Independent Version Guarantee

要保证这次重构成为一个真正独立版本，建议采用以下硬策略：

### 1. 旧版进入 Maintenance Only

默认要求：

- 旧前端只修阻塞性 bug
- 不再继续承接新功能

### 2. 新功能优先只落新版

默认要求：

- 从某个冻结点开始，新增功能优先写入新版本结构
- 除非是维持线上稳定，不再给旧版加同等能力

### 3. 新版有明确切换门槛

建议设置切换条件：

- Platform Foundation 完成
- Operator Core 完成
- AI Core 完成
- 基础权限与计费边界可用

达到这几个门槛后，再考虑替换旧主入口。

### 4. 旧版与新版不共享页面实现

可以共享：

- 后端正确的底层能力
- task system
- plugin engine
- planner / workflow draft / run asset

不建议共享：

- 页面级逻辑
- 旧式前端状态组织
- 旧式字段兼容逻辑

### 5. 切换策略建议

建议采用：

- `build new -> validate -> cutover -> retire old`

而不是：

- `边修旧版边慢慢缝新版`

### 6. 对这次重构最准确的操作建议

如果要一句话定下来：

- 开长期分支
- 保留 `webrpa-dev` / `AGENTS.md` 底线约束
- 新增 v2 重构约束
- 新前端走新代码路径
- 新前端只接 canonical contracts
- 旧版进入维护态

这 6 条同时成立，才能保证这次重构是一个真正独立版本，而不是旧系统上的又一次大修补。

## Decision

本次计划不再被视为“单纯前端改版”，而是一个“以前端需求为前提，反推整个系统如何重构”的复杂计划。

当前主前提已经升级为：

- 前端不是简单消费后端，而是产品结构的第一牵引层。
- 若现有后端 contract、能力分层、接口命名、资产边界、运行态暴露方式不适配新的产品结构，则允许纳入本次重构范围。
- 但仍坚持“产品语义先收敛，再决定后端改造最小闭环”，避免先陷入接口级修补。

因此本文件后续既记录前端信息架构，也记录：

- 哪些后端能力已存在且可直接复用
- 哪些能力虽存在但 contract 需要收口
- 哪些官方能力缺少前端入口
- 哪些官方能力需要补后端对接层或统一封装
- 哪些历史结构属于错误遗留，应在系统层一起清理

本次前端重构以产品经理视角推进，允许完全重写当前前端，不以兼容旧前端页面结构为目标。

当前阶段先沉淀方案，不直接进入实现。待页面结构、导航逻辑、用户优先级和关键流程讨论完成后，再把本文件收敛为可执行任务计划。

协作规则：

- 每次讨论产生新的产品判断后，必须立即写回本文件。
- 不允许等到“最后一次讨论”再统一整理。
- 讨论完成后，再基于本文件生成明确的任务计划并执行。

能力暴露规则：

- 后端现有的业务能力原则上都应有前端入口。
- 区别不在于“是否暴露”，而在于“放在哪一层入口、以什么产品语义暴露”。
- 高频能力放在主工作面。
- 低频能力放在深层页面或高级入口。
- 诊断和开发者能力允许放在很深的页面，但仍应可从前端进入。

## Planning Scope Upgrade

本文件当前应被理解为三层联合计划，而不是单一 UI 方案：

### Layer 1: 产品层

- 页面树
- 导航结构
- 页面职责
- 用户优先级
- 关键任务流

### Layer 2: 能力暴露层

- 哪些已有能力进入哪个页面
- 哪些能力进入主入口
- 哪些能力进入深层页面
- 哪些能力只保留为诊断入口

### Layer 3: 系统收口层

- 前后端 contract 是否需要调整
- 后端能力是否存在重复封装
- 官方能力是否已被框架完整承接
- 资产模型、任务模型、设备模型、运行态模型是否需要重新分层

当前不应再把“前端计划”和“后端计划”割裂看待。更准确的说法是：

- 这是一个由前端需求触发的系统级重构规划。
- 执行顺序仍可从前端开始，但设计依据必须覆盖系统边界。

## Reusable Facts Inventory

本节用于集中沉淀已经确认、后续可反复复用的事实，避免讨论过程中重复核对。

### A. 产品方向已确认

- 可以完全重写当前前端，不保留旧页面结构。
- 本次目标不是“在旧页面上继续堆内容”，而是降低用户心智负担。
- 允许有深层页面，但每个页面必须干净、明确、单任务导向。
- 产品优先级必须从用户最关心的操作出发，而不是从技术模块出发。
- `AI工作台` 名称必须保留，但内容必须更产品化、更引导式。
- `执行队列` 不应作为一级分类；运行态应回收到设备和任务上下文。

### B. 顶层信息架构已确认

- 一级导航暂定为：
  - `设备作战台`
  - `AI工作台`
  - `资产中心`
  - `偏好配置`
- 默认首页是 `设备作战台`。
- `AI工作台` 面向首次使用者与任务设计者。
- `资产中心` 承接任务资产、系统资产和统一导入能力。
- `偏好配置` 只保留少量真正有意义的设置和深层诊断入口。

### C. 资产边界已确认

- `业务策略文本` 不属于系统设置，属于插件变量或任务资产。
- `宿主机 IP`、`8000 端口`、`12 云机密度` 等底层运行细节对普通用户几乎没有意义。
- `导入文件的格式化与清洗能力` 是所有导入的共用能力，不属于某一种资产。
- `系统资产` 偏向设备执行环境所需资产，例如 socks 代理、未来机型参数、设备相关导入资产。
- `任务资产` 偏向任务设计与执行所需资产，例如账号、2FA、App 导入资产、插件变量、策略文本。

### D. 30001 官方基线已确认

- 仅讨论 `30001` Android API 时，官方文档目录中的 `38` 条接口分类是唯一准口径。
- 当前仓库 `AndroidApiClient` 公开方法数为 `46`，这不是 `38` 被推翻，而是工程封装粒度不同。
- 当前最明确缺口是官方 `27. webrtc 播放器` 缺少清晰的客户端/产品入口。
- 当前最明确需要后续核对的契约点包括：
  - 截图路径写法
  - 开机启动 body 形态
  - 面具接口语义收口

### E. 现有工程状态已确认

- 当前工作区已有一批前端探索性改动，尚不应视为新方案定稿：
  - `docs/FRONTEND.md`
  - `web/index.html`
  - `web/js/features/devices.js`
  - `web/js/main.js`
  - `web/styles.css`
- 当前计划文件是新阶段的讨论主线，应持续写回，不再把聊天记录视为唯一上下文。

### F. 方法论已确认

- 先沉淀可复用事实，再沉淀结构判断，再沉淀任务计划。
- 每次讨论形成的新判断，都应立即写回本文件。
- 讨论阶段允许扩大系统边界，但执行阶段仍需拆成可落地的最小闭环任务。

### G. 30002 RPC 当前判断已确认

- 官方 `MYT_ANDROID_RPA` 文档显示，`30002` 的能力主体是 SDK / DLL 方法簇，而不是 `30001` 那种 HTTP 接口目录。
- 与 `30001` 相比，当前仓库对 `30002 RPC` 的底层能力承接更完整，整体对齐情况明显更好。
- 当前应分三层理解 RPC 对齐度：
  - `MytRpc` 适配层：对齐度高
  - `engine` 动作层：大体对齐
  - 前端 / 直接产品入口层：明显未完整暴露
- 当前最明确的结论不是“RPC 缺很多”，而是“RPC SDK 基本齐，但产品入口远少于底层能力”。

### H. 8000 SDK 当前判断已确认

- 官方 `heziSDKAPI` 文档对应的是 `8000` 端口的设备级 / 宿主级控制面，不是普通业务页面应该直接平铺展示的一组能力。
- 当前仓库对 `8000 SDK` 的 adapter 承接非常完整，量级明显大于 `30001` 和 `30002`。
- 已确认：
  - `MytSdkClient` 公开方法数：`104`
  - `sdk.*` 动作绑定数：`104`
- 这说明当前系统对 `8000` 的处理，已经接近“一套官方能力一套内部封装”的完整承接状态。
- 当前真正不足的，不是底层 adapter，而是：
  - 产品入口分层
  - 面向用户的语义整理
  - 哪些应该进入业务工作流，哪些应该下沉到系统资产 / 诊断 / 管理深页

### I. AI 当前逻辑基线已确认

- AI 部分当前没有一份外部官方文档可做“文档对齐”，因此本次只能以仓库实现作为事实来源。
- 当前 AI 相关逻辑并不是单一“生成任务”接口，而是一整条链路：
  - AI 规划
  - 任务图草案
  - 工作流草稿
  - 运行资产沉淀
  - 继续执行
  - 蒸馏
  - 人工接管注释保存
  - 分支学习
  - app config candidate 审核
- 用户此前的判断“引导模式和高级模式逻辑正确”与当前代码事实基本一致。
- 当前更需要重构的是：
  - 产品壳层
  - 页面职责
  - 任务设计到执行的衔接
  - AI 结果的沉淀入口
  而不是推翻现有 AI 核心执行逻辑。

## Product Premise

`webrpa` 不是一个“展示型后台”，而是一个围绕以下核心行为展开的操作型产品：

- 查看当前哪些设备可操作
- 对单台设备进行接管与观察
- 对多台设备进行批量任务下发
- 使用 AI 设计任务并理解任务执行逻辑
- 在需要时补齐任务资产或系统资产
- 低频查看历史、成功率、错误趋势和个性化配置

## User Priority Model

页面和导航不按技术模块排序，而按用户此刻最关心的目标排序。

### P1: 高频主任务

- 看设备是否可操作
- 进入单设备接管
- 多选设备并批量下发
- 设计新任务
- 查看当前任务是否在跑
- 处理异常 / 人工接管

### P2: 支撑主任务的信息

- 设备在线 / 占用 / 异常状态
- 任务当前阶段
- 账号、2FA、资源是否齐备
- 最近一次失败原因
- 当前任务的目标范围

### P3: 低频管理信息

- 任务资产维护
- 系统资产维护
- 历史数据
- 参数数据
- 成功率 / 错误趋势

### P4: 极低频配置

- 个性化偏好
- 网段扫描
- 极少数默认行为设置

## User Segments

### 1. 熟悉系统的高级用户

进入系统后最关心的是“现在哪些设备能操作”。

默认入口应该直接到设备相关工作面，而不是 AI、配置、指标或介绍页。

### 2. 第一次使用或不熟悉 AI 流程的用户

他们需要一个明确、干净、可理解的入口，帮助快速理解：

- AI 能做什么
- AI 设计任务的流程
- 什么时候需要账号 / 2FA / 人工接管
- 设计完成后如何进入下发执行

因此第二主入口必须保留 `AI工作台`，但其内容应更产品化、更引导式。

### 3. 低频维护用户

资产、历史、参数、成功率、错误趋势、配置等属于低频功能，应该集中在靠后的导航层级，不与 P1/P2 抢首屏注意力。

## Navigation Proposal

一级导航建议如下：

1. `设备作战台`
2. `AI工作台`
3. `资产中心`
4. `偏好配置`

说明：

- `设备作战台` 面向熟悉系统的用户，作为默认首页。
- `AI工作台` 面向第一次使用或当前要设计新任务的用户。
- `资产中心` 承接任务资产、系统资产及导入能力，不再把所有低频内容混成一个资源仓库。
- `偏好配置` 为极低频入口，只保留网段扫描和少量真正需要用户干预的偏好项。

## Page Tree

```text
/
├─ 设备作战台 /devices
│  ├─ 设备列表
│  │  ├─ 搜索 / 筛选 / 分组
│  │  ├─ 设备卡片
│  │  └─ 多选状态栏
│  ├─ 单设备详情 /devices/:deviceId-:cloudId
│  │  ├─ 当前状态
│  │  ├─ 当前任务
│  │  ├─ 实时画面
│  │  ├─ 轻控制
│  │  ├─ 进入接管
│  │  ├─ AI 快速发起
│  │  └─ 最近异常 / 最近日志
│  ├─ 接管页 /devices/:deviceId-:cloudId/control
│  └─ 批量下发页 /devices/dispatch
│     ├─ 已选设备确认
│     ├─ 任务来源
│     │  ├─ AI 草稿
│     │  └─ 插件模板
│     ├─ 执行参数
│     ├─ 下发确认
│     └─ 下发后运行态
│
├─ AI工作台 /ai-workbench
│  ├─ 快速开始
│  │  ├─ AI 能帮你做什么
│  │  ├─ 任务设计流程
│  │  ├─ 账号 / 2FA / 人工接管说明
│  │  └─ 开始设计
│  ├─ 引导模式
│  ├─ 高级模式
│  ├─ 草稿列表
│  └─ 草稿详情 /ai-workbench/drafts/:draftId
│     ├─ 任务图摘要
│     ├─ 声明脚本
│     ├─ 风险点 / 接管点
│     ├─ 任务资产变量
│     └─ 进入设备批量下发
│
├─ 资产中心 /assets
│  ├─ 任务资产
│  │  ├─ 账号资源
│  │  ├─ 2FA / 凭证
│  │  ├─ App 导入资产
│  │  ├─ 插件变量
│  │  └─ 业务策略文本
│  ├─ 系统资产
│  │  ├─ socks 代理
│  │  ├─ 自定义机型参数（未来）
│  │  └─ 设备相关导入资产
│  └─ 导入中心
│     ├─ 多种文件导入
│     ├─ 格式识别
│     ├─ 字段映射
│     └─ 数据格式化 / 清洗（全局导入能力）
│
└─ 偏好配置 /settings
   ├─ 网段扫描
   ├─ 少量个性化偏好
   ├─ 极少数默认行为设置
   └─ 开发者与诊断
      ├─ 运行健康检查
      ├─ 浏览器诊断
      ├─ 引擎动作 / Skills 元数据
      ├─ Runtime 调试执行
      └─ 原始诊断数据入口
```

## Page Intent

### 1. 设备作战台

这是默认首页，目标是帮助用户在最短时间内判断：

- 哪些设备可操作
- 是否要进入单设备接管
- 是否要勾选多台设备进行批量下发

它不应该承载：

- 大量 AI 解释
- 平台级成功率
- 冗长日志
- 配置项
- 多余的流程说明

### 2. 单设备详情

允许是深层页面，但必须足够干净明确，只围绕“这一台设备”展开。

页面职责：

- 看这一台设备当前是否正常
- 看它当前在跑什么
- 快速进行轻控制
- 进入接管
- 从该设备发起 AI 快速任务

不应该混入平台级内容。

### 3. 批量下发页

这不是一级导航，也不是独立的大分类，而是从设备作战台的多选行为自然进入的上下文页面。

进入条件：

- 用户在设备作战台勾选多台设备
- 触发“批量下发”

页面职责：

- 确认目标设备
- 选择任务来源
- 设置执行参数
- 最终确认下发
- 在下发后继续观察运行态，而不是再跳去单独的“执行队列”一级页面

### 4. AI工作台

`AI工作台` 名称必须保留，但页面必须更产品化。

它面向的是：

- 第一次使用用户
- 当前需要设计新任务的用户
- 希望理解 AI 驱动任务流程和逻辑的用户

页面职责：

- 保留当前已正确的引导模式与高级模式逻辑
- 让用户快速理解 AI 驱动任务设计的流程
- 用引导模式降低首次使用门槛
- 用高级模式服务熟练用户
- 让草稿成为自然中间产物，而不是孤立对象
- 把设计结果自然衔接到设备批量下发

补充判断：

- `AI工作台` 当前的核心执行逻辑不需要推翻。
- 当前正确的是 AI 逻辑和双模式；需要重构的是入口包装、信息层级和与设备下发的关系。
- `业务策略文本` 不属于系统设置，它属于插件变量或任务资产。

### 5. 资产中心

资产必须明确拆分为两类：

#### 任务资产

服务于任务设计与执行：

- 账号资源
- 2FA / 凭证
- App 导入相关资产
- 插件变量
- 业务策略文本

#### 系统资产

服务于设备和执行环境：

- 云机所需 socks 代理
- 用户自定义机型参数（未来）
- 其他与设备相关的导入资产

资产中心还必须承接导入能力：

- 支持多种导入文件
- 识别格式
- 字段映射
- 数据格式化和清洗

补充判断：

- “导入文件的格式化与清洗能力”不是某一种资产的专属能力。
- 它是所有导入流程共用的基础能力，适用于任务资产和系统资产两侧。
- 因此前端设计上应把它抽象成统一的导入处理流程，而不是在每个导入页面里各自重复发明一套导入逻辑。

### 6. 偏好配置

极低频页面，只承接少量真正有意义的用户设置。

应保留：

- 网段扫描
  - 用于多网卡、虚拟网卡场景下自动识别网段不准确的兜底
- 少量个性化偏好
- 极少数默认行为设置
- 开发者与诊断入口
  - 面向低频高级用户和排障场景
  - 承接原始健康信息、浏览器诊断、引擎 schema、skills 和 runtime 调试执行

应移除或不对用户暴露：

- 宿主机 IP
- 8000 端口
- 12 云机密度等底层运行参数
- 其他对客户几乎没有意义的内部实现细节

## Core Flows

### Flow A: 熟练用户进入系统后快速操作设备

1. 登录后默认进入 `设备作战台`
2. 判断哪些设备可操作
3. 如果单机操作，进入 `单设备详情`
4. 如需强介入，继续进入 `接管页`

### Flow B: 熟练用户进行批量任务下发

1. 在 `设备作战台` 勾选多台设备
2. 出现明显的批量操作状态栏
3. 进入 `批量下发页`
4. 选择任务来源并确认下发
5. 在同一工作上下文中查看下发后运行态

### Flow C: 第一次使用用户设计 AI 任务

1. 进入 `AI工作台`
2. 先看到快速开始与流程说明
3. 用引导模式完成任务设计
4. 得到草稿
5. 从草稿详情进入批量下发

### Flow D: 用户补齐缺失资产

1. 在任务设计或设备下发过程中发现缺少账号、2FA、策略文本或系统代理
2. 进入 `资产中心`
3. 进入对应的任务资产或系统资产页面
4. 通过导入中心完成文件导入、字段映射与格式化
5. 返回原流程继续设计或下发

## IA Principles

### Principle 1: 首页只做最高优先级动作

首屏不讲系统全貌，只讲当前最值得做的事。

### Principle 2: 每个页面只服务一个主任务

允许有深层页面，但页面进入后必须足够干净明确。

### Principle 3: 低频信息向后放

历史、指标、成功率、错误趋势、参数等，不进入高优先级页面的视觉中心。

### Principle 4: 上下文驱动跳转

批量下发不是独立顶级模块，而是用户多选设备后的自然下一步。

### Principle 5: 名称兼顾业务和产品认知

`AI工作台` 必须保留，但页面内容不应继续是“功能堆叠工作台”，而应体现引导和任务设计逻辑。

### Principle 6: 资产边界必须清晰

任务资产和系统资产不能混放，否则用户无法判断某项数据到底服务于任务本身，还是服务于设备运行环境。

### Principle 7: 不向用户暴露底层实现细节

不具有直接业务意义的宿主机参数、端口和内部密度配置，不应进入高层产品界面。

## Current Gaps Against This Direction

当前前端仍存在以下问题：

- 页面仍带有较强“按系统模块组织”的痕迹
- 一些页面内容过多、职责不单一
- 首页和工作面之间的层次还不够清晰
- 低频信息仍有机会抢占高频任务的注意力
- `AI工作台` 的引导式体验仍不够纯粹
- `业务策略文本` 仍被错误放在系统设置语义下
- 任务资产和系统资产尚未被清晰分层
- 下发后的运行态仍容易被理解成独立模块，而不是设备上下文的一部分
- 大量后端能力已经存在，但前端没有形成明确入口或没有被产品化命名

## Rewrite Direction

后续执行阶段以“完全重写 `web/` 前端”为前提，不做旧结构兼容式修补。

建议分三个阶段推进：

### Phase 1: 信息架构确定

- 最终敲定一级导航
- 最终敲定页面树
- 最终敲定每个页面的单一职责

### Phase 2: 线框与页面骨架

- 设备作战台线框
- AI工作台线框
- 单设备详情线框
- 批量下发页线框
- 资产中心与偏好配置线框

### Phase 3: 实施计划

- 拆出现有前端可复用的数据层与 API 调用层
- 丢弃旧页面骨架与导航结构
- 按新页面树重新实现路由、布局和交互

## Capability Exposure Plan

本节用于记录“后端已具备，但前端需要重新以合适入口暴露”的能力归属。

### A. 设备作战台

应暴露：

- 设备发现与刷新
- 设备启用 / 禁用
- 设备在线 / 占用 / 异常状态
- 单设备截图获取
- 单设备轻控制
  - 点击
  - 滑动
  - 返回 / Home / Enter / Recent / Delete
  - 文本输入
- 单设备当前任务查看
- 单设备任务停止
- 批量选择后的批量下发
- 下发后的运行态查看
- 单任务事件流查看
- WebSocket 日志订阅

入口建议：

- `设备作战台` 列表页：设备发现、筛选、批量选择
- `单设备详情`：状态、截图、轻控制、当前任务、设备级停止
- `接管页`：更强的人工干预、实时画面、日志、任务事件
- `批量下发页`：提交任务、观察下发后运行态

### B. AI工作台

应暴露：

- AI planner
- AI 历史
- prompt templates
- 引导模式
- 高级模式
- 草稿列表 / 草稿详情 / 草稿快照
- 草稿继续执行
- 草稿蒸馏
- 插件蒸馏
- 保存候选 / 保存选择
- 注释与标注
- app branch profiles
- app config candidates 审核

入口建议：

- `AI工作台` 首页：快速开始、prompt templates、能力说明
- `AI工作台` 引导 / 高级：planner 主入口
- `草稿详情`：snapshot、distill、continue、save choices
- `AI 沉淀区` 或草稿详情侧栏：branch profiles、config candidates review、annotations

补充判断：

- AI 相关沉淀能力不能再以零散按钮存在。
- 它们应被组织成“设计 -> 草稿 -> 沉淀 -> 下发”的连续工作流。

### C. 资产中心

应暴露：

#### 任务资产

- 账号列表
- 账号导入
- 账号字段更新
- 账号状态更新
- 账号按 app / branch / role tag 过滤
- 账号池出队 / 占用
- 账号重置
- location / website 等现有文本型数据资产
- 业务策略文本
- App 导入相关资产
- 插件变量

#### 系统资产

- socks 代理
- 自定义机型参数（未来）
- 设备相关导入资产
- 手机型号库存获取 / 刷新
- 手机型号选择器
- 指纹生成
- 联系人生成
- 环境包生成

#### 全局导入能力

- 多种文件导入
- 格式识别
- 字段映射
- 数据格式化
- 数据清洗

入口建议：

- `资产中心 / 任务资产`：账号、2FA、文本型任务资产、插件变量
- `资产中心 / 系统资产`：代理、机型、环境包、设备环境生成能力
- `资产中心 / 导入中心`：所有资产共用的导入流程

### D. 运行洞察

应暴露：

- 任务列表
- 活跃任务查询
- 任务详情
- 任务取消
- 任务暂停
- 任务恢复
- 任务 takeover
- cleanup failed
- cleanup runtime
- clear all tasks
- 任务 metrics
- 插件 success metrics
- Prometheus 原始文本

入口建议：

- 高频运行态：放在 `设备作战台 -> 批量下发页` 的下发后运行态
- 任务详情：从设备详情、批量下发、AI 草稿详情进入
- 低频统计：放在 `资产中心` 的二级洞察页
- 原始 Prometheus 和清理能力：放在 `偏好配置 -> 开发者与诊断`

补充判断：

- “执行队列”不作为一级导航，但任务运行能力必须完整保留。
- 区别只在于它们应以设备上下文和任务上下文暴露，而不是独立顶层模块。

### E. 偏好配置 / 开发者与诊断

应暴露：

- 配置读取 / 更新
- discovery subnet / discovery enable
- 浏览器诊断
- health
- engine schema
- engine skills
- runtime execute（debug-only）

入口建议：

- `偏好配置` 主层：只保留网段扫描和极少数真正有意义的偏好
- `偏好配置 / 开发者与诊断`：承接低频高级能力和调试入口

补充判断：

- `runtime execute` 不应放到普通用户工作流中，但仍应在深层前端入口中可用。
- `engine schema / skills` 更适合作为开发者能力浏览器，而不是普通业务页面内容。

## System Refactor Targets

本节不直接定义实现方式，只定义“本次系统级重构真正要收口的对象”。

### 1. Device Domain

需要重新收口的问题：

- 设备列表页使用的设备摘要字段是否足够支撑产品排序和筛选
- 单设备详情是否有统一的设备详情 contract
- 接管页是否有独立于普通详情页的实时控制 contract
- 设备状态、任务状态、异常状态是否被混在同一层字段里

目标：

- 建立 `设备摘要`、`设备详情`、`设备接管态` 三层模型
- 首页只取设备摘要
- 深页再进入更重的实时能力

### 2. Dispatch Domain

需要重新收口的问题：

- 批量下发当前更像技术动作，而不是清晰产品流程
- 任务来源、目标设备、执行参数、运行反馈之间缺少统一上下文
- 下发后运行态容易漂移成单独模块

目标：

- 建立 `批量下发会话` 的产品语义
- 把“选设备 -> 选任务来源 -> 配参数 -> 下发 -> 观察运行态”收口成同一流程

### 3. AI Draft Domain

需要重新收口的问题：

- AI 引导、高级、草稿、沉淀能力目前更像散点接口集合
- 草稿到下发之间的上下文连续性还不够明确
- AI 设计产物与插件变量、任务资产、目标设备之间边界还不够清晰

目标：

- 建立 `AI 设计会话`、`AI 草稿`、`AI 沉淀结果` 三层产物模型
- 所有 AI 能力围绕“设计 -> 校验 -> 沉淀 -> 下发”组织

### 4. Asset Domain

需要重新收口的问题：

- 任务资产与系统资产边界过去被混淆
- 各类导入能力容易散落在不同页面重复实现
- 插件变量、策略文本、App 导入资产之间的关系未被产品化定义

目标：

- 建立 `任务资产`、`系统资产`、`导入流水线` 三层结构
- 所有导入都走统一的格式识别、字段映射、数据清洗流程

### 5. Runtime Insight Domain

需要重新收口的问题：

- 活跃任务、任务详情、任务事件流、设备运行态、平台指标当前缺少层次
- 高频运行信息和低频统计信息混杂

目标：

- 高频运行态回收到 `设备作战台` 和 `批量下发页`
- 低频统计和清理能力下沉到二级洞察页或诊断页

### 6. Settings / Diagnostics Domain

需要重新收口的问题：

- 用户偏好、网络扫描、原始诊断、开发者调试过去容易混放
- 用户无意义的底层参数暴露过多

目标：

- `偏好配置` 只承接少量真实用户设置
- `开发者与诊断` 独立成深层区，不污染主工作流

## Canonical Contract Principles

如果后续进入后端改造阶段，contract 收口建议遵循以下原则：

### Principle 1: 页面按产品对象取数，不按技术模块取数

前端请求应围绕：

- 设备摘要
- 单设备详情
- 接管态
- 批量下发会话
- AI 草稿详情
- 任务资产项
- 系统资产项

而不是直接暴露一组“模块接口集合”让页面自行拼装。

### Principle 2: 一个页面只依赖一个主 contract，再辅以少量侧向能力

例如：

- `设备作战台` 应有自己的主列表 contract
- `单设备详情` 应有自己的主详情 contract
- `批量下发页` 应有自己的主会话 contract

否则页面复杂度会继续泄漏到前端实现层。

### Principle 3: 兼容别名不应继续扩张到产品层

例如：

- `38` 条官方命令可以在内部保留包装 helper
- 但前端不应直接面对一组历史别名、兼容参数和多套命名方式

### Principle 4: 高频 contract 优先稳定，低频诊断 contract 可后置

优先级应为：

1. 设备作战台
2. 单设备详情 / 接管页
3. 批量下发会话
4. AI 工作流
5. 资产中心
6. 诊断 / 开发者入口

### Principle 5: 官方能力基线与产品能力基线要先统一，再谈工程 helper

以 `30001` 为例：

- 官方 `38` 条是系统能力基线
- 页面中实际展示的产品动作不需要等于 `38`
- 内部 helper 数也不需要等于 `38`
- 但三者之间必须有清晰映射表

## Data To Keep Recording

后续每轮讨论，优先继续把以下信息写回本文件，避免再次散落在聊天记录中：

### 1. 业务优先级判断

- 哪些功能是首页级
- 哪些功能是深页级
- 哪些功能是低频诊断级

### 2. 页面职责边界

- 每个页面的主任务是什么
- 明确哪些内容“不应该放进去”

### 3. 关键对象模型

- 设备摘要字段
- 设备详情字段
- 批量下发会话字段
- AI 草稿字段
- 资产项字段

### 4. Contract 核对点

- 文档与实现不一致之处
- 同一能力的多套命名
- 需要保留的兼容层
- 应移除的历史遗留字段

### 5. 后端改造触发点

- 哪些地方是前端无法优雅承接、必须后端先收口
- 哪些地方可以先由前端适配，后续再逐步收口

## Discussion Backlog

为了让后续讨论更高效，当前建议按以下顺序继续补充：

1. 明确 `设备作战台` 的信息密度、卡片字段、排序方式、筛选结构
2. 明确 `单设备详情` 与 `接管页` 的边界
3. 明确 `批量下发页` 的完整流程和是否允许保存方案
4. 明确 `AI工作台` 首页、引导模式、高级模式、草稿详情的职责边界
5. 明确 `资产中心` 的表结构、导入流水线和系统资产范围
6. 明确 `30001` 的 `38` 条命令分别进入哪些页面、哪些只放深层入口
7. 最后再反推出需要新增、裁剪或收口的后端 contract

## Backend Capability Audit Summary

当前框架中，已具备但前端尚未完整产品化暴露的核心能力包括：

1. 系统资产生成能力
   - 手机型号库存
   - 机型选择
   - 指纹生成
   - 联系人生成
   - 环境包生成

2. AI 沉淀与审核能力
   - annotations
   - save candidates / save choices
   - branch profiles
   - config candidates 审核

3. AI 模板能力
   - prompt templates

4. 运行控制能力
   - pause
   - runtime cleanup
   - takeover
   - device-level task stop

5. 调试与开发者能力
   - health
   - browser diagnostics
   - engine schema / skills
   - runtime execute

## Android API Count Clarification

官方 Android API 文档口径与仓库实现口径当前不是同一层，所以不能混用。

官方文档来源：

- `MYTOS API 接口文档`
- 文档版本 `v3`
- 更新日期 `2026-03-20`
- 文档在“接口目录”中列出 `38` 项接口分类

当前仓库实现口径：

- `AndroidApiClient` 公开方法数：`46`
- `android.*` 直接注册原子动作数：`39`
- `mytos.*` 兼容绑定数：`53`

造成差异的原因：

1. 官方文档按“接口分类”计数，而不是按代码中的方法数计数。
2. 仓库实现把一些文档中的单一接口分类拆成了多个原子能力。
   - 例如后台保活被拆成设置、查询、增、删、更新等多个动作。
   - 谷歌 ID 也被拆成读取、设置、生成等不同能力。
3. 仓库中还存在兼容别名。
   - 例如 `set_fingerprint` / `update_fingerprint`
   - 例如 `screenshot` / `snap_screenshot`
4. 有些能力已在 `mytos.*` 兼容层中暴露，但没有全部进入 `android.*` 直接注册层。
5. 文档中存在 `webrtc 播放器` 这一项，但当前仓库中的 `AndroidApiClient` 未看到对应同名客户端方法。

产品讨论结论：

- 后续讨论 30001 能力时，默认以“官方文档 38 项接口分类”为产品层口径。
- 落到工程实现时，再映射到客户端方法和动作别名。
- 前端能力规划时，不应直接以别名数或兼容绑定数作为产品菜单项数量。

## Official 30001 API Baseline

本节只记录官方 Android API 文档中的 `30001` 口径能力，不混入 `8000` SDK 能力。

文档来源：

- [MYTOS API 接口文档](https://dev.moyunteng.com/docs/NewMYTOS/MYT_ANDROID_API)

记录原则：

- 以文档中的 38 项接口分类为准
- 每项先记录“怎么调用”
- 再记录当前仓库实现映射
- 若当前实现与文档不完全一致，标记为“后端核对 / 可能需修改”

### Request Shape Notes

这 `38` 条命令虽然在文档里按“接口分类”计数，但请求形态并不统一。后续若前端和后端都要围绕 `30001` 重新收口，建议优先按以下调用形态建模：

- 纯查询型 `GET`
  - 例如：`/clipboard`、`/proxy`、`/queryversion`、`/info`、`/callog`、`/appbootstart?cmd=1`
- `GET + cmd` 分支型
  - 例如：`/adb?cmd=1/2/3`、`/background?cmd=1/2/3/4`、`/adid?cmd=1/2`、`/modifydev?cmd=4/7/10/11/13/17/18`
- 二进制下载型
  - 例如：`/download?path=...`、`/snapshot?type=...&quality=...`、`/?task=snap&level=...`
- `POST JSON` 型
  - 例如：`POST /proxy?cmd=4` 的域名数组、`POST /sms?cmd=4`、`POST /appbootstart?cmd=2`
- `POST multipart` 型
  - 例如：`/uploadkeybox`、`/upload`、`/installapks`
- `GET` 触发远端拉取型
  - 例如：`/?task=upload&file=<url>`
- 静态页面播放器型
  - 例如：`webplayer/play.html?...`，这是官方 `27. webrtc 播放器`，它不是标准 JSON API

因此本次计划里，“38 条命令”应作为产品和后端改造的一级能力基线；真正落地时，需要再按请求形态拆成前端 API service、后端代理层和 UI 入口。

### 1-10

| # | 命令 | 方法与路径 | 核心参数 | 当前实现映射 |
|---|---|---|---|---|
| 1 | 下载文件 | `GET /download` | `path` | 已有 `download_file` |
| 2 | 获取剪贴板内容 | `GET /clipboard` | 无 | 已有 `get_clipboard` |
| 3 | 设置剪贴板内容 | `GET /clipboard?cmd=2` | `text` | 已有 `set_clipboard` |
| 4 | 查询 S5 代理状态 | `GET /proxy` | 无 | 已有 `query_s5_proxy` |
| 5 | 设置 S5 代理 | `GET /proxy?cmd=2` | `ip` `port` `usr` `pwd` `type` | 已有 `set_s5_proxy` |
| 6 | 停止 S5 代理 | `GET /proxy?cmd=3` | 无 | 已有 `stop_s5_proxy` |
| 7 | 设置 S5 域名过滤 | `POST /proxy?cmd=4` | body 为域名数组 | 已有 `set_s5_filter` |
| 8 | 接收短信 | `POST /sms?cmd=4` | `address` `mbody/body` `scaddress` | 已有 `receive_sms` |
| 9 | 上传 Google 证书 | `POST /uploadkeybox` | `file` | 已有 `upload_google_cert` |
| 10 | ADB 切换权限 | `GET /adb` | `cmd=1/2/3` | 已有 `query_adb_permission` / `switch_adb_permission` |

### 11-20

| # | 命令 | 方法与路径 | 核心参数 | 当前实现映射 |
|---|---|---|---|---|
| 11 | 导出 app 信息 | `GET /backrestore` | `cmd=backup` `pkg` `saveto` | 已有 `backup_app`，参数名存在 `save_to/saveto` 差异，需核对 |
| 12 | 导入 app 信息 | `GET /backrestore` | `cmd=recovery` `backuppath` | 已有 `restore_app`，参数别名已兼容 |
| 13 | 虚拟摄像头热启动 | `GET /camera?cmd=start/stop` | `cmd` `path` | 已有 `camera_hot_start` |
| 14 | 后台保活 | `GET /background` | `cmd=1/2/3/4` `package` | 已有查询/设定/增删改五种拆分实现 |
| 15 | 屏蔽按键 | `GET /disablekey` | `value=1/0` | 已有 `set_key_block` |
| 16 | 批量安装 apks/xapk 分包 | `POST /installapks` | ZIP 文件 `file` | 已有 `install_apks` / `batch_install_apps` |
| 17 | 版本查询 | `GET /queryversion` | 无 | 已有 `get_version` |
| 18 | 截图功能 | `GET /snapshot` | `type` `quality` | 已有 `screenshot` |
| 19 | 自动点击 | `GET /autoclick` | `action` `id` `x` `y` `code` | 已有 `autoclick` / `autoclick_action` |
| 20 | 文件上传 | `POST /upload` 或 `GET /?task=upload&file=` | 文件或 URL | 已有 `upload_file`，支持两种模式 |

### 21-30

| # | 命令 | 方法与路径 | 核心参数 | 当前实现映射 |
|---|---|---|---|---|
| 21 | 容器信息 | `GET /info` | 无 | 已有 `get_container_info` |
| 22 | 通话记录 | `GET /callog` | `number` `type` `date` `duration` 等 | 已有 `get_call_records` |
| 23 | 刷新定位 | `GET /task` | 无 | 已有 `refresh_location` |
| 24 | 谷歌 id | `GET /adid` | `cmd` `adid` | 已拆为 `get_google_id` / `set_google_id` / `generate_google_id` |
| 25 | 安装面具 | `GET /modulemgr` | `cmd` `module` | 已有 `module_manager` / `install_magisk`，存在包装重叠 |
| 26 | 添加联系人 | `GET /addcontact` | `data=[{user,tel}]` | 已有 `add_contact`，当前客户端也支持便捷单条输入 |
| 27 | webrtc 播放器 | 本地 `webplayer/play.html?...` | `shost` `sport` `rtc_i` `rtc_p` 等 | 当前仓库未见对应前端产品化入口，需补 |
| 28 | 获取后台允许 root 授权的 app 列表 | `GET /modifydev?cmd=10&action=list` | `cmd=10` `action=list` | 已有 `get_root_allowed_apps` |
| 29 | 指定包名是否允许 root | `GET /modifydev?cmd=10&pkg=...&root=true` | `pkg` `root` | 已有 `set_root_allowed_app` |
| 30 | 设置虚拟摄像头源和类型 | `GET /modifydev?cmd=4` | `type` `path` `resolution` | 已有 `set_virtual_camera` |

### 31-38

| # | 命令 | 方法与路径 | 核心参数 | 当前实现映射 |
|---|---|---|---|---|
| 31 | 获取 APP 开机启动列表 | `GET /appbootstart?cmd=1` | `cmd=1` | 已有 `get_boot_apps` |
| 32 | 设置指定 APP 开机启动 | `POST /appbootstart?cmd=2` | JSON 数组 body | 已有 `set_boot_app`，需核对当前是否完整支持文档 body 形式 |
| 33 | IP定位 | `GET /modifydev?cmd=11` | `launage` `ip` | 已有 `ip_geolocation`，参数名保留文档拼写兼容 |
| 34 | 设置语言和国家 | `GET /modifydev?cmd=13` | `language` `country` | 已有 `set_language_country` |
| 35 | 获取设备截图 | 文档写法 `GET /task=snap&level=` | `level=1/2/3` | 当前实现为 `GET /?task=snap&level=`，需后端核对文档与实现差异 |
| 36 | 更新指纹信息 | `GET /modifydev?cmd=7` | `data` 为 URL 编码 JSON 字符串 | 已有 `set_device_fingerprint` |
| 37 | 设置摇一摇状态 | `GET /modifydev?cmd=17` | `shake=1/0` | 已有 `set_shake` |
| 38 | 设置应用权限 | `GET /modifydev?cmd=18` | `pkg` | 已有 `grant_app_permissions` |

### Current Engineering Judgment

1. 官方文档的 `38` 条命令是当前产品和计划讨论的唯一准口径。
2. 仓库现有 `46` 个客户端方法不等于 `46` 条独立文档命令。
3. 这 `46` 个方法里存在“单条文档命令拆成多个工程能力”的情况，主要包括：
   - 谷歌 id：拆成读取 / 设置 / 生成
   - 后台保活：拆成设置 / 查询 / 增 / 删 / 更新
   - 自动点击：拆成基础接口和动作封装
   - 面具：拆成通用模块管理和快捷安装
4. 这些不是简单重复，但存在工程层的包装重叠与别名扩张。
5. 当前最需要后端核对或可能修改的地方包括：
   - `35. 获取设备截图` 的文档路径与仓库调用路径不一致
   - `32. 设置指定 APP 开机启动` 的文档 body 方式与当前客户端接口形态需核对
   - `27. webrtc 播放器` 在当前仓库中缺少清晰的产品入口与实现对接层
   - `25. 安装面具` 当前在工程中通过通用模块管理包装，语义还不够清晰

### 46 Methods Duplicate / Wrapper Breakdown

如果只以官方 `38` 条命令为“原子能力”口径，那么当前 `AndroidApiClient` 的 `46` 个公开方法里，确实存在包装重叠，但不应简单理解为“多出 8 个完全重复接口”。

精确拆解如下：

- 官方原子能力：`38`
- 当前缺少明确客户端方法的官方项：`1`
  - `27. webrtc 播放器`
- 因单条官方命令被拆成多方法而多出来的工程包装：`9`

对应关系：

- `10. ADB 切换权限`
  - 文档 1 条
  - 客户端拆成 `query_adb_permission`、`switch_adb_permission`
  - 额外包装 `+1`
- `14. 后台保活`
  - 文档 1 条
  - 客户端拆成 `set_background_keepalive`、`query_background_keepalive`、`add_background_keepalive`、`remove_background_keepalive`、`update_background_keepalive`
  - 额外包装 `+4`
- `19. 自动点击`
  - 文档 1 条
  - 客户端拆成 `autoclick`、`autoclick_action`
  - 额外包装 `+1`
- `24. 谷歌 id`
  - 文档 1 条
  - 客户端拆成 `get_google_id`、`set_google_id`、`generate_google_id`
  - 额外包装 `+2`
- `25. 安装面具`
  - 文档 1 条
  - 客户端拆成 `module_manager`、`install_magisk`
  - 额外包装 `+1`

计算结果：

- `38 - 1 + 9 = 46`

当前判断：

- `46` 不是 `38` 的冲突证据，而是“官方能力分类”和“工程封装粒度”不一致。
- 真正需要清理的不是把 `46` 强行压回 `38`，而是把重复包装分成三类：
  - 保留的工程便捷封装
  - 应收口成统一 helper 的兼容包装
  - 需要真正补齐的缺口能力（当前最明确的是 `webrtc 播放器`）
- 后续若涉及后端修改，应先统一一份 `30001` canonical contract，再决定哪些方法保留为内部 helper，哪些暴露给前端。

## Official 30002 RPC Alignment

本节用于记录官方 `MYT_ANDROID_RPA` 文档与当前仓库实现之间的对齐判断。

文档来源：

- [MYT Android RPA / RPC 文档](https://dev.moyunteng.com/docs/NewMYTOS/MYT_ANDROID_RPA)

当前判断：

- `30002 RPC` 的情况确实比 `30001` 更好。
- 好的地方主要在于：当前仓库已经完整承接了官方 SDK 的主要方法簇。
- 不足主要不在 SDK 适配层，而在动作层收口和前端产品化入口。

### Layer 1: SDK Adapter Alignment

`hardware_adapters/mytRpc.py` 当前已覆盖官方文档中的主要方法簇，整体对齐度高。

已明确承接的能力族包括：

- 基础连接与设备会话
  - `init`
  - `close`
  - `check_connect_state`
  - `get_sdk_version`
  - `exec_cmd`
- UI 树与 XML
  - `dump_node_xml`
  - `dump_node_xml_ex`
- 画面与截图
  - `take_capture`
  - `take_capture_ex`
  - `take_capture_compress`
  - `take_capture_compress_ex`
  - `screentshot`
  - `screentshotEx`
  - `get_display_rotate`
- 文本、按键、触控、滑动
  - `send_text`
  - `key_press`
  - `press_back/home/enter/recent/delete`
  - `touch_down/up/move/click`
  - `long_click`
  - `swipe`
- App 控制
  - `open_app`
  - `stop_app`
- RPA 模式与视频流
  - `set_rpa_work_mode`
  - `use_new_node_mode`
  - `start_video_stream`
  - `stop_video_stream`
- Selector / Node 能力
  - `create_selector`
  - `execQueryOne`
  - `execQueryAll`
  - `clear_selector`
  - `free_selector`
  - `find_nodes`
  - 各类 `addQuery_*`
  - `get_nodes_size`
  - `get_node_by_index`
  - `free_nodes`
  - `get_node_parent`
  - `get_node_child_count`
  - `get_node_child`
  - `get_node_json/text/desc/package/class/id`
  - `get_node_bound`
  - `get_node_bound_center`
  - `click_node`
  - `long_click_node`

补充判断：

- 当前 `MytRpc` 还保留了较多 camelCase / snake_case 双命名和 SDK 原始拼写兼容。
- 这说明它在“兼容官方 SDK 历史形态”方面做得比较充分。
- 因此 `30002` 当前最不需要推翻的，恰恰是底层 adapter。

### Layer 2: Engine Action Alignment

当前 `engine` 已把大量 RPC 能力提升成动作层，整体对齐情况也较好。

已明确暴露的动作族包括：

- `ui.*`
  - `ui.click`
  - `ui.touch_down`
  - `ui.touch_up`
  - `ui.touch_move`
  - `ui.swipe`
  - `ui.long_click`
  - `ui.input_text`
  - `ui.key_press`
  - `ui.create_selector`
  - `ui.selector_add_query`
  - `ui.selector_click_one`
  - `ui.selector_exec_one`
  - `ui.selector_exec_all`
  - `ui.selector_find_nodes`
  - `ui.selector_clear/free`
  - `ui.node_*`
  - `ui.dump_node_xml`
  - `ui.dump_node_xml_ex`
  - `ui.screenshot`
  - `ui.capture_compressed`
  - `ui.match_state`
  - `ui.wait_until`
  - `ui.observe_transition`
- `app.*`
  - `app.open`
  - `app.stop`
  - `app.ensure_running`
  - `app.dismiss_popups`
  - `app.grant_permissions`
- `device.*`
  - `device.screenshot`
  - `device.capture_raw`
  - `device.capture_compressed`
  - `device.get_display_rotate`
  - `device.get_sdk_version`
  - `device.check_connect_state`
  - `device.set_work_mode`
  - `device.use_new_node_mode`
  - `device.video_stream_start`
  - `device.video_stream_stop`
  - `device.exec`

结论：

- 对运行引擎来说，RPC 并不是“只有几个点击动作”。
- 它已经是一套相对完整的 UI 观察 + 控制 + 选择器 + 节点操作能力层。

### Layer 3: Product / Direct API Exposure

这层目前明显弱于前两层。

当前直接面向前端或外部调用的 RPC 暴露，已确认主要包括：

- `/health` 返回 `rpc_enabled`
- 设备直控接口：
  - `GET /api/devices/{device_id}/{cloud_id}/screenshot`
  - `POST /api/devices/{device_id}/{cloud_id}/tap`
  - `POST /api/devices/{device_id}/{cloud_id}/swipe`
  - `POST /api/devices/{device_id}/{cloud_id}/key`
  - `POST /api/devices/{device_id}/{cloud_id}/text`
- 前端当前只在健康状态和系统状态弹窗里显示 `RPC 已启用 / 已禁用`

当前没有形成清晰产品入口的 RPC 能力包括：

- 视频流
- selector 调试与节点浏览
- XML dump / node dump
- App open / stop
- raw / compressed capture 的多种形态
- RPA work mode / new node mode
- SDK version / connection state / exec command

结论：

- 不是 RPC 功能没对齐，而是“前端与 direct API 只用了 RPC 的一小部分”。
- 这与当前产品结构过旧有关，而不是底层能力缺失。

### Known Gaps / Contract Notes

虽然整体对齐较好，但仍有几类值得在后续重构中收口：

1. 命名兼容层较厚
   - 例如 camelCase / snake_case 双命名
   - 例如 SDK 原始拼写 `screentshot`、`takeCaptrueCompress`
   - 这些适合留在 adapter 内部，不应继续泄漏到前端或高层 contract

2. 少数动作层没有完整暴露 SDK 的变体能力
   - 例如 `take_capture_compress_ex` / `screentshotEx` 目前未见清晰高层动作入口
   - 说明“SDK 有能力”不等于“系统层已有清晰产品语义”

3. 兼容别名仍然偏工程视角
   - 例如 `ui.dump_node_xml` 与 `ui.dump_node_xml_ex` 当前都走同一高层 handler
   - 这对兼容有利，但对 contract 清晰度一般

4. 产品层完全没有把 selector / node / video stream 产品化
   - 这些能力在本次重构里应被重新安置到：
     - `接管页`
     - `开发者与诊断`
     - 或 `单设备详情` 的高级入口

### Product Planning Impact

基于当前 RPC 对齐情况，后续系统级重构可直接采用以下判断：

1. `30002 RPC` 不需要像 `30001` 那样先大规模补底层能力。
2. `30002 RPC` 更适合直接进入“contract 收口 + 产品入口重构”阶段。
3. 在页面树里，RPC 能力应至少落入以下位置：
   - `设备作战台`
     - 轻控制
     - 单机截图
   - `单设备详情`
     - 状态
     - 画面
     - 控制
     - 当前任务上下文
   - `接管页`
     - 视频流
     - selector / node / XML 的高级能力
     - 更强人工干预
   - `偏好配置 -> 开发者与诊断`
     - SDK version
     - connection state
     - exec command
     - 原始 selector / node 调试能力

最终判断：

- 如果只问“当前系统是否对齐官方 RPC 功能”，答案是：底层和动作层大体对齐，而且明显优于 `30001`。
- 如果问“这些 RPC 能力是否已经被当前产品结构正确使用”，答案是否定的，当前产品入口只覆盖了很小一部分。

## Official 8000 SDK Alignment

本节用于记录官方 `heziSDKAPI` 文档与当前仓库实现之间的对齐判断。

文档来源：

- [heziSDKAPI / 8000 端口 SDK 文档](https://dev.moyunteng.com/docs/NewMYTOS/heziSDKAPI)

当前判断：

- `8000` 是整个系统里最“基础设施控制面”取向的一层。
- 与 `30001`、`30002` 相比，`8000` 的能力范围更大，也更偏设备、云机、镜像、备份、网络、宿主、LM 服务、SSH/VPC 等系统级管理。
- 当前仓库对这层的 adapter 和 action 承接都非常完整。
- 当前真正不完整的，是产品化分层，而不是能力接入。

### Layer 1: SDK Adapter Alignment

`hardware_adapters/myt_client.py` 当前包含 `104` 个 `MytSdkClient` 公开方法，整体已经是一套高覆盖 SDK adapter。

按能力族归纳，当前已明确覆盖：

- 设备 / 宿主基础信息
  - `get_device_info`
  - `get_api_version`
- 云机生命周期
  - `list_androids`
  - `create_android`
  - `reset_android`
  - `delete_android`
  - `start_android`
  - `stop_android`
  - `restart_android`
  - `rename_android`
  - `exec_android`
  - `get_cloud_status`
  - `copy_android`
  - `get_task_status`
- 镜像与导入导出
  - `pull_image`
  - `list_images`
  - `delete_image`
  - `list_image_tars`
  - `delete_image_tar`
  - `export_image`
  - `download_image_tar`
  - `import_image`
  - `export_android`
  - `import_android`
  - `switch_image`
  - `change_image_batch`
  - `switch_image_v2`
  - `change_image_batch_v2`
- 云机 V2 / 机型相关
  - `create_android_v2`
  - `reset_android_v2`
  - `copy_android_v2`
  - `switch_model`
  - `list_phone_models_online`
  - `list_local_phone_models`
  - `import_phone_model`
  - `export_local_phone_model`
  - `delete_local_phone_model`
  - `list_country_codes`
- 网络 / macvlan / bridge / VPC
  - `set_android_macvlan`
  - `list_macvlan`
  - `create_macvlan`
  - `update_macvlan`
  - `delete_macvlan`
  - `list_myt_bridge`
  - `create_myt_bridge`
  - `update_myt_bridge`
  - `delete_myt_bridge`
  - `list_vpc_groups`
  - `create_vpc_group`
  - `update_vpc_group_alias`
  - `delete_vpc_group`
  - `add_vpc_rule`
  - `add_vpc_rule_batch`
  - `list_vpc_container_rules`
  - `delete_vpc_node`
  - `delete_vpc_rule`
  - `delete_vpc_rule_batch`
  - `update_vpc_group`
  - `add_vpc_socks`
  - `set_vpc_whitelist_dns`
  - `get_container_domain_filter`
  - `set_container_domain_filter`
  - `clear_container_domain_filter`
  - `get_global_domain_filter`
  - `set_global_domain_filter`
  - `clear_global_domain_filter`
  - `test_vpc_latency`
- 备份 / 模型 / 清理
  - `list_backups`
  - `delete_backup`
  - `download_backup`
  - `backup_model`
  - `list_model_backups`
  - `delete_model_backup`
  - `export_model`
  - `import_model`
  - `prune_images`
- 安全 / SSH / 容器终端
  - `set_auth_password`
  - `close_auth`
  - `change_ssh_password`
  - `switch_ssh_root`
  - `enable_ssh`
  - `open_ssh_terminal`
  - `get_ssh_ws_url`
  - `get_ssh_page_url`
  - `open_container_exec`
  - `get_container_exec_page_url`
  - `get_container_exec_ws_url`
- 宿主升级 / Docker / 网络
  - `upgrade_server`
  - `upload_server_upgrade`
  - `reset_server_device`
  - `reboot_server_device`
  - `switch_docker_api`
  - `get_server_network`
- LM / 推理服务
  - `import_lm_package`
  - `get_lm_info`
  - `delete_lm_local`
  - `get_lm_models`
  - `chat_completions`
  - `embeddings`
  - `reset_lm_device`
  - `start_lm_server`
  - `stop_lm_server`
  - `set_lm_work_mode`

结论：

- `8000` 当前不是“缺接入”，而是“已高覆盖接入”。
- 这一层后续不应轻易推翻 adapter。
- 若发生调整，应以 contract 收口和产品分层为主，而不是重写 `MytSdkClient`。

### Layer 2: Engine Action Alignment

`engine/actions/sdk_action_catalog.py` 当前已定义：

- `ACTION_BUILDERS` 总数：`157`
- 其中 `sdk.*`：`104`
- 其中 `mytos.*`：`53`

这意味着：

- `8000` 的 `104` 个公开 SDK 方法，当前几乎被完整映射进 `sdk.*` 动作层。
- 从系统执行视角看，`8000` 并不是“少数辅助接口”，而是完整的基础设施控制能力层。

补充判断：

- `30001` 与 `30002` 更多偏云机内 Android 与 UI/RPA 能力。
- `8000` 更像设备、云机、镜像、网络、宿主、LM 的上层管控面。
- 这决定了它在产品中不应与 `设备轻控制`、`AI 草稿` 处于同一视觉层级。

### Layer 3: Product / Direct API Exposure

当前直接面向前端或显式产品入口的 `8000` 能力，其实只覆盖了很小一部分。

已确认存在明确 API / 产品入口的主要包括：

- 局域网发现与设备识别
  - discovery 过程中通过 `8000` 探测 `get_api_version` / `get_device_info`
- 机型库存与机型选择
  - `/api/inventory/phone-models/*`
  - `/api/selectors/phone-model`
- 指纹 / 联系人 / 环境包生成
  - `/api/generators/fingerprint`
  - `/api/generators/contact`
  - `/api/generators/env-bundle`

这说明当前产品层只使用了 `8000` 的一部分“设备环境准备”能力，而没有把其他系统控制能力组织成清晰入口。

当前明显没有形成前端产品入口的能力包括：

- 云机生命周期管理
- 镜像管理与导入导出
- 备份管理
- VPC / bridge / macvlan / domain filter
- SSH / 容器终端
- 宿主升级 / 网络 / Docker API
- LM 本地模型与服务控制

### Product Planning Impact

基于当前 `8000` 的特性，后续产品重构不应把它简单理解成“又一组功能按钮”，而应做分层安置：

1. 高频普通业务用户
   - 基本不应直接面对大部分 `8000` 能力
   - 只需要少量“被产品化后的结果”
   - 例如：
     - 机型库存
     - 机型选择
     - 指纹 / 联系人 / 环境包生成

2. 资产中心 / 系统资产
   - 适合承接：
     - 机型相关能力
     - 设备环境包
     - 代理 / 网络相关资产
     - 部分导入导出能力

3. 偏好配置 / 开发者与诊断 / 管理深页
   - 适合承接：
     - 云机生命周期管理
     - 镜像管理
     - 备份管理
     - VPC / bridge / macvlan
     - SSH / 容器终端
     - 宿主升级与网络
     - LM 服务控制

4. 页面树层面的结论
   - `8000` 几乎不应该直接进入 `设备作战台` 首屏。
   - 它更多应该通过：
     - `资产中心`
     - `系统资产`
     - `开发者与诊断`
     - 极少数 `单设备详情` 高级入口
     来暴露。

### System Refactor Judgment

如果只问“当前系统是否对齐官方 8000 SDK 功能”，当前判断是：

- adapter 层：高对齐
- action 层：高对齐
- 产品层：远未完成产品化分层

因此 `8000` 的改造策略应与 `30001`、`30002` 不同：

- `30001` 更需要先做 canonical contract 收口
- `30002` 更需要做产品入口重构
- `8000` 更需要做“能力分区与页面归属重构”

最终判断：

- `8000` 当前不是“功能没接进来”，而是“系统接得很深，但用户界面还没有把它放到合适的位置”
- 这层是本次“前端牵引的系统级重构”里最典型的分层设计问题

## AI Logic Baseline

本节不做“文档对齐”，只记录当前仓库里已经存在且可验证的 AI 业务逻辑。

事实来源主要包括：

- `api/routes/ai_dialog.py`
- `core/ai_dialog_service.py`
- `core/ai_dialog_save_service.py`
- `core/task_control.py`
- `core/workflow_drafts.py`
- `core/task_finalizer.py`
- `core/task_semantics.py`
- `web/js/features/credential_payload.js`
- `web/js/features/ai_workspace.js`
- `web/js/features/device_ai_dialog.js`
- `web/js/features/task_service.js`

### 1. AI Planner 不是直接下发，而是先生成任务图草案

当前 `POST /api/ai_dialog/planner` 的输入包括：

- `goal`
- `app_id`
- `app_display_name`
- `package_name`
- `account_required`
- `selected_account`
- `use_account_twofa`
- `advanced_prompt`

它返回的不是“最终任务提交结果”，而是一份结构化规划结果，核心字段包括：

- `display_name`
- `operator_summary`
- `resolved_app`
- `resolved_payload`
- `guidance`
- `follow_up`
- `account`
- `intent`
- `control_flow`
- `branch`
- `execution`
- `memory`
- `challenge_policy`
- `recommended_workflows`
- `declarative_scripts`
- `draft`

结论：

- 当前 AI planner 的定位不是聊天助手，而是“任务图生成器 + 执行前判断器”。
- 这一点在新产品设计里必须保留。

### 2. Planner 当前已经做了较完整的执行前判断

当前 planner 在 `core/ai_dialog_service.py` 中已经负责：

- app identity 解析
- app payload 预解析
- account readiness 判断
- 2FA 自动能力判断
- intent 推断
- control flow prompt 分析
- branch 快照加载
- 推荐 workflow / plugin
- 最近运行资产摘要
- reuse / distill 优先级判断
- declarative script 草案生成
- LLM 二次润色 operator summary / missing / suggestions

这说明当前 AI 不是“只靠 LLM 胡乱生成描述”，而是：

- 先用系统内规则、配置和运行资产完成结构化判断
- 再用 LLM 对结果做补充和整理

结论：

- 当前 planner 逻辑属于系统级能力，不应在前端重构时被误当作一个简单表单提交接口。

### 3. AI 工作台当前存在明确的双模式

前端 `web/js/features/ai_workspace.js` 已实现两种模式：

- `guided`
- `advanced`

`guided` 模式当前是 4 步：

1. `目标与资源`
2. `任务描述与约束`
3. `确认任务图`
4. `执行与回流`

当前行为逻辑：

- 第 1 步先绑定目标云机、应用、账号
- 第 2 步补充成功判定、失败出口、人工接管和补充说明
- 第 3 步调用 planner 生成任务图草案并确认
- 第 4 步才允许下发执行

`advanced` 模式则允许直接围绕完整输入生成与重生成 planner 结果。

结论：

- 当前“引导 + 高级”模式不是空壳，而是已有明确状态机。
- 后续重构更适合保留逻辑、重做产品壳层与视觉层级。

### 4. AI 的真实中间产物是 Workflow Draft

当前 AI 设计流程的核心中间产物不是 prompt，而是 `workflow draft`。

草稿当前承担的职责包括：

- 保存最近成功 / 可继续执行 snapshot
- 记录成功次数 / 失败次数 / 取消次数
- 记录 latest completed / terminal task
- 记录 last failure advice
- 记录 distill assessment
- 记录 latest run asset
- 记录 saved preferences
- 承担继续执行的 continuation snapshot 来源

相关 API 当前包括：

- `GET /api/tasks/drafts`
- `GET /api/tasks/drafts/{draft_id}`
- `GET /api/tasks/drafts/{draft_id}/snapshot`
- `POST /api/tasks/drafts/{draft_id}/continue`
- `POST /api/tasks/drafts/{draft_id}/distill`

结论：

- 新产品里“草稿”不是可有可无的列表页，而是 AI 设计和执行闭环的核心对象。
- 但草稿应被组织成“设计产物”，而不是孤立数据表。

### 5. 草稿不是静态文档，而是随任务终态自动演化

当前任务在 completed / failed / cancelled 后，会由 `TaskAttemptFinalizer` 调用 `WorkflowDraftService.record_terminal()` 自动更新草稿。

record_terminal 当前会：

- 评估 run asset
- 写入 run asset 存储
- 生成 task snapshot
- 更新 last replayable snapshot / last success snapshot
- 更新 success_count / failure_count / cancelled_count
- 生成 last failure advice
- 更新草稿状态
- 触发 `workflow_draft.updated` 事件

结论：

- 草稿不是只由 AI 工作台手工编辑产生。
- 草稿的真实价值来自“执行后的自动回流和持续累积”。

### 6. 当前系统已经存在“运行资产复用”逻辑

`WorkflowDraftService.summarize_recent_run_assets()` 与 `build_memory_reuse_plan()` 当前已支持：

- 最近运行资产汇总
- distill_eligible 判断
- reuse_priority 判断
- recommended_action 判断
- latest qualification 判断
- hints / observed_state_ids / entry_actions 汇总

当前 reuse / qualification 相关值包括：

- `qualification`
  - `distillable`
  - `replayable`
  - `useful_trace`
  - `context_only`
  - `discard`
- `reuse_priority`
  - `distill_sample`
  - `continue_trace`
  - `context_only`
  - `none`
- `recommended_action`
  - `distill_or_validate`
  - `continue_from_memory`
  - `reuse_context`
  - `fresh_exploration`

结论：

- 当前系统已经有“AI 结果不是一次性结果，而是可沉淀资产”的判断体系。
- 这部分在产品上应被解释清楚，而不是埋在草稿详情内部字段里。

### 7. 当前 AI 已经支持“保存学习结果”

AI 相关的“保存”能力当前分两类：

#### A. 人工接管注释

通过：

- `POST /api/ai_dialog/annotations`
- `GET /api/ai_dialog/tasks/{task_id}/annotations`

用户可以保存人工输入记录，例如：

- `search_keyword`
- `target_blogger_id`
- `dm_reply_text`
- `profile_field_text`

#### B. Save Candidates / Save Choices

通过：

- `GET /api/ai_dialog/drafts/{draft_id}/save_candidates`
- `POST /api/ai_dialog/drafts/{draft_id}/save_choices`

当前系统会把可保存项整理为候选，包括：

- 账号默认业务分支
- 草稿默认业务分支
- 草稿 payload 默认值
- branch search keywords
- branch reply texts
- branch resource namespace

结论：

- 当前 AI 已经具备“从执行中学习，并把学习结果保存回系统”的能力。
- 这说明新产品中必须有“回流保存”入口，而不应只强调生成与下发。

### 8. Branch Profiles 当前是 AI 逻辑的重要组成部分

当前 app branch profiles 通过：

- `GET /api/ai_dialog/apps/{app_id}/branch_profiles`
- `PUT /api/ai_dialog/apps/{app_id}/branch_profiles`

可管理的内容包括：

- `branch_id`
- `label`
- `search_keywords`
- `blacklist_keywords`
- `reply_texts`
- `resource_namespace`
- `reply_ai_type`
- `payload_defaults`
- `notes`

结论：

- branch profile 不是附属配置，而是 AI 任务设计、执行策略和学习沉淀的重要上下文。
- 它未来应放在 AI 设计沉淀区或资产中心的明确位置，而不是隐藏在零散入口中。

### 9. App Config Candidates 当前是 AI 沉淀链路的一部分

当前支持：

- `GET /api/ai_dialog/apps/{app_id}/config_candidates`
- `POST /api/ai_dialog/apps/{app_id}/config_candidates/review`

这表示系统已经允许：

- 从 AI 执行和草稿中抽取 app config 候选
- 对候选做 promote / reject 审核

结论：

- “AI -> app config 沉淀”当前已经不是概念，而是已存在的审核链路。
- 后续重构时，这部分不能丢；它应该被更清晰地归类为 AI 沉淀能力或配置收敛能力。

### 10. Distill 当前是 AI 草稿生命周期里的正式阶段

当前 distill 不是单纯导出，而是基于：

- success_count
- success_threshold
- latest value profile
- distill policy / run asset 判断

来决定是否允许进入蒸馏。

草稿 exit action 当前至少包括：

- `apply_suggestion`
- `continue_validation`
- `distill`
- `review_distilled`
- `retry`

结论：

- “蒸馏”当前已经是系统正式能力，不是额外按钮。
- 但它在产品层应被解释为“从 AI 试运行收敛为稳定工作流”的阶段，而不是一个技术动作。

### 11. AI 还有一个单设备快速发起入口

除了完整的 `AI工作台`，当前还存在单设备 AI 弹窗：

- `web/js/features/device_ai_dialog.js`

它当前负责：

- 在单云机上下文内快速生成 planner
- 直接提交一次单设备 AI 任务
- 观察执行态
- 转回完整 AI 工作台继续深度设计

结论：

- 单设备 AI 入口应保留，但它本质上是“快速发起入口”，不是完整设计中心。
- 这和你此前的产品判断一致。

### 12. 当前 AI 真实业务闭环

综合代码事实，当前 AI 的真实闭环可以表述为：

1. 用户输入目标、应用、账号和约束
2. planner 生成结构化任务图草案
3. 用户确认草案
4. 下发 `agent_executor` 执行
5. 任务完成后自动回流到 workflow draft
6. 系统提炼 run asset、failure advice、reuse / distill 判断
7. 用户可继续执行、蒸馏、保存学习结果
8. 学习结果可回写到：
   - workflow draft defaults
   - account default branch
   - app branch profiles
   - app config candidates review

最终判断：

- 当前 AI 系统已经具备“设计 -> 执行 -> 回流 -> 学习 -> 沉淀”的完整逻辑闭环。
- 因此本次重构不应把 AI 理解成单一页面，也不应把它重新简化成聊天框。
- 真正要做的是把这条闭环按用户心智重新排布为更干净的页面和入口。

### 13. Planner 结果与 Persisted Draft 不是同一个时点的对象

当前需要明确区分两个概念：

- `planner result`
  - 由 `POST /api/ai_dialog/planner` 返回
  - 是一次“执行前结构化规划结果”
  - 其中 `draft.display_name_candidate` 只是草稿候选信息
- `workflow draft`
  - 由 `WorkflowDraftService.prepare_submission()` 在真正提交任务时创建或复用
  - 创建时机会发生在 `TaskController.submit_with_retry()` 内
  - 提交后才会把 `_workflow_draft_id`、`_workflow_display_name`、`_workflow_success_threshold` 等字段回写进真实任务 payload

这意味着：

- planner 阶段更像“设计草案生成”
- submit 阶段才是“把设计草案绑定为可持续积累的执行对象”

结论：

- 新产品里不应把 planner 卡片误写成“已生成正式草稿”。
- 更准确的产品语义应是：
  - 先生成任务图草案
  - 确认并下发后，进入正式 AI 会话 / 草稿生命周期

### 14. 当前前端的 AI 提交链路已经有明确 contract

前端当前不是把 planner 结果原样提交，而是走一条明确的合成链路：

1. `web/js/features/credential_payload.js` 先根据输入构造 `rawPayload`
2. 其中会写入：
   - `goal`
   - `app_id`
   - `package` / `package_name`
   - `credentials_ref`
   - `use_account_twofa`
   - `advanced_prompt`
   - `_workflow_source = ai_dialog`
3. `device_ai_dialog.js` / `ai_workspace.js` 再把 `plan.resolved_payload` 与 `rawPayload` 合并
4. 然后经 `prepareTaskPayload('agent_executor')` 做一次任务 catalog 约束下的净化
5. 最终通过标准任务提交接口，以 `task = agent_executor` + `targets` 的形式下发

这里有两个重要事实：

- planner 的结构化判断会进入最终执行 payload，而不是只用于 UI 展示
- AI 并没有专门的“执行接口”，真正执行仍统一收口到通用任务系统

结论：

- 后续重构时，AI 设计页和任务系统不能割裂。
- `AI工作台` 生成的不是“前端自有对象”，而是标准任务系统可执行的 `agent_executor` 请求。

### 15. 当前已经存在两种不同的“继续”语义

代码里当前至少存在两条不同链路，产品上必须分开表达：

#### A. 继续编辑草稿

入口包括：

- `AI工作台` 历史会话中的 `继续编辑`

当前行为是：

- 读取 `GET /api/tasks/drafts/{draft_id}/snapshot`
- 把 snapshot 中的 payload / identity 重新回填到工作台输入区
- 再重新调用 planner 生成新的任务图草案

它本质上是：

- 回到设计态
- 修改输入
- 重新规划

#### B. 继续执行草稿

入口包括：

- `POST /api/tasks/drafts/{draft_id}/continue`

当前行为是：

- 直接读取 workflow draft 的 continuation snapshot
- 自动套用保存过的 branch / payload 默认值
- 重新创建一个或多个新的执行任务

它本质上是：

- 不改设计
- 直接复用已有执行上下文继续跑

结论：

- 新产品里“继续编辑”和“继续执行 / 继续验证”不能共用一个模糊按钮。
- 这两者分别属于：
  - 设计层动作
  - 运行层动作

### 16. AI 工作台当前已经把“设计、参考、运行中任务”放进同一工作面

当前 `web/js/features/ai_workspace.js` 中，`AI工作台` 不是一个只负责提交表单的页面，而是已经同时承载：

- 设计输入
- planner 结果卡片
- 历史 AI 会话
- 历史草稿详情
- distill 入口
- save reusable items 入口
- 当前运行中的 AI 任务列表
- 跳转单设备详情的桥接入口

历史区当前至少支持：

- `作为当前设计参考`
- `继续编辑草稿`
- `蒸馏`
- `保存可复用项`

运行区当前会展示：

- 正在运行的 `agent_executor` 任务

结论：

- 当前 AI 工作台已经天然是一个“设计 + 参考 + 回流”的复合页。
- 真正的问题不是功能缺失，而是：
  - 页面职责还不够清楚
  - 设计态与运行态的视觉分层还不够干净
  - 参考信息暴露方式仍偏工程感

### 17. 引导模式当前已经有“延迟暴露复杂信息”的产品雏形

从 `guidedStep` 的前端逻辑可以确认，当前工作台已经在主动控制信息出现时机：

- 第 3 步之前，历史会话 / 失败建议 / 蒸馏线索不会作为主信息暴露
- 第 4 步之前，运行中任务区域不会成为主焦点
- 在引导模式下，只有到达对应步骤后，确认、下发、详情入口才会出现

这说明当前系统已经有一个很重要的正确方向：

- 复杂能力不是没有，而是应延迟暴露
- 并非所有 AI 相关信息都要在第一页同时出现

结论：

- 后续重构时，不应回退成“大一统信息堆叠页”。
- 更合理的做法是继续强化：
  - 设计主线
  - 执行主线
  - 回流沉淀主线
  之间的显式切换关系

### 18. 当前 AI 产品壳层的主要问题，不在底层逻辑，而在对象命名与页面责任

综合现有实现，当前 AI 逻辑并不薄弱，主要问题是产品壳层没有把对象边界讲清楚。

当前最容易让用户混淆的对象包括：

- 任务图草案
- workflow draft
- 历史 AI 会话
- 运行资产
- 可保存项
- branch learning
- distill 后草稿 / YAML

这些对象当前都存在，但在产品上没有形成清晰分层。

更准确的产品判断应是：

- `AI工作台` 首屏主对象应是“正在设计的任务图”
- `历史 AI 会话` 是参考与继续入口，不应喧宾夺主
- `workflow draft` 是设计与执行之间的持续对象，应在确认下发后才进入主叙事
- `运行资产 / 可保存项 / branch learning / config candidates` 属于“回流沉淀层”
- `蒸馏结果` 属于“从 AI 试运行收敛为稳定工作流”的产物层

结论：

- 本次 AI 重构重点不应是重写 planner 逻辑。
- 重点应是把当前已经存在的复杂能力，重排成用户可理解的产品对象树与页面责任。

## Information Still Needed Before Execution

当前技术基线已经相对清楚。要把本文件从“方向性计划”收敛成“可执行任务计划”，接下来最缺的不是更多底层接口信息，而是更明确的产品规则。

下面这些信息若不先定，后续无论页面树、contract 还是前后端改造都会反复返工。

### 1. AI工作台的最终页面组织方式

当前需要明确，`AI工作台` 最终是：

- 一个复合大页，通过模式和区域切换承载全部能力
- 还是拆成三个明确层级：
  - `任务设计`
  - `AI会话 / 草稿`
  - `学习沉淀`

当前建议：

- 更偏向拆层，而不是继续保留单页大拼盘。
- 理由不是“功能太多”，而是对象语义已经不同：
  - 设计是前置思考
  - 草稿 / 会话是执行中的持续对象
  - 学习沉淀是回流后的治理对象

### 2. 页面之间的跳转规则

当前需要你继续确认的不是页面名字，而是页面之间何时跳转、何时不跳转。

尤其包括：

- 用户从 `设备作战台` 进入 `单设备详情` 的触发规则
- 多选设备后是侧边浮层、底部操作条，还是直接进入 `批量下发页`
- 在设备页点击 `AI快速发起` 后，是只做一次快速提交，还是允许直接转完整设计页
- 任务运行中是否允许随时从 `AI工作台` 跳回设备接管
- 批量任务提交后，运行态主要回到设备侧，还是停留在批量会话页

当前建议：

- 设备相关跳转尽量保持“就近完成”，避免无意义跨页。
- 设计相关跳转可以显式进入 `AI工作台`，因为那是另一类心智任务。

### 3. 批量下发的业务规则

当前页面结构已经倾向于把批量下发放回 `设备作战台` 主路径，但还缺少业务规则定义。

至少还需要明确：

- 批量下发是否支持保存为方案
- 是否支持“最近一次批量配置复用”
- 下发前是否必须做资源校验
- 校验失败时是整批阻断，还是允许部分设备继续
- 失败设备是否自动形成“待处理子集”
- 批量执行后的主回流对象是：
  - 一次批量会话
  - 还是分散回各设备和各草稿

当前建议：

- 首版先支持“最近一次复用”，不急着上完整方案管理。
- 批量失败应允许部分继续，否则会显著放大用户阻塞感。

### 4. 单设备详情页的能力边界

当前需要尽快明确单设备详情到底承载哪些能力，避免它未来再次变成技术大杂烩。

建议拆成三类：

- 必须出现：
  - 当前可操作状态
  - 当前任务 / 最近任务
  - 接管
  - 快速 AI
  - 当前异常与人工介入入口
- 可放二级区：
  - RPC 调试
  - 节点 / XML 浏览
  - 截图 / 录屏 / 控制诊断
- 不应默认暴露：
  - 8000 宿主机级能力
  - 大量系统配置
  - 与当前设备操作无关的历史统计

### 5. 资产中心的最终对象分类

我们已经确认了 `任务资产` 与 `系统资产` 的边界，但还没有定最终页面层级。

至少还要确定：

- `学习沉淀` 是独立分类，还是挂在 `AI工作台`
- `业务策略文本` 是不是只在任务资产上下文出现
- App 导入、账号、2FA、插件变量、任务模板是否同属任务资产
- socks 代理、机型参数、网段扫描结果、设备相关导入是否同属系统资产

当前建议：

- `任务资产`
  - 面向“任务设计与执行前准备”
- `系统资产`
  - 面向“设备运行环境与底层依赖”
- `学习沉淀`
  - 更适合和 `AI工作台` 强关联，而不是并入通用资产列表

### 6. 学习沉淀的治理规则

当前系统已经具备保存可复用项、branch learning、config candidates、distill 等能力，但还缺产品治理定义。

还需要明确：

- 哪些保存动作可以直接生效
- 哪些必须人工审核
- branch learning 是否允许一键写入
- app config candidates 是否必须 review 后才生效
- distill 产物生成后是：
  - 仅草稿态
  - 可测试态
  - 还是允许直接发布到正式插件目录

当前建议：

- 与执行策略直接相关的沉淀优先保守：
  - app config candidates 继续审核制
  - branch learning 可分字段决定是否直写
- 与单次草稿偏好相关的沉淀可以更快生效：
  - workflow draft defaults
  - account default branch

### 7. 运行态信息的分层规则

现在已经知道“成功率、错误趋势、历史数据”不是高优先级，但还没完全定它们各自在哪一层出现。

还需要确定：

- 首页是否展示运行中任务
- 首页是否展示异常摘要
- 错误信息是只展示“需要介入的异常”，还是所有技术错误都展示
- 成功率 / 趋势 / 历史 是放到：
  - 资产中心二级页
  - 独立运行洞察页
  - 还是设备 / AI 各自详情里弱化展示

当前建议：

- 首页只显示影响当前操作的运行态：
  - 是否可操作
  - 是否运行中
  - 是否需要介入
- 聚合指标和趋势继续后置，不抢主视图注意力。

### 8. 重构执行顺序

即使产品规则收敛，也还要确定实现顺序，否则容易在大范围改造中失速。

当前更合理的顺序建议是：

1. 先定对象模型和页面树
2. 再做 `设备作战台` 与 `单设备详情`
3. 再做 `AI工作台` 的重组
4. 再做 `资产中心`
5. 最后做 `偏好配置`、诊断入口和低频洞察

理由：

- 设备与任务下发是最高频业务面
- `AI工作台` 虽复杂，但已经有较完整逻辑基线，适合在主对象树确定后再重排
- 低频页放最后，能减少前期范围失控

### 9. 当前最适合继续补充的信息类型

后续讨论若要高效推进，最值得补充的不是更多 API 文档，而是以下三类判断：

- 你认定的页面主对象
- 你认定的页面跳转规则
- 你认定的哪些动作允许立即生效，哪些必须经过审核

如果这三类信息继续补齐，本文件就可以从“讨论记录”收敛成真正的任务分解文档。

## Recommended Product Defaults v1

本节给出一版“如果现在就开始收敛，我建议直接采用的默认产品判断”。

它不是最终拍板，但可以作为后续讨论和任务拆解的临时基线。

### A. AI工作台默认采用“三层结构”，不再维持单页复合大盘

默认建议拆成：

1. `AI工作台 / 任务设计`
2. `AI工作台 / 会话与草稿`
3. `AI工作台 / 学习沉淀`

各层职责建议如下：

- `任务设计`
  - 面向第一次使用者和当前要设计新任务的用户
  - 主对象是“当前任务图草案”
  - 主动作是：
    - 选择目标与资源
    - 生成任务图
    - 确认并下发
- `会话与草稿`
  - 面向已经开始执行或需要继续验证的用户
  - 主对象是 `workflow draft`
  - 主动作是：
    - 继续编辑
    - 继续执行
    - 查看失败建议
    - 进入蒸馏前验证
- `学习沉淀`
  - 面向要治理 AI 产出的用户
  - 主对象是：
    - 可保存项
    - branch learning
    - app config candidates
    - 蒸馏结果

推荐理由：

- 这更符合“设计 -> 运行 -> 沉淀”三段式心智。
- 也能避免首次进入 AI 页就被历史会话和技术字段干扰。

### B. 设备作战台默认只承载“当前可操作性”，不承载完整 AI 设计

默认建议 `设备作战台` 只保留以下高权重内容：

- 可操作设备列表
- 在线 / 占用 / 异常状态
- 单设备进入接管 / 详情
- 多选后进入批量下发
- 单设备 `AI 快速发起`

不建议放入首页主区的内容：

- 历史统计
- 成功率趋势
- 深层系统设置
- 大量 RPC / SDK 诊断入口
- AI 学习沉淀治理

推荐理由：

- 用户登录后的第一关注点是“现在能操作什么”，而不是“系统理解了什么”。
- 把设备主工作面做干净，比在首页堆叠各种智能信息更符合你的目标。

### C. 单设备详情默认是“执行与接管页”，不是万能控制台

默认建议单设备详情采用下面的优先级：

- 主区：
  - 当前设备状态
  - 当前任务 / 最近任务
  - 接管入口
  - 快速 AI
  - 需要人工介入的异常
- 次区：
  - 最近截图 / 运行证据
  - 基础 RPC 状态
  - 节点 / XML 浏览入口
- 深层：
  - RPC 诊断
  - 30001 高级能力
  - 8000 设备级管理能力

推荐理由：

- 单设备详情的目标是“帮助用户控制和处理当前这台设备”，不是让用户浏览全部底层能力。

### D. 批量下发默认采用“轻会话”模型，而不是重方案中心

默认建议：

- 首版支持“最近一次配置复用”
- 不做完整“批量方案库”
- 批量下发前做必要的资源校验
- 校验失败允许部分继续
- 失败设备自动沉淀成待处理子集

建议的主对象是：

- `批量下发会话`

它记录：

- 本次选中的设备集合
- 使用的任务模板 / AI 设计来源
- 资源校验结果
- 成功 / 失败 / 待处理设备子集

推荐理由：

- 这符合业务高频场景，也能避免首版过早进入复杂的方案管理系统。

### E. 学习沉淀默认分为“立即生效”和“审核生效”两档

默认建议：

- 可立即生效：
  - workflow draft defaults
  - account default branch
  - 与单次会话偏好直接相关的轻量默认值
- 需要审核后生效：
  - app config candidates
  - 影响全局配置的候选
  - 会改变公共执行策略的沉淀项
- 可按字段直写或审核：
  - branch learning
  - 其中低风险字段可直写，高风险字段进入待审核

风险分层建议：

- 低风险：
  - search keywords
  - reply texts
- 中高风险：
  - payload defaults
  - resource namespace
  - reply_ai_type
  - 影响 app config 的候选

推荐理由：

- 这样既保留 AI 的学习速度，也避免全局策略被一次异常运行污染。

### F. Distill 默认是“生成可测试产物”，不是自动发布

默认建议：

- distill 产物进入“可测试态”
- 不直接视为正式插件发布
- 后续若要进入正式插件层，应再经过人工确认

推荐理由：

- 当前 distill 已是正式能力，但其业务定位更适合被描述为“从 AI 试运行收敛出可验证工作流”。
- 直接自动发布过于激进，不符合当前系统治理成熟度。

### G. 运行态信息默认只展示与当前动作有关的内容

默认建议各层展示规则如下：

- `设备作战台`
  - 只显示：
    - 是否可操作
    - 是否运行中
    - 是否需要介入
- `单设备详情`
  - 显示当前任务与当前异常
- `AI工作台 / 会话与草稿`
  - 显示与当前 draft 相关的执行状态、失败建议、蒸馏进度
- 聚合成功率、趋势、历史
  - 统一后置到低频洞察层

推荐理由：

- 这符合“降低心智负担”的目标。
- 用户只需要知道当前该做什么，不需要首屏看到所有系统统计。

### H. 默认执行顺序建议不变，但前置补一张对象树

默认建议实施顺序仍为：

1. 先补完整对象树
2. 再定页面树
3. 再定关键跳转规则
4. 再做 `设备作战台`
5. 再做 `单设备详情`
6. 再做 `AI工作台`
7. 再做 `资产中心`
8. 最后做低频配置与诊断

这里新增一个关键前置物：

- `产品对象树`

至少应包含：

- 设备摘要
- 设备详情
- 接管态
- 批量下发会话
- 任务图草案
- workflow draft
- 运行资产
- 学习沉淀项
- 任务资产项
- 系统资产项

结论：

- 如果认可这组默认判断，下一步就不应继续泛化讨论，而应直接把它们转成：
  - 页面树 v2
  - 对象树 v1
  - 任务拆解草案
  三份更执行导向的内容。

## Framework Recommendation v1

本节记录当前对“是否需要换框架、应换到什么程度”的建议。

### 1. 后端框架不建议重换，继续保留 FastAPI 主骨架

当前建议：

- 保留 `FastAPI + task system + plugin engine + agent_executor` 主框架
- 不建议因为前端重构而重做后端基础框架

理由：

- 当前系统真正复杂的部分不在 HTTP 路由层，而在：
  - 任务系统
  - 插件执行
  - workflow draft / run asset
  - AI planner / distill / 回流沉淀
- `FastAPI` 现状已经能很好承接：
  - REST API
  - SSE 事件流
  - WebSocket 日志流
- 当前问题主要是：
  - contract 没完全按产品对象收口
  - 前端入口和页面责任不合理
  而不是“后端框架本身不行”

结论：

- 后端应做的是 contract 收口和能力分层，不是改技术底座。

### 2. 前端建议重写，但不建议上 SSR / Next 类方案

当前建议：

- 前端可以完全重写
- 但不建议转向 `Next.js`、服务端渲染后台或前后端一体模板体系

理由：

- 这是一个操作台，不是内容站点
- SEO、SSR 首屏渲染、同构路由都不是当前核心价值
- 当前系统高度依赖：
  - API 拉取
  - SSE
  - WebSocket
  - 任务运行时异步刷新
- 因此前端更适合保持为独立控制台应用，而不是为了“现代化”引入更重的服务端前端框架

结论：

- 前端升级应聚焦“交互结构和状态组织”，不是追求 SSR 技术形态。

### 3. 前端最值得升级的是：从模块化原生 JS 提升到组件化 TypeScript 应用

当前我更推荐的方向是：

- 保留 `Vite`
- 升级到：
  - `React`
  - `TypeScript`

而不是继续长期停留在当前以 `web/js/*` 为主的模块化原生 JS 结构。

理由：

- 这次不是简单页面优化，而是完整产品重构
- 接下来会出现大量稳定且可复用的产品对象：
  - 设备摘要
  - 设备详情
  - 接管态
  - 批量下发会话
  - 任务图草案
  - workflow draft
  - 学习沉淀项
- 这些对象更适合进入：
  - 组件树
  - 类型系统
  - 更明确的页面级状态管理

当前原生 JS 模块方案的主要问题不是“不能写”，而是：

- 大量页面状态会越来越难控
- 契约变更时缺少类型约束
- 多入口复用组件的成本会持续升高

结论：

- 如果要真正做“前端完全重写”，我更建议直接完成一次：
  - 组件化
  - 类型化
  - 页面级状态重组

### 4. 推荐的前端技术组合

当前更适合本项目的组合建议是：

- 构建：
  - `Vite`
- 视图层：
  - `React`
- 语言：
  - `TypeScript`
- 服务端状态：
  - `TanStack Query`
- 本地 UI / 会话状态：
  - `Zustand`
- 路由：
  - `React Router`

额外建议：

- 仅在复杂流程页中局部引入状态机思想
  - 如 `AI工作台 / 任务设计`
  - `批量下发会话`
- 不建议一开始就全局引入过重的状态机框架治理全部页面

理由：

- `TanStack Query` 很适合：
  - 设备列表
  - 任务详情
  - 草稿详情
  - 资产列表
  这类服务端真状态
- `Zustand` 很适合：
  - 筛选条件
  - 面板开关
  - 当前选中设备
  - 当前接管上下文
  这类前端会话态
- `React Router` 已足够承接这次需要的深层页面与详情页跳转

### 5. 不建议的几种路线

当前不建议：

- 继续长期基于“原生 JS 多模块拼装”扩展全部新产品结构
- 为了现代化而直接切 `Next.js`
- 过早引入微前端
- 一开始就把所有状态都塞进一个全局 store
- 在还没定对象树前先做大规模组件库抽象

理由：

- 这些路线要么会放大复杂度，要么会把真正的问题从产品结构转移到技术折腾。

### 6. 对当前业务最合适的框架判断

如果从“产品复杂度、运行模式、改造成本、后续维护”综合判断，我当前最推荐的是：

- 后端：
  - 继续 `FastAPI`
- 前端：
  - 在 `Vite` 内重写为 `React + TypeScript`
- 交互模型：
  - 保留 REST + SSE + WebSocket
- 后端 contract：
  - 围绕产品对象重新收口

一句话总结就是：

- 不换后端底座
- 重写前端壳层
- 升级前端工程组织
- 不追求 SSR
- 先定对象树，再落技术实现

## Refactor Goal Clarification

本次重构的真实目标，不是“做一个更好看的前端”，而是：

- 以前端产品对象和页面责任为牵引
- 反推后端 contract、对象边界、能力分层
- 在现有可复用基础上，重构出一个更合理、更简洁、更可维护的版本

这意味着本次重构应同时追求三个结果：

### 1. 前端层：页面更符合用户心智

前端目标不是把已有能力重新排版，而是：

- 让页面主对象清晰
- 让高频任务路径更短
- 让低频和诊断能力后置
- 让用户始终知道“当前能做什么、下一步该做什么”

### 2. 后端层：contract 以产品对象为中心重组

后端不应继续按技术来源或历史接口堆叠提供能力，而应按产品对象收口。

更准确地说，后端后续应围绕这些对象组织：

- 设备摘要
- 设备详情
- 接管态
- 批量下发会话
- 任务图草案
- workflow draft
- 运行资产
- 学习沉淀项
- 任务资产项
- 系统资产项

结论：

- 本次后端改造重点不是“把更多能力暴露出来”
- 而是“把已经存在的能力按产品对象重新装配”

### 3. 工程层：在保留有效基础的前提下删减复杂度

这次不应做两种错误路线：

- 错误路线 A：
  - 前端重写了，但后端仍保留大量历史别名、重复 contract、错误分层
- 错误路线 B：
  - 后端大拆大建，丢掉现有已经正确的任务系统、AI 草稿链路和设备能力承接

更合理的策略应是：

- 保留正确骨架
  - task system
  - plugin engine
  - planner / workflow draft / run asset / distill
  - 30002 / 8000 已有高覆盖承接
- 清理错误结构
  - 历史遗留入口
  - 页面与能力错位
  - 兼容别名继续外溢
  - 不按产品对象组织的数据返回

### 4. 本次重构的“简洁”不是代码行数少，而是边界更干净

这里的“代码更简洁”不应被理解成单纯缩短代码，而应理解成：

- 一个页面只依赖少量主 contract
- 一个对象只通过一条主要接口路径被读取和修改
- 同一种能力不再同时以多种历史名字暴露给前端
- 同一种产品动作不再跨越多个页面和多个协议拼装

因此判断是否“更简洁”，标准应是：

- 页面职责是否更单一
- contract 是否更少歧义
- 前后端字段是否更统一
- 兼容层是否被压缩到边界，而不是扩散到产品层

### 5. 本次重构的执行原则

后续如果进入实施，建议始终遵守以下原则：

1. 先定产品对象，再定接口，再写页面。
2. 新前端只接 canonical contract，不继续消费历史别名。
3. 后端兼容逻辑只保留在边界，不让它继续污染主流程。
4. 已经正确的底层能力不推翻，只重做产品入口和对象装配。
5. 每完成一类对象收口，就同步删除一批旧页面或旧入口，避免新旧并存过久。

### 6. 对当前方向的补充结论

如果用一句话把这次重构目标说得更准确一些，我建议表述为：

- 这不是“先设计前端，再让后端配合一下”。
- 而是“以前端产品结构为设计起点，对整个系统重新建立一套更合理的对象模型和 contract，再用更现代但不过度的前端工程把它实现出来”。

这个判断会直接影响后续所有实现取舍：

- 哪些页面该删
- 哪些接口该合并
- 哪些兼容层该停止扩张
- 哪些底层能力只需换入口、不必重写
- 哪些代码虽然能跑，但不再符合新对象模型，应纳入清理范围

## Maintainability And Development Constraints

你新增的要求非常关键：这次重构不仅要“更合理”，还必须做到：

- 模块清晰
- 易维护
- 方便后续开发
- 有明确且可执行的开发约束

这意味着本次计划不能只定义页面和对象，还必须定义后续代码如何组织、哪些做法被允许、哪些做法要禁止。

### 1. 模块划分必须以产品域为主，不再以零散功能文件为主

默认建议未来代码结构按“产品域”组织，而不是继续按零散页面脚本或接口来源散落。

前端建议的一级模块域应至少包括：

- `devices`
  - 设备作战台
  - 单设备详情
  - 接管态
  - 批量下发会话
- `ai-workspace`
  - 任务设计
  - 会话与草稿
  - 学习沉淀
- `assets`
  - 任务资产
  - 系统资产
  - 导入与清洗
- `settings`
  - 偏好配置
  - 开发者与诊断
- `shared`
  - 通用 UI
  - 通用 hooks
  - 通用类型
  - 通用 API client

后端建议的收口方向也应与之呼应：

- `device domain`
- `dispatch domain`
- `ai draft domain`
- `asset domain`
- `settings / diagnostics domain`

原则：

- 目录结构要让后续开发者一眼看出“这个功能属于哪一类业务对象”
- 不再允许一个页面逻辑横跨多个无关模块文件拼接完成

### 2. 每个模块必须有清晰的三层边界

无论前端还是后端，默认建议每个主要模块都分清三层：

- `view / presentation`
  - 页面、组件、显示逻辑
- `application / orchestration`
  - 页面流程、交互编排、状态流转
- `domain / contract`
  - 类型、对象模型、接口 contract、业务规则

要避免的旧问题是：

- 视图层直接拼接业务对象
- 页面组件直接散写 API 请求和字段兼容逻辑
- 多个地方各自理解一份对象结构

结论：

- 真正易维护的前提不是文件拆得多，而是每层职责稳定。

### 3. 新前端必须建立明确的 canonical types

本次若采用 `React + TypeScript`，那类型系统必须承担约束作用，而不是只做形式补全。

至少应建立一套统一的产品对象类型：

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

约束要求：

- 同一对象在前端只允许存在一套主类型定义
- 页面只消费 canonical type，不在页面里临时拼字段
- 兼容字段转换必须在 API mapping / adapter 层完成

### 4. 前后端之间必须建立 mapping 层，禁止页面直接吃原始响应

这是后续维护性里最重要的一条。

默认建议：

- 后端逐步收口 canonical response
- 前端即使在过渡期，也要通过独立 mapping 层把原始响应映射为产品对象

禁止的做法：

- 页面组件直接读取原始接口各种兼容字段
- 一个字段在 A 页面叫一种名字，在 B 页面再做另一套 fallback
- 把历史 alias 扩散到新页面代码里

结论：

- 兼容性只能存在于 adapter 层，不能进入页面层和组件层。

### 5. 状态管理必须分层，不允许继续堆成全局杂糅状态

默认建议状态分三类：

- 服务端真状态
  - 交给 `TanStack Query`
- 前端会话状态
  - 交给 `Zustand`
- 页面局部临时状态
  - 留在组件内

开发约束：

- 不把所有状态都塞进单一 store
- 不把远程数据缓存和 UI 控件状态混放
- 不在多个页面各自复制一套筛选与选择逻辑

### 6. 开发约束必须明确“禁止新增历史式兼容扩散”

本次重构若要真正变干净，必须有几条硬约束：

1. 新前端页面禁止继续使用历史字段别名。
2. 新接口优先返回产品对象，不返回技术来源拼接对象。
3. 兼容 alias 只允许保留在 ingestion / adapter 边界。
4. 不允许为单个页面临时发明一套新的对象结构。
5. 相同产品动作只能有一个主入口，不再多页并存多个版本。

### 7. 组件和页面抽象要克制，避免过早“组件库化”

为了可维护，确实要组件化；但为了避免再次失控，也要约束抽象时机。

默认建议：

- 先沉淀页面骨架和产品对象
- 再抽公共组件
- 只抽真正稳定复用的部分

不建议：

- 在页面树和对象树没稳定前就先抽一套庞大 design system
- 为了“通用”把业务组件抽成难理解的万能组件

原则：

- 复用应该来自业务稳定重复，而不是来自过早抽象欲望

### 8. 后端开发约束也必须同步升级

既然这次是“以前端设计后端”，那后端也要遵守新的开发纪律。

默认建议新增以下约束：

- 新能力优先挂到既有产品对象域，而不是追加新的杂项 route
- 同一产品对象只保留一个主读取 contract 和一个主变更 contract
- route 只做参数校验和装配，不写业务规则
- 产品对象聚合逻辑要落在 service / domain 层
- 诊断能力与业务能力分开，不允许再次混入主工作面接口

### 9. 本次重构建议产出一份“开发约束文档”

除了计划文档，后续真正开始实施前，建议再落一份长期有效的开发约束文档，内容至少包括：

- 前端目录约束
- 产品对象命名约束
- API / mapper 约束
- 状态管理约束
- 兼容层约束
- 页面新增流程约束
- 后端 route / service / domain 分层约束

这份文档的作用不是补说明，而是：

- 让后续新功能继续沿新架构长出来
- 防止几轮迭代后又回到旧式堆叠结构

### 10. 对当前方向的补充结论

如果把你这次补充要求转成一句更准确的话，我建议写成：

- 本次重构不仅要重建产品结构，还要顺带建立一套“能约束后续开发继续长在正确方向上”的模块边界和开发纪律。

否则就算第一版重构做对了，后续几轮需求照样会把系统重新拉回混乱状态。

## Product Object Tree v1

本节作为当前阶段的“对象定稿草案”。

后续页面树、contract 收口、前后端模块划分，都应优先围绕这些对象展开，而不是继续围绕历史页面名和技术能力名展开。

### L1. Device Operations Domain

#### 1. DeviceSummary

用于 `设备作战台` 列表层，表达“这台设备现在是否值得我操作”。

应包含的核心信息：

- `device_id`
- `cloud_id`
- `display_label`
- `availability_state`
- `running_state`
- `needs_intervention`
- `selected`
- `current_task_brief`
- `last_exception_brief`
- `quick_actions`

职责：

- 支撑设备列表浏览、筛选、多选、批量入口
- 不承载深层诊断信息

#### 2. DeviceDetail

用于单设备详情页，表达“围绕当前这台设备能做的主要事情”。

应包含的核心分区：

- 当前状态
- 当前任务 / 最近任务
- 接管入口
- 快速 AI
- 人工介入上下文
- 最近截图 / 运行证据
- 深层控制入口

职责：

- 支撑单设备控制与异常处理
- 是设备级深页，不是系统级管理页

#### 3. TakeoverSession

用于接管页或接管面板，表达“用户对当前运行任务的人工接管上下文”。

应包含：

- `task_id`
- `run_id`
- `target_label`
- `current_declarative_stage`
- `control_capabilities`
- `manual_actions`
- `trace_context`
- `takeover_owner`

职责：

- 承接人工接管、轻控制、观察当前声明阶段
- 是运行态对象，不是静态设备对象

#### 4. BatchDispatchSession

用于批量下发页，表达“一次批量执行会话”。

应包含：

- 设备集合
- 任务来源
- 资源校验结果
- 失败设备子集
- 成功设备子集
- 待处理设备子集
- 最近一次配置复用信息

职责：

- 承接一次批量下发的准备、确认、提交和结果回流
- 首版不扩张成复杂方案库

### L2. AI Design Domain

#### 5. TaskDraftDesign

用于 `AI工作台 / 任务设计`，表达“当前正在设计的任务图草案”。

应包含：

- 目标与资源绑定
- goal / 约束
- planner result
- operator summary
- execution readiness
- challenge policy
- recommended workflows
- declarative scripts

职责：

- 面向设计态
- 在确认下发前，它还不是正式 workflow draft

#### 6. WorkflowDraft

用于 `AI工作台 / 会话与草稿`，表达“已进入执行生命周期的持续对象”。

应包含：

- `draft_id`
- `display_name`
- `status`
- `success_count`
- `failure_count`
- `success_threshold`
- `latest_failure_advice`
- `saved_preferences`
- `continuation_snapshot`
- `declarative_binding`
- `distill_assessment`
- `exit`

职责：

- 连接设计、继续执行、蒸馏、保存偏好

#### 7. RunAsset

用于草稿详情和回流沉淀层，表达“一次终态运行沉淀出的可复用资产”。

应包含：

- `business_outcome`
- `distill_decision`
- `distill_reason`
- `value_profile`
- `retained_value`
- `observed_state_ids`
- `entry_actions`
- `terminal_message`

职责：

- 承接 reuse / distill / continue 的判断依据
- 不直接作为首页主对象

#### 8. LearningCandidate

用于 `AI工作台 / 学习沉淀`，表达“本次运行中可保存或待审核的沉淀项”。

至少包括三类：

- 草稿默认值类
- branch learning 类
- app config candidate 类

字段重点：

- `candidate_id`
- `kind`
- `save_target`
- `risk_level`
- `apply_mode`
  - `direct`
  - `review_required`

职责：

- 支撑“保存可复用项”和“审核后生效”两种治理链路

### L3. Asset Domain

#### 9. TaskAssetItem

用于 `资产中心 / 任务资产`，表达任务设计和执行前准备所需资源。

应覆盖：

- 账号
- 2FA
- App 导入资产
- 插件变量
- 业务策略文本
- 任务模板

职责：

- 面向 AI 设计和任务下发前准备

#### 10. SystemAssetItem

用于 `资产中心 / 系统资产`，表达设备运行环境和底层依赖资源。

应覆盖：

- socks 代理
- 设备相关导入资产
- 未来机型参数
- 网段扫描结果
- 其他设备执行环境资产

职责：

- 面向系统环境，不直接进入普通用户高频主工作面

### L4. Low-Frequency Settings Domain

#### 11. PreferenceProfile

用于 `偏好配置`，表达低频个性化与默认行为设置。

#### 12. DiagnosticEntry

用于 `偏好配置 / 开发者与诊断`，表达诊断入口对象。

应覆盖：

- RPC 状态
- runtime execute
- 浏览器诊断
- 深层 SDK / API 调试入口

职责：

- 仅作为低频深层入口，不反向污染主工作面

## Page Tree v2

本节作为当前阶段的“页面树定稿草案”。

原则：

- 一级只放高频心智入口
- 深层页面允许存在，但每页只服务一个主任务
- 运行态、学习沉淀、系统诊断全部后置

### 1. 一级导航

1. `设备作战台`
2. `AI工作台`
3. `资产中心`
4. `偏好配置`

### 2. 设备作战台

#### 2.1 设备作战台首页

主对象：

- `DeviceSummary`

主动作：

- 查看可操作设备
- 筛选异常 / 在线 / 占用
- 多选设备
- 进入单设备详情
- 触发批量下发

不应承担：

- AI 完整设计
- 深层诊断
- 成功率趋势主展示

#### 2.2 单设备详情

主对象：

- `DeviceDetail`

主动作：

- 进入接管
- 快速 AI 发起
- 查看当前任务 / 最近任务
- 处理当前异常

#### 2.3 接管页 / 接管面板

主对象：

- `TakeoverSession`

主动作：

- 轻控制
- 观察当前声明阶段
- 人工介入后回到任务链路

#### 2.4 批量下发页

主对象：

- `BatchDispatchSession`

主动作：

- 确认设备集合
- 选择任务来源
- 校验资源
- 提交批量任务
- 查看待处理子集

### 3. AI工作台

#### 3.1 任务设计

主对象：

- `TaskDraftDesign`

主动作：

- 选择目标与资源
- 填写 goal 与约束
- 生成任务图草案
- 确认并下发

说明：

- 默认作为 `AI工作台` 首屏
- 面向第一次使用或当前要设计新任务的用户

#### 3.2 会话与草稿

主对象：

- `WorkflowDraft`

主动作：

- 查看历史 AI 会话
- 继续编辑
- 继续执行
- 查看失败建议
- 蒸馏前验证

#### 3.3 学习沉淀

主对象：

- `LearningCandidate`
- `RunAsset`

主动作：

- 保存可复用项
- 审核 branch learning / app config candidates
- 查看蒸馏结果

### 4. 资产中心

#### 4.1 任务资产

主对象：

- `TaskAssetItem`

#### 4.2 系统资产

主对象：

- `SystemAssetItem`

#### 4.3 导入与清洗

主对象：

- 导入任务会话

职责：

- 统一承接所有导入格式化与清洗能力

### 5. 偏好配置

#### 5.1 偏好设置

主对象：

- `PreferenceProfile`

#### 5.2 开发者与诊断

主对象：

- `DiagnosticEntry`

职责：

- 集中放置低频深层调试能力

## Draft Freeze For Review

从当前开始，若无新的明确业务判断，后续讨论默认以以下草案为基线：

- `Product Object Tree v1`
- `Page Tree v2`
- `Framework Recommendation v1`
- `Maintainability And Development Constraints`

后续修正建议优先按以下顺序进行：

1. 修对象
2. 再修页面
3. 再修 contract
4. 最后修实现顺序

## Platform Capability Expansion

你新增的 4 组能力会显著扩大本次重构范围。它们不应被视为“零散附加功能”，而应被正式视为：

- `平台层 / SaaS 层 / 管理层`

如果这层不单独建模，后续一定会把：

- 设备业务
- AI 任务业务
- 平台账号权限
- 计费充值
- 系统运维能力

全部重新混成一个大杂烩。

因此从现在开始，本次重构应按“两层产品”理解：

### Layer A. Operator Product

面向普通操作用户：

- 设备作战台
- AI工作台
- 资产中心
- 偏好配置

### Layer B. Platform Product

面向平台管理员 / 组织管理员：

- 认证与用户体系
- 权限与角色
- 计费与积分
- 充值与账单
- 在线更新
- 后台管理

结论：

- 这两层不能继续共享同一套混乱导航和页面语义。
- 普通操作者的主导航不应被平台管理功能污染。

## SaaS And Platform Domain v1

本节定义这次新增的平台层对象。

### 1. UserIdentity

表达一个登录用户的身份对象。

应包含：

- `user_id`
- `account`
- `display_name`
- `email_or_phone`
- `status`
- `created_at`
- `last_login_at`

职责：

- 承接注册、登录、会话身份识别

### 2. WorkspaceMember

表达用户在当前系统中的成员关系。

应包含：

- `member_id`
- `user_id`
- `role_ids`
- `permission_scope`
- `status`

职责：

- 支撑多用户、多角色、多权限

### 3. RoleProfile

表达角色对象。

应包含：

- `role_id`
- `name`
- `description`
- `permission_keys`
- `is_system_role`

职责：

- 支撑权限模板与角色分配

### 4. PermissionPolicy

表达权限策略对象。

至少要能覆盖：

- 页面访问权限
- 功能操作权限
- 管理后台权限
- 充值 / 扣费调整权限
- 系统更新权限

### 5. CreditAccount

表达积分账户对象。

应包含：

- `owner_type`
- `owner_id`
- `balance`
- `frozen_balance`
- `billing_currency_type`
- `updated_at`

职责：

- 支撑系统积分余额和扣费基础

### 6. BillingRule

表达扣费规则对象。

必须支持：

- 普通任务步数扣费比例
- AI 驱动任务步数扣费比例
- 可后台调整
- 生效时间与版本

建议字段：

- `rule_id`
- `task_mode`
  - `standard`
  - `ai_driven`
- `step_unit_price`
- `enabled`
- `effective_at`
- `updated_by`

### 7. CreditTransaction

表达积分流水。

至少应区分：

- 充值
- 扣费
- 调整
- 退款 / 回滚

并记录：

- 关联任务
- 关联执行步骤
- 规则快照

### 8. RechargeOrder

表达积分充值订单。

职责：

- 支撑充值流程
- 形成账务记录

### 9. UpdateChannel / UpdateJob

表达在线更新对象。

建议拆为：

- `UpdateChannel`
  - 当前渠道、版本、目标版本、策略
- `UpdateJob`
  - 一次更新任务的执行记录、状态、日志、回滚信息

职责：

- 把“系统在线更新”作为平台运维能力建模，而不是一个按钮

### 10. AdminAction

表达后台管理动作记录。

职责：

- 记录权限变更
- 充值调整
- 扣费规则调整
- 更新操作
- 敏感配置修改

结论：

- 平台层对象一旦确认，后端与前端都必须给它们单独模块域。

## Page Tree v3 Addendum: Platform Layer

在 `Page Tree v2` 基础上，新增一组“平台层页面”，但它们不进入普通操作用户的一级主导航。

### A. 认证入口

- `登录`
- `注册`
- `找回密码 / 重置凭证`

说明：

- 这是系统外层入口，不属于 operator 主工作面

### B. 管理后台

建议作为：

- 独立管理员入口
  或
- 仅管理员可见的条件导航

当前不建议直接混入普通用户一级主导航。

后台建议拆分为：

#### B.1 用户与成员

- 用户列表
- 成员关系
- 角色分配
- 权限管理

#### B.2 计费与积分

- 积分余额视图
- 积分流水
- 充值订单
- 手工充值 / 调整

#### B.3 计费规则

- 普通任务扣费规则
- AI 驱动任务扣费规则
- 生效规则版本

#### B.4 系统更新

- 当前版本
- 可更新版本
- 更新任务记录
- 回滚 / 失败记录

#### B.5 系统管理

- 平台权限
- 关键系统开关
- 风险操作记录

结论：

- 管理后台是必要能力，但不应污染 operator 产品主导航。

## Billing Model Draft v1

当前按你的补充，系统计费模型应默认按“执行步骤扣费”设计。

### 核心原则

1. 计费对象是“执行步骤”，不是单纯任务创建次数。
2. 普通任务与 AI 驱动任务必须支持不同扣费比例。
3. 扣费比例必须可后台调整。
4. 扣费必须可回溯到规则快照，避免后续账务无法解释。

### 建议的计费分层

- `任务类型层`
  - 普通任务
  - AI 驱动任务
- `执行层`
  - 实际执行步数
- `账务层`
  - 根据规则快照生成扣费流水

### 重要约束

- 扣费逻辑不应散落在前端页面
- 也不应分散在多个任务入口各自计算
- 必须在后端统一结算并记录账务流水

结论：

- 计费系统必须是独立平台域，不是任务页上的一个临时功能

## Extensibility Requirement Upgrade

你强调的“框架合理，可以随时新增功能”需要被正式转化为架构要求。

这意味着这次重构必须满足：

### 1. 新增功能时优先落到既有产品域

未来新增功能时，应优先判断它属于哪一类域：

- devices
- ai-workspace
- assets
- settings
- auth
- billing
- admin
- updates

而不是继续新增一个“misc”页面或“杂项接口”。

### 2. 新功能必须先选对象，再选页面，再选接口

新增能力时的顺序约束应是：

1. 它属于哪个产品对象
2. 它出现在哪个页面层
3. 它需要什么 canonical contract
4. 最后才是具体实现

### 3. 平台功能与业务功能必须解耦

要避免后续出现这些问题：

- 计费逻辑写进设备页
- 权限判断散落在前端组件里
- 更新逻辑混入业务设置页
- 管理后台接口直接复用 operator 页面对象返回

### 4. 敏感能力必须统一进入平台层

以下能力未来应统一视为平台层：

- 权限管理
- 积分调整
- 扣费规则调整
- 系统更新
- 管理员审计

而不是作为普通用户工作面的隐藏按钮出现

## Additional Refactor Judgment

基于你新增的需求，本次重构现在已经可以更准确地定义为：

- 一次“operator product + platform product”双层重构

其中：

- operator product 负责设备、AI、资产、低频偏好
- platform product 负责认证、权限、计费、充值、更新、后台管理

因此后续计划不能只输出前端页面树，还必须再补：

- 平台层对象树
- 平台层页面树
- 权限模型草案
- 计费模型草案
- 管理后台能力边界

## Plugin Marketplace Expansion

你新增的“插件商店”能力，意味着插件系统不再只是仓库内部的运行时机制，而要升级为：

- `产品层可浏览`
- `平台层可交易`
- `用户层可上传`
- `计费层可结算`

这会直接影响：

- `AI 蒸馏产物` 的去向
- `任务资产` 与 `插件资产` 的边界
- `积分系统` 的扣费和奖励模型
- `管理员后台` 的审核与治理能力

因此插件商店必须单独建模，不能只作为资产中心里的一个列表页处理。

## Plugin Marketplace Domain v1

### 1. PluginPackage

表达一个可分发的插件包对象。

应包含：

- `plugin_id`
- `plugin_name`
- `display_name`
- `version`
- `author_id`
- `source_type`
  - `official`
  - `user_uploaded`
  - `distilled`
- `category`
- `summary`
- `cover_media`
- `capabilities`
- `price_in_credits`
- `status`
  - `draft`
  - `pending_review`
  - `published`
  - `rejected`
  - `archived`

职责：

- 作为插件商店中的核心商品对象

### 2. PluginRelease

表达插件的版本发布对象。

应包含：

- `release_id`
- `plugin_id`
- `version`
- `changelog`
- `artifact_ref`
- `manifest_snapshot`
- `script_snapshot`
- `review_status`
- `published_at`

职责：

- 把“插件”与“插件某一版本”拆开
- 便于后续更新、回滚、审核和下载统计

### 3. PluginOwnership

表达某个用户或工作空间对插件的拥有关系。

应包含：

- `owner_type`
- `owner_id`
- `plugin_id`
- `acquired_via`
  - `purchase`
  - `reward`
  - `official_grant`
  - `self_upload`
- `granted_at`

职责：

- 支撑“谁已经拥有这个插件”
- 不把“下载过”和“有权使用”混为一谈

### 4. PluginPurchase

表达一次插件购买 / 下载交易。

应包含：

- `purchase_id`
- `buyer_id`
- `plugin_id`
- `release_id`
- `credit_cost`
- `billing_rule_snapshot`
- `created_at`

职责：

- 承接插件下载消耗积分

### 5. PluginRewardTransaction

表达插件上传者因他人下载而获得的积分奖励。

应包含：

- `reward_id`
- `plugin_id`
- `release_id`
- `author_id`
- `downloader_id`
- `reward_credits`
- `reward_rule_snapshot`
- `created_at`

职责：

- 支撑上传后他人下载带来的积分奖励

### 6. PluginSubmission

表达一次用户提交上传的插件内容。

支持来源：

- 用户手工制作上传
- 从系统蒸馏产物一键送审

应包含：

- `submission_id`
- `submitter_id`
- `source_type`
- `artifact_ref`
- `manifest_preview`
- `review_notes`
- `status`

职责：

- 把“上传动作”和“已上架插件”拆开

### 7. PluginReviewTask

表达管理员对插件的审核任务。

至少应支持：

- 基础信息审核
- 安全性审核
- 计费与奖励规则审核
- 上架 / 驳回 / 下架

### 8. PluginInstallSession

表达用户安装 / 获取插件到工作空间的会话对象。

职责：

- 统一处理购买、授权、安装、版本选择

## Page Tree v4 Addendum: Plugin Marketplace

插件商店建议不直接塞进 `资产中心`，也不直接混进 `AI工作台`。

更合理的定位是：

- 作为 `平台层 / 业务扩展域`
- 对普通用户提供可进入入口
- 对管理员提供审核后台入口

### A. 普通用户侧页面

#### A.1 插件商店首页

主对象：

- `PluginPackage`

主动作：

- 浏览插件
- 搜索 / 分类筛选
- 查看积分价格
- 查看来源
- 进入插件详情

#### A.2 插件详情页

主对象：

- `PluginPackage`
- `PluginRelease`

主动作：

- 查看说明
- 查看版本
- 下载 / 购买
- 安装到当前工作空间

#### A.3 我的插件

主对象：

- `PluginOwnership`

主动作：

- 查看已拥有插件
- 查看版本
- 更新 / 安装
- 管理自己上传的插件

#### A.4 上传插件

主对象：

- `PluginSubmission`

主动作：

- 上传手工制作插件
- 从蒸馏产物发起上传
- 填写插件说明与价格
- 提交审核

### B. 管理员侧页面

#### B.1 插件审核

主对象：

- `PluginReviewTask`

主动作：

- 审核上传插件
- 审核蒸馏产物转市场插件
- 上架 / 驳回 / 下架

#### B.2 插件交易与奖励

主对象：

- `PluginPurchase`
- `PluginRewardTransaction`

主动作：

- 查看购买流水
- 查看奖励流水
- 调整奖励策略

## Plugin Marketplace Billing Draft v1

插件商店计费与奖励当前建议采用“双向积分流”：

### 1. 下载购买消耗积分

规则：

- 用户从插件商店下载 / 获取插件时消耗积分
- 该积分消耗独立于任务执行扣费

### 2. 上传者获得积分奖励

规则：

- 当其他用户下载某个已发布插件时
- 上传者获得积分奖励

### 3. 官方插件与用户插件要区分

建议区分：

- 官方插件
  - 可免费
  - 可定价
  - 可平台补贴
- 用户插件
  - 默认可定价
  - 下载后按规则给上传者奖励
- 蒸馏产物插件
  - 默认先进入审核态
  - 审核通过后才允许进入商店交易

### 4. 插件计费规则也要后台可调

建议后台支持：

- 默认下载积分价格策略
- 上传者奖励比例
- 官方插件特殊策略
- 蒸馏插件特殊策略

### 5. 重要约束

- 插件积分消耗与任务执行积分消耗必须分开记账
- 奖励规则必须保留快照
- 不允许在前端直接计算奖励和扣费
- 所有购买 / 奖励都必须由后端统一结算

## Relationship To Existing Domains

插件商店引入后，现有域之间的关系需要重新明确：

### 1. 与 AI 工作台的关系

- `AI工作台 / 学习沉淀` 中的蒸馏产物可以进入“上传到插件商店”链路
- 但 `AI工作台` 本身不是插件商店

### 2. 与资产中心的关系

- 已安装 / 已拥有插件可视为“可用任务能力资源”
- 但插件商店本身不应并入普通资产列表页

### 3. 与计费系统的关系

- 插件下载扣积分
- 插件作者获积分奖励
- 这要求计费系统支持：
  - 消费流水
  - 奖励流水
  - 规则快照

### 4. 与管理员后台的关系

- 插件审核、上下架、奖励规则、违规处理都必须进入后台治理

## Extensibility Upgrade: Marketplace As First-Class Domain

加入插件商店后，未来系统新增功能的一级域建议扩展为：

- devices
- ai-workspace
- assets
- settings
- auth
- billing
- admin
- updates
- marketplace

结论：

- `marketplace` 从现在开始应视为一等域
- 不应再把插件只理解成 `plugins/` 目录里的运行时文件
- 在产品和系统层，它已经变成：
  - 可分发能力
  - 可计费能力
  - 可奖励能力
  - 可审核能力

## Planning Impact Update

插件商店加入后，后续计划还必须再补四份内容：

- `Marketplace Object Tree`
- `Marketplace Console Tree`
- `Marketplace Permission Rules`
- `Marketplace Billing Rules`

## Commercialization Addendum

本节从“商业落地”视角补充本项目还需要考虑的能力。

这里的重点不是继续堆功能，而是识别：

- 哪些能力会直接影响是否能卖
- 哪些能力会影响是否能持续收费
- 哪些能力会影响交付、风控、运营和售后成本

## Commercial Model Judgment v1

基于当前产品结构，本项目更像一个：

- `B2B / SaaS + Automation Platform + Marketplace`

它的商业闭环至少由四条线组成：

### 1. 主产品收费线

围绕：

- 设备操作能力
- AI 驱动任务设计与执行
- 批量下发
- 资产管理

进行基础收费。

### 2. 使用量收费线

围绕：

- 执行步骤
- 普通任务与 AI 任务差异化扣费

进行用量型计费。

### 3. 平台增值收费线

围绕：

- 多用户权限
- 管理后台
- 在线更新
- 高级诊断与治理能力

进行平台级增值收费。

### 4. 市场交易收费线

围绕：

- 插件商店下载
- 上传奖励
- 平台抽成 / 奖励规则

进行市场化收费。

结论：

- 这不是单一产品售卖，而是一个多收入模型平台。
- 因此系统架构必须从一开始就支持：
  - 租户 / 工作空间
  - 权限
  - 计费
  - 交易
  - 审计

## Missing Commercial Features v1

从商业落地角度看，当前还建议补充以下能力。

### 1. Workspace / Tenant 模型

如果要做真正 SaaS，多用户还不够，还需要明确：

- 是否存在 `workspace / tenant / organization`
- 用户属于哪个工作空间
- 设备、资产、插件、积分、账单归属于谁

建议新增对象：

- `Workspace`
- `WorkspacePlan`
- `WorkspaceQuota`

推荐理由：

- 没有工作空间模型，后面的权限、计费、插件拥有关系都会变乱。

### 2. 套餐与配额体系

目前已有积分制，但商业上通常还需要“套餐层”。

建议新增：

- 免费试用 / 新手额度
- 基础版 / 专业版 / 企业版
- 套餐对应的：
  - 用户数
  - 设备数
  - AI 任务能力
  - 管理后台权限
  - 市场能力

原因：

- 只做积分，不做套餐，会让销售与定价表达太单一。

### 3. 试用与新手转化能力

商业落地里很关键的一点是：

- 用户第一次进入后是否能快速体验价值

建议补充：

- 新用户试用积分
- 新手引导任务模板
- Demo 工作空间 / Demo 插件
- 首次成功任务引导

原因：

- 这是提高转化率的核心，不只是产品体验问题。

### 4. 账单、对账与发票能力

如果要真实收费，后台仅有积分流水还不够。

建议补充：

- 账单概览
- 月度 / 周期对账
- 充值记录
- 扣费记录
- 奖励记录
- 发票 / 财务导出能力

原因：

- 没有账单层，企业客户很难接受长期采购和报销结算。

### 5. 风控与阈值控制

积分制和插件市场一上线，就必须考虑滥用问题。

建议补充：

- 每日扣费上限
- 单任务扣费预警
- 工作空间余额预警
- 插件奖励异常检测
- 高频下载 / 刷奖励检测
- 管理员风控冻结能力

原因：

- 这会直接影响平台亏损风险。

### 6. 审计日志与敏感操作追踪

既然有：

- 权限管理
- 积分调整
- 计费规则调整
- 插件审核
- 在线更新

那就必须补：

- 审计日志
- 敏感操作记录
- 管理员行为留痕

建议对象：

- `AuditLog`
- `RiskEvent`

### 7. 插件市场还缺两类关键能力

#### A. 插件安全治理

建议补充：

- 插件签名 / 包校验
- manifest / script 规则校验
- 风险关键词与危险动作检测
- 上架前安全扫描

#### B. 插件兼容性治理

建议补充：

- 插件兼容的系统版本
- 插件兼容的运行环境
- 插件依赖声明
- 插件弃用 / 版本迁移提示

原因：

- 商店一旦开放上传，没有治理就会很快不可维护。

### 8. 对外集成能力

如果要商业化，很多客户不会只在网页里点按钮。

建议补充：

- Open API / API token
- Webhook
- 任务状态回调
- 账单 / 扣费 / 更新事件回调

原因：

- 企业客户通常会把你接入自己的运营系统、工单系统、财务系统。

### 9. 客户成功与售后能力

这类平台商业化后，售后工具同样重要。

建议补充：

- 工作空间健康度概览
- 问题诊断包导出
- 远程协助 / 支持模式
- 客服可读的错误解释

原因：

- 这能明显降低售后与交付成本。

### 10. 发布与灰度能力

既然你需要在线更新，那建议一并考虑：

- 灰度发布
- 渠道发布
- 工作空间分批升级
- 插件版本灰度
- 回滚策略

原因：

- 在线更新如果只有“立即全量升级”，商业上风险很高。

## Additional Recommended Features

如果只从“是否值得加入计划”角度判断，我认为优先级较高、值得正式纳入的新增功能还有：

### P1. 必须补

- `Workspace / Tenant`
- `套餐与配额`
- `账单与对账`
- `审计日志`
- `风控与阈值控制`
- `插件审核与安全扫描`

### P2. 很有价值

- `Webhook / Open API`
- `灰度更新 / 分批发布`
- `试用与 Demo 机制`
- `客户支持工具`

### P3. 可后置

- 发票中心
- 推广 / 邀请奖励
- 渠道代理 / reseller 体系
- 插件排行榜 / 推荐系统

## Commercialization Constraint Upgrade

商业化能力加入后，当前架构约束还需要再升级两条：

### 1. 所有计费相关逻辑必须可审计

包括：

- 任务扣费
- 插件购买扣费
- 上传奖励
- 管理员调整

要求：

- 全部保留规则快照
- 全部可回溯
- 全部有流水

### 2. 所有平台级变更都必须有权限和审计边界

包括：

- 用户权限变更
- 套餐变更
- 充值和积分调整
- 插件上架 / 下架
- 系统更新

要求：

- 必须有角色权限控制
- 必须有管理员操作记录
- 必须能区分普通用户与平台管理员

## Current Best Commercial Recommendation

如果要让我现在给一个更实际的商业落地建议，我会这样定优先级：

### 第一阶段

- 先把 operator 产品做强
- 同时补最小可用平台层：
  - 登录注册
  - 工作空间
  - 角色权限
  - 积分账户
  - 扣费规则
  - 管理后台基础版

### 第二阶段

- 补完整计费与账单体系
- 补在线更新与灰度
- 补插件上传与审核

### 第三阶段

- 正式上线插件商店交易
- 做奖励分发
- 做 API / Webhook / 企业集成

结论：

- 对商业落地来说，当前最重要的新增不是继续堆操作功能，而是把：
  - 租户
  - 套餐
  - 计费
  - 审计
  - 市场治理
  这五件事尽快纳入主计划。

## Workspace / Tenant Model Draft v1

本项目若要真正 SaaS 化，默认必须引入 `workspace / tenant` 作为主归属边界。

### 1. 基础判断

建议采用：

- `User`
  - 表达自然人身份
- `Workspace`
  - 表达团队 / 公司 / 项目空间
- `WorkspaceMember`
  - 表达用户与工作空间关系

而不是让：

- 用户直接拥有全部设备
- 用户直接拥有全部积分
- 插件、资产、账单直接挂在 user 上

### 2. 建议的归属规则

默认归属建议如下：

- 设备
  - 归属 `Workspace`
- 任务资产
  - 归属 `Workspace`
- 系统资产
  - 归属 `Workspace`
- workflow draft
  - 归属 `Workspace`，并记录创建人
- run asset
  - 归属 `Workspace`
- 积分账户
  - 主账户归属 `Workspace`
- 插件拥有关系
  - 默认归属 `Workspace`
- 插件上传作者
  - 记录 `User`
- 账单
  - 归属 `Workspace`

### 3. Workspace 需要承载的对象

建议至少新增：

- `Workspace`
- `WorkspacePlan`
- `WorkspaceQuota`
- `WorkspaceCreditAccount`

其中：

- `WorkspacePlan`
  - 套餐与功能等级
- `WorkspaceQuota`
  - 用户数、设备数、并发、AI 能力等限制
- `WorkspaceCreditAccount`
  - 主积分余额与账务归属

### 4. 产品影响

这会直接决定：

- 登录后进入哪个工作空间
- 管理后台管理的是哪个空间
- 设备和资产默认显示哪个空间的数据
- 插件下载消耗的是哪个空间的积分

结论：

- `Workspace` 应从现在开始视为平台主对象，不再后补。

## Permission Model Draft v1

权限模型建议采用“三层权限”：

### 1. Platform Role

面向整个平台的高权限角色。

建议包括：

- `platform_super_admin`
- `platform_admin`
- `platform_auditor`
- `platform_support`

职责：

- 管全局规则、全局账务、全局更新、全局市场治理

### 2. Workspace Role

面向某个工作空间内部的角色。

建议包括：

- `workspace_owner`
- `workspace_admin`
- `workspace_operator`
- `workspace_designer`
- `workspace_finance`
- `workspace_viewer`

职责示意：

- `owner`
  - 全部权限
- `admin`
  - 用户、资产、设备、任务、插件管理
- `operator`
  - 设备操作、任务执行、接管
- `designer`
  - AI 设计、草稿、蒸馏、插件上传
- `finance`
  - 充值、账单、积分流水查看
- `viewer`
  - 只读

### 3. Permission Key

最终执行层建议仍使用显式 permission key，而不是只靠角色名硬编码。

建议至少分为这些域：

- `devices.*`
- `takeover.*`
- `dispatch.*`
- `ai_design.*`
- `ai_learning.*`
- `assets.task.*`
- `assets.system.*`
- `billing.*`
- `marketplace.*`
- `workspace_members.*`
- `workspace_settings.*`
- `admin.*`
- `updates.*`

### 4. 关键权限判断建议

默认建议：

- 执行任务与接管
  - 需要 `devices.operate` / `takeover.request`
- AI 设计与蒸馏
  - 需要 `ai_design.write` / `ai_learning.manage`
- 上传插件
  - 需要 `marketplace.submit`
- 调整积分与计费规则
  - 需要平台或工作空间高级财务权限
- 系统更新
  - 需要 `updates.manage`

### 5. 权限实现约束

必须遵守：

- 页面显示控制只是体验层，不是唯一权限控制
- API 必须做真正的权限校验
- 敏感能力必须同时写审计日志

## Admin Console Tree v1

后台建议拆成 6 个稳定分区，而不是一个大而平的管理页。

### 1. 工作空间管理

- 工作空间列表
- 套餐与配额
- 成员与角色
- 空间状态

### 2. 用户与权限

- 用户列表
- 角色模板
- 权限策略
- 审计查询

### 3. 计费与账务

- 积分账户
- 充值订单
- 扣费流水
- 奖励流水
- 财务调整

### 4. 计费规则与风控

- 普通任务扣费规则
- AI 任务扣费规则
- 插件交易规则
- 奖励规则
- 风控阈值

### 5. 插件市场治理

- 插件审核
- 上下架
- 举报 / 风险处理
- 版本治理

### 6. 系统更新与运维

- 当前版本
- 更新任务
- 灰度策略
- 回滚记录
- 诊断入口

结论：

- 后台必须按平台治理对象划分，不再按“想到一个管理功能就加一个 tab”。

## Canonical Contract Draft v1

本节只定义“主 contract 该长什么样”，不是最终接口文档。

### 1. Operator Contracts

建议优先建立以下主读取对象：

- `GET /operator/devices`
  - 返回 `DeviceSummary[]`
- `GET /operator/devices/{deviceKey}`
  - 返回 `DeviceDetail`
- `GET /operator/takeover/{taskId}`
  - 返回 `TakeoverSession`
- `POST /operator/batch-dispatch`
  - 创建 `BatchDispatchSession`
- `POST /operator/ai/design/plan`
  - 返回 `TaskDraftDesign`
- `GET /operator/ai/drafts`
  - 返回 `WorkflowDraft[]`
- `GET /operator/ai/drafts/{draftId}`
  - 返回 `WorkflowDraft`
- `GET /operator/ai/drafts/{draftId}/run-assets`
  - 返回 `RunAsset[]`
- `GET /operator/assets/task`
  - 返回 `TaskAssetItem[]`
- `GET /operator/assets/system`
  - 返回 `SystemAssetItem[]`

说明：

- 这里的 `/operator/*` 是目标语义，不一定代表最终物理路由必须马上这么改
- 但新前端应围绕这套对象 contract 设计

### 2. Platform Contracts

建议优先建立：

- `GET /platform/workspaces`
- `GET /platform/workspaces/{workspaceId}`
- `GET /platform/workspaces/{workspaceId}/members`
- `GET /platform/workspaces/{workspaceId}/billing`
- `GET /platform/workspaces/{workspaceId}/transactions`
- `GET /platform/workspaces/{workspaceId}/plugins`
- `GET /platform/admin/audit-logs`
- `GET /platform/admin/update-jobs`

### 3. Marketplace Contracts

建议优先建立：

- `GET /marketplace/plugins`
- `GET /marketplace/plugins/{pluginId}`
- `POST /marketplace/plugins/{pluginId}/purchase`
- `GET /marketplace/my/plugins`
- `POST /marketplace/submissions`
- `GET /marketplace/submissions`
- `POST /marketplace/admin/reviews/{reviewId}/approve`
- `POST /marketplace/admin/reviews/{reviewId}/reject`

### 4. Contract Mapping Strategy

执行策略建议分两步：

1. 后端先保留现有接口
2. 新增或聚合出 canonical object contract
3. 新前端只消费 canonical contract
4. 旧接口在过渡期只服务旧前端与兼容边界

### 5. Contract 设计硬约束

必须满足：

- 一个页面对应少量主 contract
- 一个对象只存在一套主类型
- 兼容字段不进入页面层
- 技术来源不暴露为页面对象命名

## Execution Readiness Update

到当前阶段，这份文档已经具备以下“接近开工”的基础：

- 产品对象树
- 页面树
- 平台层对象
- 市场层对象
- 商业化约束
- 工作空间模型
- 权限模型
- 后台树
- canonical contract 草案

距离真正进入实施，还差最后几类内容：

1. `Implementation Phases v1`
2. `Route / Module Refactor Plan v1`
3. `Frontend Module Tree v1`
4. `Development Rules Doc Outline`

判断：

- 现在已经不是“还没定方向”，而是“基本方向已经定了，差执行编排和少量修正”。

## Frontend Module Tree v1

如果前端按 `Vite + React + TypeScript` 重写，建议从一开始就固定模块树，避免后续重新长成“页面脚本堆”。

### 1. 顶层目录建议

建议结构：

- `web/src/app`
- `web/src/pages`
- `web/src/features`
- `web/src/entities`
- `web/src/shared`

### 2. 各层职责建议

#### `app`

职责：

- 路由入口
- 全局 providers
- 鉴权壳层
- workspace 上下文
- 权限守卫

#### `pages`

职责：

- 页面级组装
- 一个页面对应一个主对象 / 主流程

建议至少包括：

- `devices`
- `device-detail`
- `takeover`
- `batch-dispatch`
- `ai-design`
- `ai-drafts`
- `ai-learning`
- `task-assets`
- `system-assets`
- `preferences`
- `admin/*`
- `marketplace/*`
- `auth/*`

#### `features`

职责：

- 页面内的完整交互能力块

建议一级 feature 域：

- `devices`
- `takeover`
- `dispatch`
- `ai-design`
- `ai-drafts`
- `ai-learning`
- `assets`
- `billing`
- `workspace`
- `marketplace`
- `updates`
- `admin`

#### `entities`

职责：

- canonical product objects
- object-specific UI fragments
- object-specific mappers
- object-specific query keys / selectors

建议对象域：

- `device`
- `takeover-session`
- `batch-dispatch-session`
- `task-draft-design`
- `workflow-draft`
- `run-asset`
- `learning-candidate`
- `task-asset`
- `system-asset`
- `workspace`
- `member`
- `billing`
- `plugin-package`

#### `shared`

职责：

- UI primitives
- API client
- query client
- auth helpers
- common utilities
- common types

### 3. 模块树约束

必须遵守：

- `pages` 不直接写原始 API 兼容逻辑
- `features` 不跨域互相直接依赖内部实现
- `entities` 承载对象模型，不承载页面流程
- `shared` 只放真正跨域稳定能力

## Route / Module Refactor Plan v1

本节定义后端和前端的模块重构方式，目标不是“一次性推翻”，而是分阶段收口。

### 1. 后端 route 重构方向

当前建议未来 route 分三大语义层：

- `operator routes`
- `platform routes`
- `marketplace routes`

#### `operator routes`

承接：

- devices
- takeover
- dispatch
- ai draft
- assets

#### `platform routes`

承接：

- auth
- workspace
- billing
- admin
- updates

#### `marketplace routes`

承接：

- plugin browse
- purchase
- submission
- review

### 2. 后端 service 重构方向

建议同步建立 service/domain 分区：

- `device_domain`
- `dispatch_domain`
- `ai_domain`
- `asset_domain`
- `workspace_domain`
- `billing_domain`
- `marketplace_domain`
- `update_domain`
- `admin_domain`

约束：

- route 只做装配与权限入口
- 聚合对象逻辑下沉到 domain/service
- 兼容 alias 不直接散落在 route

### 3. 前端模块迁移策略

建议采用“新模块并行生长、旧模块逐步退场”：

1. 新页面全部进入 `web/src/*`
2. 旧 `web/js/*` 只做维持与过渡
3. 一个新页面完成后，立即切断旧页面对应入口
4. 不允许长期双轨维护同一页面功能

### 4. 页面切换顺序建议

建议按这个顺序重构页面：

1. `设备作战台`
2. `单设备详情`
3. `批量下发`
4. `AI工作台 / 任务设计`
5. `AI工作台 / 会话与草稿`
6. `AI工作台 / 学习沉淀`
7. `资产中心`
8. `认证与工作空间`
9. `计费与后台`
10. `插件商店`
11. `更新与运维`

## Development Rules Doc Outline

真正开始实施前，建议额外产出一份长期约束文档。这里先给提纲。

### 1. 命名约束

- 页面名按产品对象命名
- 类型名按 canonical object 命名
- API mapper 名与对象名一一对应
- 不继续把技术来源名暴露为产品对象名

### 2. 前端代码约束

- 页面只消费 canonical types
- 原始响应必须先过 mapper
- query key 必须按对象域组织
- 会话状态与远程状态分开
- 新功能先落 feature，再接 page

### 3. 后端代码约束

- route 不写业务规则
- 新 contract 先围绕对象设计
- 兼容 alias 只能留在边界
- 聚合对象逻辑必须在 service/domain
- 敏感平台操作必须写审计

### 4. 权限约束

- 页面守卫不是最终权限控制
- 所有敏感 API 再做权限校验
- 管理员操作必须保留审计日志

### 5. 计费约束

- 扣费逻辑统一后端结算
- 奖励逻辑统一后端结算
- 所有账务保留规则快照
- 所有账务有流水记录

### 6. 市场治理约束

- 插件上传必须进 submission
- 审核通过后才可 published
- 下载 / 奖励全部入账
- 风险插件可下架与冻结

### 7. 更新能力约束

- 更新任务必须有 job 记录
- 支持失败记录与回滚
- 不允许无记录的直接升级

## Implementation Phases v1

本节给出当前阶段最推荐的实施顺序。

### Phase 0. Blueprint Freeze

目标：

- 冻结对象树
- 冻结页面树
- 冻结模块树
- 冻结开发约束

产出：

- 本计划定稿版
- 开发约束文档 v1

### Phase 1. Platform Foundation

目标：

- 建立 auth / workspace / permission 基础
- 建立基础 billing objects
- 建立 admin 壳层

优先产出：

- 登录 / 注册
- workspace 切换
- 基础角色权限
- workspace credit account

### Phase 2. Operator Core

目标：

- 完成设备主工作面重构
- 完成单设备详情与接管链路重构
- 完成批量下发主链路

优先产出：

- `设备作战台`
- `单设备详情`
- `接管页`
- `批量下发页`

### Phase 3. AI Core

目标：

- 重构 `AI工作台`
- 收口 task draft / workflow draft / learning flows

优先产出：

- `任务设计`
- `会话与草稿`
- `学习沉淀`

### Phase 4. Asset And Settings

目标：

- 重构 `资产中心`
- 收口偏好配置与开发者诊断

### Phase 5. Billing And Admin

目标：

- 完整接入积分、账单、规则、风控、后台治理

### Phase 6. Marketplace

目标：

- 上线插件商店浏览、拥有、上传、审核、交易、奖励链路

### Phase 7. Updates And Integrations

目标：

- 在线更新
- 灰度策略
- Open API / Webhook

## Near-Final Planning Judgment

到当前为止，这份计划已经具备：

- 产品层结构
- 技术框架建议
- 平台层与市场层扩展
- 模块化与维护性约束
- 对象树
- 页面树
- 权限与 workspace 模型
- contract 草案
- 实施阶段草案

因此可以做出一个接近最终的判断：

- 现在缺的已经不是大的方向判断，而只是你最后一轮对局部结构的修正。
- 一旦你确认或修正这些局部项，这份文档就可以转化为正式执行计划。

## Priority And Commercial Readiness Check

本节用于明确回答两个问题：

1. 当前任务优先级是否已经清楚
2. 商业落地相关新增是否已经足够详细

### 1. 当前任务优先级判断

结论：

- `大方向优先级` 已经清楚
- `执行级优先级` 已经基本清楚
- `个别商业功能的上线顺序` 仍可微调，但不会影响主计划骨架

### 2. 当前最清楚的优先级顺序

按系统建设顺序，当前最合理的优先级应是：

#### P0. 蓝图冻结

- 对象树
- 页面树
- 模块树
- 开发约束

#### P1. 平台基础能力

- 登录 / 注册
- Workspace / Tenant
- 基础角色权限
- 基础管理员壳层

原因：

- 没有这层，后续设备、资产、计费、插件归属都会漂浮

#### P2. Operator 主业务面

- 设备作战台
- 单设备详情
- 接管
- 批量下发

原因：

- 这是最高频、最直接体现产品价值的部分

#### P3. AI 主链路

- AI 工作台 / 任务设计
- AI 工作台 / 会话与草稿
- AI 工作台 / 学习沉淀

原因：

- AI 是核心价值，但必须建立在设备操作面和基础平台边界已经稳定之上

#### P4. 资产与低频配置

- 任务资产
- 系统资产
- 导入与清洗
- 偏好配置

#### P5. 计费与后台治理

- 积分账户
- 扣费规则
- 账单流水
- 风控
- 审计

#### P6. 插件市场

- 商店浏览
- 插件拥有
- 上传与审核
- 交易与奖励

#### P7. 在线更新与外部集成

- 更新任务
- 灰度发布
- Open API / Webhook

### 3. 这套优先级是否符合商业落地

结论：

- 是符合的

理由：

- 先解决“谁在用、属于谁、能做什么”
- 再解决“核心业务价值是否顺畅”
- 再解决“如何收费、如何治理、如何扩展交易”

这比一开始就先做插件市场或复杂财务中心更稳。

### 4. 商业落地相关功能是否已经足够详细

结论：

- `已经足够支撑规划和分期`
- `但还不足以直接进入全部实现`

更准确地说：

- 结构层已经足够详细
- 执行规则层还有少量需要你最后拍板的点

### 5. 当前已经足够详细的部分

以下内容我判断已经足够详细，可以进入任务分解：

- Workspace / Tenant 基本方向
- 角色与权限的总体模型
- 管理后台分区
- 积分扣费总体模式
- 普通任务与 AI 任务差异化扣费
- 插件商店上传 / 下载 / 奖励主逻辑
- 在线更新应作为平台运维能力存在

### 6. 当前还不够细、但只剩少量规则待定的部分

以下属于“方向已定，但细则还需拍板”：

- 注册策略
  - 是否开放注册
  - 是否邀请码 / 审核制
- Workspace 策略
  - 一个用户可加入多个 workspace 到什么程度
- 套餐与配额细则
  - 免费版和付费版边界
- 扣费规则细则
  - 哪些步骤计费
  - 中断 / 失败 / 回滚如何计费
- 插件市场规则细则
  - 平台是否抽成
  - 上传者奖励比例
  - 官方插件是否免费
- 在线更新策略
  - 谁能触发
  - 是否允许工作空间级灰度

### 7. 对执行的实际影响

这意味着：

- 现在已经可以开始拆实现阶段和技术任务
- 但在正式进入计费、市场、套餐实现前，仍需要补一轮“业务规则参数表”

### 8. 下一份最值得补的文档

为了把商业化部分真正推进到可实现，下一份最值得补的是：

- `Business Rules Matrix v1`

建议覆盖：

- 注册与登录规则
- workspace 与成员规则
- 套餐与配额规则
- 扣费规则
- 奖励规则
- 审核规则
- 更新触发规则

### 9. 最终判断

如果直接回答你的问题：

- 任务优先级我现在是清楚的，而且已经能按阶段排序
- 商业落地功能新增已经足够详细到“可以进入任务规划”
- 但如果要直接编码商业模块，还需要再补一份更参数化的业务规则矩阵

## Business Rules Matrix v1

本节用于把当前已确定的商业与平台能力，进一步压缩成“可执行规则矩阵草案”。

目的不是一次把所有参数都拍死，而是先把：

- 哪些规则必须存在
- 每类规则由谁管理
- 默认推荐值是什么
- 哪些点后续只需小修正

明确下来。

### A. 注册与登录规则

#### A1. 注册模式

当前建议默认采用：

- `管理员创建 + 邀请加入`
- 可保留“开放注册”能力，但默认关闭

推荐理由：

- 你这个系统不是纯 C 端产品
- 默认开放注册会过早引入风控和垃圾账号问题

#### A2. 登录模式

默认支持：

- 账号密码登录
- 后续可扩展短信 / 邮箱验证

第一阶段不强制要求：

- 第三方 OAuth
- 企业 SSO

#### A3. 密码与安全规则

建议至少支持：

- 重置密码
- 首次登录改密
- 登录失败限制
- 可选二次验证入口

### B. Workspace 与成员规则

#### B1. Workspace 数量规则

默认建议：

- 一个用户可加入多个 workspace
- 但同一时刻只操作一个 active workspace

#### B2. Workspace 创建规则

默认建议：

- 平台管理员可创建
- 工作空间 owner 可在有权限时创建
- 普通用户默认不可自助无限创建

#### B3. 成员加入规则

默认建议：

- 通过邀请加入
- 支持角色预设
- 支持加入后再调整角色

### C. 套餐与配额规则

#### C1. 套餐层建议

建议首版至少分：

- `trial`
- `basic`
- `pro`
- `enterprise`

#### C2. 套餐控制维度

建议控制：

- 成员数
- 设备数
- 并发执行能力
- AI 任务能力
- 插件市场能力
- 后台治理能力

#### C3. 默认业务判断

建议：

- `trial`
  - 低额度积分
  - 限设备数
  - 限 AI 能力
- `basic`
  - 可正常使用 operator 产品
- `pro`
  - 增强 AI、批量、资产、市场能力
- `enterprise`
  - 强权限、强治理、开放集成

### D. 执行计费规则

#### D1. 计费对象

当前建议确定为：

- 按执行步骤扣费

而不是：

- 按任务创建次数
- 按页面点击次数

#### D2. 任务分类

默认分两类：

- `standard_task`
- `ai_driven_task`

#### D3. 费率规则

默认建议：

- 两类任务有不同 step unit price
- 由后台规则可配置
- 每次扣费都记录规则快照

#### D4. 计费触发规则

当前建议：

- 只对真实进入执行链路的步骤计费
- 纯规划阶段不计费

#### D5. 中断 / 失败 / 回滚处理

当前默认建议：

- 已执行成功的步骤正常计费
- 因系统异常导致的明显无效步骤应允许回滚或补偿
- 人工取消不默认全额回退

说明：

- 这块后续仍需更细参数化，但主方向建议先定为“按已发生执行计费，而非按最终成功才计费”

### E. 积分充值与账单规则

#### E1. 充值对象

默认建议：

- 充值主体是 `Workspace`
- 不以个人用户零钱包为主模型

#### E2. 流水分类

至少包括：

- 充值
- 扣费
- 奖励
- 调整
- 回滚

#### E3. 财务约束

必须要求：

- 每条流水可追溯
- 有规则快照
- 可按周期对账

### F. 插件市场交易规则

#### F1. 下载计费

默认建议：

- 用户下载插件时扣 workspace 积分

#### F2. 上传奖励

默认建议：

- 他人下载后，上传者获得积分奖励

#### F3. 平台抽成

当前建议：

- 预留平台抽成能力
- 首版可先不做复杂比例分账
- 但账务模型必须预留

#### F4. 官方插件规则

默认建议：

- 官方插件可免费
- 也可设置特殊价格
- 官方插件与用户插件必须区分来源

#### F5. 蒸馏插件规则

默认建议：

- 蒸馏产物不能直接进入商店交易
- 必须先经过 submission + review

### G. 审核规则

#### G1. 需要审核的对象

默认建议以下内容必须进入审核链路：

- 插件上传
- 蒸馏产物转插件
- 高风险 app config candidate
- 高风险 branch learning 写入

#### G2. 可直接生效的对象

默认建议以下内容可以直写：

- workflow draft defaults
- account default branch
- 低风险文本类学习项

### H. 在线更新规则

#### H1. 触发主体

默认建议：

- 平台管理员可触发
- 工作空间管理员仅在授权情况下触发 workspace 范围更新

#### H2. 发布策略

默认建议支持：

- 全量
- 灰度
- 分 workspace 批次

#### H3. 风险约束

必须保留：

- update job
- 状态记录
- 失败记录
- 回滚记录

### I. 风控规则

#### I1. 扣费风控

建议至少支持：

- 每任务最大扣费预警
- 每日最大扣费预警
- 余额不足预警

#### I2. 市场风控

建议至少支持：

- 高频下载检测
- 刷奖励检测
- 插件异常下架

#### I3. 权限风控

建议至少支持：

- 敏感操作二次确认
- 管理员操作审计

### J. 审计规则

必须记录的操作建议包括：

- 权限变更
- 工作空间套餐调整
- 充值与积分调整
- 扣费规则调整
- 插件审核与上下架
- 系统更新与回滚

### K. 第一阶段默认参数策略

如果现在就进入实施，为了避免参数讨论过久，建议先采用以下默认策略：

- 注册：
  - 默认关闭开放注册，采用邀请制
- workspace：
  - 一个用户可加入多个 workspace
- 扣费：
  - 规划不计费，执行按步计费
- AI 任务：
  - AI 驱动任务单步价格高于普通任务
- 市场：
  - 下载扣积分，上传有奖励
- 蒸馏插件：
  - 必审后上架
- 更新：
  - 平台管理员可控，保留灰度能力

### L. 规则矩阵的使用方式

后续执行时建议这样使用本节：

1. 先按本节默认值落架构与对象模型
2. 对仍有争议的参数做最后微调
3. 不因个别参数未拍板而阻塞整体系统重构

结论：

- 到这一步，商业和平台层已经不只是“有想法”，而是已经具备可实施的规则草案。

## Security Readiness Addendum

这个问题必须单独回答：

- `已经考虑到了，但还没有被单独收口成完整安全方案`

更准确地说：

- 权限、审计、风控、插件审核、在线更新、计费可追溯这些安全相关能力，前面已经分散写进计划
- 但如果要进入实施，安全必须从“分散要求”升级成“显式安全架构约束”

结论：

- 安全已经进入规划范围
- 但仍需要作为一等约束单独收口

### 1. 当前已经纳入的安全相关内容

本计划里已经覆盖了这些安全方向：

- 登录注册与身份体系
- Workspace / Tenant 隔离
- 角色权限与 permission key
- 管理员后台分权
- 审计日志
- 计费与奖励流水可追溯
- 风控阈值
- 插件上传审核
- 在线更新任务记录与回滚

这说明：

- 当前不是完全没考虑安全
- 但还缺一套统一安全边界描述

### 2. 现在必须明确补上的安全域

如果要真正可商用，至少还需要把以下安全域明确写进实施范围：

#### A. Authentication Security

至少应包括：

- 密码安全存储
- 登录失败限制
- 会话过期与刷新
- 可选二次验证
- 设备 / IP 异常登录检测入口

#### B. Authorization Security

至少应包括：

- 服务端强制权限校验
- workspace 级数据隔离
- 敏感 API 二次权限判断
- 管理员与普通用户彻底分层

#### C. Billing Security

至少应包括：

- 积分扣费不可由前端决定
- 所有扣费规则保留快照
- 所有积分调整必须留痕
- 防止重复扣费 / 重放请求

#### D. Marketplace Security

至少应包括：

- 上传文件校验
- 插件包签名 / 完整性校验
- manifest / script 安全扫描
- 危险动作审查
- 举报 / 下架 / 冻结机制

#### E. Update Security

至少应包括：

- 更新包来源校验
- 版本签名 / 完整性校验
- 更新 job 审计
- 回滚能力

#### F. API And Integration Security

至少应包括：

- API token 管理
- Webhook 签名校验
- 速率限制
- 敏感接口防重放
- 管理接口更严格的访问边界

#### G. Data Security

至少应包括：

- secrets 不落前端
- 凭据分类存储
- 敏感字段脱敏展示
- 数据导出权限控制
- 备份与恢复策略

### 3. 本项目最敏感的安全面

按当前业务结构，最需要重点盯住的不是通用网站安全，而是这 6 类：

1. `多租户数据隔离`
2. `计费与积分防篡改`
3. `插件上传与分发安全`
4. `在线更新供应链安全`
5. `管理员高权限操作审计`
6. `设备控制与接管权限边界`

### 4. 默认安全原则

建议本次重构从一开始就遵守以下原则：

1. 前端永远不可信，权限和计费全部以后端为准。
2. 多租户数据读取必须显式带 workspace 边界。
3. 所有敏感变更都要审计。
4. 所有可上传、可安装、可更新的包都要做完整性校验。
5. 市场、计费、管理员能力一律不走弱权限路径。
6. 安全逻辑不能只写在 UI 可见性里，必须落到 API 和 service 层。

### 5. 对执行计划的实际影响

这意味着后续实施时，安全不应作为最后补丁，而应嵌入这些阶段：

- `Phase 1`
  - auth / workspace / permission 时就建立身份与隔离边界
- `Phase 5`
  - billing / admin 时建立审计与风控
- `Phase 6`
  - marketplace 时建立上传审核与分发安全
- `Phase 7`
  - updates / integrations 时建立签名、校验、回滚和 webhook 安全

### 6. 建议新增的安全交付物

为了避免后续遗漏，建议在正式进入实施前，再补一份：

- `Security Rules Matrix v1`

建议至少覆盖：

- 身份认证规则
- 权限校验规则
- 租户隔离规则
- 敏感操作审计规则
- 计费防篡改规则
- 插件上传与安装安全规则
- 更新包校验与回滚规则
- API token / webhook 安全规则

### 7. 最终判断

如果直接回答“安全是否考虑到了”：

- 回答是：`考虑到了，而且已经覆盖了一部分关键面`

但如果问“是否已经足够细到可以无风险开工”：

- 回答是：`还差最后一份显式安全规则矩阵`

所以安全现在不再是缺席项，而是：

- `已进入主计划`
- `需要单独收口`

## Security Rules Matrix v1

本节作为安全规则的首版定稿草案。

目标不是一次补完所有安全细节，而是确保后续实施时不会遗漏关键边界。

### A. 身份认证规则

#### A1. 凭据存储

必须要求：

- 密码只允许安全哈希存储
- 不允许明文存储密码
- 不允许前端持久化敏感凭据

#### A2. 登录保护

建议首版支持：

- 连续失败次数限制
- 短时锁定
- 异常登录日志

#### A3. 会话规则

建议支持：

- access token
- refresh token 或等价刷新机制
- 可主动失效
- workspace 切换后重新校验权限上下文

### B. 租户隔离规则

#### B1. 数据读取边界

必须要求：

- 所有 operator 数据查询都显式带 workspace 边界
- 不允许通过前端传参绕过 workspace 限制

#### B2. 数据写入边界

必须要求：

- 任务、资产、草稿、积分、插件拥有关系写入时校验 workspace 归属

#### B3. 后台越权边界

必须要求：

- 平台管理员与 workspace 管理员的可见范围明确区分

### C. 权限校验规则

#### C1. 页面守卫

可做：

- 改善体验
- 隐藏无权限入口

但不作为最终权限判断。

#### C2. API 权限

必须要求：

- 所有敏感 API 都做服务端权限校验
- 权限校验基于：
  - user identity
  - workspace membership
  - permission keys

#### C3. 高危操作二次校验

建议以下操作增加更严格校验：

- 积分调整
- 扣费规则调整
- 插件上架 / 下架
- 系统更新
- 权限提升

### D. 计费安全规则

#### D1. 扣费来源

必须要求：

- 扣费只由后端统一结算
- 前端不得提交最终扣费结果

#### D2. 幂等性

建议要求：

- 充值
- 扣费
- 奖励
- 回滚

都具备幂等处理能力，防止重复入账。

#### D3. 规则快照

必须要求：

- 每笔扣费和奖励都保留规则快照

#### D4. 调整审计

必须要求：

- 所有手工积分调整都记录管理员、理由、前后差额

### E. 插件市场安全规则

#### E1. 上传校验

必须要求：

- 文件类型校验
- 大小限制
- manifest 基本结构校验
- script 规则校验

#### E2. 安全扫描

建议首版至少支持：

- 危险动作黑名单
- 可疑配置检测
- 非法依赖或异常结构检测

#### E3. 发布门槛

必须要求：

- 用户上传插件必须经审核后才可 published
- 蒸馏产物转插件也必须经过 submission + review

#### E4. 下架与冻结

必须要求：

- 平台可快速下架风险插件
- 下架动作保留审计

### F. 在线更新安全规则

#### F1. 更新来源校验

必须要求：

- 更新包来源可信
- 版本信息可校验

#### F2. 完整性校验

必须要求：

- 更新包具备完整性校验能力

#### F3. 更新执行留痕

必须要求：

- 每次更新都有 update job
- 每次更新都有状态、日志、失败记录

#### F4. 回滚能力

建议要求：

- 首版即支持失败后回滚路径

### G. API / Webhook 安全规则

#### G1. API Token

建议支持：

- token 创建
- token 撤销
- token 权限范围限制

#### G2. Webhook

必须要求：

- 签名校验
- 重试策略
- 防重放策略

#### G3. 速率限制

建议至少作用于：

- 登录接口
- 充值与积分接口
- 插件上传接口
- 管理后台敏感接口

### H. 数据安全规则

#### H1. 敏感字段管理

建议分类：

- 密码 / token / 2FA secret
- 计费信息
- 管理员操作记录
- 导入原始文件

#### H2. 展示脱敏

必须要求：

- 前端默认脱敏展示敏感字段
- 只有有权限用户才可查看完整值

#### H3. 导出控制

建议要求：

- 账单导出
- 审计导出
- 资产导出

都受权限控制并保留操作记录

### I. 接管与设备控制安全规则

#### I1. 接管权限

必须要求：

- 只有具备相应权限的成员才能接管运行任务

#### I2. 控制链路留痕

必须要求：

- 接管请求
- 人工操作
- 关键控制动作

都保留 trace / event / audit 记录

#### I3. 高风险控制保护

建议：

- 对高风险系统级控制加确认和权限门槛

### J. 管理员安全规则

#### J1. 管理后台隔离

必须要求：

- 管理后台入口与普通工作面明确隔离

#### J2. 敏感操作日志

必须要求：

- 所有管理员敏感操作留痕

#### J3. 支持型权限分离

建议：

- `support`
- `auditor`
- `finance`
- `admin`

不要都合并为一种超级管理员

### K. 第一阶段安全默认策略

如果现在就进入实施，建议先采用以下安全默认值：

- 开放注册默认关闭
- 邀请制加入 workspace
- 所有敏感 API 服务端鉴权
- 计费全部后端结算
- 插件上传默认审核
- 更新操作默认管理员权限
- 审计日志默认开启

### L. 安全矩阵的实施方式

建议执行时按以下方式落地：

1. `Phase 1`
   - 身份、workspace、权限边界先落地
2. `Phase 5`
   - 计费、审计、风控一起落地
3. `Phase 6`
   - 插件商店安全与审核一起落地
4. `Phase 7`
   - 更新与对外集成安全一起落地

结论：

- 到这里，安全已经不再是“补充考虑”，而是已具备首版可执行规则矩阵。

## Default Decisions For Final Review

为尽快进入实施，本节将前面剩余开放问题压缩成“默认定稿值”。

若后续你未明确推翻，执行计划默认按以下判断推进：

### 1. 设备作战台异常视图

默认决定：

- 不单独做一级“异常设备”页面
- 保留在设备作战台的筛选与快捷视图中

### 2. AI工作台默认进入方式

默认决定：

- 首次进入默认 `任务设计 / 快速开始`
- 熟练用户允许记忆最近一次进入模式

### 3. 历史数据 / 成功率 / 错误趋势位置

默认决定：

- 不放在高频主工作面
- 降级为资产中心或低频洞察层的二级内容

### 4. 业务策略文本位置

默认决定：

- 归属 `任务资产`
- 在总表可管理
- 在具体插件变量上下文可引用和编辑

### 5. 批量下发是否支持方案

默认决定：

- 首版不做完整方案中心
- 支持最近一次配置复用

### 6. 单设备详情中的 AI 快速发起

默认决定：

- 保留
- 但只作为快速发起入口
- 深度设计与沉淀统一回到 `AI工作台`

### 7. 系统资产入口位置

默认决定：

- 主入口放在 `资产中心 / 系统资产`
- 设备作战台只保留必要快捷入口，不作为主归属

### 8. AI工作台结构

默认决定：

- 明确拆成：
  - `任务设计`
  - `会话与草稿`
  - `学习沉淀`

结论：

- 到当前为止，前面残留的开放问题已经基本都具备默认定稿值
- 后续若有修正，应视为“微调”，不再影响整体架构骨架

## Execution Plan v1

本节作为当前计划的执行版草案。

### Phase 0. Blueprint Freeze

目标：

- 冻结对象树、页面树、模块树、规则矩阵

交付物：

- 本文档定稿版
- `Development Rules Doc v1`

### Phase 1. Platform Foundation

目标：

- 建立身份、workspace、角色权限、基础管理员壳层

交付物：

- 登录 / 注册
- workspace 切换
- 基础角色模型
- 权限守卫
- 基础后台入口

### Phase 2. Canonical Contract Foundation

目标：

- 在后端建立 operator / platform / marketplace 的 canonical object contract

交付物：

- operator contract 聚合层
- platform contract 聚合层
- marketplace contract 聚合层
- 前端 mapper/adapters 基础层

### Phase 3. Operator Core

目标：

- 完成最高频 operator 主工作面

交付物：

- 设备作战台
- 单设备详情
- 接管页 / 面板
- 批量下发页

### Phase 4. AI Core

目标：

- 重构 AI 工作台并收口草稿生命周期

交付物：

- `AI工作台 / 任务设计`
- `AI工作台 / 会话与草稿`
- `AI工作台 / 学习沉淀`

### Phase 5. Asset Core

目标：

- 重构任务资产、系统资产、导入清洗

交付物：

- `资产中心 / 任务资产`
- `资产中心 / 系统资产`
- `资产中心 / 导入与清洗`

### Phase 6. Billing And Admin

目标：

- 建立积分、规则、账务、审计、风控、后台治理

交付物：

- credit account
- transactions
- billing rules
- audit logs
- admin console base

### Phase 7. Marketplace

目标：

- 上线插件商店主链路

交付物：

- 商店浏览
- 插件详情
- 我的插件
- 上传与 submission
- 审核与发布
- 下载与奖励

### Phase 8. Updates And Integrations

目标：

- 建立在线更新、灰度发布、外部集成基础

交付物：

- update jobs
- rollout / rollback
- API token
- webhook

## Implementation Workstreams v1

为避免实施期混乱，建议按 5 条工作流并行但分阶段推进：

### 1. Product And IA

- 页面树最终修正
- 页面职责落细
- 文案与导航语义统一

### 2. Backend Contracts

- canonical contract
- domain services
- compatibility boundary cleanup

### 3. Frontend Rebuild

- 新模块树
- 页面重写
- mapper / query / state layer

### 4. Platform And Governance

- auth
- workspace
- billing
- admin
- audit

### 5. Marketplace And Distribution

- plugin submission
- review
- pricing
- reward
- update / integration

## Definition Of Planning Done

本次“计划阶段完成”的判断标准建议定义为：

1. 页面树已冻结
2. 产品对象树已冻结
3. canonical contract 草案已冻结
4. 平台层与市场层模型已冻结
5. 规则矩阵已具备首版默认值
6. 实施阶段顺序已明确

当以上 6 条满足时，即可认为：

- 计划阶段完成
- 可以进入正式开发执行

## Final Planning Judgment

当前判断：

- 本文档已经足以作为正式执行计划的前置蓝图
- 后续只需要做小幅修正，不再需要推翻主结构
- 下一步应从“继续讨论”切换为“生成开发任务并开始实施”

建议后续流程：

1. 你做最后一轮局部修正
2. 我把本文档压缩整理为执行版
3. 生成任务计划与实施顺序
4. 开始真正编码重构

## Task Breakdown v1

本节把执行计划进一步拆成更接近实际开发排期的任务包。

原则：

- 每个任务包都应有明确产出
- 每个任务包尽量围绕一个主对象域
- 避免“前端改一点 + 后端改一点 + 计费改一点”这种混杂包

### Track 0. Blueprint And Rules

#### T0-1 计划文档最终冻结

产出：

- 页面树最终版
- 对象树最终版
- 执行阶段最终版

#### T0-2 开发约束文档

产出：

- 前端目录约束
- canonical type 约束
- mapper 约束
- route / service / domain 约束

#### T0-3 安全与业务规则文档

产出：

- Business Rules Matrix 最终版
- Security Rules Matrix 最终版

### Track 1. Platform Foundation

#### T1-1 身份与会话

范围：

- 登录
- 注册
- 密码重置
- 基础会话机制

#### T1-2 Workspace / Tenant 基础

范围：

- workspace 模型
- active workspace 切换
- workspace membership

#### T1-3 角色与权限基础

范围：

- workspace roles
- platform roles
- permission keys
- 基础 API 权限守卫

#### T1-4 平台壳层

范围：

- auth shell
- workspace shell
- admin shell

### Track 2. Canonical Contracts

#### T2-1 Operator Contracts

范围：

- device summary
- device detail
- takeover session
- batch dispatch session
- task draft design
- workflow draft
- run asset
- task asset
- system asset

#### T2-2 Platform Contracts

范围：

- workspace
- member
- billing
- audit
- update jobs

#### T2-3 Marketplace Contracts

范围：

- plugin package
- plugin release
- plugin ownership
- plugin submission
- plugin review

#### T2-4 Mapper / Adapter Layer

范围：

- 新前端统一 mapper
- 旧接口兼容边界

### Track 3. Operator UI Core

#### T3-1 设备作战台

范围：

- 设备列表
- 状态筛选
- 多选逻辑
- 快捷操作

#### T3-2 单设备详情

范围：

- 当前状态
- 当前任务
- 快速 AI
- 异常处理

#### T3-3 接管页 / 面板

范围：

- takeover session
- 轻控制
- 声明阶段显示

#### T3-4 批量下发页

范围：

- 批量会话
- 最近配置复用
- 资源校验
- 提交结果

### Track 4. AI Core

#### T4-1 AI工作台 / 任务设计

范围：

- 目标与资源
- goal 与约束
- planner result
- 确认与提交

#### T4-2 AI工作台 / 会话与草稿

范围：

- workflow draft list
- draft detail
- continue edit
- continue execution

#### T4-3 AI工作台 / 学习沉淀

范围：

- run assets
- save candidates
- review flows
- distill results

### Track 5. Assets

#### T5-1 任务资产

范围：

- accounts
- 2FA
- app/task imports
- plugin variables
- strategy texts

#### T5-2 系统资产

范围：

- socks proxies
- device environment assets
- future model params
- network scan outputs

#### T5-3 导入与清洗

范围：

- 文件导入入口
- 格式化
- 清洗预览
- 错误反馈

### Track 6. Billing And Admin

#### T6-1 积分账户与流水

范围：

- credit account
- transactions
- recharge records

#### T6-2 扣费规则

范围：

- standard task rules
- ai task rules
- rule versions

#### T6-3 审计与风控

范围：

- audit logs
- risk thresholds
- alerts / freezes

#### T6-4 后台管理

范围：

- workspace management
- user / role management
- billing management
- plugin governance
- updates

### Track 7. Marketplace

#### T7-1 插件商店浏览

范围：

- marketplace home
- plugin detail
- search / category

#### T7-2 我的插件与拥有关系

范围：

- owned plugins
- install / update
- version view

#### T7-3 上传与审核

范围：

- manual submission
- distilled submission
- review queue

#### T7-4 交易与奖励

范围：

- purchase
- reward transactions
- pricing / reward rules

### Track 8. Updates And Integrations

#### T8-1 在线更新

范围：

- update jobs
- rollout / rollback
- audit trail

#### T8-2 对外集成

范围：

- API token
- webhook
- callback security

## Milestone Acceptance v1

为了避免开发过程中“功能看起来做了，但系统并没真正收口”，建议每个阶段都有明确验收标准。

### M1. Platform Foundation Accepted

满足条件：

- 用户可登录进入 active workspace
- 基础角色权限可用
- admin shell 可访问
- workspace 数据边界已生效

### M2. Operator Core Accepted

满足条件：

- 设备作战台可替代旧主工作面
- 单设备详情可替代旧设备深页
- 接管链路可用
- 批量下发主路径可用

### M3. AI Core Accepted

满足条件：

- AI工作台三层结构可用
- planner -> submit -> draft -> run asset -> save/distill 主链路可用
- 单设备快速 AI 能与 AI 工作台正确分工

### M4. Assets Accepted

满足条件：

- 任务资产与系统资产明确分离
- 导入与清洗链路可用

### M5. Billing/Admin Accepted

满足条件：

- 积分账户、扣费规则、流水、审计可用
- 管理后台具备基础治理能力

### M6. Marketplace Accepted

满足条件：

- 插件浏览、上传、审核、下载、奖励主链路可用

### M7. Updates/Integrations Accepted

满足条件：

- 在线更新 job 可追踪
- rollback 可用
- token / webhook 基础可用

## Risk Register v1

为了减少实施期返工，建议提前把最可能的风险写清楚。

### R1. 产品对象未完全冻结就开始大规模编码

后果：

- 页面反复重写
- contract 反复变形

控制方式：

- 先冻结本计划核心结构

### R2. 新前端继续消费旧兼容字段

后果：

- 旧结构被带入新架构

控制方式：

- 新前端只接 canonical contract / mapper

### R3. 平台层功能插入过早，拖慢 operator 主价值面

后果：

- 主业务面迟迟不能落地

控制方式：

- 严格按阶段推进，优先 operator core

### R4. 计费和权限后补，导致后面大面积返工

后果：

- 归属关系和审计链路全要重修

控制方式：

- Platform Foundation 必须前置

### R5. 插件市场过早追求复杂交易机制

后果：

- 治理复杂度暴涨

控制方式：

- 先做 submission / review / basic purchase / reward

### R6. 安全规则停留在文档，不进入实现边界

后果：

- 商业化能力存在实质安全漏洞

控制方式：

- 每阶段实现都绑定对应安全矩阵条目

## Immediate Next Actions

如果从现在开始进入执行准备，建议下一步就是：

1. 基于本文档做最后一轮局部修正
2. 从本文档派生正式任务清单
3. 先实施 `Phase 1 + Phase 2`
4. 再进入 operator core 重构

## Execution Tasks v1

本节作为当前计划的正式实施任务清单草案。

执行原则：

- 先打基础边界，再做高频主工作面
- 新前端只接新 contract
- 每完成一组新主路径，就尽快淘汰对应旧入口

### Wave 0. Planning Freeze

#### X0-1 冻结计划文档

目标：

- 将本文档视为当前执行蓝图

产出：

- 当前计划定稿

#### X0-2 产出开发约束文档

目标：

- 将文档中的开发约束转成长期规则文档

产出：

- `Development Rules Doc v1`

#### X0-3 产出实施任务看板

目标：

- 将以下任务清单转成实际执行任务

产出：

- 任务列表 / issue 列表 / 阶段看板

### Wave 1. Platform Foundation

#### X1-1 建立 auth 基础

范围：

- 登录
- 注册
- 密码重置
- 基础 session/token 机制

#### X1-2 建立 workspace 基础

范围：

- workspace model
- active workspace
- workspace membership

#### X1-3 建立角色与权限基础

范围：

- platform roles
- workspace roles
- permission keys
- 基础 API 权限守卫

#### X1-4 建立 admin / platform shell

范围：

- 管理后台入口壳层
- 普通工作面与平台工作面隔离

### Wave 2. Canonical Contracts

#### X2-1 建立 operator canonical contracts

范围：

- device summary
- device detail
- takeover session
- batch dispatch session
- task draft design
- workflow draft
- run asset
- task/system assets

#### X2-2 建立 platform canonical contracts

范围：

- workspace
- member
- billing
- audit
- updates

#### X2-3 建立 marketplace canonical contracts

范围：

- plugin package
- plugin release
- plugin ownership
- plugin submission
- plugin review

#### X2-4 建立前端 mapper / adapter 层

范围：

- raw API -> canonical types
- query keys
- adapter boundary

### Wave 3. Frontend Foundation

#### X3-1 创建新前端模块树

范围：

- `app`
- `pages`
- `features`
- `entities`
- `shared`

#### X3-2 创建全局基础设施

范围：

- router
- auth provider
- workspace context
- query client
- state stores
- UI shell

#### X3-3 接入 permission / route guard

范围：

- 页面访问边界
- 平台层和 operator 层路由隔离

### Wave 4. Operator Core

#### X4-1 重构设备作战台

范围：

- 设备列表
- 筛选
- 多选
- 快捷动作

#### X4-2 重构单设备详情

范围：

- 当前状态
- 当前任务
- 快速 AI
- 异常处理

#### X4-3 重构接管页 / 面板

范围：

- takeover session
- 轻控制
- 当前声明阶段

#### X4-4 重构批量下发页

范围：

- 批量会话
- 最近配置复用
- 资源校验
- 提交与回流

### Wave 5. AI Core

#### X5-1 重构 AI 工作台 / 任务设计

范围：

- 目标与资源
- goal / 约束
- planner result
- 确认与提交

#### X5-2 重构 AI 工作台 / 会话与草稿

范围：

- 草稿列表
- 草稿详情
- continue edit
- continue execution

#### X5-3 重构 AI 工作台 / 学习沉淀

范围：

- run assets
- save candidates
- review candidates
- distill results

### Wave 6. Asset Core

#### X6-1 重构任务资产

范围：

- accounts
- 2FA
- app/task imports
- plugin variables
- strategy texts

#### X6-2 重构系统资产

范围：

- proxies
- device env assets
- network scan
- future model params

#### X6-3 建立统一导入与清洗链路

范围：

- 文件导入
- 预解析
- 清洗预览
- 落库前确认

### Wave 7. Billing And Admin

#### X7-1 建立积分账户与流水

范围：

- workspace credit account
- recharge
- transactions

#### X7-2 建立扣费与奖励规则

范围：

- standard task pricing
- ai task pricing
- marketplace reward rules

#### X7-3 建立审计与风控

范围：

- audit logs
- risk thresholds
- alerts / freeze controls

#### X7-4 重构管理员后台

范围：

- workspace management
- user/role management
- billing management
- governance pages

### Wave 8. Marketplace

#### X8-1 建立插件商店浏览与详情

范围：

- marketplace home
- plugin detail
- category/search

#### X8-2 建立我的插件与拥有关系

范围：

- owned plugins
- versions
- install/update

#### X8-3 建立上传与审核

范围：

- manual upload
- distilled upload
- submission queue
- review actions

#### X8-4 建立交易与奖励链路

范围：

- purchase
- reward transaction
- pricing / reward snapshot

### Wave 9. Updates And Integrations

#### X9-1 建立在线更新链路

范围：

- update jobs
- rollout
- rollback

#### X9-2 建立 API token / webhook

范围：

- token issuance
- token revoke
- webhook signing / retry

## Default Start Point

若无额外变更，实际实施应默认从这里开始：

1. `X0-1` 冻结计划文档
2. `X0-2` 产出开发约束文档
3. `X1-1 ~ X1-4` 平台基础
4. `X2-1 ~ X2-4` canonical contracts
5. `X3-1 ~ X3-3` 新前端基础设施
6. 再进入 `X4` operator core

## Status Upgrade

到当前为止，本计划应视为：

- `discussion complete`
- `structure frozen by default`
- `ready for execution task conversion`
