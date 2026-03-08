# Atomic Features Checklist

> 目标：把当前项目能力拆成“可独立验收”的最小原子功能，便于发布前逐项核对。

## 1. Service & Entry

- `GET /`
- `GET /health`
- `POST /api/runtime/execute`（debug/internal-only direct-run；不进入 `/api/tasks` 托管生命周期）
- `GET /web`
- `GET /ws/logs`

## 2. Device & Topology (`/api/devices`)

- `GET /api/devices`（`availability=all|available_only`）
- `GET /api/devices/{device_id}`
- `GET /api/devices/{device_id}/status`
- `POST /api/devices/{device_id}/start`
- `POST /api/devices/{device_id}/stop`
- `POST /api/devices/discover`（手动强制扫描）
- 扫描结果回写 `total_devices` + `device_ips`
- 云机端口拓扑字段返回（api/rpa/sdk）
- 云机可用性字段返回（availability/probe）
- 云机机型字段返回（`machine_model_name` / `machine_model_id`）

## 3. Config (`/api/config`)

- `GET /api/config`
- `PUT /api/config`
- `device_ips` 合法性/范围/重复校验
- `discovery_enabled` / `discovery_subnet` 配置
- `discovered_device_ips` / `discovered_total_devices` 输出
- humanized 配置读写

## 4. Tasks (`/api/tasks`)

- `GET /api/tasks/catalog`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tasks/{task_id}/events` (SSE)
- `GET /api/tasks/metrics`
- `GET /api/tasks/metrics/prometheus`

## 5. Data (`/api/data`)

- `GET /api/data/accounts`
- `POST /api/data/accounts/import`
- `POST /api/data/accounts/status`
- `POST /api/data/accounts/pop`
- `GET /api/data/accounts/parsed`
- `GET/PUT /api/data/location`
- `GET/PUT /api/data/website`

## 6. Engine / Plugin / Actions

- Runner + Interpreter 执行链路
- 条件/跳转/失败策略
- 插件加载（当前内置：`x_mobile_login`、`mytos_device_setup`、`device_reboot`、`device_soft_reset`、`blogger_scrape`、`profile_clone` 及互动类插件）
- 浏览器动作（open/input/click/exists/check_html/wait_url/add_cookies/close）
- 凭据动作（`credentials.load`、`credentials.checkout`）
- Core 动作（共享数据、TOTP、X 登录阶段检测/等待）
- UI/RPC 动作（点击/滑动/输入/按键/截图/节点查询等）
- SDK/MYTOS 动作绑定（`engine/actions/sdk_actions.py`）

## 7. Adapters

- BrowserClient 拟人化执行 + 失败降级
- MytRpc 跨平台动态库选择
- Browser diagnostics：`GET /api/diagnostics/browser`

## 8. Web Console

- 云机大厅与设备/云机状态展示
- 单机任务下发与批量选机下发
- 账号池导入预览、库存展示、ready 账号批量分派
- 实时日志 WebSocket 订阅与过滤
- 配置编辑与保存
- 局域网扫描触发
- humanized 预设（高/中/低）
- 任务管理模块代码已实现，但当前未在 `web/index.html` 暴露独立任务页入口


## 9. Quality Gates

- 无 legacy 导入：`tools/check_no_legacy_imports.py`
- 全量测试通过：`pytest tests -q`
- RPC 关闭可启动 + `/health` 通过

## Quick Verify Commands

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```
