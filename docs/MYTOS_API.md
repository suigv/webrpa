# MYTOS Android API（30001）

基准文档：MYTOS API 接口文档

本地调用说明：

使用 `hardware_adapters/android_api_client.py` 的 `AndroidApiClient` 或 `mytos.*` 动作。参数名优先与文档一致，同时部分字段支持兼容别名（例如 `save_path` ↔ `local_path`）。

## 1. 下载文件

功能说明：从设备下载指定文件到本地计算机
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/download?path={filepath}
路径：`/download`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| path | 是 | string | 要下载的文件完整路径 |

参数详解：

- path: 必须是文件的完整绝对路径 获取方式： 使用"获取文件列表"接口查询文件路径 或直接使用已知的文件路径 常见文件路径： /sdcard/Download/file.apk（下载的 APK 文件） /sdcard/DCIM/Camera/photo.jpg（相机照片） /data/app/com.example/base.apk（已安装应用）
- 获取方式： 使用"获取文件列表"接口查询文件路径 或直接使用已知的文件路径
- 使用"获取文件列表"接口查询文件路径
- 或直接使用已知的文件路径
- 常见文件路径： /sdcard/Download/file.apk（下载的 APK 文件） /sdcard/DCIM/Camera/photo.jpg（相机照片） /data/app/com.example/base.apk（已安装应用）
- /sdcard/Download/file.apk（下载的 APK 文件）
- /sdcard/DCIM/Camera/photo.jpg（相机照片）
- /data/app/com.example/base.apk（已安装应用）

请求示例：

```bash
curl "http://192.168.99.108:10038/download?path=/sdcard/Download/1.jpg" -o 1.jpg
```

失败返回：

```json
{  "code": 201,  "error": "文件不存在或无权限访问"}
```

注意事项：

- 文件下载采用流式传输，支持大文件
- 下载时会显示下载进度信息
- 下载完成后会自动保存到指定位置
- 如果本地文件已存在，需要先��删除或重命名
- 某些系统文件可能需要特殊权限才能下载
- 建议使用绝对路径访问文件，以避免路径解析错误

## 2. 获取剪贴板内容

功能说明：获取设备剪贴板中的文本内容
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/clipboard
路径：`/clipboard`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| ip | 是 | string | ip |
| port | 是 | int | port |

请求示例：

```bash
curl "http://192.168.30.2:10008/clipboard"
```

成功返回：

```json
{  "code": 200,  "msg": "query success",  "data": {    "text": "123"  }}
```

失败返回：

```json
{  "code": 201,  "error": "异常原因"}{    "code":202,    "reason":"失败原因"}
```

注意事项：

- 只能获取文本内容，不支持图片或其他格式
- 需要设备授予剪贴板访问权限

## 3. 设置剪贴板内容

功能说明：将文本内容设置到设备的剪贴板
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/clipboard
路径：`/clipboard`

请求参数：无

参数详解：

- text: 可以是任意文本内容 如果包含特殊字符，需要进行 URL 编码
- 如果包含特殊字符，需要进行 URL 编码

请求示例：

```bash
curl "http://192.168.30.2:10008/clipboard?cmd=2&text=123"
```

成功返回：

```json
{  "code": 200,  "msg": "ok"}
```

失败返回：

```json
{  "code": 201,  "error": "异常原因"}{  "code": 202,  "error": "失败原因"}
```

注意事项：

- 特殊字符需要进行 URL 编码
- 设置后立即生效，用户可以粘贴该内容

## 4. 查询 S5 代理状态

功能说明：查询设备的 S5 代理服务状态
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/proxy
路径：`/proxy`

请求参数：

| 参数名 | 类型 | 说明 |
| --- | --- | --- |
| code | int | 状态码 |
| data | object | 返回数据对象 |
| data.status | string | 查询结果 |
| data.status Text | string | 提示信息 |
| data.addr | string | 代理地址 |
| data.type | int | 代理类型 |

请求示例：

```bash
curl "http://192.168.30.2:10008/proxy"
```

成功返回：

```text
启动{  "code": 200,  "msg": "query success",  "data": {    "status": 1,    "statusText": "已启动",    "addr": "socks5://test:123456@192.168.1.100:8080",    "type": 2  }}未启动{    "code":200,    "msg":"query success",    "data":{"status":0,"statusText":"未启动"}}
```

失败返回：

