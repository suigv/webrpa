# 示例索引与状态

本目录提供配置/动作/工作流示例，用于对齐功能与日志分析路径。示例默认是“结构模板”，需要替换为你的 App 与业务参数。

示例列表（状态）：
- `docs/examples/app_config_default.yaml`：模板，可用于 `config/apps/<app>.yaml` 的结构参考。
- `docs/examples/binding_sample.json`：模板，对齐 `config/bindings/*.json` 的字段结构（含 `xml_filter` / `states`）。
- `docs/examples/navigate_to.json`：结构示例（browser 路径）。
- `docs/examples/login_stage.json`：模板，需按目标 App 调整 `stage_patterns`。
- `docs/examples/ui_match_state.json`：结构示例（native + browser 两类）。
- `docs/examples/plugin_workflow.yaml`：结构示例（插件脚本 + route/hops）。
- `docs/examples/gpt_executor.json`：结构示例（GptExecutor 最小请求）。

日志分析提示：
- AI 路径事件流里会出现 `task.observation`，其中 `modality` / `fallback_reason` / `fallback_evidence` 可判断是否处于 binding-free 或回退链路。
- 如果没有匹配到 `app_package` 对应的 binding，系统会进入 binding-free 观察模式，但不会报错。
