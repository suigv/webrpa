# AI 项目指南（独立版 `new/`）

## 1）项目定位

`new/` 是可独立复制与运行的基线工程。

设计目标：
- 保留可复用基础能力（API / core / models / adapters）
- 移除历史任务实现耦合
- 运行时保持插件化架构
- 支持仅复制 `new/` 即可独立开发

## 2）运行时总览

请求链路：
1. `new/api/server.py` 启动 FastAPI 并挂载基础路由。
2. `new/api/server.py` 在 `/web` 提供控制台页面。
3. 配置/数据/设备路由调用 `new/core/*`。
4. `/api/runtime/execute` 调用 `new/engine/runner.py`。
5. `Runner` 结合 `new/engine/parser.py` 处理脚本并返回结构化结果。
6. 可选 RPC 能力由 `new/hardware_adapters/myt_client.py` 提供。
7. 可选浏览器能力由 `new/hardware_adapters/browser_client.py`（vendored DrissionPage）提供。

## 3）模块职责（按目录）

### 根目录
- `README.md`：人类开发者使用说明（安装、启动、验证）
- `AI_PROJECT_GUIDE.md`：本 AI 架构与职责说明
- `requirements.txt`：独立依赖清单

### API 层
- `api/server.py`：应用入口、中间件、路由注册、`/health`
- `api/routes/config.py`：配置读写
- `api/routes/data.py`：业务数据读写
- `api/routes/devices.py`：设备状态与基础控制
- `api/routes/websocket.py`：日志 websocket（`/ws/logs`）
- `web/*`：控制台静态资源

### Core 层
- `core/config_loader.py`：配置加载与更新
- `core/data_store.py`：`new/config/data` 下 JSON 存储
- `core/device_manager.py`：设备状态管理
- `core/port_calc.py`：端口计算逻辑

### Model 层
- `models/config.py`：配置模型
- `models/device.py`：设备模型
- `models/task.py`：任务请求/响应模型
- `models/judge.py`：执行判定模型

### 引擎层
- `engine/parser.py`：脚本归一化解析
- `engine/runner.py`：执行编排
- `engine/action_registry.py`：动作注册/解析
- `engine/actions/*`：动作实现（browser / credential / ui / sdk）
- `engine/plugin_loader.py`：插件发现与加载

### 适配器层
- `hardware_adapters/myt_client.py`：SDK/MYTOS HTTP 客户端（含回退兼容）
- `hardware_adapters/mytRpc.py`：RPA 原生库封装（惰性加载 + failure-safe）
- `hardware_adapters/browser_client.py`：浏览器能力适配

### 其他
- `plugins/`：业务插件
- `config/`：配置与数据
- `tests/`：测试集
- `tools/check_no_legacy_imports.py`：旧依赖静态门禁
- `docs/`：迁移矩阵、接口矩阵、功能可用性文档

## 4）质量门禁与自动化

最低要求：
- 静态门禁通过
- 全量测试通过
- RPC 禁用模式可启动
- `/health` 返回 200

建议命令（项目父目录执行）：

```bash
./new/.venv/bin/python new/tools/check_no_legacy_imports.py
./new/.venv/bin/python -m pytest new/tests -q
MYT_NEW_ROOT=$(pwd)/new MYT_ENABLE_RPC=0 ./new/.venv/bin/python -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

## 5）开发建议顺序

1. 优先在 `engine/` 补齐动作与编排能力。
2. 新业务流程优先放在 `plugins/`，避免路由耦合业务。
3. 适配器功能保持“可选、可降级、可恢复”。
4. 每次能力扩展都补测试（单测 + 集成校验）。

## 6）硬约束（请持续遵守）

- 禁止重新引入 `tasks` / `app.*` 历史依赖。
- 数据文件必须落在 `new/config/data`。
- 路由保持薄层，核心逻辑下沉到 `core/` 与 `engine/`。
