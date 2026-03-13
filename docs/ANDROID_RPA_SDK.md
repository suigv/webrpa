# Android RPA SDK（30002）

基准文档：Android RPA 开发文档

本地调用说明：

使用 `hardware_adapters/mytRpc.py` 的 `MytRpc`。文档中的 `handle` 参数在本项目中由 `MytRpc.init()` 创建并保存在实例内，不需要每次调用显式传入。

## 模块导入

说明：根据实际的 SDK 实现，Python 版本采用面向对象的方式进行调用。以下是正确的导入方式：

## 引用文件功能说明

说明：以下是 SDK 中各个引用文件的详细功能介绍：

字段：

| 文件名 | 功能描述 | 主要方法/类 | 使用场景 |
| --- | --- | --- | --- |
| mytRpc.py | 核心 SDK 实现，封装了与设备通信的所有主要功能 | MytRpc 类 | 所有设备控制操作的入口点 |
| mytSelector.py | 提供 UI 元素选择器功能，用于查找和筛选 UI 节点 | mytSelector 类 | 需要根据条件查找 UI 元素时使用 |
| rpcNode.py | 封装了 UI 节点的操作和属性获取方法 | rpcNode 类 | 获取节点属性、执行节点操作时使用 |
| logger.py | 提供日志记录功能 | logger 对象 | 需要记录日志信息时使用 |
| ToolsKit.py | 提供各种工具函数 | ToolsKit 类 | 获取程序路径、检查进程状态等工具操作 |
| __init__.py | 模块初始化文件 | - | 确保 common 目录可作为 Python 模块导入 |
| libmytrpc.dll | 底层动态链接库，实现了与设备通信的核心功能 | - | 提供 SDK 核心功能的底层实现，所有上层操作最终都会调用此 DLL 中的函数 |

## CaptureResult - 截图结果

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| data | bytes | 图像数据（RGBA格式） |
| width | int | 图像宽度（像素） |
| height | int | 图像高度（像素） |
| stride | int | 图像步长（每行字节数） |
| ptr | int | 原始指针，需要调用 free_rpc_ptr 释放 |

## CompressedCaptureResult - 压缩截图结果

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| data | bytes | 压缩后的图像数据（PNG或JPG格式） |
| ptr | int | 原始指针，需要调用 free_rpc_ptr 释放 |

## Bounds - 节点边界

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| left | int | 左边界坐标 |
| top | int | 上边界坐标 |
| right | int | 右边界坐标 |
| bottom | int | 下边界坐标 |

## Point - 坐标点

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| x | int | X坐标 |
| y | int | Y坐标 |

## init

说明：初始化 DLL，加载所有函数

签名：

