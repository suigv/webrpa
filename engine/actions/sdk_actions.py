from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.myt_client import MytSdkClient
from core.data_store import _resolve_root_path


def _from_payload_or_params(params: dict[str, Any], context: ExecutionContext, key: str, default: Any = None) -> Any:
    payload = context.payload if isinstance(context.payload, dict) else {}
    if key in params:
        return params[key]
    if isinstance(payload, dict) and key in payload:
        return payload[key]
    return default


def _sdk_client(params: dict[str, Any], context: ExecutionContext) -> MytSdkClient | None:
    device_ip = _from_payload_or_params(params, context, "device_ip")
    if not device_ip:
        return None
    sdk_port = int(_from_payload_or_params(params, context, "sdk_port", 8000))
    timeout_seconds = float(_from_payload_or_params(params, context, "timeout_seconds", 30.0))
    retries = int(_from_payload_or_params(params, context, "retries", 3))
    return MytSdkClient(device_ip=str(device_ip), sdk_port=sdk_port, timeout_seconds=timeout_seconds, retries=retries)


def _invoke(method_name: str, arg_builder: Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]] | None = None):
    def _handler(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
        client = _sdk_client(params, context)
        if client is None:
            return ActionResult(ok=False, code="invalid_params", message="device_ip is required")
        method = getattr(client, method_name, None)
        if method is None:
            return ActionResult(ok=False, code="not_supported", message=f"method not found: {method_name}")
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        if arg_builder is not None:
            args, kwargs = arg_builder(params)
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            return ActionResult(ok=False, code="sdk_call_failed", message=str(exc), data={"method": method_name})
        if isinstance(result, dict):
            return ActionResult(
                ok=bool(result.get("ok", False)),
                code="ok" if result.get("ok", False) else "sdk_error",
                message=str(result.get("error", "")),
                data={"method": method_name, "result": result},
            )
        return ActionResult(ok=True, code="ok", data={"method": method_name, "result": result})

    return _handler


def _args_name(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("name", ""))], {}


def _args_start_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {k: v for k, v in params.items() if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name"}}
    return [str(params.get("name", ""))], kwargs


def _args_rename_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("old_name", "")), str(params.get("new_name", ""))], {}


def _args_exec_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("name", "")), str(params.get("command", ""))], {}


def _args_switch_image(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {k: v for k, v in params.items() if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name", "image_url"}}
    return [str(params.get("name", "")), str(params.get("image_url", ""))], kwargs


def _args_switch_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {k: v for k, v in params.items() if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name", "model_id"}}
    return [str(params.get("name", "")), str(params.get("model_id", ""))], kwargs


def _args_pull_image(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("image_url", ""))], {}


def _args_download_backup(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("backup_name", "")), str(params.get("save_path", ""))], {}


def _args_backup_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_name", "")), str(params.get("suffix", ""))], {}


def _args_export_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_name", "")), str(params.get("export_path", ""))], {}


def _args_import_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("import_path", ""))], {}


def _args_import_local_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_file", ""))], {}


def _args_set_auth_password(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("new_password", "")), str(params.get("confirm_password", ""))], {}


def _args_set_s5_proxy(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [dict(params.get("s5_config", {}))], {}


def _args_set_s5_filter(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [dict(params.get("filter_rules", {}))], {}


def _args_set_clipboard(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("content", ""))], {}


def _args_download_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("remote_path", "")), str(params.get("local_path", ""))], {}


def _args_upload_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("local_path", "")), str(params.get("remote_path", ""))], {}


def _args_export_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", ""))], {}


def _args_import_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", "")), dict(params.get("data", {}))], {}


