# AI 项目指南（webrpa）

## 1）文档定位

本文档说明 `webrpa` 当前 AI 相关架构、职责边界、目标方向与约束。

文档分工：

- `README.md`：入口说明与项目摘要。
- `docs/project_progress.md`：项目看板，包含可用能力、完成状态与下一步计划。
- `docs/PLUGIN_CONTRACT.md`：插件契约与参数输入规范（v2）。
- `docs/HANDOFF.md`：架构解析、变量作用域与设计原则（精简版）。
- `docs/ai_workflow_design_checklist.md`：AI 工作流设计清单（中文）。
- `docs/TECHNICAL_DEBT.md`：系统技术债与治理重构路线图。

## 2）项目定位

`webrpa` 是可独立运行的 Web/RPA 自动化平台。

AI 在当前项目中的定位不是替代插件体系，而是：

1. 作为受控执行辅助层，帮助规划、观察、记录与蒸馏。
2. 为未来的新任务探索与插件生成提供支持。
3. 最终服务于稳定、可重放、可维护的插件化工作流。

## 3）当前 AI 基线

当前 main 分支的 AI 基线是一个**受控、边界清晰的 MVP**：

- 托管 `gpt_executor` 通过既有 `/api/tasks` 控制面运行。
- 主观察策略是 structured-state-first。
- 当前 AI 基线仍然是 bounded、structured-state-first，不是视觉主导执行。
- fallback 模态是辅助证据，不是默认主路径。
- 模型轨迹单独记录到 `config/data/traces/`。
- Golden Run 目前只支持离线蒸馏为 reviewable YAML draft。
- draft 默认不会自动安装到 `plugins/`。

这意味着当前 AI 设计更接近：

**bounded executor + trace producer + offline draft distillation**

而不是：

**fully autonomous workflow authoring and promotion**

## 4）当前 AI 运行链路

### 4.1 控制面与运行时

1. `api/server.py` 提供 API 入口与 `/web`。
2. `/api/tasks` 进入任务控制面。
3. `core/task_control.py`、`core/task_execution.py`、`core/task_finalizer.py`、`core/task_metrics.py` 共同负责托管任务生命周期。
4. `engine/runner.py` 负责分发插件任务与 `gpt_executor` 运行时。
5. 运行时配置可通过 payload `_runtime_profile` / `_runtime` / `_llm` / `_vlm` / `_uitars` 覆写，profile 文件位于 `config/<name>.json`。

### 4.2 AI 执行边界

- `ai_services/llm_client.py`
  - 统一 LLM 请求、provider/model 解析、错误归一与响应标准化。
- `engine/gpt_executor.py`
  - 负责受控 planner loop：观察、规划、执行、记录、停止。
- `engine/actions/ai_actions.py`
  - 提供 `ai.llm_evaluate`、`ai.vlm_evaluate`、`ai.locate_point` 动作边界。
- `core/model_trace_store.py`
  - 负责 append-only JSONL 模型轨迹落盘。
- `core/golden_run_distillation.py`
  - 负责从成功轨迹生成 reviewable YAML draft。
- `tools/distill_golden_run.py`
  - 负责手工/离线触发单次蒸馏。
- `tools/distill_multi_run.py`
  - 多轮 trace 聚合蒸馏，达到门槛（简单 3 次/复杂 10 次）后生成 YAML 草稿。
- `tools/distill_binding.py`
  - 从 trace XML 提取界面特征，生成 `NativeStateBinding` 代码草稿。

LLM 链路说明：`LLMClient` 使用标准 OpenAI Chat Completions 格式（`/chat/completions`）。LLM base_url 和 model 由 `config/system.yaml` 配置，API Key 则仅通过 `MYT_LLM_API_KEY` 环境变量配置（保证密钥安全）。

## 5）核心设计原则

### 5.1 插件优先，AI 不替代插件

项目的 durable workflow boundary 仍然是 `plugins/`。
AI 的职责是帮助探索、规划、沉淀和生成更稳定的插件，而不是让运行时永久停留在自由生成状态。

### 5.2 优先复用现有接口

AI 相关能力应尽量复用：

- 已注册 action
- 既有 runtime seam
- `/api/tasks` 控制面
- 当前观察接口
- 浏览器 / native / sdk 既有适配器

### 5.3 轨迹是产品资产

模型轨迹和执行证据不只是调试信息。
它们是后续 distillation、回放验证、问题归因和插件生成的重要输入。

### 5.4 单次成功不等于稳定工作流

一次成功运行可以成为 draft 输入，但不能自动等同于稳定插件。
稳定插件需要更强的参数化、验证与重放证据。

## 6）目标方向（待持续推进）

当前已记录的目标方向是：

1. 遇到新任务时，由 strong GUI-recognition and GUI-understanding visual model 主导探索执行。
2. 多轮执行中充分利用项目既有接口和动作。
3. 生成足够支撑沉淀蒸馏的日志与样本。
4. 通过日志样本处理，生成最终可落地的 YAML 插件。

补充约束：

- model selection remains capability-first and still open，不锁定到某个已命名 checkpoint。
- current AI development is cloud-machine-first。
- browser support remains supported but secondary for this wave。

对应的目标工作流见：`docs/ai_workflow_design_checklist.md`

## 7）对“视觉模型”的当前判断

视觉能力对目标方向是重要的，但当前仓库里它还不是主路径。

- 现在主执行链仍然是 structured-state-first。
- 仓库里已有视觉相关配置入口，但当前 VLM 接线仍然很轻，不能写成成熟 dedicated stack。
- `ai.vlm_evaluate` 已作为动作边界存在，但当前视觉能力还不是成熟的一等公民执行器。
- `gpt_executor` 的 VLM 路径由环境变量 `MYT_ENABLE_VLM` 控制，默认关闭；开启后才会根据 `fallback_modalities` 触发。
- 因此，若未来走 vision-led exploration，应被视为**目标方向扩展**，不是当前已完成能力。
- 当前这一波 AI 开发以云机为先，浏览器仍保持兼容支持，但不是当前主 AI 设计驱动面。

## 8）当前限制与已知差距

以下能力当前仍然不足或尚未形成完整产品路径：

- vision-led multi-run exploration executor
- 多轮样本聚合后的稳定路径抽取
- 基于多样本而不是单次 golden run 的 distillation
- draft 到插件的在线 promotion pipeline
- 更强的 workflow stability / consensus extraction

## 9）Deferred / 不应误写为已完成

在当前 repo 语境下，这些能力不应被表述为已完成：

- SoM overlays
- shadow healing
- multi-run consensus extraction
- broader workflow-level recovery system
- fully automatic plugin promotion

## 10）质量门禁

最低要求：

- 静态门禁通过
- 全量测试通过
- RPC 禁用模式可启动
- `/health` 返回 200

常用命令：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

## 11）开发提醒

1. 新能力优先沿 `engine/`、`core/`、`plugins/` 的现有边界扩展。
2. 不要把 AI 目标方向直接写成当前已交付能力。
3. 不要把生成草稿等同于安全上线插件。
4. 任何 AI 扩展都应保留验证、回放与证据链。
5. 文档进度请持续更新 `docs/ai_workflow_design_checklist.md`，而不是把 working notes 塞进 canonical status docs。

## 12）硬约束

- 禁止重新引入 `tasks` / `app.*` 历史依赖。
- 数据文件必须落在 `config/data`。
- 路由保持薄层，核心逻辑下沉到 `core/` 与 `engine/`。
- 新业务工作流仍优先收敛到插件，而不是长期停留在自由探索执行状态。
