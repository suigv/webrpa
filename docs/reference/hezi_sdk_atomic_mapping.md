# 盒子 SDK API 原子化对照（heziSDKAPI）

基准：`https://dev.moyunteng.com/docs/NewMYTOS/heziSDKAPI`（唯一 `method+path` 口径）

当前结论（2026-03-06）：
- 文档唯一接口：78
- 客户端 `MytSdkClient` 已映射：78
- 引擎原子动作：`sdk.*`（对应 `engine/actions/sdk_actions.py`）

说明：
- 文档中的 `POST /android/macvlan` 在目录里出现两次（“设置Macvlan/设置云机容器IP”），本对照合并为同一路径。
- `WebSocket /link/ssh`、`GET /link/exec`、页面 `/ssh`、`/container/exec` 已提供“直连调用 + URL 生成”两类原子能力。

## 1) 基本信息

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /info` | `get_api_version` | `sdk.get_api_version` |
| `GET /info/device` | `get_device_info` | `sdk.get_device_info` |

## 2) 云机操作

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /android` | `list_androids` / `get_cloud_status` | `sdk.list_androids` / `sdk.get_cloud_status` |
| `POST /android` | `create_android` | `sdk.create_android` |
| `PUT /android` | `reset_android` | `sdk.reset_android` |
| `DELETE /android` | `delete_android` | `sdk.delete_android` |
| `POST /android/switchImage` | `switch_image` | `sdk.switch_image` |
| `POST /android/switchModel` | `switch_model` | `sdk.switch_model` |
| `POST /android/pullImage` | `pull_image` | `sdk.pull_image` |
| `POST /android/start` | `start_android` | `sdk.start_android` |
| `POST /android/stop` | `stop_android` | `sdk.stop_android` |
| `POST /android/restart` | `restart_android` | `sdk.restart_android` |
| `GET /android/image` | `list_images` | `sdk.list_images` |
| `DELETE /android/image` | `delete_image` | `sdk.delete_image` |
| `GET /android/imageTar` | `list_image_tars` | `sdk.list_image_tars` |
| `DELETE /android/imageTar` | `delete_image_tar` | `sdk.delete_image_tar` |
| `POST /android/image/export` | `export_image` | `sdk.export_image` |
| `GET /android/image/download` | `download_image_tar` | `sdk.download_image_tar` |
| `POST /android/image/import` | `import_image` | `sdk.import_image` |
| `POST /android/export` | `export_android` | `sdk.export_android` |
| `POST /android/import` | `import_android` | `sdk.import_android` |
| `GET /android/phoneModel` | `list_phone_models_online` | `sdk.list_phone_models_online` |
| `GET /android/countryCode` | `list_country_codes` | `sdk.list_country_codes` |
| `POST /android/macvlan` | `set_android_macvlan` | `sdk.set_android_macvlan` |
| `POST /android/rename` | `rename_android` | `sdk.rename_android` |
| `GET /android/backup/model` | `list_model_backups` | `sdk.list_model_backups` |
| `DELETE /android/backup/model` | `delete_model_backup` | `sdk.delete_model_backup` |
| `POST /android/backup/model` | `backup_model` | `sdk.backup_model` |
| `POST /android/backup/modelExport` | `export_model` | `sdk.export_model` |
| `POST /android/backup/modelImport` | `import_model` | `sdk.import_model` |
| `POST /android/exec` | `exec_android` | `sdk.exec_android` |
| `POST /android/pruneImages` | `prune_images` | `sdk.prune_images` |

## 3) 云机备份

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /backup` | `list_backups` | `sdk.list_backups` |
| `GET /backup/download` | `download_backup` | `sdk.download_backup` |
| `DELETE /backup` | `delete_backup` | `sdk.delete_backup` |

## 4) 终端连接

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `WebSocket /link/ssh` | `open_ssh_terminal` / `get_ssh_ws_url` | `sdk.open_ssh_terminal` / `sdk.get_ssh_ws_url` |
| `GET /ssh` | `get_ssh_page_url` | `sdk.get_ssh_page_url` |
| `POST /link/ssh/changePwd` | `change_ssh_password` | `sdk.change_ssh_password` |
| `POST /link/ssh/switchRoot` | `switch_ssh_root` | `sdk.switch_ssh_root` |
| `POST /link/ssh/enable` | `enable_ssh` | `sdk.enable_ssh` |
| `GET /link/exec` | `open_container_exec` / `get_container_exec_ws_url` | `sdk.open_container_exec` / `sdk.get_container_exec_ws_url` |
| `GET /container/exec` | `get_container_exec_page_url` | `sdk.get_container_exec_page_url` |

## 5) myt_bridge 网卡管理

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /mytBridge` | `list_myt_bridge` | `sdk.list_myt_bridge` |
| `POST /mytBridge` | `create_myt_bridge` | `sdk.create_myt_bridge` |
| `PUT /mytBridge` | `update_myt_bridge` | `sdk.update_myt_bridge` |
| `DELETE /mytBridge` | `delete_myt_bridge` | `sdk.delete_myt_bridge` |

