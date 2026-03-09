# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
import json

from starlette.testclient import TestClient

from api.server import app
from api.routes import websocket as websocket_route


def setup_function() -> None:
    websocket_route._clients.clear()
    websocket_route._logger_bridge_ready = False


def teardown_function() -> None:
    websocket_route._clients.clear()


def test_websocket_logs_route_replies_to_ping() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/logs") as websocket:
            websocket.send_text(json.dumps({"type": "ping"}))
            assert json.loads(websocket.receive_text()) == {"type": "pong"}


def test_websocket_logs_route_filters_and_unsubscribes_broadcasts() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/logs") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "type": "subscribe",
                        "target": "Unit #1-1",
                        "task_id": "task-1",
                    }
                )
            )

            client.portal.call(
                websocket_route._broadcast,
                json.dumps(
                    {
                        "message": "matched",
                        "target": "Unit #1-1",
                        "task_id": "task-1",
                    }
                ),
            )
            assert json.loads(websocket.receive_text())["message"] == "matched"

            websocket.send_text(json.dumps({"type": "unsubscribe"}))
            client.portal.call(
                websocket_route._broadcast,
                json.dumps(
                    {
                        "message": "after-unsubscribe",
                        "target": "Other Unit",
                        "task_id": "other-task",
                    }
                ),
            )
            assert json.loads(websocket.receive_text())["message"] == "after-unsubscribe"
