# pyright: reportMissingImports=false
from pathlib import Path

from hardware_adapters.mytRpc import MytRpc


def _names(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


def test_myt_rpc_prefers_arm_library_on_linux_aarch64(monkeypatch):
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Linux")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "aarch64")

    client = MytRpc()

    assert _names(client._lib_candidates)[:2] == ["libmytrpc_arm.so", "libmytrpc.so"]


def test_myt_rpc_prefers_x86_library_on_linux_x86_64(monkeypatch):
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Linux")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "x86_64")

    client = MytRpc()

    assert _names(client._lib_candidates)[:2] == ["libmytrpc.so", "libmytrpc_arm.so"]


def test_myt_rpc_uses_dll_on_windows(monkeypatch):
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Windows")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "AMD64")

    client = MytRpc()

    assert _names(client._lib_candidates) == ["libmytrpc.dll"]


def test_myt_rpc_uses_dylib_on_macos(monkeypatch):
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Darwin")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "arm64")

    client = MytRpc()

    assert _names(client._lib_candidates) == ["libmytrpc.dylib"]


def test_myt_rpc_env_override_has_highest_priority(monkeypatch, tmp_path):
    custom = tmp_path / "custom_rpc.so"
    custom.write_bytes(b"fake")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Linux")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "x86_64")
    monkeypatch.setenv("MYT_RPC_LIB_PATH", str(custom))

    client = MytRpc()

    assert client._lib_candidates[0] == custom.resolve()
    assert "libmytrpc.so" in _names(client._lib_candidates)


def test_myt_rpc_env_override_deduplicates_default_candidate(monkeypatch, tmp_path):
    custom = tmp_path / "libmytrpc.so"
    custom.write_bytes(b"fake")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.system", lambda: "Linux")
    monkeypatch.setattr("hardware_adapters.mytRpc.platform.machine", lambda: "x86_64")
    monkeypatch.setenv("MYT_RPC_LIB_PATH", str(custom))

    client = MytRpc()

    assert client._lib_candidates.count(custom.resolve()) == 1
