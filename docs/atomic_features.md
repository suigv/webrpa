# Atomic Features Checklist

> 目标：把当前项目能力拆成“可独立验收”的最小原子功能，便于发布前逐项核对。

## 1. Service & Entry

- `GET /`
- `GET /health`
- `POST /api/runtime/execute`
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

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tasks/{task_id}/events` (SSE)

## 5. Data (`/api/data`)

- `GET/PUT /api/data/accounts`
- `POST /api/data/accounts/import`
- `GET /api/data/accounts/parsed`
- `GET/PUT /api/data/location`
- `GET/PUT /api/data/website`

## 6. Engine / Plugin / Actions

- Runner + Interpreter 执行链路
- 条件/跳转/失败策略
- 插件加载（当前内置：`plugins/x_auto_login`）
- 浏览器动作（open/input/click/exists/check_html/wait_url/close）
- 凭据动作（`credentials.load`）
- UI/RPC 动作（点击/滑动/输入/按键/截图/节点查询等）
- SDK/MYTOS 动作绑定（`engine/actions/sdk_actions.py`）

## 7. Adapters

- BrowserClient 拟人化执行 + 失败降级
- MytRpc 跨平台动态库选择

## 8. Web Console

- 设备/云机状态展示
- 云机机型展示
- 任务管理 + 事件流显示
- 配置编辑与保存
- 局域网扫描触发
- humanized 预设（高/中/低）

## 9. Quality Gates

- 无 legacy 导入：`new/tools/check_no_legacy_imports.py`
- 全量测试通过：`pytest new/tests -q`
- RPC 关闭可启动 + `/health` 通过

## Quick Verify Commands

```bash
./new/.venv/bin/python new/tools/check_no_legacy_imports.py
./new/.venv/bin/python -m pytest new/tests -q
MYT_NEW_ROOT=$(pwd)/new MYT_ENABLE_RPC=0 ./new/.venv/bin/python -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```
