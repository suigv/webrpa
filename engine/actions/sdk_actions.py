from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import time
from typing import Any
import urllib.parse

import pyotp
import yaml

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


def _extract_cloud_status_payload(result: dict[str, Any]) -> tuple[str, Any]:
    payload = result.get("data")
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            return str(payload[0].get("status") or "").strip().lower(), payload
        return "", payload
    if isinstance(payload, dict):
        if "status" in payload:
            return str(payload.get("status") or "").strip().lower(), payload
        items = payload.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return str(items[0].get("status") or "").strip().lower(), payload
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return str(data[0].get("status") or "").strip().lower(), payload
    return "", payload


def wait_cloud_status(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _sdk_client(params, context)
    if client is None:
        return ActionResult(ok=False, code="invalid_params", message="device_ip is required")

    name = str(params.get("name", "")).strip()
    if not name:
        return ActionResult(ok=False, code="invalid_params", message="name is required")

    target_status = str(params.get("target_status", "running") or "running").strip().lower()
    timeout_ms = max(int(params.get("timeout_ms", 180000) or 180000), 0)
    interval_ms = max(int(params.get("interval_ms", 5000) or 5000), 100)
    deadline = time.monotonic() + timeout_ms / 1000.0

    last_result: dict[str, Any] = {}
    last_status = ""

    while True:
        if context.should_cancel is not None and bool(context.should_cancel()):
            return ActionResult(
                ok=False,
                code="cancelled",
                message="task cancelled by user",
                data={"name": name, "target_status": target_status, "last_status": last_status},
            )

        try:
            result = client.get_cloud_status(name)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}

        if isinstance(result, dict):
            last_result = result
            last_status, payload = _extract_cloud_status_payload(result)
            if bool(result.get("ok")) and last_status == target_status:
                return ActionResult(
                    ok=True,
                    code="ok",
                    message=f"cloud status reached {target_status}",
                    data={
                        "name": name,
                        "status": last_status,
                        "target_status": target_status,
                        "result": result,
                        "payload": payload,
                    },
                )

        if time.monotonic() >= deadline:
            return ActionResult(
                ok=False,
                code="cloud_status_timeout",
                message=f"cloud status did not reach {target_status} within {timeout_ms}ms",
                data={
                    "name": name,
                    "target_status": target_status,
                    "last_status": last_status,
                    "result": last_result,
                },
            )
        time.sleep(interval_ms / 1000.0)


def _args_name(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("name", ""))], {}


def _args_payload(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    payload = {
        k: v
        for k, v in params.items()
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries"}
    }
    return [payload], {}


def _args_payload_and_name(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    payload = {
        k: v
        for k, v in params.items()
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name"}
    }
    payload["name"] = str(params.get("name", ""))
    return [payload], {}


def _args_filename(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("filename", ""))], {}


def _args_package(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", ""))], {}


def _args_save_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("filename", "")), str(params.get("save_path", ""))], {}


def _args_path_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("file", ""))], {}


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


def _args_image_url(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("image_url", ""))], {}


def _args_download_backup(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("backup_name", "")), str(params.get("save_path", ""))], {}


def _args_backup_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_name", "")), str(params.get("suffix", ""))], {}


def _args_export_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_name", "")), str(params.get("export_path", ""))], {}


def _args_import_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("import_path", ""))], {}


def _args_set_auth_password(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("new_password", "")), str(params.get("confirm_password", ""))], {}


def _args_set_s5_proxy(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [dict(params.get("s5_config", {}))], {}


def _args_set_s5_filter(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [dict(params.get("filter_rules", {}))], {}


def _args_set_clipboard(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("content", ""))], {}


def _args_receive_sms(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("address", "")), str(params.get("mbody", "")), str(params.get("scaddress", ""))], {}


def _args_download_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("remote_path", "")), str(params.get("local_path", ""))], {}


def _args_upload_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("local_path", "")), str(params.get("remote_path", "")), str(params.get("file_url", ""))], {}


def _args_export_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", ""))], {}


def _args_import_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", "")), dict(params.get("data", {}))], {}


def _args_backup_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", "")), str(params.get("save_to", ""))], {}


def _args_restore_app_info(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("backup_path", ""))], {}


