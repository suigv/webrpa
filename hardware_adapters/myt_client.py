from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib import error, parse, request

from .mytRpc import MytRpc


class BaseHTTPClient:
    def __init__(self, host: str, port: int, timeout_seconds: float = 30.0, retries: int = 3) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def _url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"http://{self.host}:{self.port}{normalized}"

    def request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        query_part = f"?{parse.urlencode(query)}" if query else ""
        url = f"{self._url(path)}{query_part}"
        data = None
        headers: Dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url=url, method=method.upper(), data=data, headers=headers)
        last_error = "request_failed"
        for _ in range(self.retries):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                    parsed = json.loads(body) if body else {}
                    return {"ok": True, "data": parsed}
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                last_error = f"http_{exc.code}: {body or exc.reason}"
            except error.URLError as exc:
                reason = str(getattr(exc, "reason", exc))
                if isinstance(getattr(exc, "reason", None), socket.timeout):
                    reason = "timeout"
                last_error = reason
            except TimeoutError:
                last_error = "timeout"
            except Exception as exc:
                last_error = str(exc)
        return {"ok": False, "error": last_error}

    def get(self, path: str, query: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("GET", path, query=query)

    def post(self, path: str, payload: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("POST", path, payload=payload)


class MytSdkClient:
    def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3) -> None:
        self.http = BaseHTTPClient(device_ip, sdk_port, timeout_seconds=timeout_seconds, retries=retries)

    def _invalid(self, message: str) -> Dict[str, Any]:
        return {"ok": False, "error": message}

    def _require_non_empty(self, value: str, field_name: str) -> Dict[str, Any] | None:
        if not str(value).strip():
            return self._invalid(f"{field_name} is required")
        return None

    def _request_with_fallback(self, candidates: list[tuple[str, str, Any, Mapping[str, Any] | None]]) -> Dict[str, Any]:
        errors: list[str] = []
        for method, path, payload, query in candidates:
            result = self.http.request_json(method=method, path=path, payload=payload, query=query)
            if result.get("ok"):
                return result
            errors.append(str(result.get("error", f"{method} {path} failed")))
        return {"ok": False, "error": "; ".join(errors) or "all fallback endpoints failed"}

    def get_device_info(self) -> Dict[str, Any]:
        return self.http.get("/info/device")

    def get_api_version(self) -> Dict[str, Any]:
        return self.http.get("/info")

    def start_android(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/start", payload={"name": name, **kwargs})

    def stop_android(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/stop", payload={"name": name})

    def restart_android(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/restart", payload={"name": name})

    def rename_android(self, old_name: str, new_name: str) -> Dict[str, Any]:
        old_name_invalid = self._require_non_empty(old_name, "name")
        if old_name_invalid is not None:
            return old_name_invalid
        new_name_invalid = self._require_non_empty(new_name, "newName")
        if new_name_invalid is not None:
            return new_name_invalid
        return self.http.post("/android/rename", payload={"name": old_name, "newName": new_name})

    def exec_android(self, name: str, command: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        command_list: list[str]
        if isinstance(command, str):
            if not command.strip():
                return self._invalid("command is required")
            command_list = [command]
        elif isinstance(command, list):
            command_list = [str(x) for x in command if str(x).strip()]
            if not command_list:
                return self._invalid("command is required")
        else:
            return self._invalid("command must be string or list")
        return self.http.post("/android/exec", payload={"name": name, "command": command_list})

    def get_cloud_status(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.get("/android", query={"name": name})

    def switch_image(self, name: str, image_url: str, **kwargs: Any) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(image_url, "imageUrl")
        if image_invalid is not None:
            return image_invalid
        return self.http.post("/android/switchImage", payload={"name": name, "imageUrl": image_url, **kwargs})

    def switch_model(self, name: str, model_id: str, **kwargs: Any) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        model_invalid = self._require_non_empty(model_id, "modelId")
        if model_invalid is not None:
            return model_invalid
        return self.http.post("/android/switchModel", payload={"name": name, "modelId": model_id, **kwargs})

    def pull_image(self, image_url: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.post("/android/pullImage", payload={"imageUrl": image_url})

    def list_images(self) -> Dict[str, Any]:
        return self.http.get("/android/image")

    def prune_images(self) -> Dict[str, Any]:
        return self.http.post("/android/pruneImages")

    def create_backup(self, name: str) -> Dict[str, Any]:
        return self.http.get("/backup", query={"name": name} if str(name).strip() else None)

    def download_backup(self, backup_name: str, save_path: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(backup_name, "name")
        if name_invalid is not None:
            return name_invalid
        path_invalid = self._require_non_empty(save_path, "save_path")
        if path_invalid is not None:
            return path_invalid
        result = self.http.get("/backup/download", query={"name": backup_name})
        if not result.get("ok"):
            return result
        Path(save_path).write_text(json.dumps(result.get("data", {}), ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "data": {"saved": save_path}}

    def backup_model(self, model_name: str, suffix: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "name")
        if name_invalid is not None:
            return name_invalid
        suffix_invalid = self._require_non_empty(suffix, "suffix")
        if suffix_invalid is not None:
            return suffix_invalid
        return self.http.post("/android/backup/model", payload={"name": model_name, "suffix": suffix})

    def export_model(self, model_name: str, export_path: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "name")
        if name_invalid is not None:
            return name_invalid
        payload = {"name": model_name}
        if str(export_path).strip():
            payload["exportPath"] = export_path
        return self.http.post("/android/backup/modelExport", payload=payload)

    def import_model(self, import_path: str) -> Dict[str, Any]:
        path_invalid = self._require_non_empty(import_path, "file")
        if path_invalid is not None:
            return path_invalid
        if not Path(import_path).exists():
            return self._invalid(f"file not found: {import_path}")
        return self.http.post("/android/backup/modelImport", payload={"file": str(import_path)})

    def list_models(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/lm/local", None, None),
            ("GET", "/models", None, None),
        ])

    def export_local_model(self, model_name: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "modelName")
        if name_invalid is not None:
            return name_invalid
        return self.http.post("/modelExport", payload={"modelName": model_name})

    def import_local_model(self, model_file: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(model_file, "modelFile")
        if invalid is not None:
            return invalid
        return self.http.post("/modelImport", payload={"modelFile": model_file})

    def set_auth_password(self, new_password: str, confirm_password: str) -> Dict[str, Any]:
        new_invalid = self._require_non_empty(new_password, "newPassword")
        if new_invalid is not None:
            return new_invalid
        confirm_invalid = self._require_non_empty(confirm_password, "confirmPassword")
        if confirm_invalid is not None:
            return confirm_invalid
        if new_password != confirm_password:
            return self._invalid("newPassword and confirmPassword must match")
        return self.http.post("/auth/password", payload={"newPassword": new_password, "confirmPassword": confirm_password})

    def close_auth(self) -> Dict[str, Any]:
        return self.http.post("/auth/close")

    def query_s5_proxy(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/proxy/status", None, None),
            ("GET", "/proxy", None, None),
        ])

    def set_s5_proxy(self, s5_config: Mapping[str, Any]) -> Dict[str, Any]:
        config = dict(s5_config)
        proxy_ip = str(config.get("ip") or config.get("s5IP") or "").strip()
        proxy_port = config.get("port") or config.get("s5Port")
        username = str(config.get("usr") or config.get("s5User") or "").strip()
        password = str(config.get("pwd") or config.get("s5Password") or "").strip()
        if not proxy_ip:
            return self._invalid("proxy ip is required")
        if proxy_port is None:
            return self._invalid("proxy port is required")
        if not username:
            return self._invalid("proxy usr is required")
        if not password:
            return self._invalid("proxy pwd is required")
        proxy_type = int(config.get("type") or config.get("s5Type") or 2)
        return self._request_with_fallback([
            ("POST", "/proxy/set", {"s5IP": proxy_ip, "s5Port": int(proxy_port), "s5User": username, "s5Password": password, "s5Type": proxy_type}, None),
            ("GET", "/proxy", None, {"cmd": 2, "ip": proxy_ip, "port": int(proxy_port), "usr": username, "pwd": password, "type": proxy_type}),
        ])

    def stop_s5_proxy(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("POST", "/proxy/stop", None, None),
            ("GET", "/proxy", None, {"cmd": 3}),
        ])

    def set_s5_filter(self, filter_rules: Mapping[str, Any]) -> Dict[str, Any]:
        rules = dict(filter_rules)
        domains = rules.get("domains")
        if domains is None:
            domains = rules.get("allow")
        if isinstance(domains, str):
            domain_values = [x.strip() for x in domains.split(",") if x.strip()]
        elif isinstance(domains, list):
            domain_values = [str(x).strip() for x in domains if str(x).strip()]
        else:
            domain_values = []
        if not domain_values:
            return self._invalid("domains is required")
        return self._request_with_fallback([
            ("POST", "/proxy/filter", {"domains": domain_values}, None),
            ("POST", "/proxy", domain_values, {"cmd": 4}),
        ])

    def get_clipboard(self) -> Dict[str, Any]:
        return self.http.get("/clipboard")

    def set_clipboard(self, content: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(content, "content")
        if invalid is not None:
            return invalid
        return self._request_with_fallback([
            ("POST", "/clipboard", {"content": content}, None),
            ("GET", "/clipboard", None, {"cmd": 2, "text": content}),
        ])

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        remote_invalid = self._require_non_empty(remote_path, "path")
        if remote_invalid is not None:
            return remote_invalid
        local_invalid = self._require_non_empty(local_path, "local_path")
        if local_invalid is not None:
            return local_invalid
        result = self.http.get("/download", query={"path": remote_path})
        if not result.get("ok"):
            return result
        Path(local_path).write_text(json.dumps(result.get("data", {}), ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "data": {"saved": local_path}}

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        local_invalid = self._require_non_empty(local_path, "local_path")
        if local_invalid is not None:
            return local_invalid
        remote_invalid = self._require_non_empty(remote_path, "path")
        if remote_invalid is not None:
            return remote_invalid
        if not Path(local_path).exists():
            return self._invalid(f"file not found: {local_path}")
        content = Path(local_path).read_bytes()
        return self.http.post("/upload", payload={"path": remote_path, "content": content.decode("utf-8", errors="ignore")})

    def export_app_info(self, package: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid is not None:
            return invalid
        return self.http.post("/app/exportInfo", payload={"package": package})

    def import_app_info(self, package: str, data: Mapping[str, Any]) -> Dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid is not None:
            return invalid
        return self.http.post("/app/importInfo", payload={"package": package, "data": dict(data)})

    def batch_install_apps(self, app_paths: list[str]) -> Dict[str, Any]:
        if not app_paths:
            return self._invalid("app_paths is required")
        return self._request_with_fallback([
            ("POST", "/app/batchInstall", {"apps": app_paths}, None),
            ("POST", "/installapks", {"apps": app_paths}, None),
        ])

    def mytos_screenshot(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/device/screenshot", None, None),
            ("GET", "/snapshot", None, None),
        ])

    def get_version(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/device/version", None, None),
            ("GET", "/queryversion", None, None),
        ])

    def get_container_info(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/device/container", None, None),
            ("GET", "/info", None, None),
        ])

    def receive_sms(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("POST", "/sms/receive", None, None),
            ("POST", "/sms", None, {"cmd": 4}),
        ])

    def get_call_records(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/call/records", None, None),
            ("GET", "/callog", None, None),
        ])

    def refresh_location(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("POST", "/location/refresh", None, None),
            ("GET", "/task", None, None),
        ])

    def ip_geolocation(self, ip: str, language: str | None = None) -> Dict[str, Any]:
        ip_invalid = self._require_non_empty(ip, "ip")
        if ip_invalid is not None:
            return ip_invalid
        query: Dict[str, Any] = {"cmd": 11, "ip": ip}
        if language is not None and str(language).strip():
            query["launage"] = str(language).strip()
        return self._request_with_fallback([
            ("GET", "/location/ip", None, {"ip": ip}),
            ("GET", "/modifydev", None, query),
        ])

    def switch_adb_permission(self, enabled: bool) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("POST", "/system/adb", {"enabled": enabled}, None),
            ("GET", "/adb", None, {"cmd": 2 if enabled else 3}),
        ])

    def get_google_id(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("GET", "/identity/googleId", None, None),
            ("GET", "/adid", None, {"cmd": 2}),
        ])

    def install_magisk(self) -> Dict[str, Any]:
        return self._request_with_fallback([
            ("POST", "/system/magisk/install", None, None),
            ("GET", "/modulemgr", None, {"cmd": "install", "module": "magisk"}),
        ])


def make_sdk_client(device_ip: str, sdk_port: int = 8000) -> MytSdkClient:
    return MytSdkClient(device_ip=device_ip, sdk_port=sdk_port)


__all__ = ["MytRpc", "BaseHTTPClient", "MytSdkClient", "make_sdk_client"]
