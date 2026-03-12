# 盒子内 SDK API（8000）

更新日期：2026-03-09

基准文档：盒子内SDK API 开发文档（MYT-SDK）

本地调用说明：

使用 `hardware_adapters/myt_client.py` 的 `MytSdkClient` 或 `sdk.*` 动作。参数名优先与文档一致，同时部分字段支持 snake_case 别名（例如 `image_url` ↔ `imageUrl`）。

## 1. 获取API版本信息

功能说明：获取当前API版本信息
请求方式：GET
请求 URL：http://{主机IP}:8000/info
路径：`/info`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/info"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "latestVersion": 110,    "currentVersion": 108  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取版本信息失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| latestVersion | int | 线上最新版本号 |
| currentVersion | int | 当前本地版本号 |

注意事项：

- 当 currentVersion < latestVersion 时，建议更新SDK

## 2. 获取设备基本信息

功能说明：获取当前设备的硬件和系统信息
请求方式：GET
请求 URL：http://{主机IP}:8000/info/device
路径：`/info/device`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/info/device"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "ip": "192.168.99.108",    "ip_1": "192.168.100.108",    "hwaddr": "AA:BB:CC:DD:EE:FF",    "hwaddr_1": "AA:BB:CC:DD:EE:F1",    "cputemp": 45,    "cpuload": "1.5",    "memtotal": "8GB",    "memuse": "4.2GB",    "mmctotal": "256GB",    "mmcuse": "120GB",    "version": "v1.1.0",    "deviceId": "MYT-P1-001",    "model": "P1",    "speed": "1000Mbps",    "mmcread": "150MB/s",    "mmcwrite": "120MB/s",    "sysuptime": "10天5小时",    "mmcmodel": "Samsung EVO",    "mmctemp": "38",    "network4g": "未连接",    "netWork_eth0": "已连接"  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取设备信息失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| ip | string | 网口IP |
| ip_1 | string | 网口1的IP |
| hwaddr | string | MAC地址 |
| hwaddr_1 | string | MAC1地址 |
| cputemp | int | CPU温度 |
| cpuload | string | CPU负载 |
| memtotal | string | 内存总大小 |
| memuse | string | 内存已使用大小 |
| mmctotal | string | 磁盘总大小 |
| mmcuse | string | 磁盘已使用大小 |
| version | string | 固件版本 |
| deviceId | string | 设备ID |
| model | string | 型号版本 |
| speed | string | 网口速率 |
| mmcread | string | 磁盘读取量 |
| mmcwrite | string | 磁盘写入量 |
| sysuptime | string | 设备运行时间 |
| mmcmodel | string | 磁盘型号 |
| mmctemp | string | 磁盘温度 |
| network4g | string | 4G网卡状态 |
| netWork_eth0 | string | ETH0网卡状态 |

## 1. 获取安卓云机列表

功能说明：获取设备上所有安卓云机容器列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android
路径：`/android`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 否 | string | 根据云机名过滤 |
| running | 否 | bool | 根据云机是否运行过滤，false查询所有 |
| indexNum | 否 | int | 根据云机实例位序号过滤(0-24) |

请求示例：

```text
# 获取所有云机curl "http://192.168.99.108:8000/android"# 根据名称过滤curl "http://192.168.99.108:8000/android?name=test"# 只获取运行中的云机curl "http://192.168.99.108:8000/android?running=true"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 2,    "list": [      {        "id": "abc123def456",        "name": "android-01",        "status": "running",        "indexNum": 1,        "dataPath": "/myt/data/android-01",        "modelPath": "/myt/model/android-01",        "image": "registry.example.com/android:v12",        "ip": "192.168.100.101",        "networkName": "myt_bridge",        "portBindings": {},        "dns": "223.5.5.5",        "doboxFps": "60",        "doboxWidth": "1080",        "doboxHeight": "1920",        "doboxDpi": "480",        "mgenable": "0",        "gmsenable": "0",        "s5User": "",        "s5Password": "",        "s5IP": "",        "s5Port": "",        "s5Type": "0",        "created": "2024-01-15 10:30:00",        "started": "2024-01-15 10:31:00",        "finished": "",        "customBinds": [],        "PINCode": ""      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取云机列表失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 云机容器ID |
| name | string | 云机名称 |
| status | string | 状态(running/stopped) |
| indexNum | int | 云机实例位序号 |
| dataPath | string | 云机Data文件在设备里的路径 |
| modelPath | string | 云机机型文件在设备里的路径 |
| image | string | 云机所用的镜像 |
| ip | string | 云机局域网IP |
| networkName | string | 容器网卡名称 |
| dns | string | 云机DNS |
| doboxFps | string | 云机FPS |
| doboxWidth | string | 云机分辨率的宽 |
| doboxHeight | string | 云机分辨率的高 |
| doboxDpi | string | 云机DPI |
| mgenable | string | magisk开关，0-关，1-开 |
| gmsenable | string | gms开关，0-关，1-开 |
| s5User | string | s5代理用户名 |
| s5Password | string | s5代理密码 |
| s5IP | string | s5代理IP |
| s5Port | string | s5代理端口 |
| s5Type | string | 代理类型，0-不开启，1-本地域名解析，2-服务器域名解析 |
| created | string | 云机容器创建时间 |
| started | string | 云机容器上次开启时间 |
| finished | string | 云机容器上次关闭时间 |
| customBinds | array | 自定义文件映射 |
| PINCode | string | 自定义屏幕锁屏密码 |

## 2. 创建安卓云机

功能说明：创建一个新的安卓云机容器
请求方式：POST
请求 URL：http://{主机IP}:8000/android
路径：`/android`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| imageUrl | 是 | string | 镜像完整地址 |
| dns | 是 | string | 云机DNS，例如223.5.5.5 |
| modelId | 否 | string | 线上机型ID |
| modelName | 否 | string | 线上机型名称 |
| LocalModel | 否 | string | 本地机型名称 |
| modelStatic | 否 | string | 本地静态机型名称(优先级最高) |
| indexNum | 否 | int | 实例序号，P1范围1-24，Q1范围1-12，传0自动分配 |
| sandboxSize | 否 | string | 沙盒大小，例如16GB，32GB |
| offset | 否 | string | 云机的开机时间 |
| doboxFps | 否 | string | 云机FPS |
| doboxWidth | 否 | string | 云机分辨率的宽 |
| doboxHeight | 否 | string | 云机分辨率的高 |
| doboxDpi | 否 | string | 云机DPI |
| network | 否 | object | 独立IP设置 |
| start | 否 | bool | 创建完成是否开机，默认true |
| mgenable | 否 | string | magisk开关，0-关，1-开，默认0 |
| gmsenable | 否 | string | gms开关，0-关，1-开，默认0 |
| latitude | 否 | float | 纬度 |
| longitude | 否 | float | 经度 |
| countryCode | 否 | string | 国家代码，例如CN，US |
| portMappings | 否 | array | 自定义端口映射 |
| s5User | 否 | string | s5代理用户名 |
| s5Password | 否 | string | s5代理密码 |
| s5IP | 否 | string | s5代理IP |
| s5Port | 否 | string | s5代理端口 |
| s5Type | 否 | string | 代理类型，0-不开启，1-tun2socks，2-tun2proxy |
| mytBridgeName | 否 | string | myt_bridge网卡名 |
| customBinds | 否 | array | 自定义文件映射 |
| PINCode | 否 | string | 屏幕锁屏密码，4-8位数字 |

network 结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| gw | string | 网关，例如192.168.100.1 |
| ip | string | 云机要设置的IP |
| subnet | string | 掩码，例如192.168.100.0/24 |

portMappings 结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| containerPort | int | 容器内端口 |
| hostPort | int | 主机端口 |
| hostIP | string | 主机IP |
| protocol | string | 协议(tcp/udp)，默认tcp |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "imageUrl": "registry.example.com/android:v12",    "dns": "223.5.5.5",    "modelId": "1",    "indexNum": 1,    "doboxFps": "60",    "doboxWidth": "1080",    "doboxHeight": "1920",    "doboxDpi": "480",    "start": true  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "id": "abc123def456789"  }}
```

失败返回：

```json
{  "code": 500,  "message": "创建云机失败: 镜像不存在",  "data": null}
```

注意事项：

- name必须唯一，不能与已有云机重名
- imageUrl必须是已拉取到本地的镜像地址
- indexNum范围：P1设备1-24，Q1设备1-12
- modelStatic优先级高于LocalModel和线上机型

## 3. 重置安卓云机

功能说明：重置指定的安卓云机
请求方式：PUT
请求 URL：http://{主机IP}:8000/android
路径：`/android`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| latitude | 否 | float | 纬度 |
| longitude | 否 | float | 经度 |
| countryCode | 否 | string | 国家代码，例如CN，US |

请求示例：

```bash
curl -X PUT "http://192.168.99.108:8000/android" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "latitude": 39.9042,    "longitude": 116.4074,    "countryCode": "CN"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "重置云机失败: 云机不存在",  "data": null}
```

注意事项：

- 重置会清除云机内的所有数据
- 重置前请确保已备份重要数据

## 4. 删除安卓云机