def _args_batch_install_apps(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    apps = params.get("app_paths", [])
    if not isinstance(apps, list):
        apps = []
    return [apps], {}


def _args_mytos_screenshot(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [int(params.get("image_type", 0)), int(params.get("quality", 80)), params.get("save_path")], {}


def _args_switch_adb_permission(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [bool(params.get("enabled", False))], {}


def _args_enabled(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [bool(params.get("enabled", False))], {}


def _args_ip_geolocation(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    ip = str(params.get("ip", ""))
    language = params.get("language")
    if language is None:
        return [ip], {}
    return [ip, str(language)], {}


def _args_upload_google_cert(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("cert_path", ""))], {}


def _args_export_app_data(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", ""))], {}


def _args_import_app_data(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", "")), str(params.get("data_path", ""))], {}


def _args_auto_click(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    interval = params.get("interval_ms")
    action = str(params.get("action", "")).strip()
    if action:
        kwargs: dict[str, Any] = {
            "action": action,
            "finger_id": int(params.get("finger_id", 0)),
        }
        if "x" in params:
            kwargs["x"] = int(params.get("x", 0))
        if "y" in params:
            kwargs["y"] = int(params.get("y", 0))
        if "code" in params:
            kwargs["code"] = str(params.get("code", ""))
        return [], kwargs
    return [bool(params.get("enabled", True)), int(interval) if interval is not None else None], {}


def _args_touch_action(action: str):
    def _builder(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "action": action,
            "finger_id": int(params.get("finger_id", 0)),
        }
        if action == "keypress":
            kwargs["code"] = str(params.get("code", ""))
        else:
            kwargs["x"] = int(params.get("x", 0))
            kwargs["y"] = int(params.get("y", 0))
        return [], kwargs

    return _builder


def _args_camera_hot_start(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [bool(params.get("enabled", True)), str(params.get("path", ""))], {}


def _args_background_keepalive(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    cmd = params.get("cmd")
    if cmd is None:
        return [bool(params.get("enabled", True))], {"package": str(params.get("package", ""))}
    return [], {"cmd": int(cmd), "package": str(params.get("package", ""))}


def _args_set_key_block(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("key_code", "")), bool(params.get("blocked", params.get("enabled", True)))], {}


def _args_add_contact(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    contacts = params.get("contacts", [])
    if isinstance(contacts, list):
        return [str(params.get("name", "")), str(params.get("number", "")), contacts], {}
    return [str(params.get("name", "")), str(params.get("number", "")), None], {}


def _args_set_root_allowed_app(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("package", "")), bool(params.get("allowed", True))], {}


def _args_set_virtual_camera_source(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [
        str(params.get("path", "")),
        str(params.get("type", "")),
        str(params.get("resolution", "")),
    ], {}


def _args_set_app_bootstart(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    packages = params.get("packages", [])
    if not isinstance(packages, list):
        packages = []
    if packages:
        return [str(params.get("package", "")), bool(params.get("enabled", True)), packages], {}
    return [str(params.get("package", "")), bool(params.get("enabled", True))], {}


def _args_set_language_country(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("language", "")), str(params.get("country", ""))], {}


def _args_set_google_id(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("adid", ""))], {}


def _args_module_manager(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("cmd", "")), str(params.get("module", ""))], {}


def _args_change_ssh_password(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("username", "")), str(params.get("password", ""))], {}


def _args_model_name(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("model_name", ""))], {}


def _args_mode(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("mode", ""))], {}


def _args_get_call_records(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {
        k: v
        for k, v in params.items()
        if k
        not in {
            "device_ip",
            "sdk_port",
            "timeout_seconds",
            "retries",
        }
    }
    return [], kwargs


def _args_get_webrtc_url(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [int(params.get("index", 1)), str(params.get("token", ""))], {}


ACTION_BUILDERS: dict[str, tuple[str, Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]] | None]] = {
    "sdk.get_device_info": ("get_device_info", None),
    "sdk.get_api_version": ("get_api_version", None),
    "sdk.list_androids": ("list_androids", _args_get_call_records),
    "sdk.create_android": ("create_android", _args_payload),
    "sdk.reset_android": ("reset_android", _args_payload_and_name),
    "sdk.delete_android": ("delete_android", _args_name),
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
    "sdk.delete_image": ("delete_image", _args_image_url),
    "sdk.list_image_tars": ("list_image_tars", _args_filename),
    "sdk.delete_image_tar": ("delete_image_tar", _args_filename),
    "sdk.export_image": ("export_image", _args_image_url),
    "sdk.download_image_tar": ("download_image_tar", _args_save_file),
    "sdk.import_image": ("import_image", _args_path_file),
    "sdk.export_android": ("export_android", _args_name),
    "sdk.import_android": ("import_android", _args_path_file),
    "sdk.list_phone_models_online": ("list_phone_models_online", None),
    "sdk.list_country_codes": ("list_country_codes", None),
    "sdk.set_android_macvlan": ("set_android_macvlan", _args_payload_and_name),
    "sdk.prune_images": ("prune_images", None),
    "sdk.list_backups": ("list_backups", _args_name),
    "sdk.delete_backup": ("delete_backup", _args_name),
    "sdk.download_backup": ("download_backup", _args_download_backup),
    "sdk.list_model_backups": ("list_model_backups", None),
    "sdk.backup_model": ("backup_model", _args_backup_model),
    "sdk.delete_model_backup": ("delete_model_backup", _args_name),
    "sdk.export_model": ("export_model", _args_export_model),
    "sdk.import_model": ("import_model", _args_import_model),
    "sdk.list_models": ("list_models", None),
    "sdk.set_auth_password": ("set_auth_password", _args_set_auth_password),
    "sdk.close_auth": ("close_auth", None),
    "sdk.change_ssh_password": ("change_ssh_password", _args_change_ssh_password),
    "sdk.switch_ssh_root": ("switch_ssh_root", _args_enabled),
    "sdk.enable_ssh": ("enable_ssh", _args_enabled),
    "sdk.open_ssh_terminal": ("open_ssh_terminal", _args_get_call_records),
    "sdk.get_ssh_ws_url": ("get_ssh_ws_url", _args_get_call_records),
    "sdk.get_ssh_page_url": ("get_ssh_page_url", _args_get_call_records),
    "sdk.open_container_exec": ("open_container_exec", _args_get_call_records),
    "sdk.get_container_exec_page_url": ("get_container_exec_page_url", _args_get_call_records),
    "sdk.get_container_exec_ws_url": ("get_container_exec_ws_url", _args_get_call_records),
    "sdk.list_myt_bridge": ("list_myt_bridge", None),
    "sdk.create_myt_bridge": ("create_myt_bridge", _args_payload),
    "sdk.update_myt_bridge": ("update_myt_bridge", _args_payload),
    "sdk.delete_myt_bridge": ("delete_myt_bridge", _args_name),
    "sdk.list_vpc_groups": ("list_vpc_groups", None),
    "sdk.create_vpc_group": ("create_vpc_group", _args_payload),
    "sdk.update_vpc_group_alias": ("update_vpc_group_alias", _args_payload),
    "sdk.delete_vpc_group": ("delete_vpc_group", _args_payload),
    "sdk.add_vpc_rule": ("add_vpc_rule", _args_payload),
    "sdk.list_vpc_container_rules": ("list_vpc_container_rules", _args_get_call_records),
    "sdk.delete_vpc_node": ("delete_vpc_node", _args_payload),
    "sdk.update_vpc_group": ("update_vpc_group", _args_payload),
    "sdk.add_vpc_socks": ("add_vpc_socks", _args_payload),
    "sdk.set_vpc_whitelist_dns": ("set_vpc_whitelist_dns", _args_enabled),
    "sdk.test_vpc_latency": ("test_vpc_latency", _args_get_call_records),
    "sdk.list_local_phone_models": ("list_local_phone_models", None),
    "sdk.delete_local_phone_model": ("delete_local_phone_model", _args_model_name),
    "sdk.export_local_phone_model": ("export_local_phone_model", _args_model_name),
    "sdk.import_phone_model": ("import_phone_model", _args_path_file),
    "sdk.upgrade_server": ("upgrade_server", None),
    "sdk.upload_server_upgrade": ("upload_server_upgrade", _args_path_file),
    "sdk.reset_server_device": ("reset_server_device", None),
    "sdk.reboot_server_device": ("reboot_server_device", None),
    "sdk.switch_docker_api": ("switch_docker_api", _args_enabled),
    "sdk.get_server_network": ("get_server_network", None),
    "sdk.import_lm_package": ("import_lm_package", _args_path_file),
    "sdk.get_lm_info": ("get_lm_info", None),
    "sdk.delete_lm_local": ("delete_lm_local", _args_model_name),
    "sdk.get_lm_models": ("get_lm_models", None),
    "sdk.reset_lm_device": ("reset_lm_device", None),
    "sdk.start_lm_server": ("start_lm_server", None),
    "sdk.stop_lm_server": ("stop_lm_server", None),
    "sdk.set_lm_work_mode": ("set_lm_work_mode", _args_mode),
    "mytos.query_s5_proxy": ("query_s5_proxy", None),
    "mytos.set_s5_proxy": ("set_s5_proxy", _args_set_s5_proxy),
    "mytos.stop_s5_proxy": ("stop_s5_proxy", None),
    "mytos.set_s5_filter": ("set_s5_filter", _args_set_s5_filter),
    "mytos.get_clipboard": ("get_clipboard", None),
    "mytos.set_clipboard": ("set_clipboard", _args_set_clipboard),
    "mytos.upload_google_cert": ("upload_google_cert", _args_upload_google_cert),
    "mytos.download_file": ("download_file", _args_download_file),
    "mytos.upload_file": ("upload_file", _args_upload_file),
    "mytos.export_app_info": ("export_app_info", _args_export_app_info),
    "mytos.import_app_info": ("import_app_info", _args_import_app_info),
    "mytos.backup_app_info": ("backup_app_info", _args_backup_app_info),
    "mytos.restore_app_info": ("restore_app_info", _args_restore_app_info),
    "mytos.export_app_data": ("export_app_data", _args_export_app_data),
    "mytos.import_app_data": ("import_app_data", _args_import_app_data),
    "mytos.batch_install_apps": ("batch_install_apps", _args_batch_install_apps),
    "mytos.screenshot": ("mytos_screenshot", _args_mytos_screenshot),
    "mytos.autoclick": ("auto_click", _args_auto_click),
    "mytos.touch_down": ("auto_click", _args_touch_action("down")),
    "mytos.touch_up": ("auto_click", _args_touch_action("up")),
    "mytos.touch_move": ("auto_click", _args_touch_action("move")),
    "mytos.tap": ("auto_click", _args_touch_action("click")),
    "mytos.keypress": ("auto_click", _args_touch_action("keypress")),
    "mytos.camera_hot_start": ("camera_hot_start", _args_camera_hot_start),
    "mytos.background_keepalive": ("set_background_keepalive", _args_background_keepalive),
    "mytos.query_background_keepalive": ("query_background_keepalive", None),
    "mytos.add_background_keepalive": ("add_background_keepalive", _args_package),
    "mytos.remove_background_keepalive": ("remove_background_keepalive", _args_package),
    "mytos.update_background_keepalive": ("update_background_keepalive", _args_package),
    "mytos.disable_key": ("set_key_block", _args_set_key_block),
    "mytos.add_contact": ("add_contact", _args_add_contact),
    "mytos.get_version": ("get_version", None),
    "mytos.get_container_info": ("get_container_info", None),
    "mytos.receive_sms": ("receive_sms", _args_receive_sms),
    "mytos.get_call_records": ("get_call_records", _args_get_call_records),
    "mytos.refresh_location": ("refresh_location", None),
    "mytos.ip_geolocation": ("ip_geolocation", _args_ip_geolocation),
    "mytos.query_adb_permission": ("query_adb_permission", None),
    "mytos.switch_adb_permission": ("switch_adb_permission", _args_switch_adb_permission),
    "mytos.set_google_id": ("set_google_id", _args_set_google_id),
    "mytos.get_google_id": ("get_google_id", None),
    "mytos.module_manager": ("module_manager", _args_module_manager),
    "mytos.install_magisk": ("install_magisk", None),
    "mytos.get_root_allowed_apps": ("get_root_allowed_apps", None),
    "mytos.set_root_allowed_app": ("set_root_allowed_app", _args_set_root_allowed_app),
    "mytos.set_virtual_camera_source": ("set_virtual_camera_source", _args_set_virtual_camera_source),
    "mytos.get_app_bootstart_list": ("get_app_bootstart_list", None),
    "mytos.set_app_bootstart": ("set_app_bootstart", _args_set_app_bootstart),
    "mytos.set_language_country": ("set_language_country", _args_set_language_country),
    "mytos.get_webrtc_player_url": ("get_webrtc_player_url", _args_get_webrtc_url),
}


def get_sdk_action_bindings() -> dict[str, Callable[[dict[str, Any], ExecutionContext], ActionResult]]:
    bindings = {
        action_name: _invoke(method_name, arg_builder)
        for action_name, (method_name, arg_builder) in ACTION_BUILDERS.items()
    }
    bindings["sdk.wait_cloud_status"] = wait_cloud_status
    return bindings


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


def _resolve_shared_key(params: dict[str, Any], context: ExecutionContext) -> str:
    key = str(params.get("key") or "").strip()
    if not key:
        return ""

    scope = str(params.get("scope") or "global").strip().lower()
    if scope in {"", "global"}:
        return key

    scope_value = str(params.get("scope_value") or "").strip()
    payload = context.payload if isinstance(context.payload, dict) else {}

    if not scope_value:
        if scope == "device":
            scope_value = str(payload.get("device_ip") or "").strip()
        elif scope == "task":
            scope_value = str(payload.get("_task_id") or "").strip()
        elif scope == "cloud":
            scope_value = str(payload.get("_cloud_target") or payload.get("name") or "").strip()

    if not scope_value:
        return key
    return f"{scope}:{scope_value}:{key}"


def save_shared(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = _resolve_shared_key(params, context)
    value = params.get("value")
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = _read_store()
    store[key] = value
    _write_store(store)
    return ActionResult(ok=True, code="ok", data={"key": key})


def load_shared_required(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = _resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = _read_store()
    if key not in store:
        return ActionResult(ok=False, code="missing_source_data", message=f"missing key: {key}")
    return ActionResult(ok=True, code="ok", data={"key": key, "value": store[key]})


def load_shared_optional(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = _resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = _read_store()
    exists = key in store
    default = params.get("default")
    return ActionResult(
        ok=True,
        code="ok",
        data={"key": key, "exists": exists, "value": store.get(key, default)},
    )


def append_shared_unique(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = _resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")

    item = params.get("item")
    if item is None:
        return ActionResult(ok=False, code="invalid_params", message="item is required")

    identity_field = str(params.get("identity_field") or "").strip()
    store = _read_store()
    items = store.get(key)
    if not isinstance(items, list):
        items = []

    added = True
    if identity_field and isinstance(item, dict):
        item_identity = item.get(identity_field)
        for existing in items:
            if isinstance(existing, dict) and existing.get(identity_field) == item_identity:
                added = False
                break
    else:
        if item in items:
            added = False

    if added:
        items.append(item)
        store[key] = items
        _write_store(store)

    return ActionResult(
        ok=True,
        code="ok",
        data={"key": key, "added": added, "size": len(items), "items": items},
    )


def increment_shared_counter(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = _resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")

    amount = int(params.get("amount", 1) or 1)
    start = int(params.get("start", 0) or 0)

    store = _read_store()
    current = store.get(key, start)
    try:
        current_value = int(current)
    except Exception:
        current_value = start
    current_value += amount
    store[key] = current_value
    _write_store(store)
    return ActionResult(ok=True, code="ok", data={"key": key, "value": current_value, "amount": amount})


def resolve_first_non_empty(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    values = params.get("values")
    if not isinstance(values, list):
        return ActionResult(ok=False, code="invalid_params", message="values must be a list")
    for index, value in enumerate(values):
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return ActionResult(ok=True, code="ok", data={"value": stripped, "index": index})
            continue
        if value:
            return ActionResult(ok=True, code="ok", data={"value": value, "index": index})
    return ActionResult(ok=False, code="value_missing", message="no non-empty value found")


def plan_follow_rounds(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    target_follow_count = max(int(params.get("target_follow_count", 5) or 5), 1)
    first_round_cap = max(int(params.get("first_round_cap", 3) or 3), 1)
    round_one = min(target_follow_count, first_round_cap)
    round_two = max(target_follow_count - round_one, 0)
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "target_follow_count": target_follow_count,
            "round_one": round_one,
            "round_two": round_two,
        },
    )


def generate_totp(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    secret = str(params.get("secret") or "").strip()
    if not secret:
        return ActionResult(ok=False, code="invalid_params", message="secret is required")
    try:
        token = pyotp.TOTP(secret).now()
    except Exception as exc:
        return ActionResult(ok=False, code="totp_failed", message=str(exc))
    return ActionResult(ok=True, code="ok", data={"token": token})


def _ui_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [Path(_resolve_root_path()) / "config" / "x_ui.yaml", repo_root / "config" / "x_ui.yaml"]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def _load_ui_config_document() -> dict[str, Any]:
    for path in _ui_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"x_ui config must be a mapping: {path}")
    raise FileNotFoundError("config/x_ui.yaml not found")


def _strategy_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [Path(_resolve_root_path()) / "config" / "strategies" / "nurture_keywords.yaml", repo_root / "config" / "strategies" / "nurture_keywords.yaml"]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def _load_strategy_document() -> dict[str, Any]:
    for path in _strategy_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"nurture strategy config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/nurture_keywords.yaml not found")


def _interaction_text_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(_resolve_root_path()) / "config" / "strategies" / "interaction_texts.yaml",
        repo_root / "config" / "strategies" / "interaction_texts.yaml",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def _load_interaction_text_document() -> dict[str, Any]:
    for path in _interaction_text_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"interaction text config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/interaction_texts.yaml not found")


def _daily_counter_path() -> Path:
    return Path(_resolve_root_path()) / "config" / "data" / "daily_counters.json"


def _read_daily_counters() -> dict[str, Any]:
    path = _daily_counter_path()
    if not path.exists():
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    if not isinstance(payload, dict):
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    return {"date": str(payload.get("date") or ""), "counts": counts}


def _write_daily_counters(payload: dict[str, Any]) -> None:
    path = _daily_counter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_daily_counter_key(params: dict[str, Any], context: ExecutionContext) -> str:
    base_key = str(params.get("key") or "nurture_daily_count").strip()
    resolved = _resolve_shared_key({"key": base_key, "scope": params.get("scope"), "scope_value": params.get("scope_value")}, context)
    return resolved or base_key


def check_daily_limit(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    limit = int(params.get("limit", 5) or 5)
    today = str(params.get("date") or datetime.now().strftime("%Y-%m-%d"))
    key = _resolve_daily_counter_key(params, context)
    store = _read_daily_counters()
    if store.get("date") != today:
        store = {"date": today, "counts": {}}
    counts = store.get("counts", {})
    try:
        current = int(counts.get(key, 0))
    except Exception:
        current = 0
    if current >= limit:
        return ActionResult(
            ok=False,
            code="daily_limit_reached",
            message=f"daily limit reached: {current}/{limit}",
            data={"key": key, "count": current, "limit": limit, "date": today},
        )
    return ActionResult(
        ok=True,
        code="ok",
        data={"key": key, "count": current, "limit": limit, "remaining": max(limit - current, 0), "date": today},
    )


def increment_daily_counter(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    amount = int(params.get("amount", 1) or 1)
    today = str(params.get("date") or datetime.now().strftime("%Y-%m-%d"))
    key = _resolve_daily_counter_key(params, context)
    store = _read_daily_counters()
    if store.get("date") != today:
        store = {"date": today, "counts": {}}
    counts = store.get("counts", {})
    try:
        current = int(counts.get(key, 0))
    except Exception:
        current = 0
    current += amount
    counts[key] = current
    store["date"] = today
    store["counts"] = counts
    _write_daily_counters(store)
    return ActionResult(ok=True, code="ok", data={"key": key, "count": current, "amount": amount, "date": today})


def pick_weighted_keyword(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "volc").strip()
    blogger = str(params.get("blogger") or "").strip()
    if override:
        return ActionResult(ok=True, code="ok", data={"keyword": override, "rendered_keyword": override, "source": "override", "ai_type": ai_type})

    try:
        document = _load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))

    strategies = document.get("strategies", {})
    strategy = strategies.get(ai_type) or strategies.get("volc")
    if not isinstance(strategy, dict):
        return ActionResult(ok=False, code="strategy_missing", message=f"strategy not found: {ai_type}")

    keywords = strategy.get("keywords", {})
    weights = strategy.get("weights", {})
    weighted_pool: list[tuple[str, str]] = []
    for bucket_name, entries in keywords.items():
        if not isinstance(entries, list):
            continue
        try:
            weight = int(weights.get(bucket_name, 1))
        except Exception:
            weight = 1
        for entry in entries:
            entry_text = str(entry).strip()
            if not entry_text:
                continue
            weighted_pool.extend([(bucket_name, entry_text)] * max(weight, 1))

    if not weighted_pool:
        return ActionResult(ok=False, code="empty_keyword_pool", message=f"keyword pool empty: {ai_type}")

    bucket, keyword = random.choice(weighted_pool)
    rendered = keyword.replace("{blogger}", blogger) if blogger else keyword
    return ActionResult(
        ok=True,
        code="ok",
        data={"ai_type": ai_type, "bucket": bucket, "keyword": keyword, "rendered_keyword": rendered},
    )


def is_text_blacklisted(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    text = str(params.get("text") or "").strip()
    ai_type = str(params.get("ai_type") or "volc").strip()
    try:
        document = _load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))
    strategies = document.get("strategies", {})
    strategy = strategies.get(ai_type) or strategies.get("volc")
    if not isinstance(strategy, dict):
        return ActionResult(ok=False, code="strategy_missing", message=f"strategy not found: {ai_type}")
    blacklist = strategy.get("blacklist", [])
    if not isinstance(blacklist, list):
        blacklist = []
    for word in blacklist:
        word_text = str(word).strip()
        if word_text and word_text in text:
            return ActionResult(ok=True, code="ok", data={"contains": True, "matched": word_text, "ai_type": ai_type})
    return ActionResult(ok=True, code="ok", data={"contains": False, "matched": "", "ai_type": ai_type})


def _select_interaction_template(section: str, ai_type: str) -> str:
    document = _load_interaction_text_document()
    section_doc = document.get(section)
    if not isinstance(section_doc, dict):
        raise ValueError(f"interaction text section missing: {section}")
    pool = section_doc.get(ai_type)
    if not isinstance(pool, list) or not pool:
        pool = section_doc.get("default")
    if not isinstance(pool, list) or not pool:
        raise ValueError(f"interaction text pool missing: {section}/{ai_type}")
    return str(random.choice(pool)).strip()


def generate_dm_reply(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    last_message = str(params.get("last_message") or "").strip()
    if override:
        return ActionResult(ok=True, code="ok", data={"reply_text": override, "source": "override", "ai_type": ai_type})
    try:
        template = _select_interaction_template("dm_reply", ai_type)
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    snippet = re.sub(r"\s+", " ", last_message).strip()
    if snippet:
        snippet = snippet[:24]
        reply_text = f"{template} {snippet}"
    else:
        reply_text = template
    return ActionResult(
        ok=True,
        code="ok",
        data={"reply_text": reply_text[:120], "source": "template", "ai_type": ai_type, "last_message": last_message},
    )


def generate_quote_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    source_text = str(params.get("source_text") or params.get("candidate_text") or params.get("target_post_url") or "").strip()
    if override:
        return ActionResult(ok=True, code="ok", data={"quote_text": override, "source": "override", "ai_type": ai_type})
    try:
        template = _select_interaction_template("quote_text", ai_type)
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    snippet = re.sub(r"\s+", " ", source_text).strip()
    if snippet:
        snippet = snippet[:28]
        quote_text = f"{template} {snippet}"
    else:
        quote_text = template
    return ActionResult(
        ok=True,
        code="ok",
        data={"quote_text": quote_text[:140], "source": "template", "ai_type": ai_type, "source_text": source_text},
    )


def save_blogger_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")
    wrapped_params = {
        "key": params.get("key", "blogger_pool"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "identity_field": params.get("identity_field", "username"),
        "item": candidate,
    }
    result = append_shared_unique(wrapped_params, context)
    if not result.ok:
        return result
    payload = dict(result.data)
    payload["candidate"] = candidate
    return ActionResult(ok=True, code="ok", data=payload)


def get_blogger_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    wrapped_params = {
        "key": params.get("key", "blogger_pool"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "default": [],
    }
    result = load_shared_optional(wrapped_params, context)
    if not result.ok:
        return result
    items = result.data.get("value", [])
    if not isinstance(items, list):
        items = []
    index = int(params.get("index", 0) or 0)
    if index < 0 or index >= len(items):
        return ActionResult(ok=False, code="blogger_candidate_missing", message="blogger candidate not found", data={"size": len(items), "index": index})
    return ActionResult(ok=True, code="ok", data={"candidate": items[index], "index": index, "size": len(items)})


def mark_processed(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    item = params.get("item")
    if item in (None, ""):
        return ActionResult(ok=False, code="invalid_params", message="item is required")
    wrapped_params = {
        "key": params.get("key", "processed_items"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "item": item,
    }
    result = append_shared_unique(wrapped_params, context)
    if not result.ok:
        return result
    payload = dict(result.data)
    payload["item"] = item
    return ActionResult(ok=True, code="ok", data=payload)


def check_processed(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    item = params.get("item")
    if item in (None, ""):
        return ActionResult(ok=False, code="invalid_params", message="item is required")
    wrapped_params = {
        "key": params.get("key", "processed_items"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "default": [],
    }
    result = load_shared_optional(wrapped_params, context)
    if not result.ok:
        return result
    items = result.data.get("value", [])
    if not isinstance(items, list):
        items = []
    contains = item in items
    return ActionResult(ok=True, code="ok", data={"contains": contains, "item": item, "size": len(items)})


def pick_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidates = params.get("candidates")
    if not isinstance(candidates, list):
        return ActionResult(ok=False, code="invalid_params", message="candidates must be a list")

    ai_type = str(params.get("ai_type") or "generic").strip()
    strategy = str(params.get("strategy") or "best").strip().lower()
    min_text_length = int(params.get("min_text_length", 4) or 4)

    try:
        document = _load_strategy_document()
        strategies = document.get("strategies", {})
        strategy_cfg = strategies.get(ai_type) or {}
        blacklist = strategy_cfg.get("blacklist", []) if isinstance(strategy_cfg, dict) else []
    except Exception:
        blacklist = []

    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = str(candidate.get("text") or "").strip()
        desc = str(candidate.get("desc") or "").strip()
        combined = " ".join(part for part in (text, desc) if part).strip()
        if len(combined) < min_text_length:
            continue
        if any(str(word).strip() and str(word).strip() in combined for word in blacklist):
            continue

        score = 1
        if candidate.get("has_media"):
            score += 3
        if ai_type == "volc" and candidate.get("has_media"):
            score += 10
        if ai_type == "part_time":
            lowered = combined.lower()
            if "円" in combined:
                score += 10
            if "paypay" in lowered:
                score += 8
            if "現金" in combined or "配布" in combined:
                score += 5
        score += min(len(combined), 120) // 20
        scored.append((score, candidate))

    if not scored:
        return ActionResult(ok=False, code="no_candidate_selected", message="no candidate selected")

    if strategy == "random":
        _, selected = random.choice(scored)
    elif strategy == "first":
        _, selected = scored[0]
    else:
        selected = max(scored, key=lambda item: item[0])[1]
    return ActionResult(ok=True, code="ok", data={"candidate": selected, "count": len(scored), "ai_type": ai_type, "strategy": strategy})


def choose_blogger_search_query(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "volc").strip()
    if override:
        return ActionResult(ok=True, code="ok", data={"query": override, "source": "override", "ai_type": ai_type})
    query = "#mytxx" if ai_type == "volc" else "#mytjz"
    return ActionResult(ok=True, code="ok", data={"query": query, "source": "default", "ai_type": ai_type})


def _derive_blogger_profile_data(
    candidate: dict[str, Any],
    fallback_username: str = "",
    fallback_display_name: str = "",
    fallback_profile: str = "",
) -> dict[str, Any] | None:
    text = str(candidate.get("text") or "").strip()
    desc = str(candidate.get("desc") or "").strip()
    combined = " ".join(part for part in (text, desc) if part).strip()

    username_matches = re.findall(r"@([A-Za-z0-9_]{1,32})", combined)
    username = username_matches[0] if username_matches else fallback_username

    display_name = fallback_display_name
    if not display_name:
        if username and text:
            marker = f"@{username}"
            if marker in text:
                prefix = text.split(marker, 1)[0].strip(" |-:")
                if prefix:
                    display_name = prefix
        if not display_name:
            display_name = username or (text[:32].strip() if text else "")

    profile = fallback_profile or combined

    if not username and not display_name:
        return None

    return {
        "username": username,
        "display_name": display_name,
        "profile": profile,
        "source_candidate": candidate,
    }


def derive_blogger_profile(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")

    profile = _derive_blogger_profile_data(
        candidate=candidate,
        fallback_username=str(params.get("fallback_username") or "").strip(),
        fallback_display_name=str(params.get("fallback_display_name") or "").strip(),
        fallback_profile=str(params.get("fallback_profile") or "").strip(),
    )
    if profile is None:
        return ActionResult(ok=False, code="blogger_profile_missing", message="unable to derive blogger identity")

    return ActionResult(
        ok=True,
        code="ok",
        data=profile,
    )


def save_blogger_candidates(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidates = params.get("candidates")
    if not isinstance(candidates, list):
        return ActionResult(ok=False, code="invalid_params", message="candidates must be a list")

    key = params.get("key", "blogger_pool")
    scope = params.get("scope", "device")
    scope_value = params.get("scope_value")
    identity_field = str(params.get("identity_field") or "username").strip() or "username"
    fallback_profile = str(params.get("fallback_profile") or "").strip()

    added_items: list[dict[str, Any]] = []
    skipped_count = 0
    last_result: ActionResult | None = None

    for candidate in candidates:
        if not isinstance(candidate, dict):
            skipped_count += 1
            continue
        derived = _derive_blogger_profile_data(candidate=candidate, fallback_profile=fallback_profile)
        if derived is None or not str(derived.get(identity_field) or "").strip():
            skipped_count += 1
            continue
        result = save_blogger_candidate(
            {
                "key": key,
                "scope": scope,
                "scope_value": scope_value,
                "identity_field": identity_field,
                "candidate": derived,
            },
            context,
        )
        if not result.ok:
            return result
        last_result = result
        if result.data.get("added") is True:
            added_items.append(derived)

    if last_result is None:
        return ActionResult(
            ok=False,
            code="blogger_candidates_missing",
            message="no blogger candidates saved",
            data={"added_count": 0, "skipped_count": skipped_count, "candidates": []},
        )

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": last_result.data.get("key"),
            "size": last_result.data.get("size", 0),
            "added_count": len(added_items),
            "skipped_count": skipped_count,
            "candidates": added_items,
        },
    )


def _resolve_ui_key(source: Any, key: str) -> Any:
    if not key:
        return None
    if isinstance(source, dict) and key in source:
        return source[key]

    current = source
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _resolve_localized_entry(entry: Any, locale: str) -> Any:
    if not isinstance(entry, dict):
        return entry
    if "type" in entry or "value" in entry or "template" in entry:
        return entry
    locale_key = str(locale or "").strip().lower()
    if locale_key and locale_key in entry:
        return entry[locale_key]
    if "default" in entry:
        return entry["default"]
    for value in entry.values():
        if isinstance(value, dict):
            return value
    return entry


def load_ui_value(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    try:
        document = _load_ui_config_document()
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    value = _resolve_ui_key(document, key)
    if value is None:
        if "default" in params:
            return ActionResult(ok=True, code="ok", data={"key": key, "value": params.get("default"), "exists": False})
        return ActionResult(ok=False, code="ui_value_missing", message=f"ui value not found: {key}")
    return ActionResult(ok=True, code="ok", data={"key": key, "value": value, "exists": True})


def load_ui_selector(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    locale = str(params.get("locale") or context.payload.get("locale") or "default").strip().lower()
    try:
        document = _load_ui_config_document()
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    selectors = document.get("selectors", {})
    entry = _resolve_localized_entry(_resolve_ui_key(selectors, key), locale)
    if not isinstance(entry, dict):
        return ActionResult(ok=False, code="ui_selector_missing", message=f"ui selector not found: {key}")

    selector_type = str(entry.get("type") or "").strip().lower()
    mode = str(entry.get("mode") or "equal").strip().lower()
    value = entry.get("value")
    if not selector_type or value in (None, ""):
        return ActionResult(ok=False, code="ui_selector_invalid", message=f"ui selector invalid: {key}")
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": key,
            "locale": locale,
            "type": selector_type,
            "mode": mode,
            "value": value,
        },
    )


def load_ui_scheme(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    try:
        document = _load_ui_config_document()
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    schemes = document.get("schemes", {})
    entry = _resolve_ui_key(schemes, key)
    if entry is None:
        return ActionResult(ok=False, code="ui_scheme_missing", message=f"ui scheme not found: {key}")

    template = entry.get("template") if isinstance(entry, dict) else entry
    if not isinstance(template, str) or not template.strip():
        return ActionResult(ok=False, code="ui_scheme_invalid", message=f"ui scheme invalid: {key}")

    args = params.get("args")
    kwargs = params.get("kwargs")
    url = template
    try:
        if isinstance(kwargs, dict) and kwargs:
            safe_kwargs = {name: urllib.parse.quote(str(value), safe="") for name, value in kwargs.items()}
            url = template.format(**safe_kwargs)
        elif isinstance(args, list) and args:
            safe_args = [urllib.parse.quote(str(value), safe="") for value in args]
            url = template.format(*safe_args)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_scheme_format_failed", message=str(exc))

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": key,
            "template": template,
            "url": url,
            "command": f'am start -a android.intent.action.VIEW -d "{url}" &',
        },
    )