```json
{  "code": 201,  "error": "查询失败"}
```

注意事项：

- S5 代理是 SOCKS5 代理协议的实现

## 5. 设置 S5 代理

功能说明：启动或配置设备的 S5 代理服务
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/proxy?cmd=2
路径：`/proxy`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | 固定值：2 |
| port | 是 | int | s5 服务器端口 |
| usr | 是 | string | s5 用户名 |
| pwd | 是 | string | s5 密码 |
| type | 否 | int | s5 域名模式 1:本地域名解析 2:服务端域名解析 |

参数详解：

- port: s5 服务器端口
- usr: s5 用户名
- pwd: s5 密码
- type: s5 域名模式(1:本地域名解析 2:服务端域名解析)

请求示例：

```bash
curl "http://192.168.30.2:10008/proxy?cmd=2&type=2&ip=192.168.1.100&port=8080&usr=test&pwd=123456"
```

成功返回：

```json
{  "code": 200,  "msg": "start success"}
```

注意事项：

- 代理配置必须正确，否则无法连接

## 6. 停止 S5 代理

功能说明：停止设备的 S5 代理服务
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/proxy?cmd=3
路径：`/proxy`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | 固定值：3 |

请求示例：

```bash
curl "http://192.168.30.2:10008/proxy?cmd=3"
```

成功返回：

```json
{  "code": 200,  "msg": "stop success"}
```

注意事项：

- 停止后代理服务将不可用

## 7. 设置 S5 域名过滤

功能说明：为 S5 代理设置域名过滤规则
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：POST
请求 URL：http://{ip}:{port}/proxy?cmd=4
路径：`/proxy`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | 固定值：4 |

参数详解：

- domains: 可以使用逗号分隔的域名列表，或 JSON 数组格式

请求示例：

```bash
POST "http://192.168.30.2:10008/proxy?cmd=4"body[    "qq.com",    "baidu.com"]
```

成功返回：

```json
{  "code": 200,  "msg": "set success"}
```

失败返回：

```json
{  "code": 201,  "error": "设置失败"}
```

注意事项：

- 在使用 S5 代理时，建议先检查代理服务器的可用性
- 域名过滤规则的变更会立即生效
- 如果需要临时禁用 S5 代理，可以使用停止 S5 代理接口
- S5 代理的设置会影响所有网络请求的路由

## 8. 接收短信

功能说明：模拟接收短信消息
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：POST
请求 URL：http://{ip}:{port}/sms
路径：`/sms`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | 固定值：4 |
| address | 是 | string | 发送者电话号码 |
| mbody | 是 | string | 短信内容 |
| scaddress | 否 | string | 短信中心号码 |

参数详解：

- address: 发送短信的电话号码
- mbody: 短信的文本内容
- scaddress: 短信中心号码

请求示例：

```bash
POST "http://192.168.30.2:10008/sms?cmd=4"headers = {"Content-Type": "application/json"}请求体body = {    "address": "13800138000",    "body": "Hello, this is a test message.",    "scaddress": "+8613900000000"}
```

成功返回：

```json
{  "code": 200,  "msg": "add inbox success",  "data": { "status": 0 }}
```

失败返回：

```json
{  "code": 201,  "error": "接收失败"}
```

注意事项：

- 电话号码必须是有效的格式
- 短信内容支持特殊字符，但需要 URL 编码

## 9. 上传 Google 证书

功能说明：上传或更新 Google 服务的证书
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：POST
请求 URL：http://{ip}:{port}/uploadkeybox
路径：`/uploadkeybox`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 证书文件（如.pem） |

参数详解：

- file: 上传 Google 证书文件（PEM 格式）

请求示例：

```text
方式一： POST  "http://192.168.30.2:10008/uploadkeybox"  请求体  form_data 上传文件  {'fileToUpload': 文件}方式二：curl -X POST "http://10.10.0.32:30101/uploadkeybox" -F "file=@1.pem"
```

成功返回：

```text
导入完成permissionabcselinux123
```

失败返回：

```text
导入失败，错误信息：
```

注意事项：

- 证书文件必须是有效的 PEM 格式
- 上传后需要重启设备才能生效
- 某些 Google 服务可能需要特定的证书

## 10. ADB 切换权限

功能说明：查询、开启、关闭当前 ADB 权限状态
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/adb
路径：`/adb`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 操作命令：1: 查询权限状态；2: 开启 ADB root 权限；3: 关闭 ADB root 权限 |

