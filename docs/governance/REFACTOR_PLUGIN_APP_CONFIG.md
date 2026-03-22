# Refactor: 插件参数应从 app yaml 单一来源获取

## 设计原则

> 插件由 agent_executor 执行后蒸馏生成。插件的所有业务参数（选择器、状态检测规则、关键词、文本模板等）
> 只有一个来源：`config/apps/{app}.yaml`。
> `script.yaml被记录
3. 成功 N 次后触发蒸馏（`distill_threshold`），提取确定性脚本
4. 生成 `plugins/{name}/script.yaml` + `manifest.yaml`
5. 同时沉淀 `config/apps/{app}.yaml`（选择器、状态检测规则等）

插件进入生态后可重复执行，无需 AI 介入。

### 当前架构的已有机制（正确的部分）

`core/app_config.py` 的 `resolve_app_payload` 在任务执行前将 app yaml 内容注入 payload：

```python
resolved["_app_stage_patterns"] = config["stage_patterns"]
resolved["_app_selectors"动注入包名
```

这是正确的设计——插件不需要显式传这些参数，框架根据 `app_id` 自动注入。

## 问题：注入了但没有被读取

`engine/actions/state_actions.py` 的 `detect_app_stage` 完全忽略了 payload 中已注入的 `_app_stage_patterns`，而是重新加载文件：

```python
# 当前错误实现（第698行）
config = sdk_config_support.load_app_config_document(str(app_name))  # 重新读文件
stage_patterns = _extract_app_stage_patterns(config)
```

正确实现应该优先读取 payload 中已注入的数据：

```python
# 正确实现
stage_patterns = context.payload.get("_app_stage_patterns") or _load_from_file(app_name)
```

## 当前修复的问题（技术债）

我们在修复 x_home_interaction 时走了错误路径：

| 错误修复 | 问题 | 正确做法 |
|----------|------|----------|
| `script.yaml` 里硬编码 `package: com.twitter.android` | 包名应从 x.yaml 自动注入 | `resolve_app_payload` 已自动注入 `package`，script 不需要写 |
| `script.yaml` 里写 `state_profile_id: app_stage` | profile 应由框架根据 app_id 推断 | 框架检测到有 `_app_stage_patterns` 时自动用 app_stage profile |
| 手工在 `x.yaml` 里加 `stage_patterns` | 应由蒸馏过程沉淀 | 人工添加破坏了蒸馏自举闭环 |

## 影响范围

### 需要修复的代码

| 文件 | 问题 | 修复方向 |
|------|------|----------|
| `engine/actions/state_actions.py:detect_app_stage` | 忽略 `_app_stage_patterns`，重新读文件 | 优先读 payload 注入的数据 |
| `engine/actions/ui_state_actions.py:_resolve_service` | `state_profile_id` 需要插件显式传 | 检测到 `_app_stage_patterns` 时自动用 app_stage profile |

### 需要回退的插件修改

| 文件 | 需要回退的内容 |
|------|----------------|
| `plugins/x_home_interaction/script.yaml` | 移除 `package: com.twitter.android`（由框架注入）|
| `plugins/x_home_interaction/script.yaml` | 移除 `state_profile_id: app_stage`（由框架推断）|
| `plugins/x_home_interaction/scrip但需要确认其格式与蒸馏输出一致。

## 任务计划

### Phase 1：修复框架读取注入数据
- [ ] 1.1 `detect_app_stage`：优先读 `context.payload["_app_stage_patterns"]`，fallback 才读文件
- [ ] 1.2 `_resolve_service`（ui_state_actions）：检测到 payload 有 `_app_stage_patterns` 时自动选择 `app_stage` profile，无需插件显式传 `state_profile_id`
- [ ] 1.3 验证 `package` 已通过 `resolve_app_payload` 正确注入，`app.stop/open` 能从 context 获取

### Phase 2：回退插件中的错误修复
- [ ] 2.1 `x_home_interaction/script.yaml`：移除 `package`、`state_profile_id`、`app` 硬编码参数
- [ ] 2.2 验证回退后任务仍能正常执行
- [ ] 2.3 检查其他 x_* 插件是否有类似硬编码

### Phase 3：验证蒸馏自举闭环
- [ ] 3.1 确认蒸馏输出的 script.yaml 格式不包含 package/state_profile_id 等硬编码
- [ ] 3.2 确认 agent_executor 执行成功后能正确沉淀 app yaml 内容
