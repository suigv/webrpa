import ctypes
import logging
import os
import platform
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class MytRpc:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self._detected_system: str = str(platform.system()).strip().lower()
        self._detected_machine: str = self._normalized_machine()
        self._lib_candidates: list[Path] = self._resolve_library_candidates(root)
        self._lib_path: Path = self._lib_candidates[0] if self._lib_candidates else root / "lib" / "libmytrpc.so"
        self._rpc: ctypes.CDLL | None = None
        self._handle: int = 0
        logger.info(
            "MytRpc library probe: system=%s machine=%s candidates=%s",
            self._detected_system,
            self._detected_machine,
            [str(p) for p in self._lib_candidates],
        )

    @staticmethod
    def _normalized_machine() -> str:
        return str(platform.machine()).strip().lower()

    @classmethod
    def _default_library_names(cls) -> list[str]:
        system_name = str(platform.system()).strip().lower()
        machine = cls._normalized_machine()
        is_arm64 = machine in {"aarch64", "arm64"}

        if system_name == "linux":
            if is_arm64:
                return ["libmytrpc_arm.so", "libmytrpc.so"]
            return ["libmytrpc.so", "libmytrpc_arm.so"]
        if system_name == "darwin":
            return ["libmytrpc.dylib"]
        if system_name == "windows":
            return ["libmytrpc.dll"]

        if sys.platform == "linux":
            return ["libmytrpc.so", "libmytrpc_arm.so"]
        if sys.platform == "darwin":
            return ["libmytrpc.dylib"]
        return ["libmytrpc.dll"]

    @classmethod
    def _resolve_library_candidates(cls, root: Path) -> list[Path]:
        lib_root = root / "lib"
        candidates: list[Path] = []

        env_override = str(os.environ.get("MYT_RPC_LIB_PATH", "")).strip()
        if env_override:
            candidates.append(Path(env_override).expanduser().resolve())

        for name in cls._default_library_names():
            candidates.append(lib_root / name)

        unique: list[Path] = []
        seen: set[Path] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            unique.append(path)
        return unique

    def _load_library(self) -> ctypes.CDLL | None:
        if self._rpc is not None:
            return self._rpc

        load_errors: list[str] = []
        for candidate in self._lib_candidates:
            if not candidate.exists():
                continue
            try:
                if sys.platform == "win32":
                    self._rpc = ctypes.WinDLL(str(candidate))
                else:
                    self._rpc = ctypes.CDLL(str(candidate))
                self._lib_path = candidate
                logger.info(
                    "Loaded mytrpc library: %s (system=%s machine=%s)",
                    candidate,
                    self._detected_system,
                    self._detected_machine,
                )
                return self._rpc
            except Exception as exc:
                load_errors.append(f"{candidate}: {exc}")

        if load_errors:
            logger.warning("Failed to load mytrpc library candidates: %s", "; ".join(load_errors))
        else:
            logger.warning("mytrpc library not found in candidates: %s", [str(p) for p in self._lib_candidates])
        return None

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

    def screentshot(self, mode: int = 0, quality: int = 80, save_path: str = "") -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "screentshot", None)
            if fn is None:
                return None
            fn.restype = ctypes.c_char_p
            result = fn(
                self._handle,
                ctypes.c_int(mode),
                ctypes.c_int(quality),
                ctypes.c_char_p(save_path.encode("utf-8")),
            )
            if result is None:
                return None
            if isinstance(result, (bytes, bytearray)):
                return bytes(result).decode("utf-8", errors="ignore")
            return str(result)
        except Exception:
            return None

    def create_selector(self):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "createSelector", None)
            if fn is None:
                return None
            return fn(self._handle)
        except Exception:
            return None

    def execQueryOne(self, selector: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "execQueryOne", None)
            if fn is None:
                return None
            return fn(self._handle, selector)
        except Exception:
            return None

    def execQueryAll(self, selector: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "execQueryAll", None)
            if fn is None:
                return None
            return fn(self._handle, selector)
        except Exception:
            return None

    def clear_selector(self, selector: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = getattr(self._rpc, "clearSelector", None)
            if fn is None:
                return False
            return bool(fn(self._handle, selector))
        except Exception:
            return False

    def addQuery_TextContainWith(self, selector: int, value: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = getattr(self._rpc, "addQuery_TextContainWith", None)
            if fn is None:
                return False
            return bool(fn(self._handle, selector, ctypes.c_char_p(value.encode("utf-8"))))
        except Exception:
            return False

    def addQuery_Clickable(self, selector: int, clickable: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = getattr(self._rpc, "addQuery_Clickable", None)
            if fn is None:
                return False
            return bool(fn(self._handle, selector, int(clickable)))
        except Exception:
            return False

    def get_nodes_size(self, nodes: int) -> int:
        if self._rpc is None or self._handle <= 0:
            return 0
        try:
            fn = getattr(self._rpc, "get_nodes_size", None)
            if fn is None:
                return 0
            return int(fn(self._handle, nodes))
        except Exception:
            return 0

    def get_node_by_index(self, nodes: int, index: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "get_node_by_index", None)
            if fn is None:
                return None
            return fn(self._handle, nodes, index)
        except Exception:
            return None

    def free_nodes(self, nodes: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = getattr(self._rpc, "free_nodes", None)
            if fn is None:
                return False
            fn(self._handle, nodes)
            return True
        except Exception:
            return False

    def get_node_json(self, node: int) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = getattr(self._rpc, "getNodeJson", None)
            if fn is None:
                return None
            fn.restype = ctypes.c_char_p
            out = fn(self._handle, node)
            if out is None:
                return None
            if isinstance(out, (bytes, bytearray)):
                return bytes(out).decode("utf-8", errors="ignore")
            return str(out)
        except Exception:
            return None

    def getNodeJson(self, node: int) -> str | None:
        return self.get_node_json(node)