请求示例：

```text
查询权限状态curl "http://192.168.30.2:10008/adb?"开启ADB root权限curl "http://192.168.99.108:10008/adb?cmd=2"关闭ADB root权限curl "http://192.168.99.108:10008/adb?cmd=3"
```

成功返回：

```text
查询{  "code": 200,  "msg": "query success",  "data": { "status": 0, "statusText": "open" }}开启权限{    "code":200,    "msg":"open adb root success"}关闭权限{    "code":200,    "msg":"close adb root success"}
```

失败返回：

```json
{  "code": 202  "reason":"错误原因"}
```

注意事项：

- 此功能依赖设备已 root 且系统支持 persist.adbd.shell 属性
- 修改后需重新连接 ADB 才能生效

## 11. 导出 app 信息

功能说明：导出已安装应用的信息
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/backrestore
路径：`/backrestore`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | str | backup |
| pkg | 是 | str | 包名 |
| saveto | 是 | str | 导出文件路径 |

请求示例：

```text
# 导出导出app信息curl "http://192.168.30.2:10020/backrestore?cmd=backup&pkg=com.ss.android.ugc.aweme&saveto=/sdcard/test.tar.gz"
```

成功返回：

```json
{  "status": "success",  "message": "Backup completed successfully"}
```

失败返回：

```json
{  "status": "failed",  "message": "失败原因"}
```

注意事项：

- 返回所有已安装应用的基本信息
- 返回的信息包括包名、应用名称、版本等
- 可用于获取设备上所有应用的列表

## 12. 导入 app 信息

功能说明：导入应用信息到设备，导入 APP 信息不需要 pkg（应用包名）参数。
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/backrestore
路径：`/backrestore`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | str | recovery |
| backuppath | 是 | str | 导入文件路径 |

请求示例：

```text
# 导入导出app信息GET http://192.168.30.2:10020/backrestore?cmd=recovery&backuppath=/sdcard/test.tar.gz
```

成功返回：

```json
{  "status": "success",  "message": "Recovery completed successfully"}
```

失败返回：

```json
{  "status": "failed",  "message": "失败原因"}
```

注意事项：

- 应用信息文件必须是有效的 JSON 格式
- 导入后需要重启安卓才能生效

## 13. 虚拟摄像头热启动

功能说明：热启动虚拟摄像头功能，无需重启设备
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/camera?cmd=start
路径：`/camera`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | str | start,stop |
| path | 否 | str | rtmp 地址或者本地地址，首次使用需要传参，后续如果不传 path 参数则使用上次的 path 参数 |

请求示例：

```bash
curl "http://192.168.30.2:10008/camera?cmd=start&path=/sdcard/Download/1.jpg"
```

成功返回：

```json
{  "code": 200,  "msg": "ok"}
```

失败返回：

```json
{  "code": 202,  "reason": "错误原因"}
```

注意事项：

- 热启动不需要重启设备
- 启动后虚拟摄像头立即可用

## 14. 后台保活

功能说明：为指定应用启用后台保活功能，防止应用被系统杀死
支持模式：仅 Android 14 支持
请求方式：GET
请求 URL：http://{ip}:{port}/background
路径：`/background`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | str | 操作类型 ：查询=1 增加=2 删除=3 更新=4 更新接口说明：被保活应用卸载和重新安装后需要调用 |
| package | 否 | str | 应用包名 ；cmd=2 和 3 需要 |

参数详解：

- cmd: 操作类型 1：查询（查询所有保活应用） 2：增加（添加应用到保活列表） 3：删除（从保活列表删除应用） 4：更新（更新保活应用列表）
- 1：查询（查询所有保活应用）
- 2：增加（添加应用到保活列表）
- 3：删除（从保活列表删除应用）
- 4：更新（更新保活应用列表）
- package: 当 cmd=2 或 3 时需要提供 被保活应用卸载和重新安装后需要调用更新接口
- 被保活应用卸载和重新安装后需要调用更新接口

请求示例：

```bash
curl "http://192.168.99.149:10026/background?cmd=1"
```

失败返回：

```json
{  "code": 202,  "reason": "应用已在保护列表中"}错误返回xxx为java层报错信息，不固定：{    "code":201,    "error":"xxxxx"}
```

注意事项：