功能说明：删除指定的安卓云机容器
请求方式：DELETE
请求 URL：http://{主机IP}:8000/android
路径：`/android`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/android" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除云机失败: 云机正在运行",  "data": null}
```

注意事项：

- 删除操作不可恢复
- 建议删除前先停止云机

## 5. 切换安卓镜像

功能说明：切换云机使用的安卓镜像
请求方式：POST
请求 URL：http://{主机IP}:8000/android/switchImage
路径：`/android/switchImage`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| imageUrl | 是 | string | 镜像完整地址 |
| modelId | 否 | string | 机型ID |
| LocalModel | 否 | string | 本地机型名称 |
| modelStatic | 否 | string | 本地静态机型名称 |
| dns | 否 | string | 云机DNS |
| offset | 否 | string | 云机的开机时间 |
| doboxFps | 否 | string | 云机FPS |
| doboxWidth | 否 | string | 云机分辨率的宽 |
| doboxHeight | 否 | string | 云机分辨率的高 |
| doboxDpi | 否 | string | 云机DPI |
| network | 否 | object | 独立IP设置 |
| start | 否 | bool | 切换完成是否开机，默认true |
| mgenable | 否 | string | magisk开关，0-关，1-开 |
| gmsenable | 否 | string | gms开关，0-关，1-开 |
| latitude | 否 | float | 纬度 |
| longitude | 否 | float | 经度 |
| countryCode | 否 | string | 国家代码 |
| s5User | 否 | string | s5代理用户名 |
| s5Password | 否 | string | s5代理密码 |
| s5IP | 否 | string | s5代理IP |
| s5Port | 否 | string | s5代理端口 |
| s5Type | 否 | string | 代理类型 |
| customBinds | 否 | array | 自定义文件映射 |
| PINCode | 否 | string | 屏幕锁屏密码 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/switchImage" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "imageUrl": "registry.example.com/android:v13",    "start": true  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "message": "镜像切换成功"  }}
```

失败返回：

```json
{  "code": 500,  "message": "切换镜像失败: 镜像不存在",  "data": null}
```

注意事项：

- 切换镜像会重置云机数据
- 确保目标镜像已拉取到本地

## 6. 切换机型

功能说明：切换云机的机型配置
请求方式：POST
请求 URL：http://{主机IP}:8000/android/switchModel
路径：`/android/switchModel`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| modelId | 否 | string | 机型ID |
| localModel | 否 | string | 本地机型名称 |
| modelStatic | 否 | string | 本地静态机型名称 |
| latitude | 否 | float | 纬度 |
| longitude | 否 | float | 经度 |
| countryCode | 否 | string | 国家代码 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/switchModel" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "modelId": "2",    "countryCode": "US"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "切换机型失败: 机型不存在",  "data": null}
```

## 7. 拉取安卓镜像

功能说明：从镜像仓库拉取安卓镜像到本地
请求方式：POST
请求 URL：http://{主机IP}:8000/android/pullImage
路径：`/android/pullImage`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| imageUrl | 是 | string | 镜像完整地址 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/pullImage" \  -H "Content-Type: application/json" \  -d '{    "imageUrl": "registry.example.com/android:v12"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "拉取镜像失败: 网络连接超时",  "data": null}
```

注意事项：

- 拉取镜像可能需要较长时间，取决于网络速度和镜像大小
- 确保设备有足够的磁盘空间

## 8. 启动安卓云机

功能说明：启动指定的安卓云机
请求方式：POST
请求 URL：http://{主机IP}:8000/android/start
路径：`/android/start`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/start" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "启动云机失败: 云机已在运行",  "data": null}
```

## 9. 关闭安卓云机

功能说明：关闭指定的安卓云机
请求方式：POST
请求 URL：http://{主机IP}:8000/android/stop
路径：`/android/stop`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/stop" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "关闭云机失败: 云机未运行",  "data": null}
```

## 10. 重启安卓云机

功能说明：重启指定的安卓云机
请求方式：POST
请求 URL：http://{主机IP}:8000/android/restart
路径：`/android/restart`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/restart" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "重启云机失败",  "data": null}
```

## 11. 获取本地镜像列表

功能说明：获取设备上已拉取的Docker镜像列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android/image
路径：`/android/image`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| imageName | 否 | string | 根据镜像名过滤 |

请求示例：

```bash
curl "http://192.168.99.108:8000/android/image"# 根据名称过滤curl "http://192.168.99.108:8000/android/image?imageName=android"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 2,    "list": [      {        "id": "sha256:abc123",        "imageUrl": "registry.example.com/android:v12",        "size": "2.5GB",        "created": "2024-01-10 08:00:00",        "labels": {          "version": "12",          "type": "android"        }      },      {        "id": "sha256:def456",        "imageUrl": "registry.example.com/android:v13",        "size": "2.8GB",        "created": "2024-01-15 10:00:00",        "labels": {          "version": "13",          "type": "android"        }      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取镜像列表失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 镜像ID |
| imageUrl | string | 镜像完整地址 |
| size | string | 镜像大小 |
| created | string | 创建时间 |
| labels | object | 镜像labels |

## 12. 删除本地镜像

功能说明：删除设备上的本地Docker镜像
请求方式：DELETE
请求 URL：http://{主机IP}:8000/android/image
路径：`/android/image`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| imageUrl | 是 | string | 要删除的镜像完整地址 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/android/image" \  -H "Content-Type: application/json" \  -d '{    "imageUrl": "registry.example.com/android:v12"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除镜像失败: 镜像正在被使用",  "data": null}
```

注意事项：

- 正在被云机使用的镜像无法删除
- 删除前请确保没有云机依赖该镜像

## 13. 获取本地镜像压缩包列表

功能说明：获取设备上的镜像压缩包文件列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android/imageTar
路径：`/android/imageTar`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| filename | 否 | string | 根据文件名过滤 |

请求示例：

```bash
curl "http://192.168.99.108:8000/android/imageTar"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 2,    "list": [      {        "name": "android_v12.tar",        "size": "2.5GB"      },      {        "name": "android_v13.tar",        "size": "2.8GB"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取镜像压缩包列表失败",  "data": null}
```

## 14. 删除本地镜像压缩包

功能说明：删除设备上的镜像压缩包文件
请求方式：DELETE
请求 URL：http://{主机IP}:8000/android/imageTar
路径：`/android/imageTar`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| filename | 是 | string | 要删除的镜像压缩包名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/android/imageTar" \  -H "Content-Type: application/json" \  -d '{    "filename": "android_v12.tar"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除镜像压缩包失败: 文件不存在",  "data": null}
```

## 15. 导出安卓镜像

功能说明：将本地镜像导出为压缩包文件
请求方式：POST
请求 URL：http://{主机IP}:8000/android/image/export
路径：`/android/image/export`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| imageUrl | 是 | string | 要导出的镜像完整地址 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/image/export" \  -H "Content-Type: application/json" \  -d '{    "imageUrl": "registry.example.com/android:v12"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "filename": "android_v12_20240115.tar"  }}
```

失败返回：

```json
{  "code": 500,  "message": "导出镜像失败: 磁盘空间不足",  "data": null}
```

注意事项：

- 导出过程可能需要较长时间
- 确保设备有足够的磁盘空间

## 16. 下载导出后的安卓镜像包

功能说明：下载已导出的镜像压缩包文件
请求方式：GET
请求 URL：http://{主机IP}:8000/android/image/download
路径：`/android/image/download`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| filename | 是 | string | 要下载的镜像包名 |

请求示例：

```bash
curl "http://192.168.99.108:8000/android/image/download?filename=android_v12.tar" -o android_v12.tar
```

失败返回：

```json
{  "code": 500,  "message": "下载失败: 文件不存在",  "data": null}
```

## 17. 导入安卓镜像

功能说明：通过上传tar文件导入安卓镜像
请求方式：POST
请求 URL：http://{主机IP}:8000/android/image/import
路径：`/android/image/import`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 导入镜像包文件，tar格式 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/image/import" \  -F "file=@android_v12.tar"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "导入镜像失败: 文件格式错误",  "data": null}
```

注意事项：

- 仅支持tar格式的镜像包
- 导入过程可能需要较长时间

## 18. 导出安卓云机

功能说明：将安卓云机导出为压缩包
请求方式：POST
请求 URL：http://{主机IP}:8000/android/export
路径：`/android/export`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/export" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "exportName": "android-01_20240115.zip"  }}
```

失败返回：

```json
{  "code": 500,  "message": "导出云机失败: 云机正在运行",  "data": null}
```

注意事项：

- 建议导出前先停止云机
- 导出文件包含云机的完整数据

## 19. 导入安卓云机

功能说明：通过上传文件导入安卓云机
请求方式：POST
请求 URL：http://{主机IP}:8000/android/import
路径：`/android/import`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 导入使用本SDK导出的安卓云机 |
| indexNum | 是 | int | 实例序号，P1范围1-24，Q1范围1-12 |
| name | 否 | string | 导入后云机名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/import" \  -F "file=@android-01_20240115.zip" \  -F "indexNum=2" \  -F "name=android-02"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "name": "android-02"  }}
```

失败返回：

```json
{  "code": 500,  "message": "导入云机失败: 实例位已被占用",  "data": null}
```

注意事项：

- 仅支持本SDK导出的云机文件
- indexNum不能与已有云机冲突

## 20. 获取机型列表

功能说明：获取线上可用的机型列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android/phoneModel
路径：`/android/phoneModel`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/android/phoneModel"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "total": 50,    "list": [      {        "id": "1",        "name": "Samsung Galaxy S23",        "md5": "abc123def456",        "status": "active",        "currentVersion": 1,        "sdk_ver": "v1.1.0",        "createdAt": 1705286400      },      {        "id": "2",        "name": "Xiaomi 14",        "md5": "def456ghi789",        "status": "active",        "currentVersion": 1,        "sdk_ver": "v1.1.0",        "createdAt": 1705286400      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取机型列表失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 机型ID |
| name | string | 机型名称 |
| md5 | string | 机型文件MD5 |
| status | string | 状态 |
| currentVersion | int | 当前版本 |
| sdk_ver | string | 对应SDK版本 |
| createdAt | int64 | 创建时间戳 |

## 21. 获取国家代码列表

功能说明：获取可用的国家代码列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android/countryCode
路径：`/android/countryCode`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/android/countryCode"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 200,    "list": [      {        "countryName": "中国",        "countryCode": "CN"      },      {        "countryName": "美国",        "countryCode": "US"      },      {        "countryName": "日本",        "countryCode": "JP"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取国家代码列表失败",  "data": null}
```

## 22. 设置Macvlan

功能说明：设置Macvlan网络配置
请求方式：POST
请求 URL：http://{主机IP}:8000/android/macvlan
路径：`/android/macvlan`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| gw | 是 | string | 网关，例如192.168.100.1 |
| subnet | 是 | string | 掩码，例如192.168.100.0/24 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/macvlan" \  -H "Content-Type: application/json" \  -d '{    "gw": "192.168.100.1",    "subnet": "192.168.100.0/24"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置Macvlan失败: 网关格式错误",  "data": null}
```

注意事项：

- 设置后需要重启相关云机才能生效
- 确保网关和子网配置正确

## 23. 设置云机容器IP (Macvlan模式)

功能说明：在Macvlan模式下设置云机容器的IP地址
请求方式：POST
请求 URL：http://{主机IP}:8000/android/macvlan
路径：`/android/macvlan`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| ip | 是 | string | 云机要设置的IP |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/macvlan" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "ip": "192.168.100.101"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置IP失败: IP已被占用",  "data": null}
```

## 24. 修改云机容器名称

功能说明：修改云机容器的名称
请求方式：POST
请求 URL：http://{主机IP}:8000/android/rename
路径：`/android/rename`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机当前名称 |
| newName | 是 | string | 云机新名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/rename" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "newName": "my-android"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "修改名称失败: 新名称已存在",  "data": null}
```

