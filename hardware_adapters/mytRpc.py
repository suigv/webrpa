# pyright: reportGeneralTypeIssues=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
import ctypes
import logging
import os
import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

VIDEO_CB_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_void_p, ctypes.c_int)
AUDIO_CB_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int)


def _noop_video_cb(rot: int, data: ctypes.c_void_p, length: int) -> None:
    _ = (rot, data, length)


def _noop_audio_cb(data: ctypes.c_void_p, length: int) -> None:
    _ = (data, length)


class MytRpc:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self._detected_system: str = str(platform.system()).strip().lower()
        self._detected_machine: str = self._normalized_machine()
        self._lib_candidates: list[Path] = self._resolve_library_candidates(root)
        self._lib_path: Path = (
            self._lib_candidates[0] if self._lib_candidates else root / "lib" / "libmytrpc.so"
        )
        self._rpc: ctypes.CDLL | None = None
        self._handle: int = 0
        self._video_cb_ref: object | None = None
        self._audio_cb_ref: object | None = None
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
            logger.warning(
                "mytrpc library not found in candidates: %s", [str(p) for p in self._lib_candidates]
            )
        return None

    def _rpc_fn(self, *names: str):
        if self._rpc is None:
            return None
        for name in names:
            fn = getattr(self._rpc, name, None)
            if fn is not None:
                return fn
        return None

    @staticmethod
    def _ptr_to_void_p(ptr: int | ctypes.c_void_p) -> ctypes.c_void_p:
        if isinstance(ptr, ctypes.c_void_p):
            return ptr
        return ctypes.c_void_p(int(ptr))

    def _owned_ptr_bytes(self, ptr: int | ctypes.c_void_p | None) -> bytes | None:
        if not ptr:
            return None
        raw_ptr = self._ptr_to_void_p(cast(int | ctypes.c_void_p, ptr))
        try:
            value = ctypes.cast(raw_ptr, ctypes.c_char_p).value
            if not isinstance(value, (bytes, bytearray)):
                return None
            return bytes(value)
        finally:
            self.free_rpc_ptr(raw_ptr)

    def _owned_ptr_text(self, ptr: int | ctypes.c_void_p | None) -> str | None:
        data = self._owned_ptr_bytes(ptr)
        if data is None:
            return None
        return data.decode("utf-8", errors="ignore")

    def get_sdk_version(self):
        lib = self._load_library()
        if lib is None or self._handle <= 0:
            return b""
        try:
            fn = self._rpc_fn("getVersion")
            if fn is None:
                return b""
            fn.argtypes = [ctypes.c_long]
            fn.restype = ctypes.c_void_p
            return self._owned_ptr_bytes(fn(self._handle)) or b""
        except Exception:
            return b""

    def init(self, ip: str, port: int, timeout: int) -> bool:
        lib = self._load_library()
        if lib is None:
            return False

        try:
            lib.openDevice.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
            lib.openDevice.restype = ctypes.c_long
        except Exception:
            pass

        started = time.time()
        while True:
            try:
                self._handle = int(lib.openDevice(bytes(ip, "utf-8"), int(port), int(timeout)))
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
                self._rpc.closeDevice.argtypes = [ctypes.c_long]
                self._rpc.closeDevice.restype = None
                self._rpc.closeDevice(self._handle)
            except Exception:
                pass
        self._handle = 0
        self._video_cb_ref = None
        self._audio_cb_ref = None

    def free_rpc_ptr(self, ptr: int | ctypes.c_void_p | None) -> None:
        if self._rpc is None or ptr is None:
            return
        try:
            fn = self._rpc_fn("freeRpcPtr")
            if fn is None:
                return
            fn.argtypes = [ctypes.c_void_p]
            fn(self._ptr_to_void_p(ptr))
        except Exception:
            return

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
            self._rpc.execCmd.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_char_p]
            self._rpc.execCmd.restype = ctypes.c_void_p
            ptr = self._rpc.execCmd(
                self._handle, ctypes.c_int(1), ctypes.c_char_p(cmd.encode("utf-8"))
            )
            if ptr is None:
                return "", True
            text = self._owned_ptr_text(ptr)
            if text is None:
                return "", True
            return text, True
        except Exception:
            return "", False

    def dump_node_xml(self, dump_all: bool) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            self._rpc.dumpNodeXml.argtypes = [ctypes.c_long, ctypes.c_int]
            self._rpc.dumpNodeXml.restype = ctypes.c_void_p
            ptr = self._rpc.dumpNodeXml(self._handle, 1 if dump_all else 0)
            return self._owned_ptr_text(ptr)
        except Exception:
            return None

    def dump_node_xml_ex(self, work_mode: bool, timeout_ms: int) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            self._rpc.dumpNodeXmlEx.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int]
            self._rpc.dumpNodeXmlEx.restype = ctypes.c_void_p
            ptr = self._rpc.dumpNodeXmlEx(self._handle, 1 if work_mode else 0, int(timeout_ms))
            return self._owned_ptr_text(ptr)
        except Exception:
            return None

    def dumpNodeXmlEx(self, work_mode: bool, timeout_ms: int = 2000) -> str | None:
        return self.dump_node_xml_ex(work_mode, timeout_ms)

    def get_display_rotate(self) -> int | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            self._rpc.getDisplayRotate.argtypes = [ctypes.c_long]
            self._rpc.getDisplayRotate.restype = ctypes.c_int
            return int(self._rpc.getDisplayRotate(self._handle))
        except Exception:
            return None

    def _capture_rgba(self, fn_name: str, *args: int) -> dict[str, object] | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn(fn_name)
            if fn is None:
                return None
            w = ctypes.c_int(0)
            h = ctypes.c_int(0)
            stride = ctypes.c_int(0)
            fn.argtypes = [
                ctypes.c_long,
                *([ctypes.c_int] * len(args)),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            fn.restype = ctypes.c_void_p
            ptr = fn(self._handle, *args, ctypes.byref(w), ctypes.byref(h), ctypes.byref(stride))
            if not ptr:
                return None
            size = max(0, int(h.value) * int(stride.value))
            if size <= 0:
                self.free_rpc_ptr(ptr)
                return None
            buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * size)).contents
            data = bytes(buf)
            self.free_rpc_ptr(ptr)
            return {
                "data": data,
                "width": int(w.value),
                "height": int(h.value),
                "stride": int(stride.value),
            }
        except Exception:
            return None

    def take_capture(self) -> dict[str, object] | None:
        return self._capture_rgba("takeCaptrue")

    def take_capture_ex(
        self, left: int, top: int, right: int, bottom: int
    ) -> dict[str, object] | None:
        return self._capture_rgba("takeCaptrueEx", int(left), int(top), int(right), int(bottom))

    def _capture_compressed(self, fn_name: str, *args: int) -> bytes | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn(fn_name)
            if fn is None:
                return None
            data_len = ctypes.c_int(0)
            fn.argtypes = [
                ctypes.c_long,
                *([ctypes.c_int] * len(args)),
                ctypes.POINTER(ctypes.c_int),
            ]
            fn.restype = ctypes.c_void_p
            ptr = fn(self._handle, *args, ctypes.byref(data_len))
            if not ptr or data_len.value <= 0:
                return None
            buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * data_len.value)).contents
            out = bytes(buf)
            self.free_rpc_ptr(ptr)
            return out
        except Exception:
            return None

    def take_capture_compress(self, image_type: int, quality: int) -> bytes | None:
        return self._capture_compressed("takeCaptrueCompress", int(image_type), int(quality))

    def take_capture_compress_ex(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        image_type: int,
        quality: int,
    ) -> bytes | None:
        return self._capture_compressed(
            "takeCaptrueCompressEx",
            int(left),
            int(top),
            int(right),
            int(bottom),
            int(image_type),
            int(quality),
        )

    def takeCaptrueCompress(self, image_type: int, quality: int) -> bytearray | bool:
        payload = self.take_capture_compress(image_type, quality)
        if payload is None:
            return False
        return bytearray(payload)

    def takeCaptrueCompressEx(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        image_type: int,
        quality: int,
    ) -> bytearray | bool:
        payload = self.take_capture_compress_ex(left, top, right, bottom, image_type, quality)
        if payload is None:
            return False
        return bytearray(payload)

    def send_text(self, text: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.sendText.argtypes = [ctypes.c_long, ctypes.c_char_p]
            self._rpc.sendText.restype = ctypes.c_int
            return self._rpc.sendText(self._handle, ctypes.c_char_p(text.encode("utf-8"))) == 1
        except Exception:
            return False

    def sendText(self, text: str) -> bool:
        return self.send_text(text)

    def open_app(self, pkg: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.openApp.argtypes = [ctypes.c_long, ctypes.c_char_p]
            self._rpc.openApp.restype = ctypes.c_int
            return self._rpc.openApp(self._handle, ctypes.c_char_p(pkg.encode("utf-8"))) == 0
        except Exception:
            return False

    def openApp(self, pkg: str) -> bool:
        return self.open_app(pkg)

    def stop_app(self, pkg: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.stopApp.argtypes = [ctypes.c_long, ctypes.c_char_p]
            self._rpc.stopApp.restype = ctypes.c_int
            return self._rpc.stopApp(self._handle, ctypes.c_char_p(pkg.encode("utf-8"))) == 0
        except Exception:
            return False

    def stopApp(self, pkg: str) -> bool:
        return self.stop_app(pkg)

    def touch_down(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.touchDown.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self._rpc.touchDown.restype = ctypes.c_int
            return self._rpc.touchDown(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchDown(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_down(finger_id, x, y)

    def touch_up(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.touchUp.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self._rpc.touchUp.restype = ctypes.c_int
            return self._rpc.touchUp(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchUp(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_up(finger_id, x, y)

    def touch_move(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.touchMove.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self._rpc.touchMove.restype = ctypes.c_int
            return self._rpc.touchMove(self._handle, finger_id, x, y) == 1
        except Exception:
            return False

    def touchMove(self, finger_id: int, x: int, y: int) -> bool:
        return self.touch_move(finger_id, x, y)

    def touch_click(self, finger_id: int, x: int, y: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.touchClick.argtypes = [
                ctypes.c_long,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            self._rpc.touchClick.restype = ctypes.c_int
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
            self._rpc.keyPress.argtypes = [ctypes.c_long, ctypes.c_int]
            self._rpc.keyPress.restype = ctypes.c_int
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

    def press_delete(self) -> bool:
        return self.key_press(67)

    def pressDelete(self) -> bool:
        return self.press_delete()

    def swipe(self, finger_id: int, x0: int, y0: int, x1: int, y1: int, elapse_ms: int):
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            self._rpc.swipe.argtypes = [
                ctypes.c_long,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_bool,
            ]
            self._rpc.swipe.restype = ctypes.c_int
            ret = self._rpc.swipe(self._handle, finger_id, x0, y0, x1, y1, elapse_ms, False)
            try:
                return int(ret)
            except Exception:
                return 1 if ret else 0
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

    def use_new_node_mode(self, enabled: bool) -> bool:
        return self.set_rpa_work_mode(1 if enabled else 0)

    def screentshot(self, mode: int = 0, quality: int = 80, save_path: str = "") -> str | None:
        if self._rpc is not None and self._handle > 0:
            try:
                fn = self._rpc_fn("screentshot")
                if fn is not None:
                    fn.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
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
                pass

        payload = self.take_capture_compress(mode, quality)
        if payload is None:
            return None
        if save_path:
            try:
                Path(save_path).write_bytes(payload)
                return save_path
            except Exception:
                return None
        return ""

    def screentshotEx(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        mode: int = 0,
        quality: int = 80,
        save_path: str = "",
    ) -> bool:
        payload = self.take_capture_compress_ex(left, top, right, bottom, mode, quality)
        if payload is None or not save_path:
            return False
        try:
            Path(save_path).write_bytes(payload)
            return True
        except Exception:
            return False

    def start_video_stream(
        self,
        width: int,
        height: int,
        bitrate: int,
        video_callback: Callable[[int, ctypes.c_void_p, int], None] | None = None,
        audio_callback: Callable[[ctypes.c_void_p, int], None] | None = None,
    ) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("startVideoStream")
            if fn is None:
                return False
            self._video_cb_ref = VIDEO_CB_FUNC(video_callback or _noop_video_cb)
            self._audio_cb_ref = AUDIO_CB_FUNC(audio_callback or _noop_audio_cb)
            fn.argtypes = [
                ctypes.c_long,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                VIDEO_CB_FUNC,
                AUDIO_CB_FUNC,
            ]
            fn.restype = ctypes.c_int
            return (
                int(
                    fn(
                        self._handle,
                        int(width),
                        int(height),
                        int(bitrate),
                        self._video_cb_ref,
                        self._audio_cb_ref,
                    )
                )
                == 1
            )
        except Exception:
            return False

    def stop_video_stream(self) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("stopVideoStream")
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_long]
            fn.restype = ctypes.c_int
            ok = int(fn(self._handle)) == 1
            self._video_cb_ref = None
            self._audio_cb_ref = None
            return ok
        except Exception:
            return False

    def startVideoStream(self, width: int = 400, height: int = 720, bitrate: int = 20000) -> bool:
        return self.start_video_stream(width, height, bitrate)

    def stopVideoStream(self) -> bool:
        return self.stop_video_stream()

    def create_selector(self):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("createSelector")
            if fn is not None:
                return fn(self._handle)
            fn = self._rpc_fn("newSelector")
            if fn is None:
                return None
            fn.argtypes = [ctypes.c_long]
            fn.restype = ctypes.c_longlong
            return int(fn(self._handle))
        except Exception:
            return None

    def new_selector(self):
        return self.create_selector()

    def execQueryOne(self, selector: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("execQueryOne")
            if fn is not None:
                return fn(self._handle, selector)
            nodes = self.find_nodes(selector, 1, 2000)
            if not nodes:
                return None
            size = self.get_nodes_size(nodes)
            node = self.get_node_by_index(nodes, 0) if size > 0 else None
            self.free_nodes(nodes)
            return node
        except Exception:
            return None

    def execQueryAll(self, selector: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("execQueryAll")
            if fn is not None:
                return fn(self._handle, selector)
            nodes = self.find_nodes(selector, 200, 2000)
            if not nodes:
                return None
            size = self.get_nodes_size(nodes)
            result = [self.get_node_by_index(nodes, idx) for idx in range(max(0, size))]
            self.free_nodes(nodes)
            return result
        except Exception:
            return None

    def clear_selector(self, selector: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("clearSelector", "clear_selector")
            if fn is None:
                return False
            try:
                fn.argtypes = [ctypes.c_longlong]
                fn(int(selector))
            except TypeError:
                fn.argtypes = [ctypes.c_long, ctypes.c_longlong]
                fn(self._handle, int(selector))
            return True
        except Exception:
            return False

    def free_selector(self, selector: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("freeSelector")
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong]
            fn(int(selector))
            return True
        except Exception:
            return False

    def find_nodes(self, selector: int, max_cnt_ret: int, timeout_ms: int) -> int | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("findNodes")
            if fn is None:
                return None
            fn.argtypes = [ctypes.c_longlong, ctypes.c_int, ctypes.c_int]
            fn.restype = ctypes.c_longlong
            return int(fn(int(selector), int(max_cnt_ret), int(timeout_ms)))
        except Exception:
            return None

    def _selector_text_call(self, method_name: str, selector: int, value: str) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn(method_name)
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong, ctypes.c_char_p]
            fn(int(selector), ctypes.c_char_p(value.encode("utf-8")))
            return True
        except Exception:
            return False

    def _selector_bool_call(self, method_name: str, selector: int, enabled: bool) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn(method_name)
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong, ctypes.c_int]
            fn(int(selector), int(bool(enabled)))
            return True
        except Exception:
            return False

    def addQuery_Text(self, selector: int, value: str) -> bool:
        return self._selector_text_call("TextEqual", selector, value)

    def addQuery_TextStartWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("TextStartWith", selector, value)

    def addQuery_TextEndWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("TextEndWith", selector, value)

    def addQuery_TextMatchWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("TextMatchWith", selector, value)

    def addQuery_TextContain(self, selector: int, value: str) -> bool:
        return self._selector_text_call("TextContainWith", selector, value)

    def addQuery_TextContainWith(self, selector: int, value: str) -> bool:
        return self.addQuery_TextContain(selector, value)

    def addQuery_Id(self, selector: int, value: str) -> bool:
        return self._selector_text_call("IdEqual", selector, value)

    def addQuery_IdStartWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("IdStartWith", selector, value)

    def addQuery_IdEndWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("IdEndWith", selector, value)

    def addQuery_IdContainWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("IdContainWith", selector, value)

    def addQuery_IdMatchWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("IdMatchWith", selector, value)

    def addQuery_Class(self, selector: int, value: str) -> bool:
        return self._selector_text_call("ClzEqual", selector, value)

    def addQuery_ClassStartWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("ClzStartWith", selector, value)

    def addQuery_ClassEndWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("ClzEndWith", selector, value)

    def addQuery_ClassContainWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("ClzContainWith", selector, value)

    def addQuery_ClassMatchWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("ClzMatchWith", selector, value)

    def addQuery_Desc(self, selector: int, value: str) -> bool:
        return self._selector_text_call("DescEqual", selector, value)

    def addQuery_DescStartWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("DescStartWith", selector, value)

    def addQuery_DescEndWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("DescEndWith", selector, value)

    def addQuery_DescContainWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("DescContainWith", selector, value)

    def addQuery_DescMatchWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("DescMatchWith", selector, value)

    def addQuery_Package(self, selector: int, value: str) -> bool:
        return self._selector_text_call("PackageEqual", selector, value)

    def addQuery_PackageStartWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("PackageStartWith", selector, value)

    def addQuery_PackageEndWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("PackageEndWith", selector, value)

    def addQuery_PackageContainWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("PackageContainWith", selector, value)

    def addQuery_PackageMatchWith(self, selector: int, value: str) -> bool:
        return self._selector_text_call("PackageMatchWith", selector, value)

    def addQuery_Bounds(self, selector: int, left: int, top: int, right: int, bottom: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("BoundsEqual")
            if fn is None:
                return False
            fn.argtypes = [
                ctypes.c_longlong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            fn(int(selector), int(left), int(top), int(right), int(bottom))
            return True
        except Exception:
            return False

    def addQuery_BoundsInside(
        self, selector: int, left: int, top: int, right: int, bottom: int
    ) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("BoundsInside")
            if fn is None:
                return False
            fn.argtypes = [
                ctypes.c_longlong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            fn(int(selector), int(left), int(top), int(right), int(bottom))
            return True
        except Exception:
            return False

    def addQuery_Clickable(self, selector: int, clickable: int) -> bool:
        return self._selector_bool_call("Clickable", selector, bool(clickable))

    def addQuery_Enable(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Enable", selector, bool(enabled))

    def addQuery_Checkable(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Checkable", selector, bool(enabled))

    def addQuery_Focusable(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Focusable", selector, bool(enabled))

    def addQuery_Focused(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Focused", selector, bool(enabled))

    def addQuery_Scrollable(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Scrollable", selector, bool(enabled))

    def addQuery_LongClickable(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("LongClickable", selector, bool(enabled))

    def addQuery_Password(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Password", selector, bool(enabled))

    def addQuery_Selected(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Selected", selector, bool(enabled))

    def addQuery_Visible(self, selector: int, enabled: int) -> bool:
        return self._selector_bool_call("Visible", selector, bool(enabled))

    def addQuery_Index(self, selector: int, index: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("Index")
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong, ctypes.c_int]
            fn(int(selector), int(index))
            return True
        except Exception:
            return False

    def get_nodes_size(self, nodes: int) -> int:
        if self._rpc is None or self._handle <= 0:
            return 0
        try:
            fn = self._rpc_fn("get_nodes_size", "getNodesSize")
            if fn is None:
                return 0
            try:
                return int(fn(self._handle, nodes))
            except TypeError:
                fn.argtypes = [ctypes.c_longlong]
                fn.restype = ctypes.c_longlong
                return int(fn(int(nodes)))
        except Exception:
            return 0

    def get_node_by_index(self, nodes: int, index: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("get_node_by_index", "getNodeByIndex")
            if fn is None:
                return None
            try:
                return fn(self._handle, nodes, index)
            except TypeError:
                fn.argtypes = [ctypes.c_longlong, ctypes.c_int]
                fn.restype = ctypes.c_longlong
                return int(fn(int(nodes), int(index)))
        except Exception:
            return None

    def free_nodes(self, nodes: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("free_nodes", "freeNodes")
            if fn is None:
                return False
            try:
                fn(self._handle, nodes)
            except TypeError:
                fn.argtypes = [ctypes.c_longlong]
                fn(int(nodes))
            return True
        except Exception:
            return False

    def get_node_parent(self, node: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("getNodeParent")
            if fn is None:
                return None
            fn.argtypes = [ctypes.c_longlong]
            fn.restype = ctypes.c_longlong
            return int(fn(int(node)))
        except Exception:
            return None

    def get_node_child_count(self, node: int) -> int:
        if self._rpc is None or self._handle <= 0:
            return 0
        try:
            fn = self._rpc_fn("getNodeChildCount")
            if fn is None:
                return 0
            fn.argtypes = [ctypes.c_longlong]
            return int(fn(int(node)))
        except Exception:
            return 0

    def get_node_child(self, node: int, index: int):
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("getNodeChild")
            if fn is None:
                return None
            fn.argtypes = [ctypes.c_longlong, ctypes.c_int]
            fn.restype = ctypes.c_longlong
            return int(fn(int(node), int(index)))
        except Exception:
            return None

    def _node_text_field(self, fn_name: str, node: int) -> str | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn(fn_name)
            if fn is None:
                return None
            fn.argtypes = [ctypes.c_longlong]
            fn.restype = ctypes.c_void_p
            ptr = fn(int(node))
            return self._owned_ptr_text(ptr)
        except Exception:
            return None

    def get_node_json(self, node: int) -> str | None:
        return self._node_text_field("getNodeJson", node)

    def get_node_text(self, node: int) -> str | None:
        return self._node_text_field("getNodeText", node)

    def get_node_desc(self, node: int) -> str | None:
        return self._node_text_field("getNodeDesc", node)

    def get_node_package(self, node: int) -> str | None:
        return self._node_text_field("getNodePackage", node)

    def get_node_class(self, node: int) -> str | None:
        return self._node_text_field("getNodeClass", node)

    def get_node_id(self, node: int) -> str | None:
        return self._node_text_field("getNodeId", node)

    def get_node_bound(self, node: int) -> dict[str, int] | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("getNodeNound")
            if fn is None:
                return None
            fn.argtypes = [
                ctypes.c_longlong,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            fn.restype = ctypes.c_int
            left = ctypes.c_int(0)
            top = ctypes.c_int(0)
            right = ctypes.c_int(0)
            bottom = ctypes.c_int(0)
            ok = (
                int(
                    fn(
                        int(node),
                        ctypes.byref(left),
                        ctypes.byref(top),
                        ctypes.byref(right),
                        ctypes.byref(bottom),
                    )
                )
                == 1
            )
            if not ok:
                return None
            return {
                "left": int(left.value),
                "top": int(top.value),
                "right": int(right.value),
                "bottom": int(bottom.value),
            }
        except Exception:
            return None

    def get_node_bound_center(self, node: int) -> dict[str, int] | None:
        if self._rpc is None or self._handle <= 0:
            return None
        try:
            fn = self._rpc_fn("getNodeNoundCenter")
            if fn is None:
                return None
            fn.argtypes = [
                ctypes.c_longlong,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            fn.restype = ctypes.c_int
            x = ctypes.c_int(0)
            y = ctypes.c_int(0)
            ok = int(fn(int(node), ctypes.byref(x), ctypes.byref(y))) == 1
            if not ok:
                return None
            return {"x": int(x.value), "y": int(y.value)}
        except Exception:
            return None

    def click_node(self, node: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("clickNode")
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong]
            return int(fn(int(node))) == 1
        except Exception:
            return False

    def long_click_node(self, node: int) -> bool:
        if self._rpc is None or self._handle <= 0:
            return False
        try:
            fn = self._rpc_fn("longClickNode")
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_longlong]
            return int(fn(int(node))) == 1
        except Exception:
            return False

    def getNodeJson(self, node: int) -> str | None:
        return self.get_node_json(node)
