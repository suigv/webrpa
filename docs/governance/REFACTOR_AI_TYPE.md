# Refactor: 移除 ai_type 系统级字段

## 问题背景

`ai_type`（如 `volc`、`part_time`）是业务插件的运营角色参数，代表不同的账号策略（交友/兼职等）。当前它被错误地提升到系统基础设施层，造成架构污染。

## 当前错误设计

`ai_type` 渗透到以下系统层位置（不应该存在的地方）：

| 文件 | 问题 |
|------|------|
| `models/task.py` | `TaskRequest.ai_type: str = \"default\"` — API 入参字段 |
| `models/device.py` | `Device.ai_type: str` — 设备模型携带运营角色 |
| `core/task_store.py` | `ai_type TEXT NOT NULL` — 数据库字段 |
| `core/task_control.py` | `ai_type` 在任务调度链路传递 |
| `core/device_manager.py` | `device.ai_type` — 设备绑定运营角色 |
| `models/config.py` | `DEFAULT_DEFAULT_AI = \"volc\"` — 代码级硬编码 |

## 根本原因

设计时将「设备运营角色」概念绑定到了基础设施层，认为每台设备对应固定的运营策略。这导致：

1. **语义泄漏**：`volc`/`part_time` 这类业务概念进入了 Task API、数据库 schema、设备模型
2. **硬编码依赖**：新增运营类型需要同时改代码、schema、插件
3. **违反插件自治**：不同插件的 `ai_type` 语义可能不同，系统层不应知晓
4. **调度灵活性丧失**：设备与运营角色强绑定，无法按任务动态调度

## 正确架构

`ai_type` 应该是插件 payload 的普通参数：

- **系统层**：只知道 `payload: dict`，完全不感知 `ai_type`
- **插件层**：在 `manifest.yaml` 声明 `ai_type` input，在 `script.yaml` 消费 `${payload.ai_type}`
- **配置层**：`config/apps/x.yaml`、`config/strategies/*.yaml` 按 `ai_type` 组织策略数据（保持不变，这是正确的）

## 影响范围评估

### 必须修改
- `models/task.py`：移除 `TaskRequest.ai_type` 字段，`ai_type` 应通过 `payload` 传递
- `models/device.py`：移除 `Device.ai_type` 字段
- `core/task_store.py`：移除 `ai_type` 数据库列（需要 migration）
- `core/task_control.py`：移除 `ai_type` 参数传递链路
- `core/device_manager.py`：移除 `device.ai_type` 及相关逻辑
- `models/config.py`：移除 `DEFAULT_DEFAULT_AI`
- `api/routes/task_routes.py`：`TaskRequest` 不再有 `ai_type`，前端改为在 `payload` 里传
- `api/routes/devices.py`：移除设备 `ai_type` 相关接口

### 保持不变
- `plugins/*/manifest.yaml`：`ai_type` input 定义保留
- `plugins/*/script.yaml`：`${payload.ai_type:-volc}` 用法保留
- `config/apps/x.yaml`：按 `ai_type` 组织的策略数据保留
- `config/strategies/*.yaml`：策略配置保留
- `engine/actions/sdk_business_support.py`：消费 `params.ai_type` 的 action 保留

### 前端兼容
- 前端提交任务时，将 `ai_type` 从顶层字段移入 `payload`：
  ```json
  // 旧
  {"task": "x_home_interaction", "ai_type": "volc", "devices": [1]}
  // 新
  {"task": "x_home_interaction", "devices": [1], "payload": {"ai_type": "volc"}}
  ```

## 任务计划

### Phase 1：代码层清理
- [ ] 1.1 移除 `models/config.py` 的 `DEFAULT_DEFAULT_AI`
- [ ] 1.2 移除 `models/task.py` 的 `TaskRequest.ai_type` 字段
- [ ] 1.3 移除 `models/device.py` 的 `Device.ai_type` 字段
- [ ] 1.4 移除 `core/task_control.py` 的 `ai_type` 参数传递
- [ ] 1.5 移除 `core/device_manager.py` 的 `device.ai_type` 逻辑

### Phase 2：数据层清理
- [ ] 2.1 移除 `core/task_store.py` 的 `ai_type` 列（加 SQLite migration）
- [ ] 2.2 更新 `TaskRecord` dataclass 移除 `ai_type` 字段

### Phase 3：API 层兼容
- [ ] 3.1 更新 `api/routes/task_routes.py`：`ai_type` 不再是顶层参数
- [ ] 3.2 更新 `api/routes/devices.py`：移除设备 `ai_type` 相关端点
- [ ] 3.3 更新前端 `task_service.js`：将 `ai_type` 移入 payload
- [ ] 3.4 （可选）实现 `payload_defaults` 机制：设备配置支持通用 payload 默认值，框架 merge 时用户显式传的优先

### Phase 4：测试修复
- [ ] 4.1 更新所有引用 `ai_type` 的测试文件（至少6个）
- [ ] 4.2 补充回归测试：验证插件通过 payload 正确消费 `ai_type`

##  决策
- `device.ai_type` **完全移除**，设备不持有运营角色
- `ai_type` 是插件 payload 的普通参数，用户在任务提交 UI 选择，通过 `payload` 传递
- 插件 `manifest.yaml` 声明 `ai_type` input（含 select options），UI 据此渲染选择器
- `device.ai_type` 没有实质调度逻辑，只是透传字段，可直接移除
- `task_control.py` 的 `ai_type` 在 workflow draft 重放时使用，移除后由 payload 自动携带，不影响功能
- 决策：**完全移除系统层 ai_type**，框架只传递 `payload`，运营角色逻辑完全在插件层
- `ai_type` 从 `TaskRequest` 顶层字段移入 `payload`，前端同步修改

### 设备默认值需求（新增 payload_defaults 机制）
如果需要设备有默认运营角色（用户不选时自动使用），通过新增通用 `payload_defaults` 机制实现：
- 设备配置支持 `payload_defaults: {ai_type: volc}` 等任意 payload 默认值
- 框架在任务执行时将 `payload_defaults` 与用户提交的 `payload` merge，用户显式传的字段优先
- 框架完全不感知 `ai_type` 语义，只做通用 key-value merge
- 此机制是可选的扩展，Phase 3 实现

## 注意事项

- **数据库 migration**：`ai_type` 列有历史数据，需要确认是否需要保留（建议直接 DROP，任务历史记录不依赖此字段的语义）
- **API 向后兼容**：如果外部调用方依赖 `TaskRequest.ai_type`，需要提供过渡期（顶层 `ai_type` → 自动注入 payload）
- **前端同步**：前端任务提交代码需同步修改

