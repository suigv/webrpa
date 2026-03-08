# heziSDKAPI 真机 Smoke Payload

适用日期：`2026-03-07`

说明：
- 现在可以直接通过插件 `hezi_sdk_probe` 做只读验证。
- 这个探针覆盖的是 heziSDKAPI 主链路里的“基础可达性 + 只读查询”。
- 写操作和文件导入导出仍建议在确认探针通过后，再单独做真实业务验证。

## 1. 同步验证 SDK 主链路

> `POST /api/runtime/execute` 在这里是 debug/internal-only 的同步直跑入口；如果你需要托管任务、重试、取消或事件流，请改用 `POST /api/tasks/`。

覆盖：
- `sdk.get_api_version`
- `sdk.get_device_info`
- `sdk.get_server_network`
- `sdk.list_androids`
- `sdk.list_backups`
- `sdk.list_vpc_groups`
- `sdk.list_local_phone_models`
- 可选：`sdk.get_cloud_status`

```bash
curl -s http://127.0.0.1:8000/api/runtime/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "hezi_sdk_probe",
    "device_ip": "192.168.1.20",
    "sdk_port": 8000,
    "android_name": "android-01"
  }' | jq
```

期望：
- `status = success`
- `message` 包含 `hezi sdk probe completed`

## 2. 异步提交 SDK 探针任务

> 这才是带有任务控制面语义的入口，会落入 `/api/tasks` 的托管生命周期。

```bash
curl -s http://127.0.0.1:8000/api/tasks/ \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "hezi_sdk_probe",
    "payload": {
      "device_ip": "192.168.1.20",
      "sdk_port": 8000,
      "android_name": "android-01"
    }
  }' | jq
```

查询详情：

```bash
curl -s http://127.0.0.1:8000/api/tasks/<task_id> | jq
```

事件流：

```bash
curl -N http://127.0.0.1:8000/api/tasks/<task_id>/events
```

## 3. 本地逐个验证 `sdk.*` 原子动作

如果你要逐个确认盒子 SDK 动作，不想走插件，当前最短调用方式是：

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
    ("sdk.get_api_version", {}),
    ("sdk.get_device_info", {}),
    ("sdk.get_server_network", {}),
    ("sdk.list_androids", {}),
    ("sdk.list_backups", {}),
    ("sdk.list_vpc_groups", {}),
]:
    result = reg.resolve(action)(params, ctx)
    print(action, result.ok, result.code, result.data)
PY
```

## 4. 结果判断

- `sdk_call_failed`：SDK 服务没起来、地址不对，或接口返回异常
- `invalid_params`：参数缺失或类型不对
- `failed_config_error`：任务或插件名不对

## 5. 后续顺序

建议顺序：
1. `hezi_sdk_probe`
2. `mytos_device_setup`
3. `x_mobile_login`
