# webrpa

一个可独立运行的 Web/RPA 自动化平台，当前仓库确认包含：

- 设备与拓扑管理
- 托管任务系统
- YAML 插件执行引擎
- AI 对话与 `agent_executor` 托管入口
- 独立 Vite 前端控制台

## 快速开始

### 1) 创建环境并安装依赖

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

### 2) 启动后端

```bash
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

纯 Web / 无 RPC 路径：

```bash
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

### 3) 健康检查

```bash
curl http://127.0.0.1:8001/health
```

### 4) 启动前端

```bash
cd web
npm install
npm run dev
```

生产部署和 `/web` 行为见 `docs/FRONTEND.md`。

## 文档系统

仓库现在只保留当前文档，不再保留历史日志、路线图、计划文档和参考副本。

- 文档入口：`docs/README.md`
- 当前状态：`docs/STATUS.md`
- 当前 API：`docs/HTTP_API.md`
- 当前插件契约：`docs/PLUGIN_CONTRACT.md`
- 当前配置：`docs/CONFIGURATION.md`
- 当前前端约束：`docs/FRONTEND.md`
- AI 进入仓库顺序：`docs/AI_ONBOARDING.md`

文档 freshness 校验：

```bash
./.venv/bin/python tools/check_docs_freshness.py
```

## AI 协作建议

如果你使用 Codex / OpenCode 在本仓库内协作开发，建议在提示词里显式带上 `$webrpa-dev`。

示例：

```text
$webrpa-dev 帮我看 task_control 的重构边界
$webrpa-dev 帮我修 web 控制台的 SSE 页面
$webrpa-dev 帮我给 plugins 新增一个 workflow
```

## 质量与验证

常用验证命令：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
./.venv/bin/python tools/check_docs_freshness.py
```

## 约束

- 不引入 `tasks` / `app.*` 历史依赖
- 业务流程优先插件化
- 路由保持薄层，核心逻辑下沉到 `core/` 与 `engine/`
- 运行数据留在 `config/data/`
