# 架构重构执行计划

> 状态：待执行 | 最后更新：2026-03-22

## 已完成的前置修复（勿重复）

以下问题在本计划制定前已修复，执行本计划时不需要重复处理：

| 修复项 | 文件 | 说明 |
|--------|------|------|
| `cloud_container.cloud_index` → `cloud_container.cloud_id` | 所有 x_* 插件 script.yaml | resolve_cloud_container 返回 cloud_id 不是 cloud_index |
| `_resolve_plugin_app_id` 错误返回 `"default"` | `engine/runner.py` | resolve_app_id(default_app="") 返回 "default" 而非空字符串，导致 manifest default 被跳过 |
| 截图接口从 RPC 改为 HTTP API | `api/routes/devices.py`、`core/device_control.py` | 截图用 AndroidApiClient /snapshot（30001端口），消除与任务 RPC 的并发竞争 |
| WebSocket 双通道重复广播 | `api/routes/websocket.py` | DB 轮询用 _mem_broadcast_max_id 跳过主进程已广播事件 |
| x.yaml home_tab selector 日语→中文 | `config/apps/x.yaml` | desc_contain: "ホーム" → "主页" |
| x.yaml 添加 stage_patterns | `config/apps/x.yaml` | 手工添加，阶段三完成后需对齐格式 |

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

### 1.4 向后兼容说明

阶段一修改是**纯增量**的：
- 插件显式传 `package`/`state_profile_id`/`app` 时，显式值优先，行为不变
- 只有插件未传这些参数时，才走新的自动推断路径
- 现有所有插件在阶段一完成后无需立即修改，可继续正常运行

### 1.4b `credentials.load` action 兼容性确认

插件通过 `credentials.load` 加载账号时传入 `app_id: "${payload.app_id:-x}"`，该参数经由 payload 注入机制已在 context.payload 里。确认 `credentials_load` action 能正确从 payload 读取 `app_id` 用于账号池过滤（阶段六完成后才生效，此处仅确认参数链路正确）。

### 1.5 验证

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

### 2.3 `config/apps/x.yaml` 已知问题

- `stage_patterns.home` 当前使用 `resource_ids`（tabs、tab_layout、composer_write），这是正确的
- **注意**：`_extract_app_stage_patterns` 对 `stage_patterns` 路径下的 `content_descs` 字段不会自动转为 `text_markers`（只有 `selectors` 路径才会）。因此 stage_patterns 里必须用 `resource_ids` 或 `text_markers`，不能用 `content_descs`
- `login_entry_btn` selector 文本仍是日语（`ログイン`）——中文设备界面登录按钮文字可能是「ログイン」或「登录」，需实测确认后修正
- 格式需与阶段三蒸馏输出格式对齐，阶段三完成后对比确认

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

### 3.3 注意 `_extract_app_stage_patterns` 的字段限制

`_extract_app_stage_patterns`（state_actions.py L122）在解析 `stage_patterns` 路径时，支持的字段为：
- `resource_ids` / `resource_id_markers`
- `focus_markers` / `window_markers`
- `text_markers` / `texts`
- `content_descs`（注意：此字段在 `selectors` 路径下才自动转为 text_markers，在 `stage_patterns` 路径下不生效）

蒸馏沉淀时应优先使用 `resource_ids`，这是最可靠的状态识别方式。

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
| `web/js/features/devices.js` 等 | 移除设备列表中 `ai_type` 的展示字段（设备卡片不再显示运营角色）|

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

### 4.5 待验证的 core action 参数

以下 action 的参数名称和行为在插件层未经完整验证，阶段四前需逐一确认：

| action | 插件用法 | 待确认项 |
|--------|----------|----------|
| `core.extract_timeline_candidates` | `app_id`、`ai_type`、`swipe_count_min/max` | 参数名是否正确，ai_type 移入 payload 后是否需要调整 |
| `core.pick_candidate` | `candidates`、`ai_type` | 同上 |
| `core.open_candidate` | `device_ip`、`cloud_index`、`candidate` | 参数名是否正确 |
| `credentials.load` | `device_ip`、`cloud_index`、`app_id`、`slot` | 验证 app_id 在 payload 里能否正确读取 |

---

## 阶段五：任务编排与执行速度控制

### 5A：任务编排（Task Pipeline）

**需求**：插件之间需要有执行顺序和循环能力。例如：
> 采集博主 → 仿冒博主 → 关注截流（顺序执行，可循环）

#### 现状分析

当前框架只支持单插件任务，插件之间无编排关系。`priority` 字段只控制队列优先级，不控制顺序依赖。

#### 设计方案：Pipeline 任务类型

新增 `_pipeline` 内置任务，在 payload 中定义编排：

