from __future__ import annotations

import json
import mimetypes
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .mytRpc import MytRpc


class BaseHTTPClient:
    def __init__(
        self, host: str, port: int, timeout_seconds: float = 30.0, retries: int = 3
    ) -> None:
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

    def _perform_request(self, req: request.Request) -> dict[str, Any]:
        last_error = "request_failed"
        for _ in range(self.retries):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read()
                    headers = dict(resp.headers.items())
                    content_type = str(resp.headers.get("Content-Type", ""))
                    return {
                        "ok": True,
                        "status": int(getattr(resp, "status", 200)),
                        "body": body,
                        "headers": headers,
                        "content_type": content_type,
                    }
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
    def _parse_response_bytes(body: bytes, content_type: str) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        query_part = self._query_string(query)
        url = f"{self._url(path)}{query_part}"
        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
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
        return {
            "ok": True,
            "data": parsed,
            "status": int(response.get("status", 200)),
            "headers": response.get("headers", {}),
        }

    def request_bytes(
        self, method: str, path: str, query: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        boundary = "----mytboundary7e5f12423f"
        body = bytearray()

        for name, value in (fields or {}).items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        for field_name, (filename, content, content_type) in (files or {}).items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
            body.extend(content)
            body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode())

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
        return {
            "ok": True,
            "data": parsed,
            "status": int(response.get("status", 200)),
            "headers": response.get("headers", {}),
        }

    def get(self, path: str, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("GET", path, query=query)

    def post(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("POST", path, payload=payload)

    def put(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("PUT", path, payload=payload)

    def delete(
        self,
        path: str,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request_json("DELETE", path, payload=payload, query=query)


class MytSdkClient:
    def __init__(
        self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3
    ) -> None:
        self.http = BaseHTTPClient(
            device_ip, sdk_port, timeout_seconds=timeout_seconds, retries=retries
        )

    def _invalid(self, message: str) -> dict[str, Any]:
        return {"ok": False, "error": message}

    def _require_non_empty(self, value: str, field_name: str) -> dict[str, Any] | None:
        if not str(value).strip():
            return self._invalid(f"{field_name} is required")
        return None

    @staticmethod
    def _infer_content_type(file_path: str) -> str:
        guessed, _ = mimetypes.guess_type(file_path)
        return guessed or "application/octet-stream"

    @staticmethod
    def _normalize_payload_keys(
        payload: Mapping[str, Any], mapping: Mapping[str, str]
    ) -> dict[str, Any]:
        body = dict(payload)
        for src, dst in mapping.items():
            if src in body and dst not in body:
                body[dst] = body.pop(src)
        return body

    def get_device_info(self) -> dict[str, Any]:
        return self.http.get("/info/device")

    def get_api_version(self) -> dict[str, Any]:
        return self.http.get("/info")

    def start_android(self, name: str, **kwargs: Any) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/start", payload={"name": name, **kwargs})

    def stop_android(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/stop", payload={"name": name})

    def restart_android(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/restart", payload={"name": name})

    def rename_android(self, old_name: str, new_name: str) -> dict[str, Any]:
        old_name_invalid = self._require_non_empty(old_name, "name")
        if old_name_invalid is not None:
            return old_name_invalid
        new_name_invalid = self._require_non_empty(new_name, "newName")
        if new_name_invalid is not None:
            return new_name_invalid
        return self.http.post("/android/rename", payload={"name": old_name, "newName": new_name})

    def exec_android(self, name: str, command: str) -> dict[str, Any]:
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

    def get_cloud_status(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.get("/android", query={"name": name})

    def list_androids(self, **filters: Any) -> dict[str, Any]:
        query = {k: v for k, v in filters.items() if v is not None and str(v).strip()}
        return self.http.get("/android", query=query or None)

    def create_android(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._normalize_payload_keys(
            payload,
            {
                "image_url": "imageUrl",
                "model_id": "modelId",
                "model_name": "modelName",
                "local_model": "localModel",
                "model_static": "modelStatic",
                "index_num": "indexNum",
                "port_mappings": "portMappings",
            },
        )
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

    def reset_android(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._normalize_payload_keys(
            payload,
            {
                "image_url": "imageUrl",
                "model_id": "modelId",
                "model_name": "modelName",
                "local_model": "localModel",
                "model_static": "modelStatic",
                "index_num": "indexNum",
                "port_mappings": "portMappings",
            },
        )
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        return self.http.put("/android", payload=body)

    def delete_android(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/android", payload={"name": name})

    def switch_image(self, name: str, image_url: str, **kwargs: Any) -> dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(image_url, "imageUrl")
        if image_invalid is not None:
            return image_invalid
        return self.http.post(
            "/android/switchImage", payload={"name": name, "imageUrl": image_url, **kwargs}
        )

    def change_image_batch(self, container_names: list[str] | str, image: str) -> dict[str, Any]:
        if isinstance(container_names, str):
            container_list = [name.strip() for name in container_names.split(",") if name.strip()]
        else:
            container_list = [str(name).strip() for name in container_names if str(name).strip()]
        if not container_list:
            return self._invalid("containerNames is required")
        image_invalid = self._require_non_empty(image, "image")
        if image_invalid is not None:
            return image_invalid
        return self.http.post(
            "/android/change-image", payload={"containerNames": container_list, "image": image}
        )

    def switch_model(self, name: str, model_id: str = "", **kwargs: Any) -> dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        model_id_value = str(model_id or kwargs.get("modelId") or "").strip()
        local_model_value = str(kwargs.get("localModel") or kwargs.get("local_model") or "").strip()
        model_static_value = str(
            kwargs.get("modelStatic") or kwargs.get("model_static") or ""
        ).strip()
        if not model_id_value and not local_model_value and not model_static_value:
            return self._invalid("one of modelId/localModel/modelStatic is required")

        payload: dict[str, Any] = {"name": name, **kwargs}
        if model_id_value:
            payload["modelId"] = model_id_value
        if local_model_value and "localModel" not in payload:
            payload["localModel"] = local_model_value
        if model_static_value and "modelStatic" not in payload:
            payload["modelStatic"] = model_static_value
        payload.pop("local_model", None)
        payload.pop("model_static", None)
        return self.http.post("/android/switchModel", payload=payload)

    def copy_android(
        self, name: str, index_num: int | None = None, count: int | None = None
    ) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        query: dict[str, Any] = {"name": name}
        if index_num is not None:
            query["indexNum"] = int(index_num)
        if count is not None:
            query["count"] = int(count)
        return self.http.get("/android/copy", query=query)

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        invalid = self._require_non_empty(task_id, "taskId")
        if invalid is not None:
            return invalid
        return self.http.get("/android/task-status", query={"taskId": task_id})

    def pull_image(self, image_url: str) -> dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.post("/android/pullImage", payload={"imageUrl": image_url})

    def list_images(self) -> dict[str, Any]:
        return self.http.get("/android/image")

    def delete_image(self, image_url: str) -> dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/image", payload={"imageUrl": image_url})

    def list_image_tars(self, filename: str = "") -> dict[str, Any]:
        query = {"filename": filename.strip()} if filename.strip() else None
        return self.http.get("/android/imageTar", query=query)

    def delete_image_tar(self, filename: str) -> dict[str, Any]:
        invalid = self._require_non_empty(filename, "filename")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/imageTar", payload={"filename": filename})

    def export_image(self, image_url: str) -> dict[str, Any]:
        invalid = self._require_non_empty(image_url, "imageUrl")
        if invalid is not None:
            return invalid
        return self.http.post("/android/image/export", payload={"imageUrl": image_url})

    def download_image_tar(self, filename: str, save_path: str) -> dict[str, Any]:
        name_invalid = self._require_non_empty(filename, "filename")
        if name_invalid is not None:
            return name_invalid
        path_invalid = self._require_non_empty(save_path, "save_path")
        if path_invalid is not None:
            return path_invalid
        result = self.http.request_bytes(
            "GET", "/android/image/download", query={"filename": filename}
        )
        if not result.get("ok"):
            return result
        Path(save_path).write_bytes(bytes(result.get("data", b"")))
        return {"ok": True, "data": {"saved": save_path}}

    def import_image(self, image_tar_path: str) -> dict[str, Any]:
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

    def export_android(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.post("/android/export", payload={"name": name})

    def import_android(self, package_path: str) -> dict[str, Any]:
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

    def create_android_v2(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._normalize_payload_keys(
            payload,
            {
                "image_url": "imageUrl",
                "index_num": "indexNum",
                "sandbox_size": "sandboxSize",
            },
        )
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(str(body.get("imageUrl", "")), "imageUrl")
        if image_invalid is not None:
            return image_invalid
        dns_invalid = self._require_non_empty(str(body.get("dns", "")), "dns")
        if dns_invalid is not None:
            return dns_invalid
        return self.http.post("/androidV2", payload=body)

    def reset_android_v2(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.put("/androidV2", payload={"name": name})

    def change_image_batch_v2(self, container_names: list[str] | str, image: str) -> dict[str, Any]:
        if isinstance(container_names, str):
            container_list = [name.strip() for name in container_names.split(",") if name.strip()]
        else:
            container_list = [str(name).strip() for name in container_names if str(name).strip()]
        if not container_list:
            return self._invalid("containerNames is required")
        image_invalid = self._require_non_empty(image, "image")
        if image_invalid is not None:
            return image_invalid
        return self.http.post(
            "/androidV2/change-image", payload={"containerNames": container_list, "image": image}
        )

    def copy_android_v2(
        self, name: str, index_num: int | None = None, count: int | None = None
    ) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        query: dict[str, Any] = {"name": name}
        if index_num is not None:
            query["indexNum"] = int(index_num)
        if count is not None:
            query["count"] = int(count)
        return self.http.get("/androidV2/copy", query=query)

    def switch_image_v2(self, name: str, image_url: str, **kwargs: Any) -> dict[str, Any]:
        name_invalid = self._require_non_empty(name, "name")
        if name_invalid is not None:
            return name_invalid
        image_invalid = self._require_non_empty(image_url, "imageUrl")
        if image_invalid is not None:
            return image_invalid
        payload = self._normalize_payload_keys(
            kwargs,
            {
                "adb_port": "adbPort",
                "dobox_dpi": "doboxDpi",
            },
        )
        payload.update({"name": name, "imageUrl": image_url})
        return self.http.post("/androidV2/switchImage", payload=payload)

    def list_phone_models_online(self) -> dict[str, Any]:
        return self.http.get("/android/phoneModel")

    def list_country_codes(self) -> dict[str, Any]:
        return self.http.get("/android/countryCode")

    def set_android_macvlan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        name_invalid = self._require_non_empty(str(body.get("name", "")), "name")
        if name_invalid is not None:
            return name_invalid
        return self.http.post("/android/macvlan", payload=body)

    def list_macvlan(self) -> dict[str, Any]:
        return self.http.get("/macvlan")

    def create_macvlan(self, gw: str, subnet: str, private: bool | None = None) -> dict[str, Any]:
        gw_invalid = self._require_non_empty(gw, "gw")
        if gw_invalid is not None:
            return gw_invalid
        subnet_invalid = self._require_non_empty(subnet, "subnet")
        if subnet_invalid is not None:
            return subnet_invalid
        payload: dict[str, Any] = {"gw": gw, "subnet": subnet}
        if private is not None:
            payload["private"] = bool(private)
        return self.http.post("/macvlan", payload=payload)

    def update_macvlan(self, gw: str, subnet: str, private: bool | None = None) -> dict[str, Any]:
        gw_invalid = self._require_non_empty(gw, "gw")
        if gw_invalid is not None:
            return gw_invalid
        subnet_invalid = self._require_non_empty(subnet, "subnet")
        if subnet_invalid is not None:
            return subnet_invalid
        payload: dict[str, Any] = {"gw": gw, "subnet": subnet}
        if private is not None:
            payload["private"] = bool(private)
        return self.http.put("/macvlan", payload=payload)

    def delete_macvlan(self) -> dict[str, Any]:
        return self.http.delete("/macvlan")

    def prune_images(self) -> dict[str, Any]:
        return self.http.post("/android/pruneImages")

    def list_backups(self, name: str = "") -> dict[str, Any]:
        return self.http.get("/backup", query={"name": name} if str(name).strip() else None)

    def delete_backup(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/backup", payload={"name": name})

    def download_backup(self, backup_name: str, save_path: str) -> dict[str, Any]:
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

    def backup_model(self, model_name: str, suffix: str) -> dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "name")
        if name_invalid is not None:
            return name_invalid
        suffix_invalid = self._require_non_empty(suffix, "suffix")
        if suffix_invalid is not None:
            return suffix_invalid
        return self.http.post(
            "/android/backup/model", payload={"name": model_name, "suffix": suffix}
        )

    def list_model_backups(self) -> dict[str, Any]:
        return self.http.get("/android/backup/model")

    def delete_model_backup(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/android/backup/model", payload={"name": name})

    def export_model(self, model_name: str, export_path: str) -> dict[str, Any]:
        name_invalid = self._require_non_empty(model_name, "name")
        if name_invalid is not None:
            return name_invalid
        payload = {"name": model_name}
        if str(export_path).strip():
            payload["exportPath"] = export_path
        return self.http.post("/android/backup/modelExport", payload=payload)

    def import_model(self, import_path: str) -> dict[str, Any]:
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

    def list_models(self) -> dict[str, Any]:
        return self.http.get("/lm/local")

    def set_auth_password(self, new_password: str, confirm_password: str) -> dict[str, Any]:
        new_invalid = self._require_non_empty(new_password, "newPassword")
        if new_invalid is not None:
            return new_invalid
        confirm_invalid = self._require_non_empty(confirm_password, "confirmPassword")
        if confirm_invalid is not None:
            return confirm_invalid
        if new_password != confirm_password:
            return self._invalid("newPassword and confirmPassword must match")
        return self.http.post(
            "/auth/password",
            payload={"newPassword": new_password, "confirmPassword": confirm_password},
        )

    def close_auth(self) -> dict[str, Any]:
        return self.http.post("/auth/close")

    def change_ssh_password(self, username: str, password: str) -> dict[str, Any]:
        pass_invalid = self._require_non_empty(password, "password")
        if pass_invalid is not None:
            return pass_invalid
        payload: dict[str, Any] = {"password": password}
        if str(username).strip():
            payload["username"] = str(username).strip()
        return self.http.post("/link/ssh/changePwd", payload=payload)

    def switch_ssh_root(self, enabled: bool) -> dict[str, Any]:
        return self.http.post("/link/ssh/switchRoot", payload={"enable": bool(enabled)})

    def enable_ssh(self, enabled: bool) -> dict[str, Any]:
        return self.http.post("/link/ssh/enable", payload={"enable": bool(enabled)})

    def open_ssh_terminal(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/link/ssh", query=normalized or None)

    def get_ssh_ws_url(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {
            "ok": True,
            "data": {"url": f"ws://{self.http.host}:{self.http.port}/link/ssh{query_str}"},
        }

    def get_ssh_page_url(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {
            "ok": True,
            "data": {"url": f"http://{self.http.host}:{self.http.port}/ssh{query_str}"},
        }

    def open_container_exec(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/link/exec", query=normalized or None)

    def get_container_exec_page_url(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {
            "ok": True,
            "data": {"url": f"http://{self.http.host}:{self.http.port}/container/exec{query_str}"},
        }

    def get_container_exec_ws_url(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        query_str = self.http._query_string(normalized or None)
        return {
            "ok": True,
            "data": {"url": f"ws://{self.http.host}:{self.http.port}/link/exec{query_str}"},
        }

    def list_myt_bridge(self) -> dict[str, Any]:
        return self.http.get("/mytBridge")

    def create_myt_bridge(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytBridge", payload=dict(payload))

    def update_myt_bridge(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.put("/mytBridge", payload=dict(payload))

    def delete_myt_bridge(self, name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(name, "name")
        if invalid is not None:
            return invalid
        return self.http.delete("/mytBridge", payload={"name": name})

    def list_vpc_groups(self) -> dict[str, Any]:
        return self.http.get("/mytVpc/group")

    def create_vpc_group(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/group", payload=dict(payload))

    def update_vpc_group_alias(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/group/alias", payload=dict(payload))

    def delete_vpc_group(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.delete("/mytVpc/group", payload=dict(payload))

    def add_vpc_rule(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/addRule", payload=dict(payload))

    def add_vpc_rule_batch(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/addRule/batch", payload=dict(payload))

    def list_vpc_container_rules(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/mytVpc/containerRule", query=normalized or None)

    def delete_vpc_node(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.delete("/mytVpc", payload=dict(payload))

    def delete_vpc_rule(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/delRule", payload=dict(payload))

    def delete_vpc_rule_batch(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/delRule/batch", payload=dict(payload))

    def update_vpc_group(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/group/update", payload=dict(payload))

    def add_vpc_socks(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/mytVpc/socks", payload=dict(payload))

    def set_vpc_whitelist_dns(self, enabled: bool) -> dict[str, Any]:
        return self.http.post("/mytVpc/whiteListDns", payload={"enable": bool(enabled)})

    def get_container_domain_filter(self, container_id: str) -> dict[str, Any]:
        invalid = self._require_non_empty(container_id, "containerID")
        if invalid is not None:
            return invalid
        return self.http.get("/mytVpc/domainFilter", query={"containerID": container_id})

    def set_container_domain_filter(self, container_id: str, domains: list[str]) -> dict[str, Any]:
        invalid = self._require_non_empty(container_id, "containerID")
        if invalid is not None:
            return invalid
        return self.http.post(
            "/mytVpc/domainFilter", payload={"containerID": container_id, "domains": domains}
        )

    def clear_container_domain_filter(self, container_id: str) -> dict[str, Any]:
        invalid = self._require_non_empty(container_id, "containerID")
        if invalid is not None:
            return invalid
        return self.http.post("/mytVpc/domainFilter", payload={"containerID": container_id})

    def get_global_domain_filter(self) -> dict[str, Any]:
        return self.http.post("/mytVpc/domainFilter/global")

    def set_global_domain_filter(self, domains: list[str]) -> dict[str, Any]:
        return self.http.post("/mytVpc/domainFilter/global", payload={"domains": domains})

    def clear_global_domain_filter(self) -> dict[str, Any]:
        return self.http.post("/mytVpc/domainFilter/global", payload={"domains": []})

    def test_vpc_latency(self, **query: Any) -> dict[str, Any]:
        normalized = {k: v for k, v in query.items() if v is not None and str(v).strip()}
        return self.http.get("/mytVpc/test", query=normalized or None)

    def list_local_phone_models(self) -> dict[str, Any]:
        return self.http.get("/phoneModel")

    def delete_local_phone_model(self, model_name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.delete("/phoneModel", payload={"modelName": model_name})

    def export_local_phone_model(self, model_name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.post("/phoneModel/export", payload={"modelName": model_name})

    def import_phone_model(self, package_path: str) -> dict[str, Any]:
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

    def upgrade_server(self) -> dict[str, Any]:
        return self.http.get("/server/upgrade")

    def upload_server_upgrade(self, package_path: str) -> dict[str, Any]:
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

    def reset_server_device(self) -> dict[str, Any]:
        return self.http.post("/server/device/reset")

    def reboot_server_device(self) -> dict[str, Any]:
        return self.http.post("/server/device/reboot")

    def switch_docker_api(self, enabled: bool) -> dict[str, Any]:
        return self.http.post("/server/dockerApi", payload={"enable": bool(enabled)})

    def get_server_network(self) -> dict[str, Any]:
        return self.http.get("/server/network")

    def import_lm_package(self, package_path: str) -> dict[str, Any]:
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

    def get_lm_info(self) -> dict[str, Any]:
        return self.http.get("/lm/info")

    def delete_lm_local(self, model_name: str) -> dict[str, Any]:
        invalid = self._require_non_empty(model_name, "modelName")
        if invalid is not None:
            return invalid
        return self.http.delete("/lm/local", payload={"modelName": model_name})

    def get_lm_models(self) -> dict[str, Any]:
        return self.http.get("/lm/models")

    def chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/v1/chat/completions", payload=dict(payload))

    def embeddings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.http.post("/v1/embeddings", payload=dict(payload))

    def reset_lm_device(self) -> dict[str, Any]:
        return self.http.post("/lm/reset")

    def start_lm_server(self) -> dict[str, Any]:
        return self.http.post("/lm/server/start")

    def stop_lm_server(self) -> dict[str, Any]:
        return self.http.post("/lm/server/stop")

    def set_lm_work_mode(self, mode: str) -> dict[str, Any]:
        invalid = self._require_non_empty(mode, "mode")
        if invalid is not None:
            return invalid
        return self.http.post("/lm/workMode", payload={"mode": mode})


def make_sdk_client(device_ip: str, sdk_port: int = 8000) -> MytSdkClient:
    return MytSdkClient(device_ip=device_ip, sdk_port=sdk_port)


__all__ = ["MytRpc", "BaseHTTPClient", "MytSdkClient", "make_sdk_client"]
