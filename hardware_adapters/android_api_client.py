"""AndroidApiClient — 云机级 Android HTTP API 客户端（30001 端口）。

对应文档：MYTOS API 接口文档 (adk_api)
端口计算：30000 + (cloud_index - 1) * 100 + 1

与 MytSdkClient（8000，物理机级）和 MytRpc（30002，RPA控制）并列。
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from hardware_adapters.myt_client import BaseHTTPClient


class AndroidApiClient:
    """云机级 Android HTTP API 客户端，连接 30001 端口（adk_api）。"""

    def __init__(
        self, device_ip: str, api_port: int, timeout_seconds: float = 30.0, retries: int = 3
    ) -> None:
        self.http = BaseHTTPClient(
            device_ip, api_port, timeout_seconds=timeout_seconds, retries=retries
        )

    def _invalid(self, message: str) -> dict[str, Any]:
        return {"ok": False, "code": "invalid_params", "message": message}

    def _require_non_empty(self, value: str, field_name: str) -> dict[str, Any] | None:
        if not str(value).strip():
            return self._invalid(f"{field_name} is required")
        return None

    # --- 剪贴板 ---

    def get_clipboard(self) -> dict[str, Any]:
        """GET /clipboard"""
        return self.http.get("/clipboard")

    def set_clipboard(self, text: str) -> dict[str, Any]:
        """GET /clipboard?cmd=2&text="""
        invalid = self._require_non_empty(text, "text")
        if invalid:
            return invalid
        return self.http.get("/clipboard", query={"cmd": 2, "text": text})

    # --- S5 代理 ---

    def query_s5_proxy(self) -> dict[str, Any]:
        """GET /proxy"""
        return self.http.get("/proxy")

    def set_s5_proxy(
        self, ip: str, port: int, username: str, password: str, proxy_type: int = 2
    ) -> dict[str, Any]:
        """GET /proxy?cmd=2&..."""
        invalid = self._require_non_empty(ip, "ip")
        if invalid:
            return invalid
        return self.http.get(
            "/proxy",
            query={
                "cmd": 2,
                "type": proxy_type,
                "ip": ip,
                "port": int(port),
                "usr": username,
                "pwd": password,
            },
        )

    def stop_s5_proxy(self) -> dict[str, Any]:
        """GET /proxy?cmd=3"""
        return self.http.get("/proxy", query={"cmd": 3})

    def set_s5_filter(self, domains: list[str]) -> dict[str, Any]:
        """POST /proxy?cmd=4"""
        if not domains:
            return self._invalid("domains is required")
        result = self.http.request_json("POST", "/proxy", payload=domains, query={"cmd": 4})
        if result.get("ok"):
            return result
        return self.http.get("/proxy", query={"cmd": 4, "domains": ",".join(domains)})

    # --- 截图 ---

    def screenshot(
        self, image_type: int = 0, quality: int = 80, save_path: str = ""
    ) -> dict[str, Any]:
        """GET /snapshot"""
        result = self.http.request_bytes(
            "GET", "/snapshot", query={"type": image_type, "quality": quality}
        )
        if not result.get("ok"):
            return result
        payload = bytes(result.get("data", b""))
        if save_path.strip():
            Path(save_path).write_bytes(payload)
            return {"ok": True, "data": {"saved": save_path, "byte_length": len(payload)}}
        return {"ok": True, "data": {"byte_length": len(payload)}}

    # --- 文件操作 ---

    def download_file(self, remote_path: str, local_path: str) -> dict[str, Any]:
        """GET /download?path="""
        for val, name in [(remote_path, "remote_path"), (local_path, "local_path")]:
            invalid = self._require_non_empty(val, name)
            if invalid:
                return invalid
        result = self.http.request_bytes("GET", "/download", query={"path": remote_path})
        if not result.get("ok"):
            return result
        Path(local_path).write_bytes(bytes(result.get("data", b"")))
        return {"ok": True, "data": {"saved": local_path}}

    def upload_file(
        self, local_path: str = "", remote_path: str = "", file_url: str = ""
    ) -> dict[str, Any]:
        """GET /?task=upload&file= or POST /upload"""
        if file_url.strip():
            return self.http.get("/", query={"task": "upload", "file": file_url})
        invalid = self._require_non_empty(local_path, "local_path")
        if invalid:
            return invalid
        f = Path(local_path)
        if not f.exists():
            return self._invalid(f"file not found: {local_path}")
        fields: dict[str, Any] = {}
        if remote_path.strip():
            fields["path"] = remote_path
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        return self.http.post_multipart(
            "/upload", fields=fields, files={"file": (f.name, f.read_bytes(), mime)}
        )

    # --- 系统配置 ---

    def set_language_country(self, language: str, country: str) -> dict[str, Any]:
        """GET /modifydev?cmd=13"""
        for val, name in [(language, "language"), (country, "country")]:
            invalid = self._require_non_empty(val, name)
            if invalid:
                return invalid
        return self.http.get(
            "/modifydev", query={"cmd": 13, "language": language, "country": country}
        )

    def refresh_location(self) -> dict[str, Any]:
        """GET /task"""
        return self.http.get("/task")

    def ip_geolocation(self, ip: str = "", language: str = "") -> dict[str, Any]:
        """GET /modifydev?cmd=11"""
        query: dict[str, Any] = {"cmd": 11}
        if ip.strip():
            query["ip"] = ip
        if language.strip():
            query["language"] = language
            query["launage"] = language
        return self.http.get("/modifydev", query=query)

    def get_container_info(self) -> dict[str, Any]:
        """GET /info"""
        return self.http.get("/info")

    def get_version(self) -> dict[str, Any]:
        """GET /queryversion"""
        return self.http.get("/queryversion")

    # --- 短信/通话 ---

    def receive_sms(self, address: str = "", body: str = "", scaddress: str = "") -> dict[str, Any]:
        """POST /sms?cmd=4"""
        payload: dict[str, Any] = {}
        if address.strip():
            payload["address"] = address
        if body.strip():
            payload["body"] = body
            payload["mbody"] = body
        if scaddress.strip():
            payload["scaddress"] = scaddress
        return self.http.request_json("POST", "/sms", payload=payload, query={"cmd": 4})

    def get_call_records(self, **query: Any) -> dict[str, Any]:
        """GET /callog"""
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/callog", query=normalized or None)

    # --- ADB 权限 ---

    def query_adb_permission(self) -> dict[str, Any]:
        """GET /adb?cmd=1"""
        return self.http.get("/adb", query={"cmd": 1})

    def switch_adb_permission(self, enabled: bool) -> dict[str, Any]:
        """GET /adb?cmd=2/3"""
        return self.http.get("/adb", query={"cmd": 2 if enabled else 3})

    # --- Google ID ---

    def get_google_id(self, cmd: int | None = None) -> dict[str, Any]:
        """GET /adid"""
        query: dict[str, Any] = {}
        if cmd is not None:
            query["cmd"] = int(cmd)
        return self.http.get("/adid", query=query or None)

    def set_google_id(self, adid: str, cmd: int = 1) -> dict[str, Any]:
        """GET /adid?cmd=1&adid="""
        invalid = self._require_non_empty(adid, "adid")
        if invalid:
            return invalid
        return self.http.get("/adid", query={"cmd": int(cmd), "adid": adid})

    def generate_google_id(self) -> dict[str, Any]:
        """GET /adid?cmd=2"""
        return self.http.get("/adid", query={"cmd": 2})

    # --- App 管理 ---

    def install_apks(
        self, apk_paths: list[str] | None = None, zip_path: str = ""
    ) -> dict[str, Any]:
        """POST /installapks (zip) or GET /installapks (legacy apks list)."""
        if zip_path.strip():
            f = Path(zip_path)
            if not f.exists():
                return self._invalid(f"file not found: {zip_path}")
            mime = mimetypes.guess_type(zip_path)[0] or "application/octet-stream"
            return self.http.post_multipart(
                "/installapks", files={"file": (f.name, f.read_bytes(), mime)}
            )
        if not apk_paths:
            return self._invalid("apk_paths is required")
        return self.http.get("/installapks", query={"apks": ",".join(apk_paths)})

    def backup_app(self, package: str, save_to: str = "") -> dict[str, Any]:
        """GET /backrestore?cmd=backup"""
        invalid = self._require_non_empty(package, "package")
        if invalid:
            return invalid
        query: dict[str, Any] = {"cmd": "backup", "pkg": package}
        if save_to.strip():
            query["saveto"] = save_to
            query["save_to"] = save_to
        return self.http.get("/backrestore", query=query)

    def restore_app(self, backup_path: str) -> dict[str, Any]:
        """GET /backrestore?cmd=recovery"""
        invalid = self._require_non_empty(backup_path, "backup_path")
        if invalid:
            return invalid
        return self.http.get(
            "/backrestore",
            query={"cmd": "recovery", "backuppath": backup_path, "path": backup_path},
        )

    # --- 权限管理 ---

    def get_root_allowed_apps(self) -> dict[str, Any]:
        """GET /modifydev?cmd=10&action=list"""
        return self.http.get("/modifydev", query={"cmd": 10, "action": "list"})

    def set_root_allowed_app(self, package: str, allowed: bool) -> dict[str, Any]:
        """GET /modifydev?cmd=10"""
        invalid = self._require_non_empty(package, "package")
        if invalid:
            return invalid
        return self.http.get(
            "/modifydev", query={"cmd": 10, "pkg": package, "root": "true" if allowed else "false"}
        )

    def get_boot_apps(self) -> dict[str, Any]:
        """GET /appbootstart?cmd=1"""
        return self.http.get("/appbootstart", query={"cmd": 1})

    def set_boot_app(
        self, package: str, enabled: bool = True, packages: list[str] | None = None
    ) -> dict[str, Any]:
        """POST /appbootstart?cmd=2/3"""
        if packages is None:
            invalid = self._require_non_empty(package, "package")
            if invalid:
                return invalid
            payload = [package]
        else:
            payload = [str(p).strip() for p in packages if str(p).strip()]
            if not payload:
                return self._invalid("packages is required")
        return self.http.request_json(
            "POST", "/appbootstart", payload=payload, query={"cmd": 2 if enabled else 3}
        )

    # --- 联系人 ---

    def add_contact(
        self, name: str = "", number: str = "", contacts: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """GET /addcontact?data=[]"""
        if contacts is None:
            for val, field in [(name, "name"), (number, "number")]:
                invalid = self._require_non_empty(val, field)
                if invalid:
                    return invalid
            data = f'[{{"user":"{name}","tel":"{number}"}}]'
        else:
            normalized = []
            for item in contacts:
                user = str(item.get("user") or item.get("name") or "").strip()
                tel = str(item.get("tel") or item.get("number") or "").strip()
                if user and tel:
                    normalized.append({"user": user, "tel": tel})
            if not normalized:
                return self._invalid("contacts is required")
            data = json.dumps(normalized, ensure_ascii=False)
        return self.http.get("/addcontact", query={"data": data})

    # --- 键盘/后台/摄像头 ---

    def set_key_block(self, blocked: bool = True, value: int | None = None) -> dict[str, Any]:
        """GET /disablekey?value=1/0"""
        if value is None:
            value = 1 if blocked else 0
        return self.http.get("/disablekey", query={"value": int(value)})

    def set_background_keepalive(
        self, package: str, enabled: bool = True, cmd: int | None = None
    ) -> dict[str, Any]:
        """GET /background?cmd=1/2/3/4"""
        if cmd is None:
            cmd = 2 if enabled else 3
        query: dict[str, Any] = {"cmd": int(cmd)}
        if package.strip():
            query["package"] = package
        return self.http.get("/background", query=query)

    def query_background_keepalive(self) -> dict[str, Any]:
        return self.http.get("/background", query={"cmd": 1})

    def add_background_keepalive(self, package: str) -> dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid:
            return invalid
        return self.http.get("/background", query={"cmd": 2, "package": package})

    def remove_background_keepalive(self, package: str) -> dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid:
            return invalid
        return self.http.get("/background", query={"cmd": 3, "package": package})

    def update_background_keepalive(self, package: str) -> dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid:
            return invalid
        return self.http.get("/background", query={"cmd": 4, "package": package})

    def camera_hot_start(self, enabled: bool = True, path: str = "") -> dict[str, Any]:
        """GET /camera?cmd=start/stop"""
        query: dict[str, Any] = {"cmd": "start" if enabled else "stop"}
        if path.strip():
            query["path"] = path
        return self.http.get("/camera", query=query)

    def set_virtual_camera(
        self, path: str = "", type: str = "", resolution: str = ""
    ) -> dict[str, Any]:
        """GET /modifydev?cmd=4"""
        if not path and not resolution:
            return self._invalid("path or resolution is required")
        query: dict[str, Any] = {"cmd": 4}
        if path:
            query["path"] = path
        if type:
            query["type"] = type
        if resolution:
            query["resolution"] = resolution
        return self.http.get("/modifydev", query=query)

    # --- 触控（autoclick） ---

    def autoclick(self, enabled: bool = True, interval_ms: int | None = None) -> dict[str, Any]:
        """GET /autoclick?enable=1/0"""
        query: dict[str, Any] = {"enable": 1 if enabled else 0}
        if interval_ms is not None:
            query["interval"] = int(interval_ms)
        return self.http.get("/autoclick", query=query)

    def autoclick_action(
        self,
        action: str,
        x: int | None = None,
        y: int | None = None,
        finger_id: int = 0,
        code: str = "",
    ) -> dict[str, Any]:
        """GET /autoclick?action=touchdown/touchup/touchmove/tap/keypress"""
        normalized = action.strip().lower()
        action_map = {
            "down": "touchdown",
            "up": "touchup",
            "move": "touchmove",
            "click": "tap",
            "touchdown": "touchdown",
            "touchup": "touchup",
            "touchmove": "touchmove",
            "tap": "tap",
            "keypress": "keypress",
        }
        mapped = action_map.get(normalized, normalized)
        query: dict[str, Any] = {"action": mapped}
        if mapped in {"touchdown", "touchup", "touchmove", "tap"}:
            if x is None or y is None:
                return self._invalid("x and y are required")
            query.update({"id": finger_id, "x": int(x), "y": int(y)})
        elif mapped == "keypress":
            if not code.strip():
                return self._invalid("code is required")
            query["code"] = code
        return self.http.get("/autoclick", query=query)

    # --- 模块管理 ---

    def module_manager(self, cmd: str, module: str) -> dict[str, Any]:
        """GET /modulemgr?cmd=check/install/uninstall&module="""
        cmd_value = str(cmd or "").strip()
        module_value = str(module or "").strip()
        if not cmd_value:
            return self._invalid("cmd is required")
        if not module_value:
            return self._invalid("module is required")
        return self.http.get(
            "/modulemgr", query={"cmd": cmd_value, "module": module_value, "moduler": module_value}
        )

    def install_magisk(self) -> dict[str, Any]:
        """GET /modulemgr?cmd=install&moduler=magisk"""
        return self.module_manager("install", "magisk")

    # --- 证书 ---

    def upload_google_cert(self, cert_path: str) -> dict[str, Any]:
        """POST /uploadkeybox"""
        invalid = self._require_non_empty(cert_path, "cert_path")
        if invalid:
            return invalid
        f = Path(cert_path)
        if not f.exists():
            return self._invalid(f"file not found: {cert_path}")
        mime = mimetypes.guess_type(cert_path)[0] or "application/octet-stream"
        return self.http.post_multipart(
            "/uploadkeybox", files={"file": (f.name, f.read_bytes(), mime)}
        )

    def get_webrtc_player_url(
        self,
        shost: str,
        sport: str | int,
        q: str = "1",
        v: str = "h264",
        rtc_i: str = "",
        rtc_j: str = "",
        rtc_p: str | int = "",
    ) -> dict[str, Any]:
        host = str(shost).strip()
        port = str(sport).strip()
        if not host or not port:
            return self._invalid("shost and sport are required")
        rtc_ip = str(rtc_i or rtc_j or host).strip()
        rtc_port = str(rtc_p or port).strip()
        url = (
            "webplayer/play.html"
            f"?shost={host}"
            f"&sport={port}"
            f"&q={q}"
            f"&v={v}"
            f"&rtc_i={rtc_ip}"
            f"&rtc_p={rtc_port}"
        )
        return {"ok": True, "data": {"url": url}}


def make_android_api_client(device_ip: str, api_port: int) -> AndroidApiClient:
    """工厂函数，创建 AndroidApiClient 实例。"""
    return AndroidApiClient(device_ip=device_ip, api_port=api_port)
