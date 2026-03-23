from engine.actions import ui_touch_actions
from engine.models.runtime import ExecutionContext


class _FakeRpc:
    def __init__(self):
        self.calls: list[tuple[int, int, int, int, int, int]] = []

    def swipe(self, finger_id: int, x0: int, y0: int, x1: int, y1: int, duration: int) -> bool:
        self.calls.append((finger_id, x0, y0, x1, y1, duration))
        return True

    def close(self) -> None:
        return None


def test_swipe_accepts_direction_shorthand(monkeypatch):
    rpc = _FakeRpc()
    monkeypatch.setattr(ui_touch_actions, "_get_rpc", lambda params, context: (rpc, None))

    context = ExecutionContext(payload={})
    context.physical_width = 720
    context.physical_height = 1280

    result = ui_touch_actions.swipe({"direction": "up", "duration_ms": 500}, context)

    assert result.ok is True
    assert rpc.calls == [(0, 360, 1049, 360, 281, 500)]


def test_swipe_accepts_start_end_aliases(monkeypatch):
    rpc = _FakeRpc()
    monkeypatch.setattr(ui_touch_actions, "_get_rpc", lambda params, context: (rpc, None))

    context = ExecutionContext(payload={})
    result = ui_touch_actions.swipe(
        {"start_x": 10, "start_y": 20, "end_x": 30, "end_y": 40}, context
    )

    assert result.ok is True
    assert rpc.calls == [(0, 10, 20, 30, 40, 300)]


def test_swipe_accepts_x1_x2_aliases(monkeypatch):
    rpc = _FakeRpc()
    monkeypatch.setattr(ui_touch_actions, "_get_rpc", lambda params, context: (rpc, None))

    context = ExecutionContext(payload={})
    result = ui_touch_actions.swipe({"x1": 100, "y1": 200, "x2": 300, "y2": 400}, context)

    assert result.ok is True
    assert rpc.calls == [(0, 100, 200, 300, 400, 300)]


def test_swipe_treats_zero_transport_code_as_success(monkeypatch):
    rpc = _FakeRpc()
    rpc.swipe = lambda finger_id, x0, y0, x1, y1, duration: 0
    monkeypatch.setattr(ui_touch_actions, "_get_rpc", lambda params, context: (rpc, None))

    context = ExecutionContext(payload={})
    result = ui_touch_actions.swipe({"direction": "up"}, context)

    assert result.ok is True
    assert result.code == "ok"
    assert result.data["raw_result"] == 0
