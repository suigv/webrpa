# Android API 原子化对照（MYT_ANDROID_API）

基准：`https://dev.moyunteng.com/docs/NewMYTOS/MYT_ANDROID_API`（页面更新时间：2026-01-30）

结论：
- `MytSdkClient` 已覆盖当前文档页能力点。
- 工作流原子动作统一暴露在 `engine/actions/sdk_actions.py` 的 `mytos.*` 命名空间。
- 文档里一部分“单接口多命令”能力，已拆成更细粒度原子动作，避免插件层自己拼 `cmd/action`。

## 文档能力到原子动作

| 文档能力 | 客户端方法 | 原子动作 |
|---|---|---|
| 下载文件 | `download_file` | `mytos.download_file` |
| 获取粘贴板 | `get_clipboard` | `mytos.get_clipboard` |
| 设置粘贴板 | `set_clipboard` | `mytos.set_clipboard` |
| 查询 S5 代理 | `query_s5_proxy` | `mytos.query_s5_proxy` |
| 设置 S5 代理 | `set_s5_proxy` | `mytos.set_s5_proxy` |
| 停止 S5 代理 | `stop_s5_proxy` | `mytos.stop_s5_proxy` |
| 过滤 S5 代理域名 | `set_s5_filter` | `mytos.set_s5_filter` |
| 盒子收短信 | `receive_sms` | `mytos.receive_sms` |
| 上传谷歌证书 | `upload_google_cert` | `mytos.upload_google_cert` |
| 切换 ADB 连接权限 | `query_adb_permission` / `switch_adb_permission` | `mytos.query_adb_permission` / `mytos.switch_adb_permission` |
| 导出 App 信息 | `backup_app_info` | `mytos.backup_app_info` |
| 导入 App 信息 | `restore_app_info` | `mytos.restore_app_info` |
| 相机热启动 | `camera_hot_start` | `mytos.camera_hot_start` |
| 后台保活查询/增删改 | `query_background_keepalive` / `add_background_keepalive` / `remove_background_keepalive` / `update_background_keepalive` | `mytos.query_background_keepalive` / `mytos.add_background_keepalive` / `mytos.remove_background_keepalive` / `mytos.update_background_keepalive` |
| disablekey | `set_key_block` | `mytos.disable_key` |
| 批量安装 APK/XAPK | `batch_install_apps` | `mytos.batch_install_apps` |
| 截图 | `mytos_screenshot` | `mytos.screenshot` |
| 查询版本 | `get_version` | `mytos.get_version` |
| 谷歌 ID | `set_google_id` / `get_google_id` | `mytos.set_google_id` / `mytos.get_google_id` |
| 上传文件 | `upload_file` | `mytos.upload_file` |
| 盒子基本信息 | `get_container_info` | `mytos.get_container_info` |
| 通话记录 | `get_call_records` | `mytos.get_call_records` |
| 刷新经纬度 | `refresh_location` | `mytos.refresh_location` |
| 添加联系人 | `add_contact` | `mytos.add_contact` |
| 自动点击接口 | `auto_click` | `mytos.autoclick` |
| 触摸按下 | `auto_click(action="down")` | `mytos.touch_down` |
| 触摸抬起 | `auto_click(action="up")` | `mytos.touch_up` |
| 触摸移动 | `auto_click(action="move")` | `mytos.touch_move` |
| 点击/轻触 | `auto_click(action="click")` | `mytos.tap` |
| 按键 | `auto_click(action="keypress")` | `mytos.keypress` |
| 查询 Root 放行应用 | `get_root_allowed_apps` | `mytos.get_root_allowed_apps` |
| 设置 Root 放行应用 | `set_root_allowed_app` | `mytos.set_root_allowed_app` |
| 设置虚拟相机来源 | `set_virtual_camera_source` | `mytos.set_virtual_camera_source` |
| 获取开机自启动列表 | `get_app_bootstart_list` | `mytos.get_app_bootstart_list` |
| 设置开机自启动 | `set_app_bootstart` | `mytos.set_app_bootstart` |
| 设置语言国家 | `set_language_country` | `mytos.set_language_country` |
| 获取 WebRTC 播放页地址 | `get_webrtc_player_url` | `mytos.get_webrtc_player_url` |
| IP 地理位置 | `ip_geolocation` | `mytos.ip_geolocation` |

## 兼容说明

- `upload_file` 同时支持：
  - 本地文件上传：`local_path`
  - 文档里的远程拉取上传：`file_url`
- `camera_hot_start` 支持文档里的 `path`，也保留原来的布尔启停调用。
- `set_background_keepalive` 保留旧的 `enabled` 形式，同时新增按文档 `cmd` 拆分后的查询/新增/删除/更新原子动作。
- `set_key_block` 支持文档里的简单 `value=1/0`，也保留旧的按键级阻断参数。
- `set_virtual_camera_source` 使用 `path/type/resolution`。
- `set_app_bootstart` 支持文档里的 `POST /appbootstart?cmd=2` + JSON 数组，也兼容旧的单包名启停方式。
- `get_webrtc_player_url` 现在输出文档风格的 `webplayer/play.html?shost=...&sport=...&rtc_i=...&rtc_p=...` 地址。
