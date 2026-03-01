import ctypes
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class MytRpc:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        if sys.platform == "linux":
            self._lib_path = root / "lib" / "libmytrpc.so"
        elif sys.platform == "darwin":
            self._lib_path = root / "lib" / "libmytrpc.dylib"
        else:
            self._lib_path = root / "lib" / "libmytrpc.dll"
        self._rpc: ctypes.CDLL | None = None
        self._handle: int = 0

    def _load_library(self) -> ctypes.CDLL | None:
        if self._rpc is not None:
            return self._rpc
        if not self._lib_path.exists():
            logger.warning("mytrpc library not found: %s", self._lib_path)
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

        started = time.time()
        while True:
            try:
                self._handle = lib.openDevice(bytes(ip, "utf-8"), int(port), 10)
            except Exception:
                self._handle = 0
            if self._handle > 0:
                return True
            if time.time() - started >= timeout:
                return False
            time.sleep(1)

    def close(self) -> None:
        if self._rpc is not None and self._handle > 0:
            try:
                self._rpc.closeDevice(self._handle)
            except Exception:
                pass
        self._handle = 0

    def check_connect_state(self) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.checkLive.argtypes = [ctypes.c_long]
            self._rpc.checkLive.restype = ctypes.c_int
            return self._rpc.checkLive(self._handle) != 0
        except Exception:
            return False

    def exec_cmd(self, cmd: str) -> tuple[str, bool]:
        if self._rpc is None or self._handle <= 0:
            return "", False
        try:
            self._rpc.execCmd.restype = ctypes.c_char_p
            ptr = self._rpc.execCmd(self._handle, ctypes.c_int(1), ctypes.c_char_p(cmd.encode("utf-8")))
            if ptr is None:
                return "", True
            return ptr.decode("utf-8"), True
        except Exception:
            return "", False

    def dump_node_xml(self, dump_all: bool) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            self._rpc.dumpNodeXml.argtypes = [ctypes.c_long, ctypes.c_int]
            self._rpc.dumpNodeXml.restype = ctypes.c_void_p
            ptr = self._rpc.dumpNodeXml(self._handle, 1 if dump_all else 0)
            if not ptr:
                return None
            value = ctypes.cast(ptr, ctypes.c_char_p).value
            if not isinstance(value, (bytes, bytearray)):
                self._rpc.freeRpcPtr.argtypes = [ctypes.c_void_p]
                self._rpc.freeRpcPtr(ptr)
                return None
            out = bytes(value).decode("utf-8")
            self._rpc.freeRpcPtr.argtypes = [ctypes.c_void_p]
            self._rpc.freeRpcPtr(ptr)
            return out
        except Exception:
            return None

    def dump_node_xml_ex(self, work_mode: bool, timeout_ms: int) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            self._rpc.dumpNodeXmlEx.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int]
            self._rpc.dumpNodeXmlEx.restype = ctypes.c_void_p
            ptr = self._rpc.dumpNodeXmlEx(self._handle, 1 if work_mode else 0, int(timeout_ms))
            if not ptr:
                return None
            value = ctypes.cast(ptr, ctypes.c_char_p).value
            if not isinstance(value, (bytes, bytearray)):
                self._rpc.freeRpcPtr.argtypes = [ctypes.c_void_p]
                self._rpc.freeRpcPtr(ptr)
                return None
            out = bytes(value).decode("utf-8")
            self._rpc.freeRpcPtr.argtypes = [ctypes.c_void_p]
            self._rpc.freeRpcPtr(ptr)
            return out
        except Exception:
            return None

    def send_text(self, text: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.sendText(self._handle, ctypes.c_char_p(text.encode("utf-8"))) == 1
        except Exception:
            return False

    def sendText(self, text: str) -> bool:
        return self.send_text(text)

    def open_app(self, pkg: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.openApp(self._handle, ctypes.c_char_p(pkg.encode("utf-8"))) == 0
        except Exception:
            return False

    def openApp(self, pkg: str) -> bool:
        return self.open_app(pkg)

    def stop_app(self, pkg: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.stopApp(self._handle, ctypes.c_char_p(pkg.encode("utf-8"))) == 0
        except Exception:
            return False

    def stopApp(self, pkg: str) -> bool:
        return self.stop_app(pkg)

    def touch_down(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.touchDown(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchDown(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_down(finger_id, x, y)

    def touch_up(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.touchUp(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchUp(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_up(finger_id, x, y)

    def touch_move(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.touchMove(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchMove(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_move(finger_id, x, y)

    def touch_click(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.touchClick(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchClick(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_click(finger_id, x, y)

    def long_click(self, finger_id: int, x: int, y: int, press_seconds: float) -> bool:
        if not self.touch_down(finger_id, x, y):
            return False
        time.sleep(press_seconds)
        return self.touch_up(finger_id, x, y)

    def longClick(self, finger_id: int, x: int, y: int, press_seconds: float) -> bool:
        return self.long_click(finger_id, x, y, press_seconds)

    def key_press(self, code: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.keyPress(self._handle, code) == 1
        except Exception:
            return False

    def keyPress(self, code: int) -> bool:
        return self.key_press(code)

    def press_back(self) -> bool:
        return self.key_press(4)

    def pressBack(self) -> bool:
        return self.press_back()

    def press_home(self) -> bool:
        return self.key_press(3)

    def pressHome(self) -> bool:
        return self.press_home()

    def press_enter(self) -> bool:
        return self.key_press(66)

    def pressEnter(self) -> bool:
        return self.press_enter()

    def press_recent(self) -> bool:
        return self.key_press(82)

    def pressRecent(self) -> bool:
        return self.press_recent()

    def swipe(self, finger_id: int, x0: int, y0: int, x1: int, y1: int, elapse_ms: int):
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            return self._rpc.swipe(self._handle, finger_id, x0, y0, x1, y1, elapse_ms, False)
        except Exception:
            return False

    def set_rpa_work_mode(self, mode: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.useNewNodeMode.argtypes = [ctypes.c_long, ctypes.c_int]
            self._rpc.useNewNodeMode.restype = ctypes.c_int
            return self._rpc.useNewNodeMode(self._handle, mode) != 0
        except Exception:
            return False

    def setRpaWorkMode(self, mode: int) -> bool:
        return self.set_rpa_work_mode(mode)