注意事项：

- 新名称不能与已有云机重名
- 建议在云机停止状态下修改

## 25. 获取机型备份�列表

功能说明：获取已备份的机型数据列表
请求方式：GET
请求 URL：http://{主机IP}:8000/android/backup/model
路径：`/android/backup/model`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/android/backup/model"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 3,    "list": [      {        "name": "samsung_s23_backup"      },      {        "name": "xiaomi_14_backup"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取机型备份列表失败",  "data": null}
```

## 26. 删除机型备份

功能说明：删除指定的机型备份数据
请求方式：DELETE
请求 URL：http://{主机IP}:8000/android/backup/model
路径：`/android/backup/model`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 机型备份文件名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/android/backup/model" \  -H "Content-Type: application/json" \  -d '{    "name": "samsung_s23_backup"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除机型备份失败: 文件不存在",  "data": null}
```

## 27. 备份机型数据

功能说明：将V3镜像创建的云机里的机型数据完整备份
请求方式：POST
请求 URL：http://{主机IP}:8000/android/backup/model
路径：`/android/backup/model`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 要备份机型数据的云机名称 |
| suffix | 是 | string | 备份后机型数据的后缀名 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/backup/model" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01",    "suffix": "backup_20240115"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "备份机型数据失败: 云机不存在",  "data": null}
```

注意事项：

- 仅支持V3镜像创建的云机
- 备份前建议停止云机

## 28. 导出机型备份数据

功能说明：导出已备份的机型数据
请求方式：POST
请求 URL：http://{主机IP}:8000/android/backup/modelExport
路径：`/android/backup/modelExport`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 备份机型数据文件名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/backup/modelExport" \  -H "Content-Type: application/json" \  -d '{    "name": "samsung_s23_backup"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "导出机型备份失败: 文件不存在",  "data": null}
```

## 29. 导入备份机型数据

功能说明：通过上传ZIP包导入备份的机型数据
请求方式：POST
请求 URL：http://{主机IP}:8000/android/backup/modelImport
路径：`/android/backup/modelImport`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 导入备份机型数据ZIP包 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/backup/modelImport" \  -F "file=@samsung_s23_backup.zip"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

注意事项：

- 仅支持ZIP格式的备份文件

## 30. 安卓云机执行命令

功能说明：在安卓云机内执行命令
请求方式：POST
请求 URL：http://{主机IP}:8000/android/exec
路径：`/android/exec`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| command | 是 | array | 执行的命令，数组形式 |

请求示例：

```text
下载并安装小红书 APKcurl --location --request POST 'http://192.168.99.91:8000/android/exec' \--header 'User-Agent: Apifox/1.0.0 (https://apifox.com)' \--header 'Content-Type: application/json' \--header 'Accept: */*' \--header 'Host: 192.168.99.91:8000' \--header 'Connection: keep-alive' \--data-raw '{    "name": "3333333",    "command": ["sd", "-c", "curl -fsSL -o /sdcard/Download/xhs.apk https://redgray.xhscdn.com/ui/androidPublish/prod/xhs/channel/apk/9.17.0/9170809/v9170809-xhs-share_package_common_X64.apk && cp /sdcard/Download/xhs.apk /data/local/tmp/xhs.apk && pm install /data/local/tmp/xhs.apk && rm /data/local/tmp/xhs.apk"]}'
```

成功返回：

```text
Success
```

失败返回：

```json
{  "code": 500,  "message": "执行命令失败: 云机未运行",  "data": null}
```

注意事项：

- 云机必须处于运行状态
- command参数为数组格式，例如 ["sd", "-c", "ls -la"]

## 31. 清理所有未被使用镜像

功能说明：清理设备上所有未被云机使用的镜像
请求方式：POST
请求 URL：http://{主机IP}:8000/android/pruneImages
路径：`/android/pruneImages`