```json
{
  "task": "_pipeline",
  "devices": [1],
  "payload": {
    "steps": [
      {"plugin": "x_scrape_blogger", "payload": {"ai_type": "volc"}},
      {"plugin": "x_clone_profile",  "payload": {"ai_type": "volc"}},
      {"plugin": "x_follow_followers", "payload": {"ai_type": "volc"}}
    ],
    "repeat": 3,
    "repeat_interval_ms": 5000
  }
}
```

#### 实现要点

- [ ] 5A.1 新增 `_pipeline` 内置 runner，按顺序依次调用各插件
- [ ] 5A.2 支持 `repeat: N`（重复 N 次，`0` 表示无限循环直到取消）
- [ ] 5A.3 支持 `repeat_interval_ms`：每轮之间的等待时间
- [ ] 5A.4 任务事件：每个子步骤完成时发出 `pipeline.step_done` 事件
- [ ] 5A.5 取消支持：取消 pipeline 时，当前执行中的子步骤也能感知并停止
- [ ] 5A.6 前端 UI：Pipeline 编排界面，拖拽排序插件，设置重复次数

### 5B：全局执行速度控制

**需求**：插件缺少全局等待参数。需要速度滑块 + 随机等待高级参数。

#### 设计方案：框架保留参数（`_` 前缀）

`_speed`、`_wait_min_ms`、`_wait_max_ms` 作为框架级保留参数，所有插件自动支持，无需单独声明：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `_speed` | string | `normal` | `slow`=2x间隔 / `normal`=1x / `fast`=0.5x |
| `_wait_min_ms` | integer | `0` | 每个 action 后随机等待最小值 |
| `_wait_max_ms` | integer | `0` | 每个 action 后随机等待最大值 |

#### 实现要点

- [ ] 5B.1 拟真引擎（HumanizedHelper）读取这些参数，调整操作间隔倍率
- [ ] 5B.2 Interpreter 在每个 action 执行后，追加 `random.uniform(_wait_min_ms, _wait_max_ms)` ms 等待
- [ ] 5B.3 `_` 前缀为框架保留命名空间，蒸馏不应硬编码这些值
- [ ] 5B.4 `_speed` 不影响 `ui.wait_until` 超时，只影响操作间主动等待
- [ ] 5B.5 前端 UI：任务提交界面统一展示速度滑块和高级等待参数

---

## 阶段六：账号资产与 App 强绑定


### 问题

账号导入时已支持 `app_id` 字段，但：
1. **`app_id` 存在 `metadata_json` 里**（`core/account_store.py` schema），无法被 SQL 过滤
2. **`pop_ready_account` 不过滤 `app_id`**，任何插件都能取到任意 App 的账号
3. **`list_accounts` 返回所有账号**，前端无法按 app 隔离显示
4. **`app_id` 默认值是 `"default"`**，导入时不强制选择 App，存在垃圾数据

### 设计决策

- `default` 保留，含义为：**系统级账号/资产**（如 socks5 代理、通用 API key 等），非特定 App
- 导入非系统资产时 `app_id` 必填，不能为 `default`（前端 UI 强制选择）
- `credentials.load` action 按 `app_id` 过滤账号池，插件只能取到对应 App 的账号
- 前端账号列表按 `app_id` 分组展示

### 6.1 DB schema 添加 `app_id` 列（core/account_store.py）

```sql
ALTER TABLE accounts ADD COLUMN app_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX idx_accounts_app_id ON accounts(app_id);
```

`upsert_account` 将 `app_id` 从 metadata 提升为独立列：
```python
fields = [..., "app_id"]  # 加入字段列表
# app_id 从 data 直接读，不再落入 metadata
```

### 6.2 `pop_ready_account` 支持 `app_id` 过滤（core/account_store.py）

```python
def pop_ready_account(self, app_id: str | None = None) -> dict[str, Any] | None:
    filter_clause = "status = 'ready'"
    params = []
    if app_id:
        filter_clause += " AND (app_id = ? OR app_id = 'default')"
        params.append(app_id)
    # ... 余下逻辑不变
```

注意：`app_id='default'` 的账str | None = None) -> list[dict[str, Any]]:
    if app_id:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE app_id = ? OR app_id = 'default' ORDER BY created_at ASC",
            (app_id,)
        ).fetchall()
    else:
        # 管理员视图：返回全部
        rows = conn.execute("SELECT * FROM accounts ORDER BY created_at ASC").fetchall()
```

### 6.4 `credentials.load` action 传入 `app_id`

插件通过 `app_id: "${payload.app_id:-x}"` 调用 `credentials.load`，action 内部用 `app_id` 过滤账号池。

### 6.4b `credentials.checkout` action 传入 `app_id`（engine/actions/credential_actions.py）

`agent_executor` 通过 `credentials.checkout` 从账号池弹出账号。阶段六完成后必须同步修改，否则 agent_executor 执行登录类任务时无法取到正确账号。

```python
def credentials_checkout(params, context):
    # 从 params 或 context.payload 读取 app_id
    app_id = str(params.get("app_id") or context.payload.get("app_id") or "").strip()
    url = f"http://{host}:{port}/api/data/accounts/pop"
    if app_id:
        url += f"?app_id={app_id}"
    # ... 余下逻辑不变
