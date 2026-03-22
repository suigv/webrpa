# 架构重构执行计划

> 状态：待执行 | 最后更新：2026-03-22

## 设计原则

1. **框架只传 payload，不感知业务语义** — ai_type、app_id 等业务概念只在插件层存在
2. **app yaml 是插件业务参数唯一来源** — 选择器、状态检测规则、关键词等都在 `config/apps/{app}.yaml`，script.yaml 只写流程骨架
3. **蒸馏自举闭环** — `agent_executor` 执行成功后蒸馏，生成的插件无需人工补充参数即可二次执行
4. **ai_type 是插件可选 input** — 有运营角色需求的插件自行声明，框架不知晓

---

## 阶段一：修复框架 payload 注入读取（最高优先级，其他阶段依赖此项）

`core/app_config.py resolve_app_payload` 已在任务执行前将 app yaml 内容注入 payload（`_app_stage_patterns`、`_app_selectors`、`package` 等），但下游 action 完全忽略这些注入数据。

### 1.1 fix `detect_app_stage`（engine/actions/state_actions.py ~L698）

**问题**：直接调用 `load_app_config_document` 重新读文件，忽略 `context.payload["_app_stage_patterns"]`。

**修复**：
```python
# 优先读 payload 注入的 stage_patterns
injected = context.payload.get("_app_stage_patterns") if hasattr(context, "payload") else None
if isinstance(injected, dict) and injected:
    stage_patterns = injected
else:
    try:
        config = sdk_config_support.load_app_config_document(str(app_name))
        stage_patterns = _extract_app_stage_patterns(config)
    except Exception:
        stage_patterns = {}
```

### 1.2 fix `_resolve_native_state_profile_id`（engine/actions/ui_state_actions.py ~L122）

**问题**：`state_profilete_profile_id(params: dict[str, object]) -> str:
    explicit = normalize_native_state_profile_id(
        str(params.get("state_profile_id") or "").strip() or None,
        binding_id=str(params.get("binding_id") or "").strip() or None,
        default="",
    )
    if explicit:
        return explicit
    # 有 _app_stage_patterns 时自动选 app_stage profile
    if params.get("_app_stage_patterns"):
        return "app_stage"
    return "login_stage"  # 原有默认值
```
注意：`_normalize_native_state_profile_params` 会把 params 传给 `NativeUIStateAdapter`，其中包含 `_app_stage_patterns`，因此推断可正常工作。

### 1.3 fix `app.stop/open/ensure_running` package 获取（engine/actions/ui_app_actions.py）

**问题**：只读 `params.get("package")`，不读 context.payload 里框架已注入的包名。

**修复**：新增 helper：
```python
def _resolve_package_name(params: dict[str, Any], context: ExecutionContext) -> str:
    pkg = str(params.get("package") or "").strip()
    if not pkg and hasattr(context, "payload"):
        pkg = str(context.payload.get("package") or "").strip()
    return pkg
```
在 `app_open`、`app_stop`、`app_ensure_running` 中用此 helper 替换 `params.get("package")`。

### 1.4 验证

阶段一完成后：将 `x_home_interaction/script.yaml` 的 `package`、`state_profile_id`、`app` 参数临时注释，提交任务，确认仍能成功执行。成功则进入阶段二。

---

## 阶段二：回退插件中的错误人工修复

阶段一验证通过后，回退调试过程中对插件和 x.yaml 的不规范人工修改。

### 2.1 `plugins/x_home_interaction/script.yaml`

移除以下硬编码参数：
- `package: com.twitter.android` — 由框架从 x.yaml 注入
- `state_profile_id: app_stage` — 由框架根据 `_app_stage_patterns` 自动推断
- `app: "${package: com.twitter.android` 也移除（框架自动注入）。

保留：`on_fail: strategy: skip`（swipe 步骤的容错处理，这是业务逻辑，合理保留）。

### 2.2 扫描其他 x_* 插件

对所有 `plugins/*/script.yaml` 扫描并移除：
- 硬编码 `package: com.xxx.xxx`（框架注入）
- `state_profile_id` 参数（除非有特殊覆盖需求）
- `app:` 参数（框架已通过 app_id 注入）

### 2.3 `config/apps/x.yaml` stage_patterns 格式对齐

当前手工添加的 `stage_patterns` 需与阶段三蒸馏输出格式对齐。阶段三完成后对比确认，必要时调整格式。

---

## 阶段三：蒸馏沉淀 stage_patterns