- 目前只支持安卓 14 版本
- 版本要求：镜像日期大于 20251217
- 被保活应用卸载和重新安装后需要调用更新接口
- 某些系统应用可能无法保活

## 15. 屏蔽按键

功能说明：屏蔽或启用设备的物理按键
支持模式：仅 Android14 支持
请求方式：GET
请求 URL：http://{ip}:{port}/disablekey?value=1
路径：`/disablekey`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| value | 否 | str | 1 为开启 0 为关闭 |

参数详解：

- value: 屏蔽状态 1：开启屏蔽 0：关闭屏蔽
- 1：开启屏蔽
- 0：关闭屏蔽

请求示例：

```bash
curl "http://192.168.99.108:10017/disablekey?value=1"
```

成功返回：

```json
{  "code": 200,  "msg": "ok"}
```

失败返回：

```text
错误返回xxx为java层报错信息，不固定{  "code": 201,  "error": "Java层报错信息"}
```

注意事项：

- 屏蔽后物理按键将不可用

## 16. 批量安装 apks/xapk 分包

功能说明：用于批量安装 Android apks/xapk 文件的接口，支持通过 ZIP 压缩包上传多个 apks/xapk 文件并自动安装
支持模式：安卓 10、12（从 v22.9.2 开始）、14 都支持
请求方式：POST
请求 URL：http://{ip}:{port}/installapks
路径：`/installapks`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 包含多个 apks/xapk 文件的 ZIP 压缩包 |

参数详解：

- file: 上传包含多个 apks/xapk 文件的 ZIP 压缩包 步骤： 将多个 apks/xapk 文件放入一个文件夹 将文件夹压缩为 ZIP 文件 上传 ZIP 文件
- 步骤： 将多个 apks/xapk 文件放入一个文件夹 将文件夹压缩为 ZIP 文件 上传 ZIP 文件
- 将多个 apks/xapk 文件放入一个文件夹
- 将文件夹压缩为 ZIP 文件
- 上传 ZIP 文件

请求示例：

```bash
curl -X POST \  "http://192.168.99.108:10017/installapks" \  -H "Content-Type: multipart/form-data" \  -F "file=@/path/to/your/apks.zip"
```

成功返回：

```text
全部安装完成
```

失败返回：

```text
错误返回xxx为java层报错信息，不固定{  "code": 202,  "error": "Java层报错信息"}
```

注意事项：

- 支持安卓 10、12（从 v22.9.2 开始）、14
- ZIP 文件必须包含有效的 APK 文件
- 安装过程可能需要几分钟，请耐心等待
- 如果某个 APK 安装失败，其他 APK 仍会继续安装

## 17. 版本查询

功能说明：查询设备或服务的版本信息
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/queryversion
路径：`/queryversion`

请求参数：无

请求示例：

```bash
curl "http://192.168.30.2:10008/queryversion"
```

成功返回：

```json
{  "code": 200,  "msg": "3"}
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}
```

注意事项：

- 版本信息可能包含多个字段
- 不同设备或服务可能返回不同的版本信息

## 18. 截图功能

功能说明：获取设备屏幕截图
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/snapshot
路径：`/snapshot`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| type | 否 | string | 截图类型 |
| quality | 否 | int | 截图质量（1-100） |

请求示例：

```bash
curl "http://192.168.30.2:10008/snapshot"curl "http://192.168.30.2:10008/snapshot?quality=80"
```

失败返回：

```json
{  "code": 201,  "error": "截图失败"}
```

注意事项：

- 截图需要设备屏幕处于唤醒状态
- 高分辨率截图可能需要较长时间
- 截图大小可能有限制

## 19. 自动点击

功能说明：自动点击
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/autoclick
路径：`/autoclick`

请求参数：

| 必选 | 类型 | 说明 |
| --- | --- | --- |
| action | string | 点击动作，可选值：touchdown 按 touchup 放 touchmove 移动 tap 点击 keypress 根据按键键码点击对应按键 |
| id | int | 点击事件编号 1-10 多指触控 |
| x | int | x 坐标 |
| y | int | y 坐标 |
| code | int | 按键键码，action 为 keypress 时必填, 点击按键键码对应的按键 |

请求示例：

