# 完整接口矩阵（来源：3 份 PDF）

来源 PDF（文件已按项目清理策略删除，以下为已提取结论）：
- `盒子内SDK API 开发文档 _ 魔云腾.pdf`（105 页）
- `Android RPA 开发文档 _ 魔云腾.pdf`（44 页）
- `MYTOS API 接口文档 _ 魔云腾.pdf`（66 页）

提取说明：
- 当前环境下 `look_at` 不可用。
- 本矩阵基于 `pdftotext` 逐页扫描，并结合计划 `3-pdf-hardware-apis-complete.md` 的接口清单整理。
- 页码与参数字段通过 `pdftotext -layout` 逐页收敛。

## 覆盖摘要（基于当前仓库证据）

- SDK API：**26** 条接口条目
- Android RPA：**18** 条方法条目
- MYTOS API：**34** 条接口条目（v3，2026-01-30）
- 合计：**78** 条规范化条目（按文档条目计，不等同于全部底层别名/回退分支）

证据优先级：
1. `hardware_adapters/myt_client.py`、`hardware_adapters/mytRpc.py` 代码接口
2. `tests/test_sdk_complete.py`、`tests/test_rpa_complete.py`、`tests/test_mytos_complete.py` 映射断言
3. `docs/reference/pdf_feature_usability_checklist.md` 的落地对照

## 已知限制与待确认项

- 当前仓库未保留原始 PDF 二进制文件（`**/*.pdf` 未检索到），因此本矩阵基于仓库内已提取结果与测试证据进行核对。
- 当前实现仅保留官方文档路径。
- RPA selector/node 能力在矩阵中按“能力族”归类；若后续需要逐方法 1:1 清单，应在 Wave 7 任务中继续细化。

## SDK API（盒子内 SDK）

| 方法 | 路径 | 关键参数 | 返回摘要 | PDF 页码 |
|---|---|---|---|---|
| GET | `/info` | - | latestVersion/currentVersion | p2 |
| GET | `/info/device` | - | device info | p3 |
| POST | `/android/start` | `name` + network options | start result | p21 |
| POST | `/android/stop` | `name` | stop result | p22 |
| POST | `/android/restart` | `name` | restart result | p23 |
| POST | `/android/rename` | `name`,`newName` | rename result | p41 |
| POST | `/android/exec` | `name`,`command[]` | command output | p47-p48 |
| GET | `/android` | `name` | cloud status/list | p6 (android section) |
| POST | `/android/switchImage` | `name`,`imageUrl` + model/network | switch result | p16-p17 |
| POST | `/android/switchModel` | `name`,`modelId` + options | switch result | p18-p19 |
| POST | `/android/pullImage` | `imageUrl` | pull task result | p20 |
| GET | `/android/image` | - | image list | p24 |
| POST | `/android/pruneImages` | - | pruneCount/releaseSpace | p49 |
| GET | `/backup` | `name` (optional filter) | backup list | p50-p51 |
| GET | `/backup/download` | `name` | backup file(binary) | p52 |
| DELETE | `/backup` | `name` | delete backup result | p52-p53 |
| GET | `/android/backup/model` | - | model backup list | p42 |
| DELETE | `/android/backup/model` | `name` | delete model-backup result | p43 |
| POST | `/android/backup/model` | `name`,`suffix` | backup model result | p44 |
| POST | `/android/backup/modelExport` | `name` | export model-backup result | p45 |
| POST | `/android/backup/modelImport` | `file`(multipart ZIP) | import model-backup result | p46-p47 |
| POST | `/auth/password` | `newPassword`,`confirmPassword` | set auth result | p84 |
| POST | `/auth/close` | - | close auth result | p85 |
| GET | `/lm/local` | - | local model list | p96-p98 |
| GET | `/lm/models` | - | model running status list | p98-p99 |

## Android RPA API（Android RPA 开发文档）