## 6) 魔云腾 VPC

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /mytVpc/group` | `list_vpc_groups` | `sdk.list_vpc_groups` |
| `POST /mytVpc/group` | `create_vpc_group` | `sdk.create_vpc_group` |
| `POST /mytVpc/group/alias` | `update_vpc_group_alias` | `sdk.update_vpc_group_alias` |
| `DELETE /mytVpc/group` | `delete_vpc_group` | `sdk.delete_vpc_group` |
| `POST /mytVpc/addRule` | `add_vpc_rule` | `sdk.add_vpc_rule` |
| `GET /mytVpc/containerRule` | `list_vpc_container_rules` | `sdk.list_vpc_container_rules` |
| `DELETE /mytVpc` | `delete_vpc_node` | `sdk.delete_vpc_node` |
| `POST /mytVpc/group/update` | `update_vpc_group` | `sdk.update_vpc_group` |
| `POST /mytVpc/socks` | `add_vpc_socks` | `sdk.add_vpc_socks` |
| `POST /mytVpc/whiteListDns` | `set_vpc_whitelist_dns` | `sdk.set_vpc_whitelist_dns` |
| `GET /mytVpc/test` | `test_vpc_latency` | `sdk.test_vpc_latency` |

## 7) 本地机型数据管理

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /phoneModel` | `list_local_phone_models` | `sdk.list_local_phone_models` |
| `DELETE /phoneModel` | `delete_local_phone_model` | `sdk.delete_local_phone_model` |
| `POST /phoneModel/export` | `export_local_phone_model` | `sdk.export_local_phone_model` |
| `POST /phoneModel/import` | `import_phone_model` | `sdk.import_phone_model` |

## 8) 接口认证

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `POST /auth/password` | `set_auth_password` | `sdk.set_auth_password` |
| `POST /auth/close` | `close_auth` | `sdk.close_auth` |

## 9) 服务管理

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `GET /server/upgrade` | `upgrade_server` | `sdk.upgrade_server` |
| `POST /server/upgrade/upload` | `upload_server_upgrade` | `sdk.upload_server_upgrade` |
| `POST /server/device/reset` | `reset_server_device` | `sdk.reset_server_device` |
| `POST /server/device/reboot` | `reboot_server_device` | `sdk.reboot_server_device` |
| `POST /server/dockerApi` | `switch_docker_api` | `sdk.switch_docker_api` |
| `GET /server/network` | `get_server_network` | `sdk.get_server_network` |

## 10) 大模型管理

| 接口 | 客户端方法 | 原子动作 |
|---|---|---|
| `POST /lm/import` | `import_lm_package` | `sdk.import_lm_package` |
| `GET /lm/info` | `get_lm_info` | `sdk.get_lm_info` |
| `DELETE /lm/local` | `delete_lm_local` | `sdk.delete_lm_local` |
| `GET /lm/local` | `list_models` | `sdk.list_models` |
| `GET /lm/models` | `get_lm_models` | `sdk.get_lm_models` |
| `POST /lm/reset` | `reset_lm_device` | `sdk.reset_lm_device` |
| `POST /lm/server/start` | `start_lm_server` | `sdk.start_lm_server` |
| `POST /lm/server/stop` | `stop_lm_server` | `sdk.stop_lm_server` |
| `POST /lm/workMode` | `set_lm_work_mode` | `sdk.set_lm_work_mode` |

## 参数兼容备注

- `POST /android/switchModel`：`switch_model` 支持 `modelId/localModel/modelStatic`（三选一）。
- `POST /link/ssh/changePwd`：`change_ssh_password` 仅强制 `password`，`username` 可选。