```text
按下curl "http://192.168.99.108:10038/autoclick?action=touchdown&id=1&x=100&y=100"放开curl "http://192.168.99.108:10038/autoclick?action=touchup&id=1&x=100&y=100"移动curl "http://192.168.99.108:10038/autoclick?action=touchmove&id=1&x=100&y=100"点击curl "http://192.168.99.108:10038/autoclick?action=tap&id=1&x=100&y=100"根据按键键码点击对应按键curl "http://192.168.99.108:10038/autoclick?action=keypress&id=1&code=4"
```

成功返回：

```json
{    "code": 200,    "msg": "ok"}
```

## 20. 文件上传

功能说明：文件上传
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/upload
路径：`/upload`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 需要上传的文件（如.txt） |

请求示例：

```bash
curl -X POST "http://192.168.99.108:10038/upload" -H "Content-Type: multipart/form-data" -F "file=@./1.txt"
```

成功返回：

```text
文件上传完成！
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}
```

注意事项：

- 接口一是标准文件上传：通过 multipart/form-data 格式直接将本地文件（如本地 APK）上传到接口；适用场景：上传本地存储的文件，是常规的文件上传方式。
- 接口二是文件 URL 上传：通过 URL 参数传递文件 URL，接口会自动下载文件并上传；适用场景：上传远程存储的文件，如文件服务器上的文件，或需要先下载再上传。

## 21. 容器信息

功能说明：获取容器信息
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/info
路径：`/info`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:10026/info"
```

成功返回：

```json
{  "code": 200,  "msg": "ok",  "data": {    "hostIp": "-",    "instance": "8",    "name": "p738c384c1581ad24c3fcf199684f5f5_8",    "buildTime": "1766829184"  }}
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}
```

## 22. 通话记录

功能说明：获取容器通话记录
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/callog
路径：`/callog`

请求参数：

| 参数名 | 类型 | 是否必选 | 说明 |
| --- | --- | --- | --- |
| number | string | 是 | 要模拟的电话号码（如 "13800138000"） |
| type | int | 否 | 通话类型：1 呼出 2 接收 3 错过（默认） |
| date | string | 否 | 时间戳（毫秒），默认当前时间 |
| duration | int | 否 | 通话时长（秒），默认 0 |
| presentation | int | 否 | 显示方式，默认 1 |
| subscription_id | int | 否 | SIM 卡 ID，默认 0 |
| is_read | int | 否 | 是否已读，默认 1 |
| new | int | 否 | 是否新消息，默认 1 |
| features | int | 否 | 特性标志，默认 0 |

请求示例：

```bash
curl "http://192.168.30.2:10008/callog?number=10086&type=2"
```

成功返回：

```json
{  "code": 200,  "msg": "query success"}
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}
```

## 23. 刷新定位

功能说明：根据 ip 刷新定位
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/task
路径：`/task`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:10026/task"
```

成功返回：

```json
{  "code": 200}
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}
```

## 24. 谷歌 id

功能说明：获取容器谷歌 id
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/adid
路径：`/adid`

请求参数：

| 参数名 | 类型 | 是否必选 | 说明 |
| --- | --- | --- | --- |
| cmd | string | 是 | 操作指令：1 - 自定义设置谷歌 ID（需传 adid 参数）2 - 生成随机谷歌 ID 默认值：1 |
| adid | string | 是 | 仅 cmd=1 时必选，需设置的谷歌 ID 值 |

请求示例：

```bash
curl "http://192.168.99.108:10026/adid?cmd=1&adid=my_adid"
```

成功返回：

```json
{  "succ": true,  "msg": "generate random adid success",  "data": {    "adid": "my_adid"  }}
```

失败返回：

```json
{  "succ": false,  "msg": "cmd err"}
```

## 25. 安装面具

功能说明：安装面具（安装面具之后需要重启）
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/modulemgr?cmd=install&moduler={}
路径：`/modulemgr`

请求参数：

| 参数名 | 类型 | 是否必选 | 说明 |
| --- | --- | --- | --- |
| cmd | string | 是 | 操作指令：check - 检查模块状态；install - 安装模块 ；uninstall - 卸载模块 |
| adid | string | 是 | 面具名称 |

请求示例：

```text
#以gms为例，检查面具状态curl "http://192.168.99.108:10026/modulemgr?cmd=check&module=gms"#安装面具curl "http://192.168.99.108:10026/modulemgr?cmd=install&module=gms"#卸载面具curl "http://192.168.99.108:10026/modulemgr?cmd=uninstall&module=gms"
```

成功返回：

