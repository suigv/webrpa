# AI 对话交互重构设计

> 状态：设计阶段 | 最后更新：2026-03-22

## 设计原则

> 首次任务通过自然语言交互式下发，历史任务一键重放减少交互负担。
> 用户永远有控制权，AI 卡住时可接管，接管操作同样作为蒸馏依据。
> 系统提示词分层管理，普通用户不需要了解 system prompt 概念。

---

## 一、三种模式统一入口

```
[AI 对话入口]
    ├── 模式1：新任务（交互式对话）       ← 首次，LLM 引导收集参数
    ├── 模式2：历史任务（一键重放）       ← 再次，零交互或最小交互
    └── 模式3：蒸馏插件（表单提交）       ← 现有插件逻辑，保持不变
```

---

## 二、模式1：首次任务 — 交互式对话

### 流程

1. 用户输入自然语言 goal（如「帮我登录 X」）
2. 前端调用轻量 LLM（`ai_dialog_planner`）识别意图、推断缺失参数并追问用户
   - 账号可从账号池列表选择，无需手填
3. 构建 `agent_executor` payload，自动填入 `expected_state_ids`、`allowed_actions` 等
4. 下发任务，进入执行状态（见第四节）
5. 执行完成后询问：「是否保存为快捷任务？」→ 写入历史任务

### 关键设计

- 用户不接触 `expected_state_ids`、`state_profile_id` 等技术概念
- 无 app yaml 时自动用探索模式（`expected_state_ids: ["unknown"]`），AI 靠 VLM 视觉探索
- 对话历史和推断出的参数保存为「任务模板」供模式2使用

---

## 三、模式2：历史任务 — 一键重放

执行过的任务自动记录为快捷任务卡片：

```
┌─────────────────────────────┐
│ 登录 X                      │
│ 上次：2小时前 | 成功          │
│ 账号：xxx@gmail.com          │
│ [立即执行]  [编辑后执行]      │
└─────────────────────────────┘
```

- **立即执行**：直接重放上次完整 payload，零交互
- **编辑后执行**：展开对话，只修改变化的参数（如换账号）

### 账号策略

重放时上次账号可能已 `in_progress` 或 `banned`，策略：
- 默认从账号池重新取同 app_id 的可用账号
- 若上次账号仍 `ready`，优先使用（保持操作连续性）
- 若账号池为空，提示用户补充账号后再执行

---

## 四、执行中状态提示

当前日志流太技术化，重构为明显的执行状态浮层：

```
┌─────────────────────────────────────┐
│  🤖 AI 正在执行：登录 X              │
│  ━━━━━━━━━━━━━━━ 步骤 3/∞           │
│                                      │
│  ✅ 打开 X App                       │
│  ✅ 识别到登录页                      │
│  ⏳ 正在输入账号...                   │
│                                      │
│  已执行 23 步不用 `max_steps` 限制，靠停滞检测 + 用户干预
- **停滞检测触发时**：不直接失败，暂停并弹出干预选项
- 步骤描述用 `label` 字段（人话），不用 action 名
- 浮层明显（屏幕中央或侧边），不是底部技术日志
- 消费现有 WebSocket `task.action_result` 事件

---

## 五、用户接管机制

### 接管流程

1. AI 停滞 → 系统通知用户「AI 卡住了」
2. 用户点击「我来接管」→ AI 暂停，切到手动控制模式（截图+点击/滑动）
3. 用户手动操作解决问题
4. 用户点击「交还给 AI」→ agent_executor 从当前 UI 状态继续执行

### 接管操作作为蒸馏依据

**核心设计：统一 Trace 记录层**

不管 AI 执行还是用户接管，所有操作写入同一个 `ModelTraceStore`，来源标记不同：

```
AI 操作  → trace_record(source="ai",    action="ui.click", ...)
用户操作 → trace_record(source="human", action="ui.click", ...)
```

- 前端接管模式的操作通过现有 `/api/devices/{id}/{cloud}/tap` 等接口执行
- 这些 API 新增可选参数 `trace_context: {task_id, run_id}`，传入时写入 trace record 并标记 `human_guided: true`
- **关键**：前端接管模式必须持有当前任务的 `task_id` 和 `run_id`，才能将操作关联到正确蒸馏上下文

**价值**：用户接管解决的「AI 卡住」场景 = app yaml 里缺失的边缘状态处理。这是最高质量的蒸馏数据，沉淀后 AI 下次遇到相同情况不再卡住。

### 实现要点

- [ ] `api/routes/devices.py` tap/swipe/key_press 等接口：可选写入 trace record
- [ ] 接管模式前端：操作时携带 `trace_context`（task_id、run_id）
- [ ] agent_executor 暂停/恢复 API
- [ ] trace record 新增 `source` 字段和 `human_guided` 标记

---

## 六、系统提示词分层管理

当前前端有 `unitAiSystemPrompt` 输入框，用户手填——这是错误设计。
 | `config/apps/{app}.yaml` 的 `agent_hint` 字段 | ❌ | App 特有提示（界面语言、常见弹窗、按钮文字）|
| 任务层 | `ai_dialog_planner` 根据 goal 生成 | ❌ | 当前任务目标、成功标志 |
| 用户层 | 用户手填（高级选项，默认隐藏）| ✅ | 专家模式自定义补充 |

### app yaml 新增 `agent_hint` 字段

```yaml
# config/apps/x.yaml
agent_hint: |
  界面语言：中文
  登录按钮：「ログイン」或「登录」
  主页特征：底部导航栏有「主页」选项
  常见弹窗需关闭：「许可」「今はしない」
