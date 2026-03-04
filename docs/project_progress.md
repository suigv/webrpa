# Project Progress

> 本文档用于持续记录项目当前可用能力、完成状态和下一步计划。
> 自动快照区由 `tools/update_project_progress.py` 生成，请勿手工修改该区块。

## 1. 当前阶段

- 阶段：**可独立运行的 v1 可用态**
- 核心状态：API、任务系统、插件执行、Web 控制台、配置管理、适配器降级均可用
- 最近重点：
  - Web 端拟人化配置新增高/中/低档位
  - MytRpc 动态库加载支持 Linux(arm/x86)、macOS、Windows 自动匹配与环境变量覆盖

## 2. 已实现功能清单

### 2.1 API 与控制面

- 健康检查、运行时执行、Web 控制台入口（`api/server.py`）
- 设备管理：列表/详情/状态/启停（`api/routes/devices.py`）
- 任务管理：创建/列表/详情/取消 + SSE 事件流（`api/routes/task_routes.py`）
- 配置管理：读取/更新系统配置与 humanized 配置（`api/routes/config.py`）
- 数据接口：账号/位置/网站读写与账号导入解析（`api/routes/data.py`）
- 日志 WebSocket 推送（`api/routes/websocket.py`）

### 2.2 引擎与插件

- Runner + Interpreter 工作流执行（`engine/runner.py`, `engine/interpreter.py`）
- 条件、跳转、等待、失败策略（`engine/conditions.py`, `engine/models/*`）
- 插件扫描与加载（`engine/plugin_loader.py`）
- 示例插件：`plugins/x_auto_login`（manifest + script）

### 2.3 适配器与动作

- 浏览器动作：open/input/click/exists/wait/check_html/close（`engine/actions/browser_actions.py`）
- 账号凭据动作：`credentials.load`（`engine/actions/credential_actions.py`）
- UI/RPC 动作：点击、滑动、输入、按键、截图、节点查询等（`engine/actions/ui_actions.py`）
- SDK 动作绑定（`engine/actions/sdk_actions.py`）
- BrowserClient 拟人化与降级兜底（`hardware_adapters/browser_client.py`）
- MytRpc 跨平台动态库选择（`hardware_adapters/mytRpc.py`）

### 2.4 前端控制台

- 多 Tab 控制台（监控、任务、账号、配置）
- 配置页支持拟人化参数编辑 + 高/中/低档位快捷设置（`web/index.html`, `web/app.js`）
- 实时日志、任务详情、事件监听

### 2.5 质量保障

- 关键门禁脚本：`tools/check_no_legacy_imports.py`
- 测试覆盖：API、任务、配置迁移、插件、适配器、Web smoke、跨平台库选择等（`tests/`）

## 3. 自动统计快照

<!-- AUTO_PROGRESS_SNAPSHOT:START -->
- Last generated (UTC): `2026-03-04T13:31:36.841777+00:00`
- Source: `tools/update_project_progress.py`

| Metric | Value |
|---|---:|
| API route decorators (`api/routes`) | 21 |
| App-level route decorators (`api/server.py`) | 4 |
| Plugin count (`plugins/*/manifest.yaml`) | 1 |
| SDK action bindings (`engine/actions/sdk_actions.py`) | 44 |
| Test files (`tests/test_*.py`) | 33 |
| Test functions (`def test_*`) | 95 |
<!-- AUTO_PROGRESS_SNAPSHOT:END -->

## 4. 维护方式（实时更新建议）

每次“有意义变更”后执行：

```bash
./new/.venv/bin/python new/tools/update_project_progress.py
```

推荐在以下时机执行：

1. 合并功能分支前
2. 每次完成测试与验证后
3. 发布前（用于生成最新项目快照）

## 5. 下一步建议（滚动）

1. 将 FastAPI 生命周期从 `on_event` 迁移到 `lifespan`。
2. 引入基础可观测性（trace + 关键指标）。
3. 增强插件安全边界（动作白名单/参数校验）。
4. 持续完善任务系统可靠性（幂等与失败恢复策略）。