```text
检查面具是否安装，如果安装了返回结果：{  "code":200,  "msg":"1"}检查面具是否安装，如果没有安装返回结果：{  "code":200,  "msg":"0"}安装成功：{    "code":200,    "msg":"OK"}
```

失败返回：

```text
安装面具失败：{  "code": 201,  "msg": "Error"}
```

注意事项：

- 安装面具后需要重启

## 26. 添加联系人

功能说明：添加联系人
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/addcontact?data=[]
路径：`/addcontact`

请求参数：

| 参数名 | 类型 | 是否必选 | 说明 |
| --- | --- | --- | --- |
| data | JSON 字符串 | 是 | 联系人列表，数组内每个对象需包含：- user：联系人姓名- tel：联系电话 |

请求示例：

```text
GET"http://192.168.99.108:10035/addcontact?data=[{"user":"张三","tel":"13800138000"},{"user":"李四","tel":"13900139000"}]"
```

成功返回：

```json
{  "code": 200,  "msg": "OK"}
```

失败返回：

```json
{  "code": 201,  "error": "org.json.JSONException: Unterminated string at character 59 of [{\"user\":\"张三\",\"tel\":\"13800138000\"},{\"user\":\"李四\",\"tel\":\"1390"}
```

## 27. webrtc 播放器

功能说明：调用 webrtc 的播放器
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| shost | 是 | string | WebRTC 流媒体服务器主机地址（如 192.168.99.108） |
| sport | 是 | string | WebRTC 流媒体服务器端口（TCP）（如 31207） |
| q | 是 | string | 视频质量参数 (0=低 1=高) |
| v | 是 | string | 视频编码格式（如 h264） |
| rtc_j | 是 | string | RTC 服务端 IP（与 shost 一致，用于建立点对点连接） |
| rtc_p | 是 | string | WebRTC 端口（UDP）（如 31208） |

请求示例：

```text
GET"./webplayer/play.html?shost=192.168.99.108&sport=31207&q=1&v=h264&rtc_i=192.168.99.108&rtc_p=31208"
```

成功返回：

```text
成功响应（页面加载完成）
```

失败返回：

```text
失败响应（页面加载失败）
```

## 28. 获取后台允许 root 授权的 app 列表

功能说明：获取当前后台配置中允许授予 Root 权限的应用包名列表。
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/modifydev?cmd=10&action=list
路径：`/modifydev`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 固定值：10 |
| action | 是 | string | �固定值：list |

请求示例：

```text
GET"http://192.168.99.108:31401/modifydev?cmd=10&action=list"
```

成功返回：

```json
{  "code": 200,  "msg": "获取成功",  "data": { "apps": ["com.ss.android.ugc.aweme"] }}查询列表：老版本未支持的时候提示{  "code":202,  "reason":"not find package:null"}
```

## 29. 指定包名是否允许 root

功能说明：为指定包名的应用开启 ROOT 权限，安卓里面先要安装对应的 apk。
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/modifydev?cmd=10&pkg={package}&root=true
路径：`/modifydev`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 固定值：10 |
| pkg | 是 | string | 应用包名（如抖音：com.ss.android.ugc.aweme） |
| action | 是 | string | 固定值 true，表示允许 root |

请求示例：

```text
GET"http://192.168.99.108:31401/modifydev?cmd=10&pkg=com.ss.android.ugc.aweme&root=true"
```

成功返回：

```json
{  "code": 200,  "msg": "OK"}
```

失败返回：

```text
找不到包名{  "code":202,  "reason":"not find package:com.ss.android.ugc.awemenull"}
```

## 30. 设置虚拟摄像头源和类型

功能说明：配置虚拟摄像头的视频源类型及地址（支持图��像、视频文件、RTMP 流、WebRTC、物理摄像头等）。
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/modifydev?cmd=4&type={type}&path={path}&resolution={resolution}
路径：`/modifydev`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 固定值：4 |
| type | 是 | string | 视频源类型，可选值：image、video、webrtc、rtmp、camera |
| path | 是 | string | 对应资源路径或 URL:1.image/video：本地文件路径（如 /sdcard/test.jpg） 2.rtmp/webrtc：流地址（如 rtmp://server/live） 3.camera：固定值null（实际由魔云互联接管设备物理摄像头） |
| resolution | 否 | int | 分辨率预设：1 = 自动（默认）;2 = 1920x1080@30;3 = 1280x720@30 |

请求示例：

