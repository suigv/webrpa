# 完整接口矩阵（来源：3 份 PDF）

来源 PDF（文件已按项目清理策略删除，以下为已提取结论）：
- `盒子内SDK API 开发文档 _ 魔云腾.pdf`（105 页）
- `Android RPA 开发文档 _ 魔云腾.pdf`（44 页）
- `MYTOS API 接口文档 _ 魔云腾.pdf`（66 页）

提取说明：
- 当前环境下 `look_at` 不可用。
- 本矩阵基于 `pdftotext` 逐页扫描，并结合计划 `3-pdf-hardware-apis-complete.md` 的接口清单整理。
- 页码与参数字段通过 `pdftotext -layout` 逐页收敛。

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
| POST | `/installapks` | multipart `file`(ZIP with apks/xapk) | p35-p37 |
| GET | `/snapshot` | `type`(optional),`quality`(optional) | p39 |
| GET | `/queryversion` | - | p38 |
| GET | `/info` | - | p45 |
| POST | `/sms/receive` | - | p22-p23 |
| GET | `/callog` | `number`(required),`type`,`date`,`duration`,... | p45-p46 |
| GET | `/task` | - | p47 |
| GET | `/modifydev?cmd=11` | `ip`(optional),`launage`(optional) — docs title “IP定位”，用于按IP刷新地理/区域设置 | p59-p60 |
| POST | `/system/adb` | `enabled` | p25 (`/adb`) |
| GET | `/adid` | `cmd`(required),`adid`(required when cmd=1) | p48 |
| GET | `/modulemgr` | `cmd=check|install|uninstall`,`module=magisk|gms` | p49-p50 |

## 核验说明

- RPA 截图命名已确认：API 调用使用 `screentshot(...)`，示例输出文件名使用 `screenshot.png`（p7、p9、p40）。
- Selector/Node 扩展 API（`create_selector`、`addQuery_*`、`execQuery*`、`get_node_*`、`Click_events`）已在 p10-p11 与 p30-p35 做逐页核对。