请求参数：无

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/android/pruneImages"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "pruneCount": 5,    "releaseSpace": "12.5GB"  }}
```

失败返回：

```json
{  "code": 500,  "message": "清理镜像失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| pruneCount | int | 清理数量 |
| releaseSpace | string | 释放空间 |

注意事项：

- 此操作不可恢复
- 仅清理未被任何云机使用的镜像

## 32. 批量切换容器镜像

功能说明：清理设备上所有未被云机使用的镜像
请求方式：POST
请求 URL：http://{主机IP}:8000/android/change-image
路径：`/android/change-image`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| containerNames | 是 | array | 云机容器名称列表 |
| image | 是 | string | 目标镜像完整地址 |

请求示例：

```bash
curl http://192.168.99.108:8000/android/change-image \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "containerNames": [    "test-1", "test-2", "test-3"  ],  "image": "registry.cn-guangzhou.aliyuncs.com/mytos/dobox:myt_supser_sdk_v1.0.14.30.36.1",}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "taskId": "mdezt502491dgy413sp0hpf200goqkoa",    "message": "任务已提交，请使用 taskId 查询进度"  }}
```

失败返回：

```json
{  "code": 51,  "message": "The image field is required",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| message | string | 任务提交成功 |
| taskId | string | 任务ID |

## 33. 复制云机

功能说明：复制指定云机的配置和数据，创建多个相同的云机实例
请求方式：GET
请求 URL：http://{主机IP}:8000/android/copy
路径：`/android/copy`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机名称 |
| indexNum | 否 | int | 实例序号，P1范围1-24，Q1范围1-12，要复制到的目标实例号 |
| count | 否 | int | 复制的数量，一次最大20个 |

请求示例：

```bash
GET "http://192.168.99.108:8000/android/copy?name=1772502684783_2_T0002&indexNum=6"或者curl 'curl 'http://192.168.99.108:8000/android/copy?name=1772502684783_2_T0002&indexNum=6'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

## 34. 查询指定任务进度

功能说明：复制指定云机的配置和数据，创建多个相同的云机实例
请求方式：GET
请求 URL：http://{主机IP}:8000/android/task-status
路径：`/android/task-status`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| taskId | 是 | string | 任务 ID（异步任务返回的 taskId） |

请求示例：

```bash
GET "http://192.168.99.108:8000/android/copy?task-status?taskId=mdezt502491dgy413sp0hpf200goqkoa"或者curl 'http://192.168.99.183:8000/android/task-status?taskId=mdezt502491dgy413sp0hpf200goqkoa'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "taskId": "tmdezt502491dgy413sp0hpf200goqkoa",    "taskType": "change-image",    "progress": 80,    "status": "running",    "successCount": 2,    "failCount": 0,    "totalCount": 3,    "failDetail": [],    "createTime": "2026-03-09 16:30:00",    "updateTime": "2026-03-09 16:35:00"  }}
```

失败返回：

```json
{  "code": 50,  "message": "任务不存在",  "data": null}
```

## 1. 获取备份压缩包文件列表

功能说明：获取设备上的云机备份压缩包文件列表
请求方式：GET
请求 URL：http://{主机IP}:8000/backup
路径：`/backup`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 否 | string | 根据文件名过滤 |

请求示例：

```bash
curl "http://192.168.99.108:8000/backup"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 3,    "list": [      {        "name": "android-01_20240115.zip",        "size": "1.2GB"      },      {        "name": "android-02_20240116.zip",        "size": "1.5GB"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取备份列表失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 备份压缩包文件名 |
| size | string | 备份压缩包大小 |

## 2. 下载备份压缩包文件

功能说明：下载指定的云机备份压缩包
请求方式：GET
请求 URL：http://{主机IP}:8000/backup/download
路径：`/backup/download`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 备份压缩包文件名 |

请求示例：

```bash
curl "http://192.168.99.108:8000/backup/download?name=android-01_20240115.zip" -o android-01_20240115.zip
```

失败返回：

```json
{  "code": 500,  "message": "下载失败: 文件不存在",  "data": null}
```

## 3. 删除备份压缩包文件

功能说明：删除指定的云机备份压缩包
请求方式：DELETE
请求 URL：http://{主机IP}:8000/backup
路径：`/backup`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 备份压缩包文件名 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/backup" \  -H "Content-Type: application/json" \  -d '{    "name": "android-01_20240115.zip"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除备份失败: 文件不存在",  "data": null}
```

## 1. 连接设备SSH

功能说明：提供基于 WebSocket 的 SSH 终端流服务，用于在 Web 页面或客户端中建立 SSH 连接，而非直接返回静态网页。
请求方式：WebSocket（基于 HTTP 升级协议）
请求 URL：http://{主机IP}:8000/ssh
路径：`/ssh`

请求参数：无

请求示例：

```text
# 1.在浏览器中直接访问：在浏览器地址栏直接输入以下地址，浏览器会自动完成 WebSocket 握手并渲染http://192.168.99.108:8000/ssh# 2.代码对接（流方式）：若需在程序中对接，需使用 WebSocket 客户端库，以下为 Python 示例：import asyncioimport websocketsimport json# 核心配置（替换为你的实际账号密码）WS_URL = "ws://10.10.0.32:8000/link/ssh"SSH_USER = "user"SSH_PASSWORD = "myt"async def ssh_ws_client():    """WebSocket 连接 SSH 终端并收发数据"""    try:        # 1. 建立 WebSocket 连接        async with websockets.connect(WS_URL) as websocket:            print(f"✅ 已连接到 {WS_URL}")            # 2. 发送鉴权数据（核心：无鉴权则无法获取有效流数据）            auth_data = json.dumps({                "username": SSH_USER,                "password": SSH_PASSWORD            })            await websocket.send(auth_data)            print(f"📤 已发送鉴权信息：{auth_data}")            # 3. 持续接收 SSH 流数据（模拟终端输出）            print("📥 开始接收 SSH 终端数据（按 Ctrl+C 停止）：")            print("-" * 50)            while True:                # 阻塞接收服务端推送的字节流/字符串数据                data = await websocket.recv()                # 解码并保持终端格式输出                if isinstance(data, bytes):                    print(data.decode("utf-8", errors="ignore"), end="")                else:                    print(data, end="")    except ConnectionRefusedError:        print(f"❌ 连接失败：请检查 10.10.0.32 的 8000 端口是否开放、IP 是否正确")    except websockets.exceptions.ConnectionClosed:        print("\n🔌 SSH 连接已断开")    except Exception as e:        print(f"❌ 异常：{type(e).__name__} - {str(e)}")if __name__ == "__main__":    # 适配 Windows 系统 asyncio 策略    try:        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())    except AttributeError:        pass    # 启动客户端    asyncio.run(ssh_ws_client())
```

注意事项：

- 该接口为 WebSocket 流服务，不支��持普通 HTTP 客户端（如 curl）直接访问，否则会报错 upgrade token not found。
- 必须使用支持 WebSocket 协议的客户端（浏览器、WebSocket 库）以 “流” 的方式对接，持续收发数据。
- 默认用户名：user

## 2. 修改SSH登录用户密码

功能说明：修改SSH登录用户的密码
请求方式：POST
请求 URL：http://{主机IP}:8000/link/ssh/changePwd
路径：`/link/ssh/changePwd`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| username | 否 | string | 用户名，默认user |
| password | 是 | string | 新密码 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/link/ssh/changePwd" \  -H "Content-Type: application/json" \  -d '{    "username": "user",    "password": "newpassword123"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "修改密码失败",  "data": null}
```

注意事项：

- 密码修改后立即生效
- 请牢记新密码

## 3. 开关SSH root登录

功能说明：启用或禁止SSH root用户登录
请求方式：POST
请求 URL：http://{主机IP}:8000/link/ssh/switchRoot
路径：`/link/ssh/switchRoot`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| enable | 是 | bool | true-启用root登录，false-禁止root登录 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/link/ssh/switchRoot" \  -H "Content-Type: application/json" \  -d '{    "enable": true  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置失败",  "data": null}
```

注意事项：

- 出于安全考虑，建议禁用root登录

## 4. 开关SSH服务

功能说明：启用或关闭SSH服务
请求方式：POST
请求 URL：http://{主机IP}:8000/link/ssh/enable
路径：`/link/ssh/enable`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| enable | 是 | bool | true-启用ssh服务，false-关闭ssh服务 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/link/ssh/enable" \  -H "Content-Type: application/json" \  -d '{    "enable": true  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置SSH服务失败",  "data": null}
```

## 5. 连接容器终端

功能说明：通过Web页面连接云机容器终端
请求方式：GET
请求 URL：http://{主机IP}:8000/link/exec
路径：`/link/exec`

请求参数：无

请求示例：

```text
# 在浏览器中直接访问http://192.168.99.108:8000/container/exec
```

注意事项：

- 需要在浏览器中访问
- 可以选择要连接的云机容器

## 1. 获取myt_bridge网卡列表

功能说明：获取设备上的myt_bridge网卡列表
请求方式：GET
请求 URL：http://{主机IP}:8000/mytBridge
路径：`/mytBridge`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/mytBridge"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 2,    "list": [      {        "name": "myt_bridge",        "cidr": "172.17.0.1/16"      },      {        "name": "myt_bridge_lan",        "cidr": "10.0.0.1/16"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取网卡列表失败",  "data": null}
```

## 2. 创建myt_bridge网卡

功能说明：创建新的myt_bridge网卡
请求方式：POST
请求 URL：http://{主机IP}:8000/mytBridge
路径：`/mytBridge`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| customName | 是 | string | 自定义名(最多4字符)，会拼接在myt_bridge后面 |
| cidr | 是 | string | CIDR，例如10.0.0.1/16 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/mytBridge" \  -H "Content-Type: application/json" \  -d '{    "customName": "lan",    "cidr": "10.0.0.1/16"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "创建网卡失败: 名称已存在",  "data": null}
```

注意事项：

- customName最多4个字符
- 创建后网卡名为 myt_bridge_customName

## 3. 更新myt_bridge网卡

功能说明：更新myt_bridge网卡的CIDR配置
请求方式：PUT
请求 URL：http://{主机IP}:8000/mytBridge
路径：`/mytBridge`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 网卡名(全称或自定义名) |
| newCidr | 是 | string | 新CIDR，例如10.0.0.1/16 |

请求示例：

```bash
curl -X PUT "http://192.168.99.108:8000/mytBridge" \  -H "Content-Type: application/json" \  -d '{    "name": "myt_bridge_lan",    "newCidr": "10.0.0.1/24"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "更新网卡失败: 网卡不存在",  "data": null}
```

## 4. 删除myt_bridge网卡

功能说明：删除指定的myt_bridge网卡
请求方式：DELETE
请求 URL：http://{主机IP}:8000/mytBridge
路径：`/mytBridge`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 网卡名(全称或自定义名) |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/mytBridge" \  -H "Content-Type: application/json" \  -d '{    "name": "myt_bridge_lan"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除网卡失败: 网卡正在被使用",  "data": null}
```

注意事项：

- 正在被云机使用的网卡无法删除
- 删除前请确保没有云机依赖该网卡

## 1. 获取网卡详情

功能说明：查询指定 ID 的 macVlan 网卡详细信息
请求方式：GET
请求 URL：http://{主机IP}:8000/macvlan
路径：`/macvlan`

请求参数：无

请求示例：

```bash
GET "http://192.168.99.108:8000/macvlan"
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "macVlan": {      "Name": "myt",      "Id": "24732efd39a53baa9822d49302f701c878e701f2553574fc217e255f1c5289a9",      "Created": "2026-02-04T13:42:39.460109818+08:00",      "Scope": "local",      "Driver": "macvlan",      "EnableIPv6": false,      "IPAM": {        "Driver": "default",        "Options": null,        "Config": [          {            "Subnet": "192.168.99.0/24",            "Gateway": "192.168.99.1"          }        ]      },      "Internal": false,      "Attachable": false,      "Ingress": false,      "ConfigFrom": {        "Network": ""      },      "ConfigOnly": false,      "Containers": {},      "Options": {        "macvlan_mode": "private",        "parent": "eth0"      },      "Labels": {}    }  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取网卡详情失败",  "data": null}
```

## 2. 创建网卡

功能说明：创建新的macVlan网卡
请求方式：POST
请求 URL：http://{主机IP}:8000/macvlan
路径：`/macvlan`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| gw | 是 | string | 网关，例如 192.168.100.1 |
| subnet | 是 | string | 掩码，例如 192.168.100.0/24 |
| private | 否 | boolean | 是否禁止macvlan容器互相访问，默认为 true |

请求示例：

