# Migration Matrix

This document records the standalone baseline decisions without referencing external repository paths.

## KEEP
- `models/config.py`
- `models/device.py`
- `core/config_loader.py`
- `core/data_store.py`
- `core/port_calc.py`
- `api/routes/config.py`
- `api/routes/data.py`
- `api/routes/devices.py`
- `api/routes/websocket.py`

## STUB
- `hardware_adapters/myt_client.py` (lazy-load optional RPC)
- `common/logger.py` (standalone logger bridge)
- `engine/runner.py` (runtime skeleton)

## EXCLUDE
- Legacy task workflow implementations
- Legacy command/stop API surfaces
- Legacy workflow engine coupling