```

`POST /api/data/accounts/pop` API 需同步支持 `?app_id=` 查询参数。

**注意**：`agent_executor` 运行时 payload 里已有 `app_id`（由 `resolve_app_payload` 注入），无需 agent 显式传参，框架自动透传。

### 6.5 API 层更新

- `GET /api/data/accounts`：支持 `?app_id=x` 查询参数，前端按 App 分组展示
- `AccountsImportRequest.app_id`：改为必填（`app_id: str`，移除默认值 `"default"`），前端强制选择
- 前端导入界面：下拉选择 App（从插件 catalog 动态获取 app_id 列表），无「默认」选项，另有「系统资产」选项对应 `default`

### 6.6 数据迁移

现有 `metadata_json` 中含 `app_id` 的账号需提取到新列：
```sql
UPDATE accounts
SET app_id = json_extract(metadata_json, '$.app_id')
WHERE json_extract(metadata_json, '$.app_id') IS NOT NULL;
```

---

## 阶段七：插件热加载机制

蒸馏生成新插件后，任务执行路径（`Runner._plugin_loader`）使用启动时的缓存，无法感知新插件，必须重启服务。对于同一 App 的多任务蒸馏积累场景，这是严重阻碍。

### 现状分析

er._plugin_loader` — 进程启动时加载一次，**之后不更新** ❌
- `app yaml`（`config/apps/*.yaml`）— 文件形式，`_merge_selectors_to_app_config` merge 追加，天然支持多次蒸馏累积 ✅

### 5.1 fix `Runner` 插件加载（engine/runner.py:44）

**问题**：`self._plugin_loader = get_shared_plugin_loader()` 缓存不更新。

**修复**：任务执行时按需刷新 loader。最小改动方案——在 `run()` 方法里获取插件时用 refresh：

```python
# engine/runner.py run() 方法内，替换静态 plugin_loader.esh（插件不存在时才 refresh，避免每次扫描）：

```python
# 优化版：先查缓存，未命中才 refresh
plugin = self._plugin_loader.get(task_name)
if plugin is None:
    plugin = get_shared_plugin_loader(refresh=True).get(task_name)
```

### 5.2 蒸馏完成后自动触发 loader 刷新

蒸馏完成时（`distill_golden_run.py` 写入插件文件后），通知 Runner 刷新 loader。
最简实现：蒸馏 API 在写完文件后调用 `clear_shared_plugin_loader_cache()`，下次任务执行时自动重建。

```python
# api/routes/task_routes.py 蒸馏成功后
from engine.plugin_loader import clear_shared_plugin_loader_cache
clear_shared_plugin_loader_cache()
```

### 5.3 app yaml 热加载（已天然支持）

`config/apps/*.yaml` 是文件，`_merge_selectors_to_app_config` 每次蒸馏都读取并 merge，已支持累积。
但 `AppConfigManager.load_app_config` 是否有缓存需要确认：

```python
# core/app_config.py — 确认 get_app_config 无内存缓存
# 若有 lru_cache 或 _cache 则需清除
```

### 5.4 验证

1. 蒸馏生成新插件后，**不重启服务**，直接下发该插件任务，确认能正常执行
2. 同一 App 执行两次不同任务蒸馏，确认 app yaml 正确累积两次的选择器和 stage_patterns

---

## 执行顺序说明

- 阶段一是基础，必须首先完成并验证
- 阶段二依赖阶段一（框架修复后才能安全回退插件硬编码）
- 阶段三可与阶段二并行（蒸馏改动独立）
- 阶段四必须在阶段一、二完成后执行（确保插件通过 payload 工作正常）
- 阶段五（编排+速度）可与阶段三、四并行（框架新增功能，无破坏性依赖）
- 阶段六（账号绑定）可与任意阶段并行（账号系统改动独立）
- 阶段七（热加载）可与任意阶段并行（独立改动）

## 完成标准

- 对任意新 App，agent_executor 执行成功 -> 蒸馏 -> 不重启服务 -> 插件直接二次执行成功
- 账号导入强制绑定 App，插件只能取到对应 App 的账号
- 同一 App 多次蒸馏，app yaml 正确累积所有选择器和 stage_patterns
- 蒸馏生成的 script.yaml 不含 package、state_profile_id 硬编码
- ai_type 完全从系统层移除，只在插件 payload 层存在
- 所有现有 x_* 插件回退人工补丁后仍能正常执行
- 全套测试通过