```bash
POST http://192.168.99.108:8000/macvlanContent-Type: application/json请求体{  "gw": "192.168.100.1",  "subnet": "192.168.100.0/24",  "private": true}或者curl http://192.168.99.108:8000/macvlan \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "gw": "",  "subnet": "192.168.100.0/24",  "private": true}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "id": "string"  }}
```

失败返回：

```json
{  "code": 500,  "message": "创建网卡失败",  "data": null}
```

## 3. 更新网卡

功能说明：更新一个已存在的 macVlan 网卡的配置。
请求方式：PUT
请求 URL：http://{主机IP}:8000/macvlan
路径：`/macvlan`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| gw | 是 | string | 新的网关，例如 192.168.100.1 |
| subnet | 是 | string | 新的掩码，例如 192.168.100.0/24 |
| private | 否 | boolean | 是否禁止macvlan容器互相访问，默认为 true |

请求示例：

```bash
POST http://192.168.99.108:8000/macvlanContent-Type: application/json请求体{  "gw": "192.168.100.1",  "subnet": "192.168.100.0/24",  "private": true}或者curl http://192.168.99.108:8000/macvlan \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "gw": "192.168.100.1",  "subnet": "192.168.100.0/24",  "private": true}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "id": "string"  }}
```

失败返回：

```json
{  "code": 500,  "message": "创建网卡失败",  "data": null}
```

## 4. 删除网卡

功能说明：更新一个已存在的 macVlan 网卡的配置。
请求方式：DELETE
请求 URL：http://{主机IP}:8000/macvlan
路径：`/macvlan`

请求参数：无

请求示例：

```bash
curl http://192.168.99.108:8000/macvlan \  --request DELETE
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

## 1. 获取网络分组列表

功能说明：查询所有网络分组列表，支持按别名过滤
请求方式：GET
请求 URL：http://{主机IP}:8000/mytVpc/group
路径：`/mytVpc/group`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| alias | 否 | string | 分组别名，传空查询所有 |

请求示例：

```text
# 查询所有分组GET "http://{主机IP}:8000/mytVpc/group"# 按别名过滤curl "http://192.168.99.108:8000/mytVpc/group?alias=test-group"
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "count": 1,    "list": [      {        "id": 11,        "alias": "111saa",        "url": "",        "vpcs": {          "vpcCount": 1,          "list": [            {              "id": 289,              "groupId": 11,              "remarks": "socks_220csx",              "protocol": "socks",              "profile": "{\"configType\":3,\"remarks\":\"socks_220csx\",\"server\":\"nub2ccs1.user.wuyouip.com\",\"serverPort\":\"xxxx\",\"password\":\"xxxx\",\"username\":\"xxxx\"}",              "outConfig": "{\"protocol\":\"socks\",\"sendThrough\":null,\"tag\":\"socks_220csx_11_1769492725191\",\"settings\":{\"servers\":[{\"address\":\"nub2ccs1.user.wuyouip.com\",\"port\":xxxx,\"level\":8,\"users\":[{\"user\":\"xxxxx\",\"pass\":\"xxxxxx\",\"level\":8}]}]},\"streamSettings\":null,\"proxySettings\":null,\"mux\":{\"enabled\":false,\"concurrency\":-1,\"xudpConcurrency\":0,\"xudpProxyUDP443\":\"\"},\"targetStrategy\":\"\"}",              "source": 2,              "tag": "socks_220csx_11_1769492725191"            }          ]        }      }    ]  }}
```

## 2. 增加网络分组列表

功能说明：创建新的网络分组，支持订阅地址或节点地址模式
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/group
路径：`/mytVpc/group`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| alias | 是 | string | 网络分组别名 |
| addresses | 否 | array | 批量添加节点列表（source=2 时必填） |
| source | 否 | int | 1-订阅地址，2-节点地址，默认 |
| url | 否 | string | 批量添加节点列表（source=1 时必填） |

请求示例：

```text
# 订阅地址模式curl -X POST "http://192.168.99.108:8000/mytVpc/group" \  -H "Content-Type: application/json" \  -d '{    "alias": "test-group",    "source": 1,    "url": "http://example.com/subscribe"  }'# 节点地址模式curl -X POST "http://192.168.99.108:8000/mytVpc/group" \  -H "Content-Type: application/json" \  -d '{    "alias": "node-group",    "source": 2,    "addresses": ["192.168.1.100:8080", "192.168.1.101:8080"]  }'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```text
# 分组名称未填{  "code": 51,  "message": "The alias field is required",  "data": null}# 填错地址{  "code": 50,  "message": "Get \"\": unsupported protocol scheme \"\"",  "data": null}# 分组已存在{  "code": 10021,  "message": "Error: 此订阅分组已存在无法新建",  "data": null}
```

## 3. 更新网络分组名

功能说明：修改指定网络分组的别名
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/group/alias
路径：`/mytVpc/group/alias`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| id | 是 | int | 网络分组ID |
| newAlias | 是 | string | 分组新别名 |

请求示例：

```bash
curl http://192.168.99.108:8000/mytVpc/group/alias \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "id": 1,  "newAlias": "111"}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "更新分组别名失败: 新别名已存在",  "data": null}
```

## 4. 删除网络分组列表

功能说明：删除指定的网络分组，删除前需确保分组内无 VPC 节点
请求方式：DELETE
请求 URL：http://{主机IP}:8000/mytVpc/group
路径：`/mytVpc/group`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| id | 是 | int | 网络分组ID |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/mytVpc/group" \  -H "Content-Type: application/json" \  -d '{    "id": 2  }'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 10022,  "message": "Error: 此订阅分组不存在",  "data": null}
```

## 5. 指定云机 VPC 节点

功能说明：为指定云机绑定 VPC 节点及 DNS 白名单
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/addRule
路径：`/mytVpc/addRule`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机容器名称 |
| vpcID | 是 | int | VPC 节点 ID |
| WhiteListDns | 否 | array | VDNS 白名单列表 |

请求示例：

```bash
curl http://192.168.99.108:8000/mytVpc/addRule \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "name": "p738c384c1581ad24c3fcf199684f5f5_13_T00013",  "vpcID": 1,  "WhiteListDns": [    ""  ]}
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 51,  "message": "The name field is required",  "data": null}或{  "code": 10023,  "message": "Error: 此VPC节点不存在",  "data": null}
```

## 6. 已设置云机 VPC 节点

功能说明：查询已绑定 VPC 节点的云机规则列表
请求方式：GET
请求 URL：http://{主机IP}:8000/mytVpc/containerRule
路径：`/mytVpc/containerRule`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/mytVpc/containerRule"
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "count": 2,    "list": [      {        "id": 1,        "containerID": "5fd727704a60691f7ed5c13575ac261c0f28eebb9aea8141412818f74fa110d5",        "containerIP": "",        "containerName": "Test_1",        "containerState": "running",        "status": 1,        "groupName": "111saa",        "vpcRemarks": "socks_220csx",        "WhiteListDns": []      },      {        "id": 2,        "containerID": "e2e38a2d7ea53d40e58ba5d54327b807a714139dca0ec69faeb176336686a060",        "containerIP": "172.17.0.7",        "containerName": "p738c384c1581ad24c3fcf199684f5f5_13_T00013",        "containerState": "running",        "status": 1,        "groupName": "test-grup",        "vpcRemarks": "澳洲AX01 50500进阶版 0.3x",        "WhiteListDns": []      }    ]  }}
```

## 8. 删除网络分组内节点

功能说明：从指定网络分组中移除一个云机节点。
请求方式：DELETE
请求 URL：http://{主机IP}:8000/mytVpc
路径：`/mytVpc`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| vpcID | 是 | int | 要删除的 VPC 节点 ID |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/mytVpc" \  -H "Content-Type: application/json" \  -d '{    "vpcID": 1  }'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 10023,  "message": "Error: 此VPC节点不存在",  "data": null}
```

## 9. 更新指定网络分组

功能说明：更新指定网络分组的配置信息。
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/group/update
路径：`/mytVpc/group/update`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| ID | 是 | int | 网络分组ID |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/mytVpc" \  -H "Content-Type: application/json" \  -d '{    "vpcID": 1  }'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 10022,  "message": "Error: 此订阅分��组不存在",  "data": null}
```

## 10. 增加socks5节点

功能说明：向指定网络分组添加 socks5 节点。
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/socks
路径：`/mytVpc/socks`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| alias | 是 | string | 订阅分组别名，如果别名不存在将创建新分组，若存在则加入到此分组中 |
| list | 是 | array | socks5 节点列表 |

list  结构：

| 字��段 | 类型 | 说明 |
| --- | --- | --- |
| remarks | string | 节点别名 |
| socksIp | string | s5 IP |
| socksPort | int | s5 端口 |
| socksUser | string | s5 用户名 |
| socksPassword | istring | s5 密码 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/mytVpc/socks" \  -H "Content-Type: application/json" \  -d '{    "alias": "socks-group",    "list": [      {        "remarks": "node1",        "socksIp": "192.168.1.100",        "socksPort": 1080,        "socksUser": "user1",        "socksPassword": "pass123"      }    ]  }'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 51,  "message": "The alias field is required",  "data": null}
```

## 11. 开关DNS白名单

功能说明：启用 / 禁用指定 VPC 规则的 DNS 白名单。
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/whiteListDns
路径：`/mytVpc/whiteListDns`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| ruleID | 是 | int | 规则 ID |
| enable | 否 | bool | 是否启用，默认 true |
| whiteListDns | 否 | array | DNS 白名单列表 |