| 类型 | 方法 | 规范化签名 | PDF 页码 |
|---|---|---|---|
| Core | `init` | `init(ip, rpa_port, timeout)` | p7-10 |
| Core | `close` | `close()` | p7-10 |
| Core | `check_connect_state` | `check_connect_state()` | p7-10 |
| Touch | `touchClick` | `touchClick(finger_id, x, y)` | p17-p19 |
| Touch | `swipe` | `swipe(finger_id, x0, y0, x1, y1, elapse_ms)` | p25-p27 |
| Touch | `longClick` | `longClick(finger_id, x, y, press_seconds)` | p20-p22 |
| Input | `sendText` | `sendText(text)` | p14-p16 |
| Input | `keyPress` | `keyPress(code)` | p23-p25 |
| App | `openApp` | `openApp(package)` | p15-p17 |
| App | `stopApp` | `stopApp(package)` | p15-p17 |
| Command | `exec_cmd` | `exec_cmd(command)` | p11-p13 |
| Tree | `dumpNodeXml` | `dumpNodeXml(dump_all)` | p31-p34 |
| Tree | `dump_node_xml_ex` | `dumpNodeXmlEx(work_mode, timeout_ms)` | p35-p38 |
| Selector | `create_selector` | `create_selector()` | p39-p42 (selector section) |
| Selector | `execQueryOne` | selector query one | p39-p42 |
| Selector | `execQueryAll` | selector query all | p39-p42 |
| Node | `rpcNode.*` | node property/bounds/tree methods | p40-p44 |
| 备注 | `screentshot` | Python 示例中调用为 `mytapi.screentshot(1,90,...)`；方法名在示例里就是 `screentshot` | p7,p9,p40 |

## MYTOS API（MYTOS API 接口文档）

v3 新增/扩展能力已在 `hardware_adapters/myt_client.py` 和 `engine/actions/sdk_actions.py` 对齐，按能力族覆盖到：
- 文件传输：下载/上传/批量安装/证书上传
- 代理与系统：S5、ADB 查询与切换、root 授权、module manager
- 设备能力：截图、自动点击、摄像头热启动、后台保活、按键屏蔽、容器信息、版本
- 业务数据：应用导入导出、短信、通话、联系人、定位、语言国家、开机启动、webrtc URL

| 方法 | 路径 | 关键参数 | PDF 页码 |
|---|---|---|---|
| GET | `/proxy/status` | - | p17-p20 (proxy section) |
| POST | `/proxy/set` | `s5IP,s5Port,s5User,s5Password,s5Type` | p21 |
| POST | `/proxy/stop` | - | p20-p21 |
| POST | `/proxy?cmd=4` | body `domains[]` / comma-separated domains | p21 |
| GET | `/clipboard` | - | p14-p16 |
| POST | `/clipboard` | `content` | p15-p16 |
| GET | `/download` | `path` | p12-p13 |
| POST | `/upload` | `path`,`file/content` | p24-p25 |
| POST | `/app/batchInstall` | JSON body `files[]` | p35-p37 |
| GET | `/snapshot` | `type`(optional),`quality`(optional) | p39 |
| GET | `/device/version` | - | p38 |
| GET | `/info` | - | p45 |
| POST | `/sms/receive` | - | p22-p23 |
| GET | `/call/records` | `number`,`type`,`date`,`duration`,... | p45-p46 |
| GET | `/task` | - | p47 |
| GET | `/modifydev?cmd=11` | `ip`(optional),`launage`(optional) — docs title “IP定位”，用于按IP刷新地理/区域设置 | p59-p60 |
| POST | `/system/adb` | `enabled` | p25 (`/adb`) |
| GET/POST | `/identity/googleId` | GET 查询；POST body `adid` | p48 |
| GET | `/modulemgr` | `cmd=check|install|uninstall`,`module=magisk|gms` | p49-p50 |

## 核验说明

- RPA 截图命名已确认：API 调用使用 `screentshot(...)`，示例输出文件名使用 `screenshot.png`（p7、p9、p40）。
- Selector/Node 扩展 API（`create_selector`、`addQuery_*`、`execQuery*`、`get_node_*`、`Click_events`）已在 p10-p11 与 p30-p35 做逐页核对。
