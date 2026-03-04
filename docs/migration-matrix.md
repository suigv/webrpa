# 迁移矩阵（Migration Matrix）

本文档记录 `new/` 独立化基线的迁移决策（不依赖外部仓库路径）。

## 保留（KEEP）
- `models/config.py`
- `models/device.py`
- `core/config_loader.py`
- `core/data_store.py`
- `core/port_calc.py`
- `api/routes/config.py`
- `api/routes/data.py`
- `api/routes/devices.py`
- `api/routes/websocket.py`

## 存根实现（STUB）
- `hardware_adapters/myt_client.py`（可选 RPC，惰性加载）
- `common/logger.py`（独立日志桥接）
- `engine/runner.py`（运行时骨架）

## 排除（EXCLUDE）
- 旧版任务工作流实现
- 旧版 command/stop API 形态
- 与旧工作流引擎的耦合代码