请求示例：

```bash
curl http://192.168.99.108:8000/mytVpc/whiteListDns \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "ruleID": 1,  "enable": true,  "whiteListDns": [    ""  ]}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

## 12. VPC节点延迟测试

功能说明：测试指定 VPC 节点的网络延迟。
请求方式：GET
请求 URL：http://{主机IP}:8000/mytVpc/test
路径：`/mytVpc/test`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| address | 是 | string | 节点地址，address 格式如 "1.1.1.1:80" 或 "www.google.com:443" |

请求示例：

```bash
curl 'http://192.168.99.108:8000/mytVpc/test?address=50500.b-vm915x.8h2jssajkd.g-songs.ting-wo-shuo-xiexieni.com'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "msg": "dial tcp: address 50500.b-vm915x.8h2jssajkd.g-songs.ting-wo-shuo-xiexieni.com: missing port in address",    "latency": "0ms"  }}
```

## 13. 批量指定云机VPC节点

功能说明：批量指定云机VPC节点
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/addRule/batch
路径：`/mytVpc/addRule/batch`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| names | 是 | array | 云机容器名称列表 |
| vpcID | 是 | integer | vpc节点ID |
| WhiteListDns | 否 | array | DNS白名单 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "names": ["android_1", "android_2"],  "vpcID": 123,  "WhiteListDns": ["8.8.8.8"]}' "http://192.168.99.108:8000/mytVpc/addRule/batch"
```

成功返回：

```json
{  "code": 0,  "message": "批量指定成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "批量指定失败",  "data": null}
```

## 14. 清除云机VPC节点