```

蒸馏时从成功执行记录中提取这些提示并沉淀到 app yaml，逐步完善。

---

## 七、参数简化原则

### 7.1 allowed_actions — 框架自动管理，不暴露用户

当前前端有 `allowed_actions` 复选框，用户需要勾选 `ui.click`、`ai.locate_point` 等，这是错误的设计。

**正确设计**：
- 框架内置所有注册 skill action 为候选集
- `config/apps/{app}.yaml` 可声明 `allowed_actions` 字段限制该 App 下可用动作
- 蒸馏时自动从成功执行记录中提取实际用到的 action 写入 app yaml
- **用户完全不接触此参数**，前端移除该复选框组

### 7.2 LLM / VLM — 必选能力，自动 fallback，不需要用户选择

当前前端有「使用 VLM」开关，让用户手动触发 fallback，设计不合理。

**正确设计**：
- **LLM**：必选，AI 规划决策核心，始终启用
- **VLM**：系统自动 fallback，当 XML 结构化状态检测失败（`unknown`）时自动切换视觉理解
- 观察策略由框架 `_observation_modality` 逻辑自动决定
- **前端移除「使用 VLM」开关**

### 7.3 前端 AI 对话界面最终保留的用户参数

| 参数 | 展示形式 | 说明 |
|------|----------|------|
| goal（任务描述） | 文本输入 | 必填，自然语言 |
| 账号选择 | 下拉（按 app 过滤）| 可选，从账号池选 |
| 高级：用户自定义提示 | 折叠区域 | 专家模式，默认隐藏 |

其他所有技术参数（`expected_state_ids`、`allowed_actions`、`max_steps`、`stagnant_limit`、VLM 开关）均由框架自动处理，不暴露给普通用户。

---

## 八、实现任务计划

### Phase 0：移除不合理参数（前置清理）
- [ ] 0.1 前端移除 `allowed_actions` 复选框组
- [ ] 0.2 前端移除「使用 VLM」开关
- [ ] 0.3 前端移除 `unitAiSystemPrompt` 顶层输入框（降级为高级选项折叠区域）
- [ ] 0.4 前端移除 `unitAiState` 状态复选框组（由框架推断）
- [ ] 0.5 前端移除 `max_steps`、`stagnant_limit` 显式输入（保留为高级选项）

### Phase 1：执行状态浮层（最高价值，独立可交付）
- [ ] 1.1 前端新增 AI 执行浮层组件，消费 WebSocket `task.action_result` 事件
- [ ] 1.2 浮层展示：步骤序号、label（人话描述）、成功/失败/进行中状态
- [ ] 1.3 停滞检测触发时弹出干预选项（继续等待/我来接管/放弃）
- [ ] 1.4 取消按钮调用现有取消任务 API

### Phase 2：交互式对话下发
- [ ] 2.1 新增 `ai_dialog_planner` 轻量 LLM 调用：意图识别 + 参数推断
  - 使用轻量模型（Haiku 级别），控制调用成本，不用 agent_executor 同款重模型
- [ ] 2.2 `expected_state_ids` 从 app yaml states 自动推断，无 yaml 时用 `["unknown"]`
- [ ] 2.3 对话式账号选择（从账号池列表，按 app_id 过滤）
- [ ] 2.4 `allowed_actions` 从 app yaml 读取，无 yaml 时用框架全集
- [ ] 2.5 任务完成后询问是否保存为快捷任务

### Phase 3：历史任务快捷重放
- [ ] 3.1 `workflow_drafts` 新增 `source: ai_dialog` 标记
- [ ] 3.2 `GET /api/ai_dialog/history` 接口
- [ ] 3.3 前端历史任务卡片（按 App 分组，一键执行/编辑执行）

### Phase 4：用户接管与统一 Trace
- [ ] 4.1 `ModelTraceStore` trace record 新增 `source`（`ai`/`human`）和 `human_guided` 字段
- [ ] 4.2 `api/routes/devices.py` tap/swipe/key_press 接口支持可选 `trace_context` 参数，传入时写入 trace record
- [ ] 4.3 前端接管模式持有当前 `task_id` 和 `run_id`，操作时透传
- [ ] 4.4 agent_executor 暂停/恢复 API（接管时暂停，交还时从当前 UI 状态重新观察继续）
- [ ] 4.5 蒸馏器不过滤 `source`，`human_guided` 步骤在蒸馏报告中标注

### Phase 5：系统提示词分层
- [ ] 5.1 app yaml 新增 `agent_hint` 字段
- [ ] 5.2 agent_executor 合并各层 system prompt
- [ ] 5.3 蒸馏时从执行记录提取 agent_hint 沉淀到 app yaml
- [ ] 5.4 前端移除顶层 system prompt 输入框，降级为高级选项
