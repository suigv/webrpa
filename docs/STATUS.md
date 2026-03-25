---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-25
stale_after_days: 14
verification_method:
  - ./.venv/bin/python tools/check_no_legacy_imports.py
  - ./.venv/bin/python -m pytest tests -q
  - ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
  - curl http://127.0.0.1:8001/health
  - MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
  - ./.venv/bin/python tools/check_docs_freshness.py
---

# Current Status

本文件只记录**当前成立**且已经被代码或验证命令支撑的状态。

## 当前范围

当前仓库确认存在并对外暴露的能力：

- FastAPI 服务入口：`api.server:app`
- 健康检查与控制面 API：`/health`、`/api/*`
- 设备与云机接口：`/api/devices/*`
- 托管任务系统：`/api/tasks/*`
- AI 对话接口：`/api/ai_dialog/*`
- 插件执行引擎与动作目录：`plugins/`、`/api/engine/schema`、`/api/engine/skills`
- 前端控制台工程：`web/`

## 最近一次验证

2026-03-25 这组命令为当前文档系统的验证基线：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
./.venv/bin/python tools/check_docs_freshness.py
```

## 当前已确认的仓库事实

- `docs/` 现在只保留当前文档，不再保留规划、历史、参考副本和示例目录。
- 账号导入和 AI 对话规划都可以按当前输入自动创建或补全 app 命名空间，不要求先手写新 app 代码。
- app 身份当前支持 `app_id`、`display_name`、`aliases`、`package_name/package_names` 这一组共享元数据。
- 账号池当前支持 `default_branch` 与 `role_tags`，账号分配支持按 `app_id + branch_id + 任一命中的 role_tags` 取号。
- app 当前支持分支资料配置、AI 输入标注、草稿可选保存，以及共享 app 配置候选审核后再写入正式 app YAML。
- AI planner 当前会返回结构化任务意图、分支解析、执行阻塞原因和候选固定工作流，而不再只生成一句摘要文案。
- AI planner 当前会同步返回 `declarative_scripts` 草案列表，用于表达单个 App 业务脚本的声明层结构。
- AI planner 当前会给 AI 对话入口提供控制流写法引导，并从用户提示词中抽取条件判断、等待、超时和成功标准等结构化线索。
- AI planner 当前会把声明脚本列表、主脚本摘要和阶段锚点写入 `resolved_payload._planner_declarative_*`，使声明层信息进入实际任务载荷。
- AI 草稿当前会为带保留价值的 failed/cancelled run 保留 continuation snapshot，因此失败但有价值的任务仍可继续编辑、继续执行和提取可复用项。
- 插件 manifest 当前支持 `ai_hints` 任务语义元数据；planner 的意图推断与 run asset 的蒸馏资格判定优先读取插件声明，而不是在 `core` 里硬编码现有任务族。
- workflow draft 当前只把 `accepted` 的终态计入蒸馏成功样本；已完成但未达蒸馏资格的运行会以 run asset 形式保留为可复用记忆。
- AI planner 当前会消费近期同 app / 同 objective / 同 branch 的 run asset，并在响应 `memory` 中返回最近终态、保留价值和复用提示。
- 任务语义层当前统一输出 run value profile、草稿 `exit`、`distill_assessment` 和 memory `reuse_priority`，用于同时回答“是否有蒸馏资格”“保留了什么价值”“再次下发优先复用什么”“现在统一该走哪一步”。
- AI 对话前端当前会直接消费 `execution.reuse_*`、草稿 `exit` 与 `distill_assessment`，在规划卡片和快捷历史中显示统一出口、复用优先级与蒸馏状态。
- AI 对话前端当前会在规划卡片中展示 `declarative_scripts` 草案列表，供用户在下发前查看脚本标题、角色、依赖、产出和阶段摘要。
- 前端主导航当前新增 `AI 工作台` 一级入口，并把原本分散的草稿历史与运行洞察合并到同一工作台中展示。
- `AI 工作台` 当前会集中展示近期 AI 会话、运行中的 `agent_executor` 任务、草稿列表/详情、插件蒸馏进度、异常根因分布和 Prometheus 观测入口。
- `AI 工作台` 当前还提供任务设计表单，可先选择目标云机、应用、账号和提示词，再带着这些上下文进入设备详情中的完整 AI 设计器。
- `AI 工作台` 当前会直接请求 `POST /api/ai_dialog/planner` 并在工作台内预览执行摘要、控制流提示与声明脚本草案，不必先进入设备详情才能看到 planner 结果。
- `AI 工作台` 当前可直接基于该页面中的 planner 结果下发 `agent_executor` 任务，并沿用统一的 AI 执行浮层。
- `AI 工作台` 当前会把近期 AI 会话以工作台原生动作形式展示，支持载入到当前设计表单、蒸馏和保存可复用项，而不必退回旧弹窗完成这些操作。
- `AI 工作台` 当前会为选中的历史会话在侧栏原生展示复用优先级、失败建议、最近运行资产和 `declarative_binding`，减少对旧设备 AI 弹窗历史视图的依赖。
- `AI 工作台` 当前会在页面内展开完整设计器扩展区，用于展示执行门槛、补充信息和参考会话锚点，不再把“打开完整 AI 设计器”按钮绑定到旧设备弹窗语义。
- 设备详情中的 `AI 对话` 接口当前仍然保留，但职责已收敛为单设备快速发起、执行和人工接管入口；历史沉淀与蒸馏复用统一回到 AI 工作台。
- 草稿详情当前只保留验证、蒸馏和配置收敛信息；失败建议、会话复用和阶段锚点不再在草稿区重复展开。
- `agent_executor` 当前会把 planner 抽取出的控制流摘要、声明脚本摘要与阶段锚点写入 runtime planner artifact，让本次执行和后续蒸馏都能复用这些提示词线索。
- `agent_executor` 当前会在 observation / action_result / pause / terminal 结果中持续产出 `current_declarative_stage`，让探索态、接管态和蒸馏态共享同一阶段定位。
- 人工接管与设备轻控制当前都可携带 `current_declarative_stage`；后端会把它写入 takeover 事件和 human trace。
- workflow draft 当前会在摘要、continuation snapshot 与 distill 响应中统一暴露 `declarative_binding`，把声明脚本摘要和最近阶段上下文绑定到可复用样本上。
- `agent_executor` 当前会在缺少 `routes/hops` 时收紧 `ui.navigate_to` 规划权限，并支持“返回主页即完成”这类分支型业务目标的通用完成判定。
- `agent_executor` 当前会对 app 级 AI 任务使用更高的默认步数预算，并在最近步骤存在真实进展时最多做两轮尾部延长；如果 planner 连续给出无效运行时契约的动作参数，会提前终止而不是继续白跑。
- AI 对话历史当前把 `can_replay`、`can_edit`、`can_save` 分开计算；`保存可复用项` 的候选提取会优先使用最近 completed task，没有则回退到最近 terminal task，因此 failed/cancelled 但保留价值的 AI 任务也能继续沉淀数据。
- 后端仍保留 `/web` 入口，但前端是独立的 Vite 工程，部署方式见 [FRONTEND.md](FRONTEND.md)。
- 当前仓库存在 11 个已加载插件：
  - `app_config_explorer`
  - `device_reboot`
  - `one_click_new_device`
  - `x_clone_profile`
  - `x_follow_followers`
  - `x_home_interaction`
  - `x_login`
  - `x_nurture`
  - `x_quote_intercept`
  - `x_reply_dm`
  - `x_scrape_blogger`
- 当前动作目录支持按 `tag` 过滤，并提供 `/api/engine/skills` 作为 AI-facing skill 集合。
- `GET /api/tasks/catalog/apps` 当前会返回 app 标识、展示名、别名与包名集合，用于前端和 AI 任务入口对齐共享 app 身份。

## 当前明确不声明的内容

- 不声明任何未来路线图、阶段名、里程碑计划。
- 不声明浏览器 hands-on QA 已完整完成。
- 不声明 WebRTC 接管、自动 promotion pipeline 等未在当前代码和当前验证里锁定的能力。