```python
def init(dll_path: str = "") -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| dll_path | str | DLL文件的路径，如果为空则使用默认路径 "libmytrpc.dll" |

异常：Exception - 加载失败时抛出异常

## release

说明：释放 DLL

签名：

```python
def release() -> None:
```

异常：Exception - 释放失败时抛出异常

## get_sdk_version

说明：获取当前库的版本号

签名：

```python
def get_sdk_version() -> int:
```

返回值：int - 版本号

## openDevice

说明：远程连接设备

签名：

```python
def openDevice(ip: str, port: int, timeout: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| ip | str | 要远程控制的设备的IP地址 |
| port | int | 要远程控制的设备的端口 |
| timeout | int | 远程连接的超时时间，单位秒 |

返回值：int - 句柄id，大于0表示成功，失败返回0

## closeDevice

说明：关闭远程连接

签名：

```python
def closeDevice(handle: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：int - 0表示成功，失败返回非0

## check_connect_state

说明：检测远程连接是否处于连接状态

签名：

```python
def check_connect_state(handle: int) -> bool:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：int - 1表示已连接，0表示已断开

## free_rpc_ptr

说明：释放截图数据

签名：

```python
def free_rpc_ptr(ptr: int) -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| ptr | int | 指针数据 |

## get_display_rotate

说明：获取当前屏幕的旋转角度

签名：

```python
def get_display_rotate(handle: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：int - 返回0,1,2,3

## exec_cmd

说明：执行shell命令

签名：

```python
def exec_cmd(handle: int, wait_for_exit: bool, cmdline: str) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| wait_for_exit | bool | 是否等待执行结束才返回 |
| cmdline | str | 命令行 |

返回值：str - 命令执行结果字符串

## dumpNodeXml

说明：获取节点树数据（XML格式）

签名：

```python
def dumpNodeXml(handle: int, dump_all: bool) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| dump_all | bool | 是否导出所有节点 |

返回值：str - 节点树XML字符串

## dump_node_xml_ex

说明：获取节点树数据（扩展版本）

签名：

```python
def dump_node_xml_ex(handle: int, use_new_mode: bool, timeout: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| use_new_mode | bool | 是否使用新模式 |
| timeout | int | 超时时间 |

返回值：str - 节点树XML字符串

## use_new_node_mode

说明：设置节点模式

签名：

```python
def use_new_node_mode(handle: int, use: bool) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| use | bool | 是否使用新模式 |

返回值：int - 操作结果

## take_capture

说明：远程截图，获取到的是RGBA的数据流

签名：

```python
def take_capture(handle: int) -> CaptureResult:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：CaptureResult - 截图结果

异常：Exception - 截图失败时抛出异常

## take_capture_ex

说明：远程截图（指定区域）

签名：

```python
def take_capture_ex(handle: int, l: int, t: int, r: int, b: int) -> CaptureResult:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| l | int | 截图区域的左坐标 |
| t | int | 截图区域的上坐标 |
| r | int | 截图区域的右坐标 |
| b | int | 截图区域的下坐标 |

返回值：CaptureResult - 截图结果

异常：Exception - 截图失败时抛出异常

## takeCaptrueCompress

说明：远程截图，获取压缩后的png或jpg格式

签名：

```python
def takeCaptrueCompress(handle: int, image_type: int, quality: int) -> CompressedCaptureResult:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| image_type | int | 0表示png，1表示jpg |
| quality | int | 压缩质量，取值0-100 |

返回值：CompressedCaptureResult - 压缩截图结果

异常：Exception - 截图失败时抛出异常

## setRpaWorkMode

说明：设置RPA工作模式（无障碍模式开关）

签名：

```python
def setRpaWorkMode(mode: int) -> bool:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| mode | int | 工作模式（0: 关闭无障碍, 1: 开启无障碍） |

返回值：bool - 设置成功返回True，失败返回False

## take_capture_compress_ex

说明：远程截图（指定区域，压缩格式）

签名：

```python
def take_capture_compress_ex(handle: int, l: int, t: int, r: int, b: int, image_type: int, quality: int) -> CompressedCaptureResult:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| l | int | 截图区域的左坐标 |
| t | int | 截图区域的上坐标 |
| r | int | 截图区域的右坐标 |
| b | int | 截图区域的下坐标 |
| image_type | int | 0表示png，1表示jpg |
| quality | int | 压缩质量，取值0-100 |

返回值：CompressedCaptureResult - 压缩截图结果

异常：Exception - 截图失败时抛出异常

## touchDown

说明：模拟按下

签名：

```python
def touchDown(handle: int, id: int, x: int, y: int) -> int:
```

参数：

| 参数 | 类��型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| id | int | 手指编号(0-9) |
| x | int | X坐标 |
| y | int | Y坐标 |

返回值：int - 操作结果

## touchUp

说明：模拟弹起

签名：

```python
def touchUp(handle: int, id: int, x: int, y: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| id | int | 手指编号(0-9) |
| x | int | X坐标 |
| y | int | Y坐标 |

返回值：int - 操作结果

## touchMove

说明：模拟滑动

签名：

```python
def touchMove(handle: int, id: int, x: int, y: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| id | int | 手指编号(0-9) |
| x | int | X坐标 |
| y | int | Y坐标 |

返回值：int - 操作结果

## touchClick

说明：模拟单击

签名：

```python
def touchClick(handle: int, id: int, x: int, y: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| id | int | 手指编号(0-9) |
| x | int | X坐标 |
| y | int | Y坐标 |

返回值：int - 操作结果

## swipe

说明：模拟滑动

签名：

```python
def swipe(handle: int, id: int, x0: int, y0: int, x1: int, y1: int, millis: int, async: bool) -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| id | int | 手指编号(0-9) |
| x0 | int | 起始X坐标 |
| y0 | int | 起始Y坐标 |
| x1 | int | 结束X坐标 |
| y1 | int | 结束Y坐标 |
| millis | int | 滑动持续时间（毫秒） |
| async | bool | 是否异步执行 |

## keyPress

说明：模拟按键

签名：

```python
def keyPress(handle: int, code: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| code | int | 按键码 |

返回值：int - 操作结果

## sendText

说明：模拟键盘输入

签名：

```python
def sendText(handle: int, text: str) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| text | str | 要输入的字符串 |

返回值：int - 操作结果

## openApp

说明：打开指定包名的app

签名：

```python
def openApp(handle: int, pkg: str) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| pkg | str | 包名 |

返回值：int - 操作结果

## stopApp

说明：停止指定的应用

签名：

```python
def stopApp(handle: int, pkg: str) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| pkg | str | 包名 |

返回值：int - 操作结果

## start_video_stream

说明：启动屏幕视频流传输

签名：

```python
def start_video_stream(handle: int, w: int, h: int, bitrate: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |
| w | int | 希望输出的宽度 |
| h | int | 希望输出的高度 |
| bitrate | int | 输出的比特率 |

返回值：int - 操作结果

## stop_video_stream

说明：关闭屏幕视频流

签名：

```python
def stop_video_stream(handle: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：int - 操作结果

## create_selector

说明：创建一个筛选器

签名：

```python
def create_selector(handle: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| handle | int | openDevice返回的id |

返回值：int - 筛选器唯一标识号

## clear_selector

说明：清空筛选器中所有的筛选条件

签名：

```python
def clear_selector(sel: int) -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| sel | int | new_selector返回的筛选器编号 |

## free_selector

说明：释放筛选器

签名：

```python
def free_selector(sel: int) -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| sel | int | new_selector返回的筛选器编号 |

## find_nodes

说明：使用筛选器去查找

签名：

```python
def find_nodes(sel: int, max_cnt_ret: int, timeout: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| sel | int | new_selector返回的筛选器编号 |
| max_cnt_ret | int | 最大返回节点数 |
| timeout | int | 查找超时时间（毫秒） |

返回值：int - 结果集唯一标识编号

## free_nodes

说明：释放结果集

签名：

```python
def free_nodes(nodes: int) -> None:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| nodes | int | find_nodes返回的结果集 |

## get_nodes_size

说明：获取结果集中节点的个数

签名：

```python
def get_nodes_size(nodes: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| nodes | int | find_nodes返回的结果集 |

返回值：int - 节点个数

## get_node_by_index

说明：按照顺序从结果集中获取节点

签名：

```python
def get_node_by_index(nodes: int, index: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| nodes | int | find_nodes返回的结果集 |
| index | int | 节点索引 |

返回值：int - 节点句柄

## get_node_parent

说明：获取给定节点的父节点句柄

签名：

```python
def get_node_parent(node: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：int - 父节点句柄

## get_node_child_count

说明：获取给定节点的子节点数��量

签名：

```python
def get_node_child_count(node: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：int - 子节点数量

## get_node_child

说明：获取给定节点的子节点

签名：

```python
def get_node_child(node: int, index: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |
| index | int | 子节点索引 |

返回值：int - 子节点句柄

## get_node_json

说明：获取节点的JSON字符串格式

签名：

```python
def get_node_json(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - JSON字符串

## get_node_text

说明：获取节点的文本属性

签名：

```python
def get_node_text(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - 文本内容

## get_node_desc

说明：获取节点的描述属性

签名：

```python
def get_node_desc(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - 描述内容

## get_node_package

说明：获取节点的包名属性

签名：

```python
def get_node_package(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - 包名

## get_node_class

说明：获取节点的类名属性

签名：

```python
def get_node_class(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - 类名

## get_node_id

说明：获取节点的资源ID属性

签名：

```python
def get_node_id(node: int) -> str:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：str - 资源ID

## get_node_bound

说明：获取节点的范围属性

签名：

```python
def get_node_bound(node: int) -> Bounds:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：Bounds - 边界信息

异常：Exception - 获取失败时抛出异常

## get_node_bound_center

说明：获取节点的中心坐标

签名：

```python
def get_node_bound_center(node: int) -> Point:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：Point - 中心坐标

异常：Exception - 获取失败时抛出异常

## Click_events

说明：点击节点

签名：

```python
def Click_events(node: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：int - 1表示成功，0表示失败

## longClick_events

说明：长按节点

签名：

```python
def longClick_events(node: int) -> int:
```

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| node | int | 节点句柄 |

返回值：int - 1表示成功，0表示失败

## 布尔属性筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| enable(sel: int, v: bool) | 设置节点是否可用筛选器 |
| checkable(sel: int, v: bool) | 设置节点是否可以被选中筛选器 |
| clickable(sel: int, v: bool) | 设置节点是否可以被点击筛选器 |
| focusable(sel: int, v: bool) | 设置节点是否可以获取焦点筛选器 |
| focused(sel: int, v: bool) | 设置节点是否已经获取焦点筛选器 |
| scrollable(sel: int, v: bool) | 设置节点是否可以滚动筛选器 |
| long_clickable(sel: int, v: bool) | 设置节点是否可以长按筛选器 |
| password(sel: int, v: bool) | 设置节点是否是密码筛选器 |
| selected(sel: int, v: bool) | 设置节点是否被选中筛选器 |
| visible(sel: int, v: bool) | 设置节点是否可见筛选器 |
| index(sel: int, v: int) | 设置节点索引筛选器 |

## 边界筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| bounds_inside(sel: int, l: int, t: int, r: int, b: int) | 设置在节点指定范围内的筛选器 |
| bounds_equal(sel: int, l: int, t: int, r: int, b: int) | 设置节点的范围等于指定范围的筛选器 |

## ID匹配筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| id_equal(sel: int, str: str) | 设置节点的资源ID等于指定id的筛选器 |
| id_start_with(sel: int, str: str) | 设置节点的资源ID以指定字符串开头的筛选器 |
| id_end_with(sel: int, str: str) | 设置节点的资源ID以指定字符串结尾的筛选器 |
| id_contain_with(sel: int, str: str) | 设置节点的资源ID包含指定字符串的筛选器 |
| id_match_with(sel: int, str: str) | 设置节点的资源ID正则匹配指定字符串的筛选器 |

## Text匹配筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| text_start_with(sel: int, str: str) | 设置节点文本以指定字符串开头的筛选器 |
| text_end_with(sel: int, str: str) | 设置节点文本以指定字符串结尾的筛选器 |
| text_contain_with(sel: int, str: str) | 设置节点文本包含指定字符串的筛选器 |
| text_match_with(sel: int, str: str) | 设置节点文本正则匹配指定字符串的筛选器 |

## Class匹配筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| clz_start_with(sel: int, str: str) | 设置节点类名以指定字符串开头的筛选器 |
| clz_end_with(sel: int, str: str) | 设置节点类名以指定字符串结尾的筛选器 |
| clz_contain_with(sel: int, str: str) | 设置节点类名包含指定字符串的筛选器 |
| clz_match_with(sel: int, str: str) | 设置节点类名正则匹配指定字符串的筛选器 |

## Package匹配筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| package_start_with(sel: int, str: str) | 设置节点包名以指定字符串开头的筛选器 |
| package_end_with(sel: int, str: str) | 设置节点包名以指定字符串结尾的筛选器 |
| package_contain_with(sel: int, str: str) | 设置节点包名包含指定字符串的筛选器 |
| package_match_with(sel: int, str: str) | 设置节点包名正则匹配指定字符串的筛选器 |

## Desc匹配筛选

字段：

| 方法名 | 说明 |
| --- | --- |
| desc_start_with(sel: int, str: str) | 设置节点描述以指定字符串开头的筛选器 |
| desc_end_with(sel: int, str: str) | 设置节点描述以指定字符串结尾的筛选器 |
| desc_contain_with(sel: int, str: str) | 设置节点描述包含指定字符串的筛选器 |
| desc_match_with(sel: int, str: str) | 设置节点描述正则匹配指定字符串的筛选器 |