def _args_batch_install_apps(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    apps = params.get("app_paths", [])
    if not isinstance(apps, list):
        apps = []
    return [apps], {}


def _args_switch_adb_permission(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [bool(params.get("enabled", False))], {}


def _args_ip_geolocation(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    ip = str(params.get("ip", ""))
    language = params.get("language")
    if language is None:
        return [ip], {}
    return [ip, str(language)], {}


ACTION_BUILDERS: dict[str, tuple[str, Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]] | None]] = {
    "sdk.get_device_info": ("get_device_info", None),
    "sdk.get_api_version": ("get_api_version", None),
    "sdk.start_android": ("start_android", _args_start_android),
    "sdk.stop_android": ("stop_android", _args_name),
    "sdk.restart_android": ("restart_android", _args_name),
    "sdk.rename_android": ("rename_android", _args_rename_android),
    "sdk.exec_android": ("exec_android", _args_exec_android),
    "sdk.get_cloud_status": ("get_cloud_status", _args_name),
    "sdk.switch_image": ("switch_image", _args_switch_image),
    "sdk.switch_model": ("switch_model", _args_switch_model),
    "sdk.pull_image": ("pull_image", _args_pull_image),
    "sdk.list_images": ("list_images", None),
    "sdk.prune_images": ("prune_images", None),
    "sdk.create_backup": ("create_backup", _args_name),
    "sdk.download_backup": ("download_backup", _args_download_backup),
    "sdk.backup_model": ("backup_model", _args_backup_model),
    "sdk.export_model": ("export_model", _args_export_model),
    "sdk.import_model": ("import_model", _args_import_model),
    "sdk.list_models": ("list_models", None),
    "sdk.export_local_model": ("export_local_model", _args_backup_model),
    "sdk.import_local_model": ("import_local_model", _args_import_local_model),
    "sdk.set_auth_password": ("set_auth_password", _args_set_auth_password),
    "sdk.close_auth": ("close_auth", None),
    "mytos.query_s5_proxy": ("query_s5_proxy", None),
    "mytos.set_s5_proxy": ("set_s5_proxy", _args_set_s5_proxy),
    "mytos.stop_s5_proxy": ("stop_s5_proxy", None),
    "mytos.set_s5_filter": ("set_s5_filter", _args_set_s5_filter),
    "mytos.get_clipboard": ("get_clipboard", None),
    "mytos.set_clipboard": ("set_clipboard", _args_set_clipboard),
    "mytos.download_file": ("download_file", _args_download_file),
    "mytos.upload_file": ("upload_file", _args_upload_file),
    "mytos.export_app_info": ("export_app_info", _args_export_app_info),
    "mytos.import_app_info": ("import_app_info", _args_import_app_info),
    "mytos.batch_install_apps": ("batch_install_apps", _args_batch_install_apps),
    "mytos.screenshot": ("mytos_screenshot", None),
    "mytos.get_version": ("get_version", None),
    "mytos.get_container_info": ("get_container_info", None),
    "mytos.receive_sms": ("receive_sms", None),
    "mytos.get_call_records": ("get_call_records", None),
    "mytos.refresh_location": ("refresh_location", None),
    "mytos.ip_geolocation": ("ip_geolocation", _args_ip_geolocation),
    "mytos.switch_adb_permission": ("switch_adb_permission", _args_switch_adb_permission),
    "mytos.get_google_id": ("get_google_id", None),
    "mytos.install_magisk": ("install_magisk", None),
}


def get_sdk_action_bindings() -> dict[str, Callable[[dict[str, Any], ExecutionContext], ActionResult]]:
    return {action_name: _invoke(method_name, arg_builder) for action_name, (method_name, arg_builder) in ACTION_BUILDERS.items()}


def _shared_path() -> Path:
    root = Path(_resolve_root_path())
    path = root / "config" / "data" / "migration_shared.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_store() -> dict[str, Any]:
    path = _shared_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_store(payload: dict[str, Any]) -> None:
    _shared_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_shared(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = str(params.get("key") or "").strip()
    value = params.get("value")
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = _read_store()
    store[key] = value
    _write_store(store)
    return ActionResult(ok=True, code="ok", data={"key": key})


def load_shared_required(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = _read_store()
    if key not in store:
        return ActionResult(ok=False, code="missing_source_data", message=f"missing key: {key}")
    return ActionResult(ok=True, code="ok", data={"key": key, "value": store[key]})
