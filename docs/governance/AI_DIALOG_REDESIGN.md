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
2. 前端调用轻量 LLM（`ai_di）并追问用户
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
- **编辑后执行**：展开对话，只修改变化分组展示

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
- 这些 API uided: true`

**价值**：用户接管解决的「AI 卡住」场景 = app yaml 里缺失的边缘状态处理。这是最高质量的蒸馏数据，沉淀后 AI 下次遇到相同情况不再卡住。

### 实现要点

- [ ] `api/routes/devices.py` tap/swipe/key_press 等接口：可选写入 trace record
- [ ] 接管模式前端：操作时携带 `trace_context`（task_id、run_id）
- [ ] agent_executor 暂停/恢复 API
- [ ] trace record 新增 `source` 字段和 `human_guided` 标记

---

## 六、系统提示词分层管理

当前前端有 `unitAiSystemPrompt` 输入框，用户手填，层 | `config/apps/{app}.yaml` 的 `agent_hint` 字段 | ❌ | App 特有提示（界面语言、常见弹窗、按钮文字）|
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

## 七、实现任务计划

### Phase 1：执行状态浮层（最高价值，独立可交付）
- [ ] 1.1 前端新增 AI 执行浮层组件，消费 WebSocket `task.action_result` 事件
- [ ] 1.ner` 轻量 LLM 调用：意图识别 + 参数推断
- [ ] 2.2 `expected_state_ids` 从 app yaml states 自动推断
- [ ] 2.3 无 app yaml 时自动使用探索模式
- [ ] 2.4 对话式账号选择（从账号池列表，按 app_id 过滤）

### Phase 3：历史任务快捷重放
- [ ] 3.1 `workflow_drafts` 新增 `source: ai_dialog` 标记
- [ ] 3.2 `GET /api/ai_dialog/history` 接口
- [ ] 3.3 前端历史任务卡片（按 App 分组，一键执行/编辑执行）

### Phase 4：用户接管与统一 Trace
- [ ] 4.1 `ModelTraceStore` 新增 `source` Phase 5：系统提示词分层
- [ ] 5.1 app yaml 新增 `agent_hint` 字段
- [ ] 5.2 agent_executor 合并各层 system prompt
- [ ] 5.3 蒸馏时从执行记录提取 agent_hint 沉淀到 app yaml
- [ ] 5.4 前端移除顶层 system prompt 输入框，降级为高级选项
