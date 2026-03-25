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
- AI 工作台当前采用三栏布局：左侧为设计输入区，中间为任务图主画布，右侧为参考上下文区。

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

- AI 相关的主导航入口当前是 `AI 工作台`，并且它是唯一的任务图设计主入口。
- AI 工作台当前遵循显式设计流程：先选择目标云机、任务描述、应用和账号，再点击“开始设计任务图”生成草案；确认任务图后才能下发执行。
- 任务图主画布当前固定显示在 AI 工作台主区，不再通过“展开完整设计器”这类隐藏入口承载设计主流程。
- 任务图草案当前为只读展示，用于确认控制流、声明脚本、成功/失败出口、人工接管点和执行门槛；当前不支持节点级手工编辑。
- AI 工作台右侧参考上下文区当前统一展示历史 AI 会话、最近运行资产、失败建议和蒸馏线索；历史会话只保留两类动作：作为当前设计参考、继续编辑草稿。
- AI 工作台当前仍可直接下发 `agent_executor` 任务，并在成功后进入统一执行视图。
- 设备详情中的 `AI 对话` 接口继续保留，但当前只负责单设备快速发起、执行观察和人工接管；任务图设计、历史复用和蒸馏沉淀统一收口到 AI 工作台。
- 设备视图中的 AI 对话弹窗当前不会在输入期自动规划；执行摘要会在真正准备执行时生成，用于当前单任务执行判断。
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
