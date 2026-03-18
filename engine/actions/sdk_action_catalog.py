from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext


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
    kwargs = {
        k: v
        for k, v in params.items()
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name"}
    }
    return [str(params.get("name", ""))], kwargs


def _args_rename_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("old_name", "")), str(params.get("new_name", ""))], {}


def _args_exec_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("name", "")), str(params.get("command", ""))], {}


def _args_switch_image(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {
        k: v
        for k, v in params.items()
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name", "image_url"}
    }
    image_url = str(params.get("image_url") or params.get("imageUrl") or "").strip()
    return [str(params.get("name", "")), image_url], kwargs


def _args_switch_model(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    kwargs = {
        k: v
        for k, v in params.items()
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries", "name", "model_id"}
    }
    return [str(params.get("name", "")), str(params.get("model_id", ""))], kwargs


def _args_pull_image(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    image_url = str(params.get("image_url") or params.get("imageUrl") or "").strip()
    return [image_url], {}


def _args_change_image_batch(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    container_names = (
        params.get("container_names") or params.get("containerNames") or params.get("names") or []
    )
    if isinstance(container_names, str):
        containers = [name.strip() for name in container_names.split(",") if name.strip()]
    else:
        containers = [str(name).strip() for name in container_names if str(name).strip()]
    image = str(params.get("image") or params.get("imageUrl") or "").strip()
    return [containers, image], {}


def _args_copy_android(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    name = str(params.get("name") or "")
    index_num = params.get("index_num") if "index_num" in params else params.get("indexNum")
    count = params.get("count")
    return [name, index_num, count], {}


def _args_task_status(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    task_id = str(params.get("task_id") or params.get("taskId") or "")
    return [task_id], {}


def _args_macvlan(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    gw = str(params.get("gw") or params.get("gateway") or "")
    subnet = str(params.get("subnet") or "")
    private = params.get("private")
    return [gw, subnet, private], {}


def _args_container_domain_filter(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    container_id = str(params.get("container_id") or params.get("containerID") or "")
    return [container_id], {}


def _args_container_domains(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    container_id = str(params.get("container_id") or params.get("containerID") or "")
    domains = params.get("domains") or []
    if isinstance(domains, str):
        domain_list = [d.strip() for d in domains.split(",") if d.strip()]
    else:
        domain_list = [str(d).strip() for d in domains if str(d).strip()]
    return [container_id, domain_list], {}


def _args_domains(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    domains = params.get("domains") or []
    if isinstance(domains, str):
        domain_list = [d.strip() for d in domains.split(",") if d.strip()]
    else:
        domain_list = [str(d).strip() for d in domains if str(d).strip()]
    return [domain_list], {}


def _args_image_url(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    image_url = str(params.get("image_url") or params.get("imageUrl") or "").strip()
    return [image_url], {}


def _args_download_backup(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    backup_name = str(params.get("backup_name") or params.get("name") or "").strip()
    return [backup_name, str(params.get("save_path", ""))], {}


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
    return [
        str(params.get("address", "")),
        str(params.get("mbody", "")),
        str(params.get("scaddress", "")),
    ], {}


def _args_download_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [str(params.get("remote_path", "")), str(params.get("local_path", ""))], {}


def _args_upload_file(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [
        str(params.get("local_path", "")),
        str(params.get("remote_path", "")),
        str(params.get("file_url", "")),
    ], {}


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
    return [
        int(params.get("image_type", 0)),
        int(params.get("quality", 80)),
        params.get("save_path"),
    ], {}


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
    return [
        str(params.get("key_code", "")),
        bool(params.get("blocked", params.get("enabled", True))),
    ], {}


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
        if k not in {"device_ip", "sdk_port", "timeout_seconds", "retries"}
    }
    return [], kwargs


def _args_get_webrtc_url(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    return [int(params.get("index", 1)), str(params.get("token", ""))], {}


ACTION_BUILDERS: dict[
    str, tuple[str, Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]] | None]
] = {
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
    "sdk.change_image_batch": ("change_image_batch", _args_change_image_batch),
    "sdk.switch_model": ("switch_model", _args_switch_model),
    "sdk.copy_android": ("copy_android", _args_copy_android),
    "sdk.get_task_status": ("get_task_status", _args_task_status),
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
    "sdk.create_android_v2": ("create_android_v2", _args_payload),
    "sdk.reset_android_v2": ("reset_android_v2", _args_name),
    "sdk.change_image_batch_v2": ("change_image_batch_v2", _args_change_image_batch),
    "sdk.copy_android_v2": ("copy_android_v2", _args_copy_android),
    "sdk.switch_image_v2": ("switch_image_v2", _args_switch_image),
    "sdk.list_phone_models_online": ("list_phone_models_online", None),
    "sdk.list_country_codes": ("list_country_codes", None),
    "sdk.set_android_macvlan": ("set_android_macvlan", _args_payload_and_name),
    "sdk.list_macvlan": ("list_macvlan", None),
    "sdk.create_macvlan": ("create_macvlan", _args_macvlan),
    "sdk.update_macvlan": ("update_macvlan", _args_macvlan),
    "sdk.delete_macvlan": ("delete_macvlan", None),
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
    "sdk.add_vpc_rule_batch": ("add_vpc_rule_batch", _args_payload),
    "sdk.list_vpc_container_rules": ("list_vpc_container_rules", _args_get_call_records),
    "sdk.delete_vpc_node": ("delete_vpc_node", _args_payload),
    "sdk.delete_vpc_rule": ("delete_vpc_rule", _args_payload),
    "sdk.delete_vpc_rule_batch": ("delete_vpc_rule_batch", _args_payload),
    "sdk.update_vpc_group": ("update_vpc_group", _args_payload),
    "sdk.add_vpc_socks": ("add_vpc_socks", _args_payload),
    "sdk.set_vpc_whitelist_dns": ("set_vpc_whitelist_dns", _args_enabled),
    "sdk.test_vpc_latency": ("test_vpc_latency", _args_get_call_records),
    "sdk.get_container_domain_filter": (
        "get_container_domain_filter",
        _args_container_domain_filter,
    ),
    "sdk.set_container_domain_filter": ("set_container_domain_filter", _args_container_domains),
    "sdk.clear_container_domain_filter": (
        "clear_container_domain_filter",
        _args_container_domain_filter,
    ),
    "sdk.get_global_domain_filter": ("get_global_domain_filter", None),
    "sdk.set_global_domain_filter": ("set_global_domain_filter", _args_domains),
    "sdk.clear_global_domain_filter": ("clear_global_domain_filter", None),
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
    "sdk.chat_completions": ("chat_completions", _args_payload),
    "sdk.embeddings": ("embeddings", _args_payload),
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
    "mytos.set_virtual_camera_source": (
        "set_virtual_camera_source",
        _args_set_virtual_camera_source,
    ),
    "mytos.get_app_bootstart_list": ("get_app_bootstart_list", None),
    "mytos.set_app_bootstart": ("set_app_bootstart", _args_set_app_bootstart),
    "mytos.set_language_country": ("set_language_country", _args_set_language_country),
    "mytos.get_webrtc_player_url": ("get_webrtc_player_url", _args_get_webrtc_url),
}


def build_mytos_android_bindings() -> dict[
    str, Callable[[dict[str, Any], ExecutionContext], ActionResult]
]:
    from engine.actions.android_api_actions import (
        android_add_background_keepalive,
        android_add_contact,
        android_autoclick,
        android_backup_app,
        android_batch_install_apps,
        android_camera_hot_start,
        android_download_file,
        android_export_app_info,
        android_get_app_bootstart_list,
        android_get_call_records,
        android_get_clipboard,
        android_get_container_info,
        android_get_google_id,
        android_get_root_allowed_apps,
        android_get_version,
        android_get_webrtc_player_url,
        android_import_app_info,
        android_install_magisk,
        android_ip_geolocation,
        android_query_adb,
        android_query_background_keepalive,
        android_query_proxy,
        android_receive_sms,
        android_refresh_location,
        android_remove_background_keepalive,
        android_restore_app,
        android_screenshot,
        android_set_app_bootstart,
        android_set_background_keepalive,
        android_set_clipboard,
        android_set_google_id,
        android_set_key_block,
        android_set_language,
        android_set_proxy,
        android_set_proxy_filter,
        android_set_root_allowed_app,
        android_set_virtual_camera_source,
        android_stop_proxy,
        android_switch_adb,
        android_update_background_keepalive,
        android_upload_file,
        android_upload_google_cert,
    )

    return {
        "mytos.query_s5_proxy": android_query_proxy,
        "mytos.set_s5_proxy": android_set_proxy,
        "mytos.stop_s5_proxy": android_stop_proxy,
        "mytos.set_s5_filter": android_set_proxy_filter,
        "mytos.get_clipboard": android_get_clipboard,
        "mytos.set_clipboard": android_set_clipboard,
        "mytos.upload_google_cert": android_upload_google_cert,
        "mytos.download_file": android_download_file,
        "mytos.upload_file": android_upload_file,
        "mytos.export_app_info": android_export_app_info,
        "mytos.import_app_info": android_import_app_info,
        "mytos.backup_app_info": android_backup_app,
        "mytos.restore_app_info": android_restore_app,
        "mytos.export_app_data": android_backup_app,
        "mytos.import_app_data": android_restore_app,
        "mytos.batch_install_apps": android_batch_install_apps,
        "mytos.screenshot": android_screenshot,
        "mytos.autoclick": android_autoclick,
        "mytos.touch_down": android_autoclick,
        "mytos.touch_up": android_autoclick,
        "mytos.touch_move": android_autoclick,
        "mytos.tap": android_autoclick,
        "mytos.keypress": android_autoclick,
        "mytos.camera_hot_start": android_camera_hot_start,
        "mytos.background_keepalive": android_set_background_keepalive,
        "mytos.query_background_keepalive": android_query_background_keepalive,
        "mytos.add_background_keepalive": android_add_background_keepalive,
        "mytos.remove_background_keepalive": android_remove_background_keepalive,
        "mytos.update_background_keepalive": android_update_background_keepalive,
        "mytos.disable_key": android_set_key_block,
        "mytos.add_contact": android_add_contact,
        "mytos.get_version": android_get_version,
        "mytos.get_container_info": android_get_container_info,
        "mytos.receive_sms": android_receive_sms,
        "mytos.get_call_records": android_get_call_records,
        "mytos.refresh_location": android_refresh_location,
        "mytos.ip_geolocation": android_ip_geolocation,
        "mytos.query_adb_permission": android_query_adb,
        "mytos.switch_adb_permission": android_switch_adb,
        "mytos.set_google_id": android_set_google_id,
        "mytos.get_google_id": android_get_google_id,
        "mytos.module_manager": android_install_magisk,
        "mytos.install_magisk": android_install_magisk,
        "mytos.get_root_allowed_apps": android_get_root_allowed_apps,
        "mytos.set_root_allowed_app": android_set_root_allowed_app,
        "mytos.set_virtual_camera_source": android_set_virtual_camera_source,
        "mytos.get_app_bootstart_list": android_get_app_bootstart_list,
        "mytos.set_app_bootstart": android_set_app_bootstart,
        "mytos.set_language_country": android_set_language,
        "mytos.get_webrtc_player_url": android_get_webrtc_player_url,
    }
