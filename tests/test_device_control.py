from _pytest.monkeypatch import MonkeyPatch

from core import device_control


class _FakeRpc:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def exec_cmd(self, cmd: str) -> tuple[str, bool]:
        self.calls.append(cmd)
        return "Physical size: 1080x1920", True


class _FakeManager:
    def __init__(self, cached: tuple[int, int] | None = None) -> None:
        self.cached = cached
        self.updated: list[tuple[int, int, int]] = []

    def get_device_resolution(self, device_id: int) -> tuple[int, int] | None:
        return self.cached

    def update_device_resolution(self, device_id: int, width: int, height: int) -> None:
        self.updated.append((device_id, width, height))
        self.cached = (width, height)


def test_discover_device_resolution_uses_cache(monkeypatch: MonkeyPatch) -> None:
    manager = _FakeManager(cached=(720, 1280))
    rpc = _FakeRpc()
    monkeypatch.setattr(device_control, "get_device_manager", lambda: manager)

    result = device_control.discover_device_resolution(rpc, device_id=3)

    assert result == (720, 1280)
    assert rpc.calls == []


def test_resolve_rpc_point_updates_resolution_cache(monkeypatch: MonkeyPatch) -> None:
    manager = _FakeManager()
    rpc = _FakeRpc()
    monkeypatch.setattr(device_control, "get_device_manager", lambda: manager)

    point = device_control.resolve_rpc_point(
        x=None,
        y=None,
        nx=500,
        ny=250,
        rpc=rpc,
        device_id=2,
    )

    assert point == (540, 480)
    assert rpc.calls == ["wm size"]
    assert manager.updated == [(2, 1080, 1920)]
