from __future__ import annotations

import json
import mimetypes
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

    def _query_string(self, query: Mapping[str, Any] | None) -> str:
        if not query:
            return ""
        normalized: dict[str, Any] = {}
        for key, value in query.items():
            if value is None:
                continue
            normalized[str(key)] = value
        return f"?{parse.urlencode(normalized, doseq=True)}" if normalized else ""

    def _perform_request(self, req: request.Request) -> Dict[str, Any]:
        last_error = "request_failed"
        for _ in range(self.retries):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read()
                    headers = dict(resp.headers.items())
                    content_type = str(resp.headers.get("Content-Type", ""))
                    return {"ok": True, "status": int(getattr(resp, "status", 200)), "body": body, "headers": headers, "content_type": content_type}
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

    @staticmethod
    def _parse_response_bytes(body: bytes, content_type: str) -> Dict[str, Any]:
        content_type_lower = content_type.lower()
        if "application/json" in content_type_lower:
            try:
                return json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                pass
        text = body.decode("utf-8", errors="ignore") if body else ""
        if text:
            try:
                return json.loads(text)
            except Exception:
                return {"text": text}
        return {}

    def request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        query_part = self._query_string(query)
        url = f"{self._url(path)}{query_part}"
        data = None
        headers: Dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url=url, method=method.upper(), data=data, headers=headers)
        response = self._perform_request(req)
        if not response.get("ok"):
            return response
        parsed = self._parse_response_bytes(
            body=bytes(response.get("body", b"")),
            content_type=str(response.get("content_type", "")),
        )
        return {"ok": True, "data": parsed, "status": int(response.get("status", 200)), "headers": response.get("headers", {})}

    def request_bytes(self, method: str, path: str, query: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        query_part = self._query_string(query)
        url = f"{self._url(path)}{query_part}"
        req = request.Request(url=url, method=method.upper(), headers={"Accept": "*/*"})
        response = self._perform_request(req)
        if not response.get("ok"):
            return response
        return {
            "ok": True,
            "data": bytes(response.get("body", b"")),
            "status": int(response.get("status", 200)),
            "headers": response.get("headers", {}),
            "content_type": str(response.get("content_type", "")),
        }

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, Any] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        boundary = "----mytboundary7e5f12423f"
        body = bytearray()

        for name, value in (fields or {}).items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        for field_name, (filename, content, content_type) in (files or {}).items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            body.extend(content)
            body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        query_part = self._query_string(query)
        url = f"{self._url(path)}{query_part}"
        req = request.Request(
            url=url,
            method="POST",
            data=bytes(body),
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        response = self._perform_request(req)
        if not response.get("ok"):
            return response
        parsed = self._parse_response_bytes(
            body=bytes(response.get("body", b"")),
            content_type=str(response.get("content_type", "")),
        )
        return {"ok": True, "data": parsed, "status": int(response.get("status", 200)), "headers": response.get("headers", {})}

    def get(self, path: str, query: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("GET", path, query=query)

    def post(self, path: str, payload: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("POST", path, payload=payload)

    def put(self, path: str, payload: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("PUT", path, payload=payload)

    def delete(self, path: str, payload: Mapping[str, Any] | None = None, query: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        return self.request_json("DELETE", path, payload=payload, query=query)


class MytSdkClient:
    def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3) -> None:
        self.http = BaseHTTPClient(device_ip, sdk_port, timeout_seconds=timeout_seconds, retries=retries)

    def _invalid(self, message: str) -> Dict[str, Any]:
        return {"ok": False, "error": message}

    def _require_non_empty(self, value: str, field_name: str) -> Dict[str, Any] | None:
        if not str(value).strip():
            return self._invalid(f"{field_name} is required")
        return None

    @staticmethod
    def _infer_content_type(file_path: str) -> str:
        guessed, _ = mimetypes.guess_type(file_path)
        return guessed or "application/octet-stream"

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

    def list_androids(self, **filters: Any) -> Dict[str, Any]:
        query = {k: v for k, v in filters.items() if v is not None and str(v).strip()}
        return self.http.get("/android", query=query or None)

    def create_android(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(str(body.get("imageUrl", "")), "imageUrl")
        if image_invalid is not None:
            return image_invalid
        dns_invalid = self._require_non_empty(str(body.get("dns", "")), "dns")
        if dns_invalid is not None:
            return dns_invalid
        return self.http.post("/android", payload=body)

    def reset_android(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        return self.http.put("/android", payload=body)

    def delete_android(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/android", payload={"name": name})

    def switch_image(self, name: str, image_url: str, **kwargs: Any) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(image_url, "imageUrl")
        if image_invalid is not None:
            return image_invalid
        return self.http.post("/android/switchImage", payload={"name": name, "imageUrl": image_url, **kwargs})

    def switch_model(self, name: str, model_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        model_id_value = str(model_id or kwargs.get("modelId") or "").strip()
        local_model_value = str(kwargs.get("localModel") or kwargs.get("local_model") or "").strip()
        model_static_value = str(kwargs.get("modelStatic") or kwargs.get("model_static") or "").strip()
        if not model_id_value and not local_model_value and not model_static_value:
            return self._invalid("one of modelId/localModel/modelStatic is required")

        payload: Dict[str, Any] = {"name": name, **kwargs}
        if model_id_value:
            payload["modelId"] = model_id_value
        if local_model_value and "localModel" not in payload:
            payload["localModel"] = local_model_value
        if model_static_value and "modelStatic" not in payload:
            payload["modelStatic"] = model_static_value
        payload.pop("local_model", None)
        payload.pop("model_static", None)
        return self.http.post("/android/switchModel", payload=payload)

    def pull_image(self, image_url: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.post("/android/pullImage", payload={"imageUrl": image_url})

    def list_images(self) -> Dict[str, Any]:
        return self.http.get("/android/image")

    def delete_image(self, image_url: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/image", payload={"imageUrl": image_url})

    def list_image_tars(self, filename: str = "") -> Dict[str, Any]:
        query = {"filename": filename.strip()} if filename.strip() else None
        return self.http.get("/android/imageTar", query=query)

    def delete_image_tar(self, filename: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(filename, "filename")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/imageTar", payload={"filename": filename})

    def export_image(self, image_url: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.post("/android/image/export", payload={"imageUrl": image_url})

    def download_image_tar(self, filename: str, save_path: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(filename, "filename")
        if name_invalid is not None:
            return name_invalid
        path_invalid = self._require_non_empty(save_path, "save_path")
        if path_invalid is not None:
            return path_invalid
        result = self.http.request_bytes("GET", "/android/image/download", query={"filename": filename})
        if not result.get("ok"):
            return result
        Path(save_path).write_bytes(bytes(result.get("data", b"")))
        return {"ok": True, "data": {"saved": save_path}}

    def import_image(self, image_tar_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(image_tar_path, "file")
        if invalid is not None:
            return invalid
        file_path = Path(image_tar_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {image_tar_path}")
        return self.http.post_multipart(
            "/android/image/import",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def export_android(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/export", payload={"name": name})

    def import_android(self, package_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package_path, "file")
        if invalid is not None:
            return invalid
        file_path = Path(package_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {package_path}")
        return self.http.post_multipart(
            "/android/import",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def list_phone_models_online(self) -> Dict[str, Any]:
        return self.http.get("/android/phoneModel")

    def list_country_codes(self) -> Dict[str, Any]:
        return self.http.get("/android/countryCode")

    def set_android_macvlan(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        return self.http.post("/android/macvlan", payload=body)

    def prune_images(self) -> Dict[str, Any]:
        return self.http.post("/android/pruneImages")

    def list_backups(self, name: str = "") -> Dict[str, Any]:
        return self.http.get("/backup", query={"name": name} if str(name).strip() else None)

    def delete_backup(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/backup", payload={"name": name})

    def download_backup(self, backup_name: str, save_path: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(backup_name, "name")
        if name_invalid is not None:
            return name_invalid
        path_invalid = self._require_non_empty(save_path, "save_path")
        if path_invalid is not None:
            return path_invalid
        result = self.http.request_bytes("GET", "/backup/download", query={"name": backup_name})
        if not result.get("ok"):
            return result
        Path(save_path).write_bytes(bytes(result.get("data", b"")))
        return {"ok": True, "data": {"saved": save_path}}

    def backup_model(self, model_name: str, suffix: str) -> Dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "name")
        if name_invalid is not None:
            return name_invalid
        suffix_invalid = self._require_non_empty(suffix, "suffix")
        if suffix_invalid is not None:
            return suffix_invalid
        return self.http.post("/android/backup/model", payload={"name": model_name, "suffix": suffix})

    def list_model_backups(self) -> Dict[str, Any]:
        return self.http.get("/android/backup/model")

    def delete_model_backup(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/backup/model", payload={"name": name})

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
        file_path = Path(import_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {import_path}")
        return self.http.post_multipart(
            "/android/backup/modelImport",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def list_models(self) -> Dict[str, Any]:
        return self.http.get("/lm/local")

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

    def change_ssh_password(self, username: str, password: str) -> Dict[str, Any]:
        pass_invalid = self._require_non_empty(password, "password")
        if pass_invalid is not None:
            return pass_invalid
        payload: Dict[str, Any] = {"password": password}
        if str(username).strip():
            payload["username"] = str(username).strip()
        return self.http.post("/link/ssh/changePwd", payload=payload)

    def switch_ssh_root(self, enabled: bool) -> Dict[str, Any]:
        return self.http.post("/link/ssh/switchRoot", payload={"enable": bool(enabled)})

    def enable_ssh(self, enabled: bool) -> Dict[str, Any]:
        return self.http.post("/link/ssh/enable", payload={"enable": bool(enabled)})

    def open_ssh_terminal(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/link/ssh", query=normalized or None)

    def get_ssh_ws_url(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {"ok": True, "data": {"url": f"ws://{self.http.host}:{self.http.port}/link/ssh{query_str}"}}

    def get_ssh_page_url(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {"ok": True, "data": {"url": f"http://{self.http.host}:{self.http.port}/ssh{query_str}"}}

    def open_container_exec(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/link/exec", query=normalized or None)

    def get_container_exec_page_url(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {"ok": True, "data": {"url": f"http://{self.http.host}:{self.http.port}/container/exec{query_str}"}}

    def get_container_exec_ws_url(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {"ok": True, "data": {"url": f"ws://{self.http.host}:{self.http.port}/link/exec{query_str}"}}

    def list_myt_bridge(self) -> Dict[str, Any]:
        return self.http.get("/mytBridge")

    def create_myt_bridge(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytBridge", payload=dict(payload))

    def update_myt_bridge(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.put("/mytBridge", payload=dict(payload))

    def delete_myt_bridge(self, name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/mytBridge", payload={"name": name})

    def list_vpc_groups(self) -> Dict[str, Any]:
        return self.http.get("/mytVpc/group")

    def create_vpc_group(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytVpc/group", payload=dict(payload))

    def update_vpc_group_alias(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytVpc/group/alias", payload=dict(payload))

    def delete_vpc_group(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.delete("/mytVpc/group", payload=dict(payload))

    def add_vpc_rule(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytVpc/addRule", payload=dict(payload))

    def list_vpc_container_rules(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/mytVpc/containerRule", query=normalized or None)

    def delete_vpc_node(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.delete("/mytVpc", payload=dict(payload))

    def update_vpc_group(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytVpc/group/update", payload=dict(payload))

    def add_vpc_socks(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.http.post("/mytVpc/socks", payload=dict(payload))

    def set_vpc_whitelist_dns(self, enabled: bool) -> Dict[str, Any]:
        return self.http.post("/mytVpc/whiteListDns", payload={"enable": bool(enabled)})

    def test_vpc_latency(self, **query: Any) -> Dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/mytVpc/test", query=normalized or None)

    def list_local_phone_models(self) -> Dict[str, Any]:
        return self.http.get("/phoneModel")

    def delete_local_phone_model(self, model_name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.delete("/phoneModel", payload={"modelName": model_name})

    def export_local_phone_model(self, model_name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.post("/phoneModel/export", payload={"modelName": model_name})

    def import_phone_model(self, package_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package_path, "file")
        if invalid is not None:
            return invalid
        file_path = Path(package_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {package_path}")
        return self.http.post_multipart(
            "/phoneModel/import",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def upgrade_server(self) -> Dict[str, Any]:
        return self.http.get("/server/upgrade")

    def upload_server_upgrade(self, package_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package_path, "file")
        if invalid is not None:
            return invalid
        file_path = Path(package_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {package_path}")
        return self.http.post_multipart(
            "/server/upgrade/upload",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def reset_server_device(self) -> Dict[str, Any]:
        return self.http.post("/server/device/reset")

    def reboot_server_device(self) -> Dict[str, Any]:
        return self.http.post("/server/device/reboot")

    def switch_docker_api(self, enabled: bool) -> Dict[str, Any]:
        return self.http.post("/server/dockerApi", payload={"enable": bool(enabled)})

    def get_server_network(self) -> Dict[str, Any]:
        return self.http.get("/server/network")

    def import_lm_package(self, package_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package_path, "file")
        if invalid is not None:
            return invalid
        file_path = Path(package_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {package_path}")
        return self.http.post_multipart(
            "/lm/import",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def get_lm_info(self) -> Dict[str, Any]:
        return self.http.get("/lm/info")

    def delete_lm_local(self, model_name: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.delete("/lm/local", payload={"modelName": model_name})

    def get_lm_models(self) -> Dict[str, Any]:
        return self.http.get("/lm/models")

    def reset_lm_device(self) -> Dict[str, Any]:
        return self.http.post("/lm/reset")

    def start_lm_server(self) -> Dict[str, Any]:
        return self.http.post("/lm/server/start")

    def stop_lm_server(self) -> Dict[str, Any]:
        return self.http.post("/lm/server/stop")

    def set_lm_work_mode(self, mode: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(mode, "mode")
        if invalid is not None:
            return invalid
        return self.http.post("/lm/workMode", payload={"mode": mode})

    def query_s5_proxy(self) -> Dict[str, Any]:
        return self.http.get("/proxy/status")

    def set_s5_proxy(self, s5_config: Mapping[str, Any]) -> Dict[str, Any]:
        config = dict(s5_config)
        proxy_ip = str(config.get("s5IP") or "").strip()
        proxy_port = config.get("s5Port")
        username = str(config.get("s5User") or "").strip()
        password = str(config.get("s5Password") or "").strip()
        if not proxy_ip:
            return self._invalid("proxy ip is required")
        if proxy_port is None:
            return self._invalid("proxy port is required")
        if not username:
            return self._invalid("proxy usr is required")
        if not password:
            return self._invalid("proxy pwd is required")
        proxy_type = int(config.get("s5Type") or 2)
        return self.http.post(
            "/proxy/set",
            payload={
                "s5IP": proxy_ip,
                "s5Port": int(proxy_port),
                "s5User": username,
                "s5Password": password,
                "s5Type": proxy_type,
            },
        )

    def stop_s5_proxy(self) -> Dict[str, Any]:
        return self.http.post("/proxy/stop")

    def set_s5_filter(self, filter_rules: Mapping[str, Any]) -> Dict[str, Any]:
        rules = dict(filter_rules)
        domains = rules.get("domains")
        if isinstance(domains, str):
            domain_values = [x.strip() for x in domains.split(",") if x.strip()]
        elif isinstance(domains, list):
            domain_values = [str(x).strip() for x in domains if str(x).strip()]
        else:
            domain_values = []
        if not domain_values:
            return self._invalid("domains is required")
        return self.http.post("/proxy/filter", payload={"domains": domain_values})

    def get_clipboard(self) -> Dict[str, Any]:
        return self.http.get("/clipboard")

    def set_clipboard(self, content: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(content, "content")
        if invalid is not None:
            return invalid
        return self.http.post("/clipboard", payload={"content": content})

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        remote_invalid = self._require_non_empty(remote_path, "path")
        if remote_invalid is not None:
            return remote_invalid
        local_invalid = self._require_non_empty(local_path, "local_path")
        if local_invalid is not None:
            return local_invalid
        result = self.http.request_bytes("GET", "/download", query={"path": remote_path})
        if not result.get("ok"):
            return result
        Path(local_path).write_bytes(bytes(result.get("data", b"")))
        return {"ok": True, "data": {"saved": local_path}}

    def upload_file(self, local_path: str = "", remote_path: str = "", file_url: str = "") -> Dict[str, Any]:
        if file_url.strip():
            return self.http.get("/", query={"task": "upload", "file": file_url})
        local_invalid = self._require_non_empty(local_path, "local_path")
        if local_invalid is not None:
            return local_invalid
        if not Path(local_path).exists():
            return self._invalid(f"file not found: {local_path}")
        content = Path(local_path).read_bytes()
        fields: Dict[str, Any] = {}
        if str(remote_path).strip():
            fields["path"] = remote_path
        return self.http.post_multipart(
            "/upload",
            fields=fields,
            files={
                "file": (
                    Path(local_path).name,
                    content,
                    self._infer_content_type(local_path),
                )
            },
        )

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

    def backup_app_info(self, package: str, save_to: str = "") -> Dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid is not None:
            return invalid
        query: Dict[str, Any] = {"cmd": "backup", "pkg": package}
        if save_to.strip():
            query["saveto"] = save_to
        return self.http.get("/backrestore", query=query)

    def restore_app_info(self, backup_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(backup_path, "backup_path")
        if invalid is not None:
            return invalid
        return self.http.get("/backrestore", query={"cmd": "recovery", "path": backup_path})

    def batch_install_apps(self, app_paths: list[str]) -> Dict[str, Any]:
        if not app_paths:
            return self._invalid("app_paths is required")
        return self.http.post("/app/batchInstall", payload={"apps": app_paths})

    def mytos_screenshot(self, image_type: int = 0, quality: int = 80, save_path: str | None = None) -> Dict[str, Any]:
        query = {"type": int(image_type), "quality": int(quality)}
        result = self.http.request_bytes("GET", "/device/screenshot", query=query)
        if not result.get("ok"):
            return result
        payload = bytes(result.get("data", b""))
        if save_path and str(save_path).strip():
            Path(save_path).write_bytes(payload)
            return {"ok": True, "data": {"saved": save_path, "byte_length": len(payload), "path": "/device/screenshot"}}
        return {"ok": True, "data": {"bytes": payload, "byte_length": len(payload), "path": "/device/screenshot"}}

    def get_version(self) -> Dict[str, Any]:
        return self.http.get("/device/version")

    def get_container_info(self) -> Dict[str, Any]:
        return self.http.get("/device/container")

    def receive_sms(self, address: str = "", mbody: str = "", scaddress: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if address.strip():
            payload["address"] = address
        if mbody.strip():
            payload["mbody"] = mbody
        if scaddress.strip():
            payload["scaddress"] = scaddress
        return self.http.post("/sms/receive", payload=payload or None)

    def get_call_records(self, **query_params: Any) -> Dict[str, Any]:
        query = {k: v for k, v in query_params.items() if v is not None and str(v).strip()}
        return self.http.get("/call/records", query=query or None)

    def refresh_location(self) -> Dict[str, Any]:
        return self.http.post("/location/refresh")

    def ip_geolocation(self, ip: str = "", language: str | None = None) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if str(ip).strip():
            query["ip"] = ip
        if language is not None and str(language).strip():
            query["language"] = str(language).strip()
        return self.http.get("/location/ip", query=query or None)

    def query_adb_permission(self) -> Dict[str, Any]:
        return self.http.get("/system/adb")

    def switch_adb_permission(self, enabled: bool) -> Dict[str, Any]:
        return self.http.post("/system/adb", payload={"enabled": enabled})

    def set_google_id(self, adid: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(adid, "adid")
        if invalid is not None:
            return invalid
        return self.http.post("/identity/googleId", payload={"adid": adid})

    def get_google_id(self) -> Dict[str, Any]:
        return self.http.get("/identity/googleId")

    def module_manager(self, cmd: str, module: str) -> Dict[str, Any]:
        cmd_invalid = self._require_non_empty(cmd, "cmd")
        if cmd_invalid is not None:
            return cmd_invalid
        module_invalid = self._require_non_empty(module, "module")
        if module_invalid is not None:
            return module_invalid
        return self.http.post("/system/module", payload={"cmd": cmd, "module": module})

    def install_magisk(self) -> Dict[str, Any]:
        return self.module_manager("install", "magisk")

    def upload_google_cert(self, cert_path: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(cert_path, "cert_path")
        if invalid is not None:
            return invalid
        file_path = Path(cert_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {cert_path}")
        return self.http.post_multipart(
            "/uploadkeybox",
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def export_app_data(self, package: str) -> Dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid is not None:
            return invalid
        return self.http.get("/backrestore", query={"cmd": "backup", "package": package})

    def import_app_data(self, package: str, data_path: str) -> Dict[str, Any]:
        package_invalid = self._require_non_empty(package, "package")
        if package_invalid is not None:
            return package_invalid
        path_invalid = self._require_non_empty(data_path, "data_path")
        if path_invalid is not None:
            return path_invalid
        file_path = Path(data_path)
        if not file_path.exists():
            return self._invalid(f"file not found: {data_path}")
        return self.http.post_multipart(
            "/backrestore",
            fields={"cmd": "recovery", "package": package},
            files={
                "file": (
                    file_path.name,
                    file_path.read_bytes(),
                    self._infer_content_type(str(file_path)),
                )
            },
        )

    def auto_click(
        self,
        enabled: bool | None = None,
        interval_ms: int | None = None,
        *,
        action: str = "",
        finger_id: int = 0,
        x: int | None = None,
        y: int | None = None,
        code: str = "",
    ) -> Dict[str, Any]:
        if action.strip():
            normalized = action.strip().lower()
            query: Dict[str, Any] = {"action": normalized}
            if normalized in {"down", "up", "move", "click"}:
                if x is None or y is None:
                    return self._invalid("x and y are required")
                query.update({"id": int(finger_id), "x": int(x), "y": int(y)})
            elif normalized == "keypress":
                code_invalid = self._require_non_empty(code, "code")
                if code_invalid is not None:
                    return code_invalid
                query["code"] = code
            else:
                return self._invalid("unsupported autoclick action")
            return self.http.post("/autoclick", payload=query)
        query = {"enable": int(bool(enabled if enabled is not None else True))}
        if interval_ms is not None:
            query["interval"] = int(interval_ms)
        return self.http.post("/autoclick", payload=query)

    def camera_hot_start(self, enabled: bool = True, path: str = "") -> Dict[str, Any]:
        query: Dict[str, Any] = {"cmd": "start" if enabled else "stop"}
        if path.strip():
            query["path"] = path
        return self.http.post("/camera", payload=query)

    def set_background_keepalive(self, enabled: bool | None = None, cmd: int | None = None, package: str = "") -> Dict[str, Any]:
        if cmd is None:
            cmd = 2 if bool(enabled) else 3
        query: Dict[str, Any] = {"cmd": int(cmd)}
        if package.strip():
            query["package"] = package
        return self.http.post("/background", payload=query)

    def query_background_keepalive(self) -> Dict[str, Any]:
        return self.set_background_keepalive(cmd=1)

    def add_background_keepalive(self, package: str) -> Dict[str, Any]:
        return self.set_background_keepalive(cmd=2, package=package)

    def remove_background_keepalive(self, package: str) -> Dict[str, Any]:
        return self.set_background_keepalive(cmd=3, package=package)

    def update_background_keepalive(self, package: str) -> Dict[str, Any]:
        return self.set_background_keepalive(cmd=4, package=package)

    def set_key_block(self, key_code: str = "", blocked: bool = True, enabled: bool | None = None) -> Dict[str, Any]:
        if enabled is not None:
            blocked = enabled
        query: Dict[str, Any]
        if str(key_code).strip():
            query = {"key": key_code, "enable": int(bool(blocked))}
        else:
            query = {"value": 1 if bool(blocked) else 0}
        return self.http.post("/disablekey", payload=query)

    def add_contact(
        self,
        name: str = "",
        number: str = "",
        contacts: list[Mapping[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        normalized: list[dict[str, str]] = []
        for item in contacts or []:
            user = str(item.get("user") or item.get("name") or "").strip()
            tel = str(item.get("tel") or item.get("number") or "").strip()
            if user and tel:
                normalized.append({"user": user, "tel": tel})
        if not normalized:
            name_invalid = self._require_non_empty(name, "name")
            if name_invalid is not None:
                return name_invalid
            number_invalid = self._require_non_empty(number, "number")
            if number_invalid is not None:
                return number_invalid
            normalized = [{"user": name, "tel": number}]
        return self.http.post("/addcontact", payload=normalized)

    def get_root_allowed_apps(self) -> Dict[str, Any]:
        return self.http.get("/modifydev", query={"cmd": 10, "action": "list"})

    def set_root_allowed_app(self, package: str, allowed: bool) -> Dict[str, Any]:
        invalid = self._require_non_empty(package, "package")
        if invalid is not None:
            return invalid
        query = {"cmd": 10, "pkg": package, "root": "true" if allowed else "false"}
        return self.http.get("/modifydev", query=query)

    def set_virtual_camera_source(
        self,
        path: str = "",
        type: str = "",
        resolution: str = "",
    ) -> Dict[str, Any]:
        final_path = str(path).strip()
        final_type = str(type).strip()
        final_resolution = str(resolution).strip()
        if not final_path and not final_resolution:
            return self._invalid("path or resolution is required")
        query: Dict[str, Any] = {"cmd": 4}
        if final_path:
            query["path"] = final_path
        if final_type:
            query["type"] = final_type
        if final_resolution:
            query["resolution"] = final_resolution
        return self.http.get("/modifydev", query=query)

    def get_app_bootstart_list(self) -> Dict[str, Any]:
        return self.http.get("/appbootstart", query={"cmd": 1})

    def set_app_bootstart(self, package: str = "", enabled: bool = True, packages: list[str] | None = None) -> Dict[str, Any]:
        normalized = [str(item).strip() for item in (packages or []) if str(item).strip()]
        if not normalized and str(package).strip():
            normalized = [str(package).strip()]
        if not normalized:
            return self._invalid("package is required")
        if enabled:
            return self.http.request_json("POST", "/appbootstart", payload=normalized, query={"cmd": 2})
        return self.http.request_json("POST", "/appbootstart", payload=normalized, query={"cmd": 3})

    def set_language_country(self, language: str, country: str) -> Dict[str, Any]:
        language_invalid = self._require_non_empty(language, "language")
        if language_invalid is not None:
            return language_invalid
        country_invalid = self._require_non_empty(country, "country")
        if country_invalid is not None:
            return country_invalid
        return self.http.get("/modifydev", query={"cmd": 13, "language": language, "country": country})

    def get_webrtc_player_url(self, index: int, token: str = "") -> Dict[str, Any]:
        idx = int(index)
        stream_port = 30000 + (idx - 1) * 100 + 7
        rtc_port = 30000 + (idx - 1) * 100 + 8
        query = {
            "shost": self.http.host,
            "sport": stream_port,
            "q": 1,
            "v": "h264",
            "rtc_i": self.http.host,
            "rtc_p": rtc_port,
        }
        if token.strip():
            query["token"] = token.strip()
        url = f"http://{self.http.host}:{self.http.port}/webplayer/play.html?{parse.urlencode(query)}"
        return {
            "ok": True,
            "data": {
                "url": url,
                "player_port": self.http.port,
                "stream_port": stream_port,
                "rtc_port": rtc_port,
                "index": idx,
            },
        }


def make_sdk_client(device_ip: str, sdk_port: int = 8000) -> MytSdkClient:
    return MytSdkClient(device_ip=device_ip, sdk_port=sdk_port)


__all__ = ["MytRpc", "BaseHTTPClient", "MytSdkClient", "make_sdk_client"]