`core/golden_run_distillation.py _merge_selectors_to_app_config`（L533）只沉淀 `selectors`，需扩展为同时沉淀 `stage_patterns`。

### 3.1 扩展 `_merge_selectors_to_app_config`

在沉淀 selectors 后，追加 stage_patterns 沉淀逻辑：
```python
# 从 step records 提取：观察到 state_id X 时，界面有哪些 resource_id
stage_patterns: dict[str, dict] = {}
for record in records:
    observed_states = record.get("observed_state_ids") or []
    # 从 record 的 XML index 中提取 resource_id 列表
    xml_index = record.get("xml_index") or {}
    resource_ids = list(xml_index.get("resource_ids", []))
    for state_id in observed_states:
        if state_id and state_id != "unknown":
            entry = stage_patterns.setdefault(state_id, {"resource_ids": []})
            for rid in resource_ids:
                if rid not in entry["resource_ids"]:
                    entry["resource_ids"].append(rid)

# merge 到 app yaml
if stage_patterns:
    existing = doc.get("stage_patterns") or {}
    for state_id, entry in stage_patterns.items():
        if state_id not in existing:
            existing[state_id] = entry
    doc["stage_patterns"] = existing
```

### 3.2 确认蒸馏输出不含硬编码

确认 `_build_draft` 生成的 `ui.wait_until` 步骤（L256）只含 `expected_state_ids`、`timeout_ms`、`interval_ms`，不含 `state_profile_id`、`package`。当前代码已如此，确认即可。

---

## 阶段四：移除 ai_type 系统级字段

**依赖**：阶段一、二完成验证后执行。

### 4.1 代码层清理

| 文件 | 操作 |
|------|------|
| `models/config.py` | 删除 `DEFAULT_DEFAULT_AI = "volc"` |
| `models/task.py` | 删除 `TaskRequest.ai_type: str = "default"` 字段 |
| `models/device.py` | 删除 `Device.ai_type: str` 字段 |
| `core/task_store.py` | 删除 `ai_type` 字段和 SQL 列，加 migration：`ALTER TABLE tasks DROP COLUMN ai_type` |
| `core/task_control.py` | 删除 `submit_with_retry` 的 `ai_type` 参数及内部传递链路（L154、L180、L195、L369、L380） |
| `core/device_manager.py` | 删除 `device.ai_type`、`get_device(ai_type=)` 参数及相关逻辑（L29、L31、L289、L295、L427-437） |

### 4.2 API 层更新

| 文件 | 操作 |
|------|------|
| `api/routes/task_routes.py` | `TaskRequest` 不再有 `ai_type`，移除相关代码 |
| `api/routes/devices.py` | 移除返回 `ai_type` 的设备信息字段 |
| `web/js/features/task_service.js` | 将 `ai_type` 移入 payload（`payload: {...payload, ai_type: selectedValue}`），移除顶层 `ai_type` 字段 |

### 4.3 可选：payload_defaults 机制

如需设备级默认运营角色，在 `config/devices.json` 增加 `payload_defaults` 字段：
```json
{ "device_id": 1, "payload_defaults": { "ai_type": "volc" } }
```
在 `engine/interpreter.py _build_session_defaults` 里 merge `payload_defaults`，用户显式传的字段优先。框架不感知任何 key 的语义。

### 4.4 测试修复

更新以下测试文件中所有 `ai_type` 相关断言和 fixture：
- `tests/test_task_cancellation.py`
- `tests/test_task_scheduling_events.py`
- `tests/test_task_control_plane.py`
- `tests/test_workflow_drafts.py`
- `tests/test_task_mapper.py`
- `tests/test_task_request_contracts.py`

补充回归测试：验证插件通过 `payload` 正确消费 `ai_type`，且 `TaskRequest` 不含 `ai_type` 时任务仍能正常下发。

---

## 执行顺序说明

- 阶段一是基础，必须首先完成并验证
- 阶段二依赖阶段一（框架修复后才能安全回退插件硬编码）
- 阶段三可与阶段二并行
- 阶段四必须在阶段一二完成后执行（确保插件通过 payload 工作正常）

## 完成标准

- 对任意新 App，agent_executor 执行成功 -> 蒸馏 -> 插件直接二次执行，无需人工补充参数
- 蒸馏生成的 script.yaml 不含 package、state_profile_id 硬编码
- ai_type 完全从系统层移除，只在插件 payload 层存在
- 所有现有 x_* 插件回退人工补丁后仍能正常执行
- 全套测试通过
