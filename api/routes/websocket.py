import asyncio
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from common.logger import log_manager
from core.task_events import TaskEventStore

router = APIRouter()
logger = logging.getLogger(__name__)


# --- 任务事件桥接逻辑 ---
def get_event_broadcaster(loop: asyncio.AbstractEventLoop) -> Callable[[Any], None]:
    """返回一个将任务事件转发到 WebSocket 的回调函数"""
    if not loop.is_running():
        raise RuntimeError("event loop must be running")

    def _on_event(event):
        # 构造纯净的结构化数据
        payload = {
            "event_type": event.event_type,
            "task_id": event.task_id,
            "timestamp": event.created_at,
            "data": event.payload,
            "target": event.payload.get("target", "SYS"),
            "level": "info",
        }
        json_str = json.dumps(payload, ensure_ascii=False)

        # 由于事件可能在后台线程产生，需要安全地调度到主循环
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(json_str), loop)

    return _on_event


# --- 桥接逻辑结束 ---

_db_poll_started = False
_db_poll_lock = threading.Lock()
_db_poll_stop_event = threading.Event()
_db_poll_thread: threading.Thread | None = None


def start_db_event_poller(loop: asyncio.AbstractEventLoop) -> None:
    """启动后台线程，轮询 SQLite 新事件并广播到 WebSocket（用于 process 模式下的子进程事件）"""
    global _db_poll_started, _db_poll_thread
    with _db_poll_lock:
        if _db_poll_started:
            return
        _db_poll_started = True
        _db_poll_stop_event.clear()

    def _poll_loop() -> None:
        event_store = TaskEventStore()
        # 启动时跳过历史事件，只广播新事件
        try:
            last_event_id = event_store.max_event_id()
        except Exception:
            last_event_id = 0

        while not _db_poll_stop_event.is_set():
            try:
                new_events = event_store.list_events_after(last_event_id, limit=50)
                for event in new_events:
                    last_event_id = event.event_id
                    payload = {
                        "event_type": event.event_type,
                        "task_id": event.task_id,
                        "timestamp": event.created_at,
                        "data": event.payload,
                        "target": event.payload.get("target", "SYS"),
                        "level": "info",
                    }
                    json_str = json.dumps(payload, ensure_ascii=False)
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(_broadcast(json_str), loop)
            except Exception:
                pass
            _db_poll_stop_event.wait(timeout=0.5)

    _db_poll_thread = threading.Thread(target=_poll_loop, name="ws-db-event-poller", daemon=True)
    _db_poll_thread.start()


def stop_db_event_poller() -> None:
    global _db_poll_started, _db_poll_thread
    with _db_poll_lock:
        if not _db_poll_started:
            return
        _db_poll_started = False
        _db_poll_stop_event.set()
        thread = _db_poll_thread
        _db_poll_thread = None

    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


# Track active WebSocket clients and their optional filters
# _clients[websocket] = {"filter_target": "Unit #1-1", "filter_task": "..."}
_clients: dict[WebSocket, dict[str, Any]] = {}
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