```text
GET设置物理摄像头："http://192.168.99.108:31401/modifydev?cmd=4&type=camera&path=null "设置视频video："http://192.168.99.108:31401/modifydev?cmd=4&type=video&path=/Dowload/11111.mp4&resolution=1 "仅修改分辨率为 720P（不换源）:"http://192.168.99.108:31401/modifydev?cmd=4&resolution=3 "
```

成功返回：

```json
{  "code": 200,  "msg": "OK"}
```

失败返回：

```json
{  "code":202,  "reason":"错误原因"}已知错误原因列表：type is not find:"+type                path is empty                image not exist（image类型）
```

注意事项：

- 如果只传 resolution 而不传 type 和 path，系统将仅修改当前视频流的分辨率，不会切换源
- 当 type=camera（物理摄像头）时，需要配合「魔云互联」使用。

## 31. 获取 APP 开机启动列表

功能说明：获取当前已配置为开机启动的应用列表.
支持模式：🌉 桥接模式 | 🔗 非桥接模式
请求方式：GET
请求 URL：http://{ip}:{port}/appbootstart?cmd=1
路径：`/appbootstart`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | cmd=1：获取当前已配置为开机启动的应用列表 |

请求示例：

```text
GET："http://192.168.99.182:30301/appbootstart?cmd=1"
```

成功返回：

```json
{  "code": 200,  "msg": "query success",  "data": { "pkg": ["cn.test", "android.ttt"] }}
```

## 32. 设置指定 APP 开机启动

功能说明：设置指定应用是否允许在系统启动时自动运行。
请求方式：GET
请求 URL：http://{ip}:{port}/appbootstart?cmd=2
路径：`/appbootstart`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | int | cmd=2：设置一组应用为开机启动（需通过 POST 提交 JSON 数组） |
| body | 是 | list | APP数组 |

请求示例：

```text
POSTcurl "http://127.0.0.1:9082/appbootstart?cmd=2" -X POST -H "Content-Type: application/json" -d '["cn.test", "android.ttt"]'
```

成功返回：

```json
{  "code": 200,  "msg": "set success"}
```

失败返回：

```json
{  "code": 201,  "error": "失败原因"}
```

## 33. IP定位

功能说明：设置设备语言或IP，同时会自动更新相关的区域设置和系统环境。
请求方式：GET
请求 URL：http://{ip}:{port}/modifydev?cmd=11
路径：`/modifydev`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 固定值：11 |
| launage | 否 | string | 语言代码(zh 中文/en 英语/fr 法语/th 泰国/vi �越南/ja 日本/ko 韩国/lo 老挝/in 印尼) |
| ip | 否 | string | 用户IP，用于确定地理位置相关的设置 |

请求示例：

```text
# 设置语言为英语（美国）GET"http://192.168.99.182:30301/modifydev?cmd=11&launage=en"# 设置IP为23.247.138.215GET"http://192.168.99.182:30301/modifydev?cmd=11&ip=23.247.138.215"
```

成功返回：

```json
{  "code": 200,  "msg": "OK"}
```

失败返回：

```json
{  "code": 201,  "error": "异常原因"}
```

## 34. 设置语言和国家

功能说明：设置设备语言和国家。
请求方式：GET
请求 URL：http://{ip}:{port}/modifydev?cmd=13
路径：`/modifydev`

请求参数：

| 参数名 | 是否必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| cmd | 是 | string | 固定值：13 |
| language | 是 | string | 语言代码 |
| country | 是 | string | 国家代码 |

请求示例：