功能说明：清除指定云机的VPC节点
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/delRule
路径：`/mytVpc/delRule`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机容器名称 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"name": "android_1"}' "http://192.168.99.108:8000/mytVpc/delRule"
```

成功返回：

```json
{  "code": 0,  "message": "清除成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "清除失败，容器不存在",  "data": null}
```

## 15. 批量清除云机VPC节点

功能说明：批量清除云机的VPC节点
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/delRule/batch
路径：`/mytVpc/delRule/batch`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 云机容器名称列表 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"name": ["android_1", "android_2"]}' "http://192.168.99.108:8000/mytVpc/delRule/batch"
```

成功返回：

```json
{  "code": 0,  "message": "批量清除成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "批量清除失败",  "data": null}
```

## 16. 清除容器域名过滤

功能说明：清除指定容器的域名过滤设置
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter
路径：`/mytVpc/domainFilter`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| containerID | 是 | string | 容器ID或名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/mytVpc/domainFilter?containerID=abc123"
```

成功返回：

```json
{  "code": 0,  "message": "清除成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "清除失败，容器不存在",  "data": null}
```

## 17. 查询容器域名过滤

功能说明：查询指定容器的域名过滤列表
请求方式：GET
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter
路径：`/mytVpc/domainFilter`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| containerID | 是 | string | 容器ID或名称 |

请求示例：

```bash
curl -X GET "http://192.168.99.108:8000/mytVpc/domainFilter?containerID=abc123"
```

成功返回：

```json
{  "code": 0,  "message": "查询成功",  "data": {    "domains": ["example.com", "google.com"]  }}
```

失败返回：

```json
{  "code": 500,  "message": "查询失败，容器不存在",  "data": null}
```

## 18. 设置容器域名过滤

功能说明：设置指定容器的域名过滤列表
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter
路径：`/mytVpc/domainFilter`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| containerID | 是 | string | 容器ID或名称 |
| domains | 是 | array | 域名列表，传空数组则清空 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "containerID": "abc123",  "domains": ["example.com", "google.com"]}' "http://192.168.99.108:8000/mytVpc/domainFilter"
```

成功返回：

```json
{  "code": 0,  "message": "设置成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置失败",  "data": null}
```

## 19. 清除全局域名过滤

功能说明：清除全局域名过滤设置
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter/global
路径：`/mytVpc/domainFilter/global`

请求参数：无

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "containerID": "abc123",  "domains": ["example.com", "google.com"]}' "http://192.168.99.108:8000/mytVpc/domainFilter"
```

成功返回：

```json
{  "code": 0,  "message": "清除成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "清除失败",  "data": null}
```

## 20. 查询全局域名过滤

功能说明：查询全局域名过滤列表
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter/global
路径：`/mytVpc/domainFilter/global`

请求参数：无

请求示例：

```bash
curl -X GET "http://192.168.99.108:8000/mytVpc/domainFilter/global"
```

成功返回：

```json
{  "code": 0,  "message": "查询成功",  "data": {    "domains": ["example.com", "*.blocked.com"]  }}
```

失败返回：

```json
{  "code": 500,  "message": "查询失败",  "data": null}
```

## 21. 设置全局域名过滤

功能说明：设置全局域名过滤列表
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/domainFilter/global
路径：`/mytVpc/domainFilter/global`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| domains | 是 | array | 域名列表，支持 domain:/full:/keyword:/regexp: 前缀，传空数组则清空 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "domains": ["domain:example.com", "keyword:blocked"]}' "http://192.168.99.108:8000/mytVpc/domainFilter/global"
```

成功返回：

```json
{  "code": 0,  "message": "设置成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "设置失败",  "data": null}
```

## 22. 更新网络分组别名

功能说明：更新网络分组别名
请求方式：POST
请求 URL：http://{主机IP}:8000/mytVpc/group/alias
路径：`/mytVpc/group/alias`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| id | 是 | integer | 网络分组ID |
| newAlias | 是 | string | 分组新别名 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"id":123, "newAlias": "newgroup"}' "http://192.168.99.108:8000/mytVpc/group/alias"
```

成功返回：

```json
{  "code": 0,  "message": "更新成功",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "更新失败，分组不存在",  "data": null}
```

## 1. 获取本地机型列表

功能说明：获取设备上的本地机型数据列表
请求方式：GET
请求 URL：http://{主机IP}:8000/phoneModel
路径：`/phoneModel`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/phoneModel"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 5,    "list": [      {        "name": "samsung_s23"      },      {        "name": "xiaomi_14"      },      {        "name": "pixel_8"      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取本地机型列表失败",  "data": null}
```

返回字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 机型文件名称 |

## 2. 删除本地机型数据

功能说明：删除指定的本地机型数据
请求方式：DELETE
请求 URL：http://{主机IP}:8000/phoneModel
路径：`/phoneModel`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 机型文件名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/phoneModel" \  -H "Content-Type: application/json" \  -d '{    "name": "samsung_s23"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "删除本地机型失败: 文件不存在",  "data": null}
```

## 3. 导出本地机型数据

功能说明：导出指定的本地机型数据
请求方式：POST
请求 URL：http://{主机IP}:8000/phoneModel/export
路径：`/phoneModel/export`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 机型文件名称 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/phoneModel/export" \  -H "Content-Type: application/json" \  -d '{    "name": "samsung_s23"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "导出本地机型失败: 文件不存在",  "data": null}
```

## 4. 导入机型数据

功能说明：通过上传ZIP包导入机型数据
请求方式：POST
请求 URL：http://{主机IP}:8000/phoneModel/import
路径：`/phoneModel/import`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 导入修改后的机型ZIP包 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/phoneModel/import" \  -F "file=@samsung_s23.zip"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "导入机型数据失败: 文件格式错误",  "data": null}
```

注意事项：

- 仅支持ZIP格式的机型数据包

## 1. 修改认证密码

功能说明：修改API接口认证密码（默认用户名admin）
请求方式：POST
请求 URL：http://{主机IP}:8000/auth/password
路径：`/auth/password`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| newPassword | 是 | string | 新密码 |
| confirmPassword | 是 | string | 确认新密码 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/auth/password" \  -H "Content-Type: application/json" \  -d '{    "newPassword": "newpassword123",    "confirmPassword": "newpassword123"  }'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "修改密码失败: 两次密码不一致",  "data": null}
```

注意事项：

- 两次输入的密码必须一致
- 默认用户名为admin
- 密码修改后立即生效

## 2. 关闭接口认证

功能说明：关闭API接口认证功能
请求方式：POST
请求 URL：http://{主机IP}:8000/auth/close
路径：`/auth/close`

请求参数：无

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/auth/close"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "关闭认证失败",  "data": null}
```

注意事项：

- 关闭认证后，所有接口将无需认证即可访问
- 出于安全考虑，建议在内网环境下使用

## 1. 更新服务

功能说明：在线更新SDK服务到最新版本
请求方式：GET
请求 URL：http://{主机IP}:8000/server/upgrade
路径：`/server/upgrade`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/server/upgrade"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "msg": "更新成功，服务将自动重启"  }}
```

失败返回：

```json
{  "code": 500,  "message": "更新失败: 网络连接超时",  "data": null}
```

注意事项：

- 更新成功后服务会自动重启
- 更新过程中请勿断电或断网

## 2. 通过上传SDK更新服务

功能说明：通过上传SDK压缩包更新服务
请求方式：POST
请求 URL：http://{主机IP}:8000/server/upgrade/upload
路径：`/server/upgrade/upload`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | SDK压缩包文件，zip格式 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/server/upgrade/upload" \  -F "file=@myt-sdk-v1.2.0.zip"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "更新失败: 文件格式错误",  "data": null}
```

注意事项：

- 仅支持zip格式的SDK压缩包
- 更新成功后服务会自动重启

## 3. 清空设备磁盘数据

功能说明：清空设备磁盘上的所有数据（高危操作！）
请求方式：POST
请求 URL：http://{主机IP}:8000/server/device/reset
路径：`/server/device/reset`

请求参数：无

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/server/device/reset"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "清空数据失败",  "data": null}
```

注意事项：

- ⚠️ 高危操作！此操作将清空设备上的所有数据，不可恢复！
- 执行前请确保已备份所有重要数据
- 操作完成后设备将恢复出厂状态

## 4. 重启设备

功能说明：重启设备
请求方式：POST
请求 URL：http://{主机IP}:8000/server/device/reboot
路径：`/server/device/reboot`

请求参数：无

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/server/device/reboot"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "message": "设备将在5秒后重启"  }}
```

失败返回：

```json
{  "code": 500,  "message": "重启设备失败",  "data": null}
```

注意事项：

- 重启过程中所有云机将停止运行
- 重启完成后需要手动启动云机

## 5. 开启和屏蔽dockerApi 2375端口

功能说明：控制主机上 Docker Remote API（端口 2375）的开启或屏蔽状态
请求方式：POST
请求 URL：http://{主机IP}:8000/server/dockerApi
路径：`/server/dockerApi`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| enable | 是 | boolean | true 表示开启，false 表示屏蔽 |

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/server/dockerApi" \-H "Content-Type: application/json" \-d '{"enable": true}'
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {}}
```

失败返回：

```json
{  "code": 500,  "message": "操作失败",  "data": null}
```

## 6. 获取主机网络信息

功能说明：获取设备当前的网络配置信息，包括网关、子网和网卡接口
请求方式：GET
请求 URL：http://{主机IP}:8000/server/network
路径：`/server/network`

请求参数：无

请求示例：

```bash
curl http://192.168.99.108:8000/server/network
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "info": {      "gateway": "192.168.99.1",      "networkCIDR": "192.168.99.0/24",      "interface": "eth0"    }  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取网络信息失败",  "data": null}
```

## 1. 导入大模型 ZIP 包

功能说明：导入大模型 ZIP 包到设备中
请求方式：POST
请求 URL：http://{主机IP}:8000/lm/import
路径：`/lm/import`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| file | 是 | file | 大模型 ZIP 包文件（multipart/form-data 格式） |

请求示例：

```bash
curl -X POST -F "file=@./llm_model.zip" "http://192.168.99.108:8000/lm/import"
```

成功返回：

```json
{  "code": 0,  "message": "导入大模型ZIP包成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "导入大模型ZIP包失败，文件格式错误或损坏",  "data": null}
```

## 2. 获取系统信息

功能说明：获取设备及大模型相关系统信息
请求方式：GET
请求 URL：http://{主机IP}:8000/lm/info
路径：`/lm/info`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/lm/info"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "api_version": "v1.0.0",    "nsmi_version": "1.2.3",    "pcie_driver_version": "4.5.6",    "firmware_version": "v2.1.0",    "devices": [      {        "device_id": 1,        "mode": "PCIE",        "global_id": 1001,        "internal_id": 101,        "fan_speed_ratio": 50,        "temp": 42,        "power": 35,        "voltage": 12,        "chips": [          {            "chip_id": 10001,            "chip_name": "RK3588",            "chip_ver": "v1.1",            "cpu_id": "CPU001",            "health": 0,            "temp": 40,            "memory_info": {              "total_size": 8589934592,              "free_size": 4294967296,              "util_rate": 50,              "hugepage_size": 2097152,              "hugepage_total_cnt": 1024,              "hugepage_free_cnt": 512            }          }        ]      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取系统信息失败",  "data": null}
```

返回字段说明：

| 参数名 | 类型 | 说明 |
| --- | --- | --- |
| api_version | string | API 版本 |
| firmware_version | string | 固件版本 |
| devices | array | 设备列表 |
| device_id | integer | 设备全局 ID |
| chips | array | 芯片列表 |
| memory_info | object | 内存信息 |
| total_size | integer | 总内存大小（Bytes） |
| util_rate | integer | 内存使用率（%） |

## 3. 删除本地大模型

功能说明：删除设备上指定名称的本地大模型
请求方式：DELETE
请求 URL：http://{主机IP}:8000/lm/local
路径：`/lm/local`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | 是 | string | 本地大模型名称 |

请求示例：

```bash
curl -X DELETE "http://192.168.99.108:8000/lm/local?name=chatglm3"
```

成功返回：

```json
{  "code": 0,  "message": "删除本地大模型成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "删除本地大模型失败，模型不存在",  "data": null}
```

## 4. 获取本地大模型列表

功能说明：获取设备上所有本地大模型的列表信息
请求方式：GET
请求 URL：http://{主机IP}:8000/lm/local
路径：`/lm/local`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/lm/local"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "count": 2,    "list": [      {        "name": "chatglm3",        "size": "10GB",        "files": [          {            "filePath": "/models/chatglm3/main.rknn",            "size": "8GB"          },          {            "filePath": "/models/chatglm3/vocab.json",            "size": "200MB"          }        ]      },      {        "name": "llama2",        "size": "15GB",        "files": [          {            "filePath": "/models/llama2/model.rknn",            "size": "12GB"          },          {            "filePath": "/models/llama2/tokenizer.gguf",            "size": "300MB"          }        ]      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取本地大模型列表失败",  "data": null}
```

返回字段说明：

| 参数名 | 类型 | 说明 |
| --- | --- | --- |
| count | integer | 本地大模型总数 |
| name | string | string |
| size | array | 大模型总大小 |
| files | array | 大模型包含文件列表 |
| filePath | string | 文件路径 |

## 5. 获取模型运行状态

功能说明：获取当前设备上大模型的运行状态信息
请求方式：GET
请求 URL：http://{主机IP}:8000/lm/models
路径：`/lm/models`

请求参数：无

请求示例：

```bash
curl "http://192.168.99.108:8000/lm/models"
```

成功返回：

```json
{  "code": 0,  "message": "ok",  "data": {    "object": "model_list",    "data": [      {        "id": "model_001",        "object": "model",        "created": 1735689600,        "owned_by": "local",        "meta": {          "ctx_size": 2048,          "predict": 1024,          "temp": 0.7        }      }    ]  }}
```

失败返回：

```json
{  "code": 500,  "message": "获取模型运行状态失败",  "data": null}
```

返回字段说明：

| 参数名 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 模型 ID |
| created | integer | 创建时间戳 |
| meta | object | 模型元数据 |
| ctx_size | integer | 上下文窗口大小 |

## 6. 重置设备

功能说明：对指定设备进行硬件或软件重置
请求方式：POST
请求 URL：http://{主机IP}:8000/lm/reset
路径：`/lm/reset`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| type | 是 | string | 重置类型（hw - 硬件，sw - 软件） |
| device_id | 是 | integer | 设备 ID |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"type":"sw","device_id":1}' "http://192.168.99.108:8000/lm/reset"
```

成功返回：

```json
{  "code": 0,  "message": "设备重置成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "设备重置失败，设备ID不存在",  "data": null}
```

## 7. 启动 LLM 服务

功能说明：启动指定配置的 LLM 服务
请求方式：POST
请求 URL：http://{主机IP}:8000/lm/server/start
路径：`/lm/server/start`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| host | 否 | string | 监听地址，默认值：0.0.0.0 |
| port | 否 | integer | 监听端口，默认值：8081 |
| timeout | 否 | integer | 超时时间（秒），默认值：30 |
| models | 是 | object | 模型配置列表（key 为模型别名） |
| alias | 是 | string | 模型别名（与 key 一致） |
| model | 是 | string | 主模型文件路径（RKNN） |
| weight | 是 | string | 主模型权重路径 |
| ctx-size | 否 | integer | 上下文窗口大小，默认值：0 |
| temp | 否 | number | 温度参数，默认值：0.8 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "host": "0.0.0.0",  "port": 8081,  "timeout": 30,  "models": {    "chatglm3": {      "alias": "chatglm3",      "model": "/models/chatglm3/main.rknn",      "weight": "/models/chatglm3/weight.bin",      "ctx-size": 2048,      "temp": 0.7    }  }}' "http://192.168.99.108:8000/lm/server/start"
```

成功返回：

```json
{  "code": 0,  "message": "LLM服务启动成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "LLM服务启动失败，模型文件不存在",  "data": null}
```

## 8. 停止 LLM 服务

功能说明：停止当前运行的 LLM 服务
请求方式：POST
请求 URL：http://{主机IP}:8000/lm/server/stop
路径：`/lm/server/stop`

请求参数：无

请求示例：

```bash
curl -X POST "http://192.168.99.108:8000/lm/server/stop"
```

成功返回：

```json
{  "code": 0,  "message": "LLM服务停止成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "LLM服务停止失败，服务未运行",  "data": null}
```

## 9. 设置工作模式

功能说明：设置指定设备和芯片的工作模式
请求方式：POST
请求 URL：http://{主机IP}:8000/lm/workMode
路径：`/lm/workMode`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| device_id | 是 | integer | 设备 ID |
| chip_id | 是 | integer | 芯片 ID |
| work_mode | 是 | integer | 工作模式，默认值：2 |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{"device_id":1,"chip_id":10001,"work_mode":2}' "http://192.168.99.108:8000/lm/workMode"
```

成功返回：

```json
{  "code": 0,  "message": "工作模式设置成功",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "工作模式设置失败，设备或芯片ID不存在",  "data": null}
```

## 10. 模型推理对话补全

功能说明：模型推理对话补全
请求方式：POST
请求 URL：http://{主机IP}:8000/v1/chat/completions
路径：`/v1/chat/completions`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "model": "llama3",  "messages": [    {"role": "user", "content": "Hello, who are you?"}  ],  "stream": true,  "max_tokens": 2048,  "temperature": 0.7,  "top_p": 0.9}' "http://192.168.99.108:8000/v1/chat/completions"
```

成功返回：

```json
{  "code": 0,  "message": "操作成功",  "data": {    "id": "chatcmpl-123",    "object": "chat.completion",    "created": 1677652288,    "model": "llama3",    "choices": [      {        "index": 0,        "message": {          "role": "assistant",          "content": "I am an AI assistant."        },        "finish_reason": "stop"      }    ],    "usage": {      "prompt_tokens": 10,      "completion_tokens": 20,      "total_tokens": 30    }  }}
```

失败返回：

```json
{  "code": 500,  "message": "模型不存在或服务异常",  "data": null}
```

## 11. 模型文本向量化

功能说明：模型文本向量化
请求方式：POST
请求 URL：http://{主机IP}:8000/v1/embeddings
路径：`/v1/embeddings`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |

请求示例：

```bash
curl -X POST -H "Content-Type: application/json" -d '{  "model": "text-embedding-3-small",  "input": "The quick brown fox jumps over the lazy dog",  "dimensions": 256,  "encoding_format": "float"}' "http://192.168.99.108:8000/v1/embeddings"
```

失败返回：

```json
{  "code": 500,  "message": "向量化失败，模型不支持或输入格式错误",  "data": null}
```

## 1. 创建云机V2

功能说明：创建一个新的安卓云机实例。
请求方式：POST
请求 URL：http://{主机IP}:8000/androidV2
路径：`/androidV2`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 云机名称 |
| indexNum | integer | 否 | 实例序号，P1范围1-24，Q1范围1-12，传0将自动分配一个空闲实例序号 |
| imageUrl | string | 是 | 镜像完整地址 |
| sandboxSize | string | 否 | 沙盒大小，例如 "16GB"，"32GB" |
| dns | string | 是 | 云机DNS，例如 "223.5.5.5" |
| offset | string | 否 | 云机的开机时间 |
| doboxFps | string | 否 | 云机FPS |
| doboxWidth | string | 否 | 云机分辨率的宽 |
| doboxHeight | string | 否 | 云机分辨率的高 |
| doboxDpi | string | 否 | 云机DPI |
| enforce | boolean | 否 | 安全模式，默认开启 |
| macVlanIp | string | 否 | 独立IP设置 |
| start | boolean | 否 | 创建完成是否开机，默认为 true |
| vpcID | integer | 否 | 添加的魔云腾VPC节点ID |
| portMappings | array | 否 | 增加自定义端口映射，格式见下方示例 |
| mytBridgeName | string | 否 | myt_bridge网卡名，可以接口查询或在设备终端使用ifconfig查询 |

请求示例：

```bash
POST http://192.168.99.108:8000/androidv2Content-Type: application/json请求体{  "name": "test-cloud-phone-v2",  "indexNum": 0,  "imageUrl": "registry.example.com/android:12.0-base",  "sandboxSize": "32GB",  "dns": "8.8.8.8",  "offset": "08:00",  "doboxFps": "60",  "doboxWidth": "1080",  "doboxHeight": "1920",  "doboxDpi": "480",  "enforce": true,  "macVlanIp": "192.168.100.100",  "start": true,  "vpcID": 0,  "portMappings": [    {      "containerPort": 5555,      "hostPort": 55550,      "hostIP": "0.0.0.0",      "protocol": "tcp"    }  ],  "mytBridgeName": "myt_bridge_default"}
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": {    "id": "string"  }}
```

失败返回：

```json
{  "code": 50,  "message": "失败原因",  "data": {    "id": ""  }}
```

## 2. 重置云机V2

功能说明：重置指定名称的安卓云机实例，恢复到初始状态。
请求方式：PUT
请求 URL：http://{主机IP}:8000/androidV2
路径：`/androidV2`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 云机名称 |

请求示例：

```bash
POST http://192.168.99.108:8000/androidv2/Content-Type: application/json{  "name": "test-cloud-phone-v2"}或者curl http://192.168.99.108:8000/androidV2 \  --request PUT \  --header 'Content-Type: application/json' \  --data '{  "name": "test-cloud-phone-v2"}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "重置云机失败",  "data": null}
```

## 3. 批量切换容器镜像

功能说明：将多个指定名称的安卓云机批量切换到一个新的镜像。
请求方式：POST
请求 URL：http://{主机IP}:8000/androidV2/change-image
路径：`/androidV2/change-image`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| containerNames | array | 是 | 云机名称列表 |
| image | string | 是 | 新的镜像地址 |

请求示例：

```bash
POST http://192.168.99.108:8000/androidV2/change-imageContent-Type: application/json请求体{  "containerNames": [    "test-cloud-phone-v2",    "test-cloud-phone-v2-2"  ],  "image": "registry.example.com/android:12.0-base"}或者curl http://192.168.99.108:8000/androidV2/change-image \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "containerNames": [    "test-cloud-phone-v2",    "test-cloud-phone-v2-2"  ],  "image": "registry.example.com/android:12.0-base"}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 500,  "message": "批量切换容器镜像失败",  "data": null}
```

## 4. 复制云机

功能说明：复制指定名称的安卓云机实例。
请求方式：GET
请求 URL：http://{主机IP}:8000/androidV2/copy
路径：`/androidV2/copy`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 云机名称 |
| indexNum | integer | 否 | 坑位数 |
| count | integer | 否 | 复制数量，默认为1 |

请求示例：

```bash
GET http://192.168.99.108:8000/androidV2/copy?name=test&indexNum=1&count=1或curl 'http://192.168.99.108:8000/androidV2/copy?name=test&indexNum=1&count=1'
```

成功返回：

```text
data: {"current":1,"total":1,"name":"test_copy_1","status":"copying","message":"正在复制 data 目录"}data: {"current":1,"total":1,"name":"test_copy_1","status":"copying","message":"正在创建容器"}data: {"current":1,"total":1,"name":"test_copy_1","status":"success","message":"27cccd9e0ef05c089c92f4831d191bee9cc20c00db8695f920968d6e2d927181"}data: {"current":1,"total":1,"name":"","status":"done","message":"","success":["test_copy_1"]}
```

失败返回：

```json
{  "code": 500,  "message": "失败原因",  "data": null}
```

## 5. 切换安卓镜像

功能说明：切换指定名称的安卓云机实例的镜像。
请求方式：POST
请求 URL：http://{主机IP}:8000/androidV2/switchImage
路径：`/androidV2/switchImage`

请求参数：

| 参数名 | 必选 | 类型 | 说明 |
| --- | --- | --- | --- |
| imageUrl | 是 | string | 镜像完整地址称 |
| name | 是 | string | 云机名称像地址 |
| adbPort | 否 | integer | 自定义adb端口，默认5555，设置端口0的时候不开启adb，请不要使用9082、9083、10000、10001、10006、10007、10008等端口 |
| dns | 否 | string | 云机DNS，例如223.5.5.5 |
| doboxDpi | 否 | string | 云机DPI |
| doboxFps | 否 | string | 云机的帧率（FPS） |
| doboxWidth | 否 | string | 云机分辨率的宽度 |
| doboxHeight | 否 | string | 云机分辨率的高度 |
| enforce | 否 | string | 是否启用安全模式，默认开启 |
| macVlanIp | 否 | string | 独立 IP 设置，用于为云机分配一个固定的 MACVLAN IP 地址。 |
| mytBridgeName | 否 | string | myt_bridge 网卡名称，可通过接口查询或在设备终端使用 ifconfig 查询。 |
| offset | 否 | string | 云机的开机时间度 |
| portMappings | 否 | string | 增加自定义端口映射 |
| start | 否 | boolean | 创建完成开机，默认不开机 |
| vpcID | 否 | integer | 添加的魔云腾VPC节点ID |

请求示例：

```bash
POST http://192.168.99.183:8000/androidV2/switchImageContent-Type: application/json请求体{  "name": "1773039649840_3_T0003",  "imageUrl": "registry.cn-guangzhou.aliyuncs.com/mytos/dobox:P10_base_202509221352"}# 或使用curlcurl http://192.168.99.183:8000/androidV2/switchImage \  --request POST \  --header 'Content-Type: application/json' \  --data '{  "name": "1773039649840_3_T0003",  "imageUrl": "registry.cn-guangzhou.aliyuncs.com/mytos/dobox:P10_base_202509221352",  "dns": "",  "offset": "",  "doboxFps": "",  "doboxWidth": "",  "doboxHeight": "",  "doboxDpi": "",  "enforce": true,  "macVlanIp": "",  "start": true,  "vpcID": 0,  "adbPort": 5555,  "portMappings": [    {      "containerPort": 0,      "hostPort": 0,      "hostIP": "",      "protocol": "tcp"    }  ]}'
```

成功返回：

```json
{  "code": 0,  "message": "OK",  "data": null}
```

失败返回：

```json
{  "code": 10006,  "message": "Error: 容器不存在无法操作，请确认容器名称是否正确",  "data": null}
```

## 错误码说明


请求参数：无

## 常见问题


请求参数：无
