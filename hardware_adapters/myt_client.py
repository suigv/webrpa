import ctypes
import os
import sys
from pathlib import Path
from typing import Optional


class MytRpc:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        if sys.platform == "linux":
            self._lib_path = root / "lib" / "libmytrpc.so"
        elif sys.platform == "darwin":
            self._lib_path = root / "lib" / "libmytrpc.dylib"
        else:
            self._lib_path = root / "lib" / "libmytrpc.dll"
        self._rpc: Optional[ctypes.CDLL] = None
        self._handle = 0

    def _load_library(self):
        if self._rpc is not None:
            return self._rpc
        if not self._lib_path.exists():
            return None
        if sys.platform == "win32":
            self._rpc = ctypes.WinDLL(str(self._lib_path))
        else:
            self._rpc = ctypes.CDLL(str(self._lib_path))
        return self._rpc

    def get_sdk_version(self):
        lib = self._load_library()
        if lib is None:
            return b""
        try:
            return lib.getVersion()
        except Exception:
            return b""

    def init(self, ip: str, port: int, timeout: int) -> bool:
        lib = self._load_library()
        if lib is None:
            return False
        try:
            self._handle = lib.openDevice(bytes(ip, "utf-8"), port, timeout)
        except Exception:
            self._handle = 0
        return self._handle > 0

    def close(self):
        if self._rpc is not None and self._handle > 0:
            try:
                self._rpc.closeDevice(self._handle)
            except Exception:
                pass
        self._handle = 0
