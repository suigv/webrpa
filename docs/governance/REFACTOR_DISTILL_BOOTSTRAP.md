# Refactor: 蒸馏自举闭环修复

## 设计原则

> 框架应支持从零开始对任意新 App 完成完整的自举流程：
> agent_executor 执行 -> 成功后蒸馏 -> 生成插件 -> 插件可直接二次执行，无需人工补充参数。

## 当前缺失环节

### 1. 蒸馏不沉淀 stage_patterns

`core/golden_run_distillation.py` 的 `_merge_selectors_to_app_config` 只沉淀 `selectors`，不沉淀 `stage_patterns`。
导致插件二次执行时 `detect_app_stage` 找不到状态检测规则，`ui.wait_until` 超时。

### 2. detect_app_stage 不读 payload 注入数据

`core/app_config.py resolve_app_payload` 已将 `_app_stage_patterns` 注入 payload，但
`engine/actions/state_actions.py detect_app_stage` 完全忽略它，重新读文件。
如果 app yaml 没有 `stage_patterns`（新 App 初次蒸馏后），检测始终返回 `unknown`。

### 3. ui.wait_until 需要显式传 state_profile_id

蒸馏生成的 `ui.wait_until` 步骤只有 `expected_state_ids`，没有 `state_profile_id`。
框架默认用 `login_stage` profile，无法检测新 App 的自定义状态。
应能根据 payload 是否有 `_app_stage_patterns` 自动选择正确 profile。

### 4. app.stop/open 需要显式传 package

蒸馏生成的步骤里 `package` 被列为可参数化字段（第401行），可能生成 `${payload.package}`。
但 `resolve_app_payload` 已将包名注入 `payload["package"]`，action 层应能从 context 自动获取，
无需插件显式声明。

## 任务计划

### Phase 1：修复框架读取注入数据（核心）

- [ ] 1.1 `detect_app_stage`（state_actions.py）：
  优先读 `context.payload.get("_app_stage_patterns")`，fallback 才从文件加载。
  这样只要 `resolve_app_payload` 注入了数据，任何 App 都能正确检测状态。

- [ ] 1.2 `_resolve_service`（ui_state_actions.py）：
  当 payload 含 `_app_stage_patterns` 时自动选择 `app_stage` profile，
  无需插件显式传 `state_profile_id`。
  优先级：显式传 > payload 推断 > 默认 login_stage。

- [ ] 1.3 `app.stop/open/ensure_running`（ui_app_actions.py）：
  当 params 无 `package` 时，从 `context.payload.get("package")` 获取（框架已注入）。

### Phase 2：蒸馏沉淀 stage_patterns

- [ ] 2.1 `_merge_selectors_to_app_config` 扩展：在沉淀 selectors 的同时，沉淀 stage_patterns。
  最小实现：将 agent_executor 执行中观察到的 state_id（如 `package` 硬编码。
  这些应由框架自动处理，蒸馏输出保持最小化。

### Phase 3：回退当前错误的人工修复

- [ ] 3.1 `plugins/x_home_interaction/script.yaml`：
  移除 `package: com.twitter.android`（框架自动注入）
  移除 `state_profile_id: app_stage`（框架自动推断）
  移除 `app: "${payload.app_id:-x}"`（框架已通过 app_id 注入）
  验证移除后任务仍正常执行。

- [ ] 3.2 检查其他 x_* 插件是否有类似人工补丁，统一回退。

### Phase 4：新 App 端到端验证

- [ ] 4.1 选择一个新 App（无任何 app yaml 配置），通过 agent_executor 执行任务
- [ ] 4.2 蒸馏生成插件
- [ ] 4.3 直接运行蒸馏插件，验证无需人工补充参数即可成功执行
- [ ] 4.4 确认 app yaml 已自动沉淀 selectors 和 stage_patterns

## 完成标准

对任意新 App，完成以下流程无需人工介入：
1. 用自然语言通过 agent_executor 下发任务
2. 执行成功后触发蒸馏
3. 蒸馏插件直接二次执行成功
4. app yaml 自动包含 selectors 和 stage_patterns
