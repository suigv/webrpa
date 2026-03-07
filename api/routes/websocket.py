import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from common.logger import log_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Track active WebSocket clients and their optional filters
# _clients[websocket] = {"filter_target": "Unit #1-1", "filter_task": "..."}
_clients: Dict[WebSocket, Dict[str, Any]] = {}
_logger_bridge_ready = False


async def _broadcast(log_json: str):
    """
    Broadcast a log message to all connected clients, respecting their filters.
    """
    _cleanup_clients()
    
    try:
        log_data = json.loads(log_json)
    except Exception:
        return

    for ws, context in list(_clients.items()):
        try:
            # Server-side filtering logic
            filter_target = context.get("filter_target")
            if filter_target and log_data.get("target") != filter_target:
                continue
            
            filter_task = context.get("filter_task")
            if filter_task and log_data.get("task_id") != filter_task:
                continue

            await ws.send_text(log_json)
        except Exception:
            # Client disconnected or send failed
            pass


def _cleanup_clients():
    stale = [ws for ws in _clients if ws.client_state != WebSocketState.CONNECTED]
    for ws in stale:
        _clients.pop(ws, None)


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
    
    # Initialize client context with no filters
    _clients[websocket] = {}

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                m_type = msg.get("type")
                
                if m_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
                elif m_type == "subscribe":
                    # Update filters for this client
                    # Expected: {"type": "subscribe", "target": "Unit #1-1", "task_id": "..."}
                    _clients[websocket]["filter_target"] = msg.get("target")
                    _clients[websocket]["filter_task"] = msg.get("task_id")
                    
                elif m_type == "unsubscribe":
                    _clients[websocket]["filter_target"] = None
                    _clients[websocket]["filter_task"] = None
                    
            except Exception as e:
                logger.debug(f"WS message error: {e}")
                
    except WebSocketDisconnect:
        pass
    finally:
        _clients.pop(websocket, None)
