---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-25
stale_after_days: 14
verification_method:
  - web/ tree audit
  - backend /web behavior audit
---

# Frontend

当前前端是 `web/` 下的独立 Vite 工程。后端不是前端静态文件服务器。

控制台当前采用单页分栏结构：

- 顶部为品牌区、系统状态区和主导航。
- 主内容区包含统一总览 Hero，并在其下切换设备、AI 工作台、任务、资源、配置等 tab。
- 设备视图会在页面总览区同步展示节点总量、在线数、占用数和已锁定数。
- AI 工作台当前整合了统一 AI 入口说明、任务设计表单、planner 结果预览、近期 AI 会话列表与原生详情面板、运行中的 AI 执行协作、草稿列表/详情，以及 AI 相关运行洞察与蒸馏进度。

## 本地开发

后端：

```bash
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

前端：

```bash
cd web
npm install
npm run dev
```

如需无 RPC 的纯 Web 路径：

```bash
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

## 部署边界

- 前端构建产物位于 `web/dist/`。
- 推荐由 Nginx 或其他静态服务器托管 `web/dist/`。
- 后端保留 `/web` 作为入口路由：
  - 配置 `MYT_FRONTEND_URL` 时重定向到前端地址。
  - 未配置时返回部署提示。
- 仓库当前不再提供 `webplayer` 静态播放页；人工接管仍走任务接管接口和设备轻控制接口。

## AI 对话当前界面

- AI 相关的主导航入口当前是 `AI 工作台`；工作台会先选择目标云机、任务描述、应用和账号，并直接展示 planner 返回的执行摘要、控制流提示和声明脚本草案。
- AI 工作台当前可直接从该页面下发 `agent_executor` 任务，并在成功后进入统一执行视图。
- AI 工作台当前支持把历史 AI 会话载入到当前设计表单中，再基于同一条工作台链路继续编辑、蒸馏或重新执行。
- AI 工作台当前会为选中的历史会话直接展示复用优先级、最近运行资产、失败建议和 `declarative_binding`，尽量不再依赖旧弹窗承担历史查看职责。
- 工作台当前会在页面内展开“完整设计器”扩展区，用于继续查看执行门槛、补充信息和参考会话锚点；不再通过该按钮强依赖旧设备弹窗语义。
- 设备详情中的 `AI 对话` 接口继续保留，但当前只负责单设备快速发起、执行和人工接管；历史沉淀、失败建议与蒸馏复用统一收口到 AI 工作台。
- 设备视图中的 AI 对话弹窗当前会显示 planner 返回的执行摘要、控制流提示、声明脚本草案和后续建议。
- 声明脚本草案当前为只读展示，用于帮助用户确认脚本标题、角色、阶段和依赖产出摘要；还不支持前端逐项编辑。
- AI 对话弹窗和设备详情轻控制当前会在 SSE 事件、接管请求和人工轻控制 trace 中持续透传 `currentDeclarativeStage`，保证人工接管时仍知道当前停留在哪个声明阶段。

## 前端任务提交契约

- 任务表单应来自 `GET /api/tasks/catalog`。
- 插件提交必须遵守 `manifest.inputs` 白名单。
- `targets` 承载目标设备上下文。
- 不要让前端重新把 `device_ip`、`package`、目标元数据之类的运行时字段塞回插件 `payload`。

## 鉴权

启用 JWT 时：

- HTTP 使用 `Authorization: Bearer <jwt>`
- 浏览器 WebSocket 使用 `Sec-WebSocket-Protocol: bearer.<jwt>`
