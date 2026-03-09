# 真机最小验证 Payload

适用日期：`2026-03-07`

说明：
- 当前外部 HTTP 接口直接暴露的是“任务执行”，不是“任意原子 action 执行”。
- 所以对外最短路径是：
  - `POST /api/runtime/execute` 用 debug/internal-only 同步直跑做快速验证；它不会创建 `/api/tasks` 托管任务、重试、取消、事件流或指标副作用
  - `POST /api/tasks/` 用异步任务做真实调度验证
- 如果你要逐个验证 `mytos.*` 原子动作，当前最短路径是本地 Python 调用 `ActionRegistry`。

## 1. 启动前检查

```bash
curl -s http://127.0.0.1:8000/health | jq
```

## 2. 同步验证 `mytos_device_setup`

> 该入口适合 smoke/debug 验证；需要可追踪任务生命周期时，请改用 `POST /api/tasks/`。

这条会覆盖：
- `mytos.query_adb_permission`
- `mytos.switch_adb_permission`
- `mytos.set_language_country`
- `mytos.get_app_bootstart_list`
- `mytos.set_app_bootstart`
- `mytos.get_root_allowed_apps`
- `mytos.set_root_allowed_app`
- `mytos.get_container_info`

```bash
curl -s http://127.0.0.1:8000/api/runtime/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "mytos_device_setup",
    "device_ip": "192.168.1.20",
    "sdk_port": 8000,
    "package": "com.twitter.android",
    "language": "en",
    "country": "US",
    "enable_app_bootstart": true,
    "allow_root": true
  }' | jq
```

期望：
- `status = success`
- `message` 包含 `mytos device setup completed`

## 3. 同步验证 `x_mobile_login` 入口连通性

> 该入口仍是 direct-run smoke/debug surface，不会产出托管任务记录或任务事件。

这条不会真的登录，只验证：
- RPA 连接
- App 拉起
- 节点模式切换
- 登录页阶段识别

```bash
curl -s http://127.0.0.1:8000/api/runtime/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "x_mobile_login",
    "device_ip": "192.168.1.20",
    "package": "com.twitter.android",
    "acc": "demo_user",
    "pwd": "demo_pass",
    "status_hint": "runtime"
  }' | jq
```

期望：
- 如果设备/RPA 不通，返回 `device_connection_failed`
- 如果流程真的进入登录判断，返回值会落在：
  - `login completed`
  - `bad credentials`
  - `captcha`
  - `missing_2fa`
  - `login_not_confirmed`

## 4. 异步提交真实登录任务

> `POST /api/tasks/` 是托管任务入口；当前必须显式提供 `targets`（推荐）或兼容输入 `devices`。缺失目标的托管任务请求会被拒绝，不再隐式回落到默认设备。

提交前可先查看 catalog，确认当前插件 manifest 暴露的输入字段：

```bash
curl -s http://127.0.0.1:8000/api/tasks/catalog | jq
```

异步提交示例：

```bash
curl -s http://127.0.0.1:8000/api/tasks/ \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "x_mobile_login",
    "payload": {
      "package": "com.twitter.android",
      "acc": "your_account",
      "pwd": "your_password",
      "two_factor_code": "",
      "fa2_secret": "",
      "status_hint": "runtime"
    },
    "targets": [
      { "device_id": 1, "cloud_id": 2 }
    ],
    "priority": 50,
    "max_retries": 0,
    "retry_backoff_seconds": 2,
    "run_at": null
  }' | jq
```

列表查询：

```bash
curl -s http://127.0.0.1:8000/api/tasks/ | jq
```

重点字段：
- 列表项名称看 `task_name`，不是旧的 `display_name`
- 目标设备看 `targets`
- 任务生命周期建议结合 SSE 事件流观察

查询详情：

```bash
curl -s http://127.0.0.1:8000/api/tasks/<task_id> | jq
```

详情重点字段：
- `result`：任务执行结果对象
- `error`：失败原因文本
- 不再依赖旧的 `payload` / `message` 字段表达结果

查看事件流：

```bash
curl -N http://127.0.0.1:8000/api/tasks/<task_id>/events
```

补充说明：
- `DELETE /api/tasks/` 清理的是托管任务状态与对应事件流水，不是整套 runtime/full reset。
- 如果仍有 `running` 任务，清理会被拒绝，避免把运行态与历史事件清到不一致状态。
- `config/data/tasks.db` 是运行时 SQLite 产物，不应作为源码提交。
- `config/data/.migration_shared.json.lock` 是共享 JSON 存储的预期 lock artifact，应忽略而不是纳入版本控制。

## 5. 本地逐个验证 `mytos.*` 原子动作

如果你要逐个确认新增原子动作，当前最短调用方式是：

```bash
./.venv/bin/python - <<'PY'
from engine.action_registry import ActionRegistry, register_defaults
from engine.models.runtime import ExecutionContext
from engine import action_registry as reg_mod

reg = ActionRegistry()
reg_mod._registry = reg
register_defaults()

ctx = ExecutionContext(payload={"device_ip": "192.168.1.20", "sdk_port": 8000})

for action, params in [
    ("mytos.query_background_keepalive", {}),
    ("mytos.tap", {"x": 540, "y": 1200}),
    ("mytos.keypress", {"code": "KEYCODE_ENTER"}),
    ("mytos.get_webrtc_player_url", {"index": 1}),
]:
    result = reg.resolve(action)(params, ctx)
    print(action, result.ok, result.code, result.data)
PY
```

重点看：
- `mytos.tap`
- `mytos.keypress`
- `mytos.query_background_keepalive`
- `mytos.get_webrtc_player_url`

## 6. 结果判断

- `device_connection_failed`：RPA 端口或云机索引不对
- `rpc_connect_failed`：RPA 服务没起来
- `sdk_call_failed`：SDK 8000 端口没起来或接口异常
- `login_not_confirmed`：动作执行了，但没有明确识别到 `home/captcha/2fa/password/account`
