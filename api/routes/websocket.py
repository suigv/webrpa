import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from new.common.logger import log_manager

router = APIRouter()
_clients = []
_logger_bridge_ready = False


async def _broadcast(message: str):
    _cleanup_clients()
    disconnected = []
    for client in list(_clients):
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        if client in _clients:
            _clients.remove(client)


def _cleanup_clients():
    stale = []
    for client in _clients:
        if client.client_state != WebSocketState.CONNECTED:
            stale.append(client)
    for client in stale:
        if client in _clients:
            _clients.remove(client)


def _ensure_logger_bridge():
    global _logger_bridge_ready
    if _logger_bridge_ready:
        return
    log_manager.set_ws_broadcast(_broadcast)
    _logger_bridge_ready = True


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    _ensure_logger_bridge()
    await websocket.accept()
    _cleanup_clients()
    if websocket not in _clients:
        _clients.append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _clients:
            _clients.remove(websocket)
