# WebRPA 项目助手配置

## 项目概述
Web/RPA 自动化平台：FastAPI + 插件化执行引擎 + 浏览器自动化
- 设备与拓扑管理（多设备、云机端口映射）
- 任务调度（优先级、定时、重试、SSE 事件流）
- YAML 工作流引擎 + 动作注册器
- Web 控制台（`/web` + `/ws/logs`）

## 技术栈
- **运行时**：Python 3.11+, FastAPI 0.115, uvicorn 0.32, Pydantic 2.9
- **通信**：WebSocket (websockets 13.1), SSE（任务事件流）
- **数据**：SQLite (config/data/tasks.db), JSON 配置
- **RPA**：DownloadKit/lxml/cssselect/浏览器自动化
- **AI**：VLM/LLM 客户端 (ai_services/)

## 目录结构
```
webrpa/
├── api/              # FastAPI 路由 (devices, tasks, websocket, config, data)
│   ├── server.py     # 应用入口，setup_routes()
│   └── routes/
├── core/             # 业务核心
│   ├── task_control.py    # TaskController，任务生命周期
│   ├── task_queue.py      # TaskQueue，优先级队列
│   ├── task_store.py      # TaskStore，SQLite 持久化
│   ├── task_events.py     # TaskEventEmitter，SSE 事件
│   ├── device_manager.py  # DeviceManager，设备/云机/端口管理
│   ├── data_store.py      # DataStore，JSON 数据管理
│   └── port_calc.py       # 端口计算逻辑
├── engine/           # 执行引擎
│   ├── interpreter.py     # WorkflowInterpreter，YAML 执行
│   ├── action_registry.py # @register_action 装饰器
│   ├── plugin_loader.py   # YAML 插件加载
│   ├── parser.py          # 工作流解析
│   ├── conditions.py      # 条件判断
│   └── actions/           # 内置动作
│       ├── browser_actions.py    # 浏览器：navigate, click, input...
│       ├── credential_actions.py # 凭据：load_credentials
│       ├── sdk_actions.py        # SDK：sdk_command
│       ├── ui_actions.py         # UI：screenshot, wait_element...
│       └── ai_actions.py         # AI：vlm_click, llm_parse
├── ai_services/      # AI 客户端
│   ├── llm_client.py
│   └── vlm_client.py
├── models/           # Pydantic 模型
│   └── humanized.py  # HumanizedConfig，拟人化配置
├── common/           # 工具
│   ├── config_manager.py   # 配置加载/热更新
│   ├── logger.py           # 结构化日志
│   ├── runtime_state.py    # 全局运行时状态
│   └── toolskit.py         # 通用工具
├── plugins/          # 插件目录
│   └── x_auto_login/       # X/Twitter 登录示例
├── config/           # 运行时配置
│   ├── devices.json        # 设备定义
│   └── data/               # 数据目录
│       ├── tasks.db        # SQLite 任务库
│       ├── accounts.json   # 账号数据
│       ├── website.json    # 网站配置
│       └── location.json   # 位置数据
├── tests/            # 测试
└── web/              # Web 控制台静态文件
```

## 核心命令（uv）

### 安装依赖
```bash
uv pip install -r requirements.txt
```

### 启动服务
```bash
uv run python api/server.py                 # 生产启动
uv run uvicorn api.server:app --reload      # 开发热重载
uv run uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### 调试任务
```bash
# 健康检查
curl http://localhost:8000/health | jq

# 任务指标
curl http://localhost:8000/api/tasks/metrics | jq

# SSE 事件流
curl -N http://localhost:8000/api/tasks/{task_id}/events

# WebSocket 日志
websocat ws://localhost:8000/ws/logs
```

### 代码检查
```bash
uv run ruff check api/ core/ engine/ ai_services/ common/
uv run ruff check --fix .
uv run ruff format .
```

## 开发约定

### 新增 API 路由
1. 在 `api/routes/` 创建模块（参考 `task_routes.py`, `devices.py`）
2. 在 `api/server.py:setup_routes()` 注册
3. 使用 `APITaskResponse` 等标准响应模型

### 新增引擎动作
1. 在 `engine/actions/` 添加模块
2. 使用装饰器注册：
   ```python
   from engine.action_registry import register_action
   
   @register_action("browser.navigate")
   async def browser_navigate(ctx, url: str, ...):
       ...
   ```
3. 动作第一个参数为 `ctx: ActionContext`
4. 参考 `browser_actions.py` 实现浏览器交互

### 任务系统关键类
- `TaskController` (core/task_control.py)：创建、启动、取消、重试任务
- `TaskQueue` (core/task_queue.py)：优先级队列，支持 `priority` / `run_at`
- `TaskStore` (core/task_store.py)：SQLite 持久化，任务状态查询
- `TaskEventEmitter` (core/task_events.py)：SSE 事件推送
- `WorkflowInterpreter` (engine/interpreter.py)：YAML 工作流执行

### 拟人化配置
- 配置类：`models/humanized.HumanizedConfig`
- 字段：鼠标移动节奏、点击延迟、输入速度、fallback 策略
- 用途：`browser_actions.py` 中的 `BrowserClient`

### 设备与端口
- `DeviceManager` (core/device_manager.py)：管理云机生命周期
- 端口分配：`port_calc.py`，每个设备返回 `api/rpa/sdk` 三个端口

### 配置热加载
- `ConfigManager` (common/config_manager.py)：监视 config/ 目录变更
- 使用 `watchdog` 实现，配置变更自动重载

### 日志与监控
- 结构化日志：`common/logger.py`，支持 JSON 输出
- Prometheus 指标：`/api/tasks/metrics/prometheus`
- 监控模板：`config/monitoring/`

## 禁止事项
- 不要直接操作 `config/data/tasks.db`，统一用 `TaskStore` API
- 不要在动作处理器中阻塞事件循环，使用 `async/await`
- 不要硬编码敏感信息，用 `credentials_loader` 或环境变量
- 不要修改 `PLUGIN_CONTRACT.md` 而不更新实现

## 插件开发
参考 `plugins/x_auto_login/`：
- `plugin.yaml`：定义工作流
- 使用内置动作组合复杂流程
- 支持变量插值：`{{ credentials.username }}`

## 调试技巧

### 查看任务执行流程
```bash
# 1. 创建任务
response=$(curl -s -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"name":"test","priority":10}')
task_id=$(echo $response | jq -r '.data.task_id')

# 2. 监听事件
curl -N http://localhost:8000/api/tasks/$task_id/events

# 3. 查询详情
curl http://localhost:8000/api/tasks/$task_id | jq
```

### 测试动作注册
```python
uv run python -c "
from engine.action_registry import list_actions
print('\\n'.join(list_actions()))
"
```