```text
GET"http://192.168.99.182:30301/modifydev?cmd=13&language=zh&country=US"常见的国家和语言 字典表   国家=>语言'GR'=>'el','NL'=>'nl','BE'=>'de','FR'=>'fr','MC'=>'fr','AD'=>'ca','ES'=>'eu','HU'=>'hu','BA'=>'sr','HR'=>'hr','RS'=>'sr','IT'=>'fur','RO'=>'ro','CH'=>'rm','CZ'=>'cs','SK'=>'sk','AT'=>'en','GB'=>'cy','DK'=>'en','SE'=>'se','NO'=>'nn','FI'=>'fi','LT'=>'lt','LV'=>'lv','EE'=>'et','RU'=>'os', 'UA'=>'uk','BY'=>'be','MD'=>'ru','PL'=>'pl','DE'=>'hsb','GI'=>'en','PT'=>'pt','LU'=>'lb','IE'=>'en','IS'=>'is','AL'=>'sq','MT'=>'en','CY'=>'en','GE'=>'os','AM'=>'hy','BG'=>'bg','TR'=>'tr','FO'=>'fo','GL'=>'da','SM'=>'it','SI'=>'en','MK'=>'mk','LI'=>'gsw','ME'=>'sr','CA'=>'en','PM'=>'fr','US'=>'en','US'=>'en','US'=>'en','US'=>'en','US'=>'en','US'=>'en','US'=>'en','PR'=>'en','VI'=>'en','MX'=>'es','JM'=>'en','MQ'=>'fr','BB'=>'en','AG'=>'en','KY'=>'en','VG'=>'en','BM'=>'en','GD'=>'en','MS'=>'en','KN'=>'en','LC'=>'en','VC'=>'en','CW'=>'nl','AW'=>'nl','BS'=>'en','AI'=>'en','DM'=>'en','CU'=>'es','DO'=>'es','HT'=>'fr','TT'=>'en','TC'=>'en','AZ'=>'az','KZ'=>'kk','BT'=>'dz','IN'=>'hi','IN'=>'hi','IN'=>'hi','PK'=>'pa','AF'=>'uz','LK'=>'si','MM'=>'my','LB'=>'ar','JO'=>'ar','SY'=>'ar','IQ'=>'ar','KW'=>'ar','SA'=>'ar','YE'=>'ar','OM'=>'ar','AE'=>'ar','PS'=>'ar','BH'=>'ar','QA'=>'ar','MN'=>'mn','NP'=>'ne','AE'=>'ar','AE'=>'ar','IR'=>'mzn','UZ'=>'uz','KG'=>'ky','JP'=>'ja','JP'=>'ja','KR'=>'ko','VN'=>'vi','HK'=>'zh','MO'=>'en','KH'=>'km','LA'=>'lo','CN'=>'zh','CN'=>'zh','TW'=>'zh','KP'=>'ko','BD'=>'bn','MY'=>'en','AU'=>'en','ID'=>'in','TL'=>'pt','PH'=>'en','TH'=>'th','SG'=>'en','BN'=>'ms','NZ'=>'en','MP'=>'en','GU'=>'en','NR'=>'en','PG'=>'en','TO'=>'en','SB'=>'en','VU'=>'fr','FJ'=>'en','WF'=>'fr','AS'=>'en','KI'=>'en','NC'=>'fr','PF'=>'fr','CK'=>'en','WS'=>'en','FM'=>'en','MH'=>'en','PW'=>'en','NU'=>'en','EG'=>'ar','DZ'=>'kab','MA'=>'fr','TN'=>'fr','LY'=>'ar','GM'=>'en','SN'=>'ff','MR'=>'ar','ML'=>'khq','GN'=>'ff','CI'=>'fr','BF'=>'fr','NE'=>'dje','TG'=>'fr','BJ'=>'fr','MU'=>'fr','LR'=>'vai','SL'=>'en','GH'=>'en','NG'=>'ha','TD'=>'ar','CF'=>'sg','CM'=>'kkj','CV'=>'kea','ST'=>'pt','GQ'=>'es','GA'=>'fr','CG'=>'ln','CD'=>'fr','AO'=>'ln','GW'=>'pt','SC'=>'en','SD'=>'en','RW'=>'en','ET'=>'am','SO'=>'ar','DJ'=>'so','KE'=>'guz','TZ'=>'kde','UG'=>'lg','BI'=>'fr','MZ'=>'seh','ZM'=>'bem','MG'=>'en','RE'=>'fr','SZ'=>'en','KM'=>'ar','ZA'=>'af','ER'=>'en','BZ'=>'en','GT'=>'es','SV'=>'es','HN'=>'es','NI'=>'es','CR'=>'es','PA'=>'es','PE'=>'qu','AR'=>'es','BR'=>'pt','CL'=>'es','CO'=>'es','VE'=>'es','BO'=>'qu','GY'=>'en','EC'=>'es','GF'=>'fr','PY'=>'es','SR'=>'nl','UY'=>'es','FK'=>'en'
```

成功返回：

```json
{  "code": 200,  "msg": "OK"}
```

失败返回：

```json
{  "code": 202,  "reason": "失败原因"}{  "code": 201,  "reason": "异常原因"}
```
