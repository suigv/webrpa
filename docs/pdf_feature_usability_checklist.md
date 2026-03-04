# PDF 功能可用性对照清单

本文用于追踪「PDF 定义的能力」在项目中的落地状态：

- **客户端方法**：`hardware_adapters/myt_client.py` / `engine/actions/ui_actions.py`
- **运行时动作**：`engine/actions/sdk_actions.py` / `engine/action_registry.py`
- **测试证据**：`new/tests/*`

## 1）SDK（盒子内 SDK API）

| 功能 | 客户端方法 | 运行时动作 | 测试证据 |
|---|---|---|---|
| 设备信息与版本 | `get_device_info`, `get_api_version` | `sdk.get_device_info`, `sdk.get_api_version` | `test_sdk_complete.py::test_sdk_core_endpoint_mapping` |
| 云机生命周期 | `start_android`, `stop_android`, `restart_android`, `rename_android`, `exec_android`, `get_cloud_status` | `sdk.start_android`, `sdk.stop_android`, `sdk.restart_android`, `sdk.rename_android`, `sdk.exec_android`, `sdk.get_cloud_status` | `test_sdk_complete.py`, `test_sdk_actions_runtime.py` |
| 镜像相关 | `switch_image`, `switch_model`, `pull_image`, `list_images`, `prune_images` | `sdk.switch_image`, `sdk.switch_model`, `sdk.pull_image`, `sdk.list_images`, `sdk.prune_images` | `test_sdk_complete.py` |
| 备份文件 | `create_backup`（GET `/backup`）, `download_backup` | `sdk.create_backup`, `sdk.download_backup` | `test_sdk_complete.py` |
| 机型备份 | `backup_model`, `export_model`, `import_model` | `sdk.backup_model`, `sdk.export_model`, `sdk.import_model` | `test_sdk_complete.py::test_sdk_required_field_validation` |
| 本地模型列表/状态 | `list_models`（`/lm/local` → `/models` 回退） | `sdk.list_models` | `test_sdk_complete.py::test_sdk_fallback_endpoint_calls` |
| 本地模型导入导出 | `export_local_model`, `import_local_model` | `sdk.export_local_model`, `sdk.import_local_model` | `test_sdk_complete.py` |
| 认证 | `set_auth_password`, `close_auth` | `sdk.set_auth_password`, `sdk.close_auth` | `test_sdk_complete.py::test_sdk_required_field_validation` |

## 2）MYTOS

| 功能 | 客户端方法 | 运行时动作 | 测试证据 |
|---|---|---|---|
| S5 代理（查/设/停/过滤） | `query_s5_proxy`, `set_s5_proxy`, `stop_s5_proxy`, `set_s5_filter` | `mytos.query_s5_proxy`, `mytos.set_s5_proxy`, `mytos.stop_s5_proxy`, `mytos.set_s5_filter` | `test_mytos_complete.py::test_mytos_api_method_mapping` |
| 剪贴板 | `get_clipboard`, `set_clipboard` | `mytos.get_clipboard`, `mytos.set_clipboard` | `test_mytos_complete.py`, `test_sdk_actions_runtime.py` |
| 文件传输 | `download_file`, `upload_file` | `mytos.download_file`, `mytos.upload_file` | `test_sdk_complete.py` |
| 应用信息与安装 | `export_app_info`, `import_app_info`, `batch_install_apps` | `mytos.export_app_info`, `mytos.import_app_info`, `mytos.batch_install_apps` | `test_sdk_complete.py` |
| 截图/版本/容器信息 | `mytos_screenshot`, `get_version`, `get_container_info` | `mytos.screenshot`, `mytos.get_version`, `mytos.get_container_info` | `test_sdk_complete.py::test_sdk_fallback_endpoint_calls` |
| 短信/通话/定位 | `receive_sms`, `get_call_records`, `refresh_location`, `ip_geolocation` | `mytos.receive_sms`, `mytos.get_call_records`, `mytos.refresh_location`, `mytos.ip_geolocation` | `test_sdk_complete.py`, `test_sdk_actions_runtime.py` |
| 系统能力（ADB/GoogleID/Magisk） | `switch_adb_permission`, `get_google_id`, `install_magisk` | `mytos.switch_adb_permission`, `mytos.get_google_id`, `mytos.install_magisk` | `test_sdk_complete.py::test_sdk_fallback_endpoint_calls` |

## 3）RPA（Android RPA 文档）

| 功能 | 处理器/类 | 运行时动作 | 测试证据 |
|---|---|---|---|
| 触控/输入/按键/应用 | `click`, `swipe`, `long_click`, `input_text`, `key_press`, `app_open`, `app_stop` | `ui.click`, `ui.swipe`, `ui.long_click`, `ui.input_text`, `ui.key_press`, `app.open`, `app.stop` | `test_rpa_complete.py::test_ui_core_actions_success` |
| 截图/命令 | `screenshot`（`screentshot` 兼容）, `exec_command` | `device.screenshot`, `device.exec` | `test_rpa_complete.py` |
| UI 树导出 | `dumpNodeXml`, `dump_node_xml_ex` | `ui.dump_node_xml`, `ui.dump_node_xml_ex` | `test_rpa_complete.py` |
| Selector 能力 | `MytSelector`（`addQuery_*`, `execQueryOne/All`） | 通过 `ui.create_selector` 将对象保存到 `context.vars["selector"]` | `test_rpa_complete.py` |
| Node 能力 | `RpcNode`（`get_node_*`、边界、父子、点击事件） | 包装工具类（由上层动作消费） | `test_rpa_complete.py::test_rpc_node_helpers` |

## 4）运行时注册覆盖

- 注册入口：`engine/action_registry.py::register_defaults`
- SDK/MYTOS 动态绑定：`engine/actions/sdk_actions.py::get_sdk_action_bindings`
- 注册验证：
  - `tests/test_sdk_actions_runtime.py::test_registry_contains_sdk_and_mytos_actions`
  - `tests/test_mytos_complete.py::test_registry_registers_new_ui_actions`

## 5）当前验证状态

- 旧依赖静态检查：`new/tools/check_no_legacy_imports.py` ✅
- 全量测试：`pytest new/tests -q` ✅
- RPC 禁用启动 + `/health` ✅
