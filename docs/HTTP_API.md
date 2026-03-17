# HTTP API（WebRPA 自身服务）

本文件只描述 **webrpa 服务本身**暴露的 HTTP / WebSocket API（FastAPI）。设备 SDK（8000）、MYTOS Android API（api_port）与 RPA SDK（rpa_port）请分别参考：
- `docs/MYT_SDK_API.md`
- `docs/MYTOS_API.md`
- `docs/ANDROID_RPA_SDK.md`

> 交互式 OpenAPI：启动服务后访问 `/docs`。

---

## 1) 基础与控制台

- `GET /health`：健康检查，返回运行策略快照与已加载插件列表。
- `GET /web`：控制台入口（静态页面）。
- `WS /ws/logs`：实时日志流（WebSocket）。

---

## 2) Runtime 直跑（debug/internal-only）

- `POST /api/runtime/execute`：同步执行 runtime payload，不进入 `/api/tasks` 托管链路（无重试/取消/SSE/指标）。

---

## 3) 配置读写（在线修改 `config/system.yaml` 相关项）

- `GET /api/config/`：读取当前运行配置视图（用于前端展示）。
- `PUT /api/config/`：更新配置（用于在线调参/修改 host_ip、device_ips、Location/Website 等）。

---

## 4) 数据与账号池（SQLite）

账号池与业务文本使用 `config/data/` 下的 SQLite 数据库/文件存储（详见 `docs/CONFIGURATION.md`）。

- `GET /api/data/accounts`：获取账号列表。
- `POST /api/data/accounts/import`：导入账号数据（可能触发从旧格式迁移）。
- `GET /api/data/accounts/parsed`：获取解析后的账号视图。
- `POST /api/data/accounts/pop`：原子抽号（取一个可用账号）。
- `POST /api/data/accounts/reset`：重置账号池状态（运维/回归用途）。
- `POST /api/data/accounts/status`：更新账号状态（如 ready/blocked 等）。
- `POST /api/data/accounts/update`：更新账号字段。

- `GET /api/data/location` / `PUT /api/data/location`：读取/更新 Location 文本。
- `GET /api/data/website` / `PUT /api/data/website`：读取/更新 Website 文本。

---

## 6) 设备与云机（拓扑与探测）

- `GET /api/devices/`：设备列表（包含云机端口映射信息）。
- `GET /api/devices/{device_id}`：设备详情。
- `GET /api/devices/{device_id}/status`：设备状态。
- `POST /api/devices/{device_id}/start`：启动设备（runtime_stub 模式下为占位实现）。
- `POST /api/devices/{device_id}/stop`：停止设备（runtime_stub 模式下为占位实现）。
- `POST /api/devices/discover`：局域网设备发现（当前也兼容 `POST /api/devices/discover/`）。
- `GET /api/devices/{device_id}/{cloud_id}/screenshot`：云机截图（`MYT_ENABLE_RPC=0` 时会返回 503）。

---

## 7) 任务系统（托管执行）

- `POST /api/tasks/`：创建任务（插件任务或匿名脚本任务）。
- `GET /api/tasks/`：任务列表。
- `GET /api/tasks/{task_id}`：任务详情（含 result / error）。
- `GET /api/tasks/{task_id}/events`：任务事件流（SSE）。

### 7.1 任务取消与清理
- `POST /api/tasks/{task_id}/cancel`：取消任务（等价于“更显式”的取消入口）。
- `POST /api/tasks/cleanup_failed`：清理 failed/cancelled 任务及相关运行产物（兼容 `DELETE`）。
- `DELETE /api/tasks/`：清空任务（运维用途，谨慎使用）。
- `POST /api/tasks/device/{device_id}/stop`：停止某设备的所有活跃任务（运维用途）。

### 7.2 任务目录与模板
- `GET /api/tasks/catalog`：插件/任务目录（用于前端下拉与校验）。
- `GET /api/tasks/catalog/apps`：已发现的 app 配置列表（来自 `config/apps/*.yaml`）。
- `GET /api/tasks/prompt_templates`：默认提示词列表（当前收敛为单一默认模板，来自 `engine/prompt_templates.py`）。

### 7.3 指标
- `GET /api/tasks/metrics`：JSON 指标。
- `GET /api/tasks/metrics/prometheus`：Prometheus 抓取格式。
- `GET /api/tasks/metrics/plugins`：按插件聚合的成功次数与蒸馏进度。

### 7.4 蒸馏
- `POST /api/tasks/distill/{plugin_name}`：触发插件蒸馏（受 `distill_threshold` 与目录边界约束）。

---

## 8) Engine 自描述（Action Schema）

- `GET /api/engine/schema`：动作元数据（用于 AI/前端发现可用 action；默认返回带 `skill` 标签的动作集合）。

---

## 9) 浏览器诊断

- `GET /api/diagnostics/browser`：浏览器能力/依赖诊断（DrissionPage/CDP 可用性等）。
