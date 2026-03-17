"""android_api_actions — 云机级 Android HTTP API 原子动作（30001 端口）。

动作命名空间：android.*
底层客户端：AndroidApiClient
对应端口：30001（adk_api，非桥接模式：30000 + (index-1)*100 + 1）
"""

from __future__ import annotations

from typing import Any

from engine.action_registry import ActionMetadata
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.android_api_client import AndroidApiClient


def _api_client(params: dict[str, Any], context: ExecutionContext) -> AndroidApiClient | None:
    """从 params 或 context.runtime 构建 AndroidApiClient。"""
    device_ip = str(
        params.get("device_ip")
        or context.runtime.get("device_ip")
        or context.payload.get("device_ip")
        or ""
    ).strip()
    if not device_ip:
        return None
    api_port = int(params.get("api_port") or context.runtime.get("api_port") or 30001)
    timeout = float(params.get("timeout_seconds", 30.0))
    return AndroidApiClient(device_ip=device_ip, api_port=api_port, timeout_seconds=timeout)


def _ok(data: dict[str, Any]) -> ActionResult:
    return ActionResult(ok=True, code="ok", data=data)


def _err(code: str, message: str) -> ActionResult:
    return ActionResult(ok=False, code=code, message=message)


def _from_api(result: dict[str, Any]) -> ActionResult:
    ok = bool(result.get("ok", False))
    data = result.get("data") or {}
    if not isinstance(data, dict):
        data = {"result": data}
    msg = str(result.get("message") or result.get("error") or result.get("reason") or "")
    code = "ok" if ok else str(result.get("code") or "api_error")
    return ActionResult(ok=ok, code=code, message=msg, data=data)


# ------------------------------------------------------------------ #
# 剪贴板
# ------------------------------------------------------------------ #

GET_CLIPBOARD_METADATA = ActionMetadata(
    description="获取安卓设备的剪贴板文本。",
    params_schema={
        "type": "object",
        "properties": {
            "device_ip": {"type": "string", "description": "设备 IP，可选（由运行时推导）"},
            "api_port": {"type": "integer", "description": "API 端口，可选（默认 30001）"},
        },
    },
    returns_schema={
        "type": "object",
        "properties": {"result": {"type": "string", "description": "剪贴板中的文本内容"}},
    },
)


def android_get_clipboard(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_clipboard())


SET_CLIPBOARD_METADATA = ActionMetadata(
    description="设置安卓设备的剪贴板文本。",
    params_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要设置的文本内容"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
        "required": ["text"],
    },
)


def android_set_clipboard(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    text = str(params.get("text") or params.get("content") or "").strip()
    if not text:
        return _err("invalid_params", "text is required")
    return _from_api(client.set_clipboard(text))


# ------------------------------------------------------------------ #
# S5 代理
# ------------------------------------------------------------------ #

QUERY_PROXY_METADATA = ActionMetadata(
    description="查询安卓设备当前的 S5 代理状态。",
    params_schema={
        "type": "object",
        "properties": {"device_ip": {"type": "string", "description": "设备 IP"}},
    },
)


def android_query_proxy(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.query_s5_proxy())


SET_PROXY_METADATA = ActionMetadata(
    description="设置安卓设备的 S5 代理。",
    params_schema={
        "type": "object",
        "properties": {
            "ip": {"type": "string", "description": "代理服务器 IP"},
            "port": {"type": "integer", "description": "代理服务器端口"},
            "username": {"type": "string", "description": "用户名"},
            "password": {"type": "string", "description": "密码"},
            "proxy_type": {"type": "integer", "description": "代理类型（默认 2）"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
        "required": ["ip", "port"],
    },
)


def android_set_proxy(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    ip = str(params.get("s5IP") or params.get("ip") or "").strip()
    port = params.get("s5Port") or params.get("port")
    username = str(
        params.get("s5User") or params.get("username") or params.get("usr") or ""
    ).strip()
    password = str(
        params.get("s5Password") or params.get("password") or params.get("pwd") or ""
    ).strip()
    proxy_type = int(params.get("s5Type") or params.get("proxy_type") or params.get("type") or 2)
    if not ip or port is None:
        return _err("invalid_params", "ip and port are required")
    return _from_api(
        client.set_s5_proxy(
            ip=ip, port=int(port), username=username, password=password, proxy_type=proxy_type
        )
    )


def android_stop_proxy(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.stop_s5_proxy())


def android_set_proxy_filter(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    domains_raw = params.get("domains") or ""
    if isinstance(domains_raw, str):
        domains = [d.strip() for d in domains_raw.split(",") if d.strip()]
    elif isinstance(domains_raw, list):
        domains = [str(d).strip() for d in domains_raw if str(d).strip()]
    else:
        domains = []
    if not domains:
        return _err("invalid_params", "domains is required")
    return _from_api(client.set_s5_filter(domains))


# ------------------------------------------------------------------ #
# 截图
# ------------------------------------------------------------------ #

SCREENSHOT_METADATA = ActionMetadata(
    description="截取安卓设备屏幕。",
    params_schema={
        "type": "object",
        "properties": {
            "image_type": {"type": "integer", "description": "图片类型：0 为截图，1 为 XML"},
            "quality": {"type": "integer", "description": "图片质量 (1-100)"},
            "save_path": {"type": "string", "description": "服务端保存路径"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
    },
    returns_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "截图访问 URL"},
            "path": {"type": "string", "description": "截图保存路径"},
        },
    },
)


def android_screenshot(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    image_type = params.get("image_type")
    if image_type is None:
        image_type = params.get("type", 0)
    image_type = int(image_type)
    quality = int(params.get("quality", 80))
    save_path = str(params.get("save_path") or "").strip()
    return _from_api(client.screenshot(image_type=image_type, quality=quality, save_path=save_path))


# ------------------------------------------------------------------ #
# 文件操作
# ------------------------------------------------------------------ #


def android_download_file(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    remote = str(params.get("remote_path") or params.get("path") or "").strip()
    local = str(params.get("local_path") or params.get("save_path") or "").strip()
    if not remote or not local:
        return _err("invalid_params", "remote_path and local_path are required")
    return _from_api(client.download_file(remote, local))


def android_upload_file(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(
        client.upload_file(
            local_path=str(params.get("local_path") or params.get("file") or ""),
            remote_path=str(params.get("remote_path") or params.get("path") or ""),
            file_url=str(params.get("file_url") or params.get("url") or ""),
        )
    )


# ------------------------------------------------------------------ #
# 系统功能
# ------------------------------------------------------------------ #

SET_LANGUAGE_METADATA = ActionMetadata(
    description="设置安卓设备的语言和国家/地区。",
    params_schema={
        "type": "object",
        "properties": {
            "language": {"type": "string", "description": "语言代码 (如 zh)"},
            "country": {"type": "string", "description": "国家代码 (如 CN)"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
        "required": ["language", "country"],
    },
)


def android_set_language(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    language = str(params.get("language") or "").strip()
    country = str(params.get("country") or "").strip()
    if not language or not country:
        return _err("invalid_params", "language and country are required")
    return _from_api(client.set_language_country(language, country))


def android_refresh_location(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.refresh_location())


def android_get_google_adid(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_google_id())


RECEIVE_SMS_METADATA = ActionMetadata(
    description="模拟接收或读取短信内容。",
    params_schema={
        "type": "object",
        "properties": {
            "address": {"type": "string", "description": "发件人地址"},
            "body": {"type": "string", "description": "短信正文内容"},
            "scaddress": {"type": "string", "description": "服务中心地址"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
    },
)


def android_receive_sms(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(
        client.receive_sms(
            address=str(params.get("address") or ""),
            body=str(params.get("body") or params.get("mbody") or ""),
            scaddress=str(params.get("scaddress") or ""),
        )
    )


ADD_CONTACT_METADATA = ActionMetadata(
    description="向安卓设备添加联系人。",
    params_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "联系人姓名"},
            "number": {"type": "string", "description": "电话号码"},
            "contacts": {
                "type": "array",
                "items": {"type": "object"},
                "description": "批量联系人列表",
            },
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
    },
)


def android_add_contact(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    contacts = params.get("contacts") or params.get("data")
    if isinstance(contacts, list):
        return _from_api(client.add_contact(contacts=contacts))
    name = str(params.get("name") or "").strip()
    number = str(params.get("number") or "").strip()
    if not name or not number:
        return _err("invalid_params", "name and number are required")
    return _from_api(client.add_contact(name=name, number=number))


def android_get_container_info(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_container_info())


def android_get_version(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_version())


def android_set_virtual_camera_source(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(
        client.set_virtual_camera(
            path=str(params.get("path") or ""),
            type=str(params.get("type") or params.get("source_type") or ""),
            resolution=str(params.get("resolution") or ""),
        )
    )


def android_get_app_bootstart_list(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_boot_apps())


def android_set_app_bootstart(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    packages = params.get("packages")
    package = str(params.get("package") or "").strip()
    enabled = bool(params.get("enabled", True))
    return _from_api(client.set_boot_app(package=package, enabled=enabled, packages=packages))


def android_get_webrtc_player_url(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(
        client.get_webrtc_player_url(
            shost=str(params.get("shost") or ""),
            sport=params.get("sport") or "",
            q=str(params.get("q") or "1"),
            v=str(params.get("v") or "h264"),
            rtc_i=str(params.get("rtc_i") or ""),
            rtc_j=str(params.get("rtc_j") or ""),
            rtc_p=params.get("rtc_p") or "",
        )
    )


def android_set_key_block(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    if "value" in params:
        return _from_api(client.set_key_block(value=int(params.get("value", 1))))
    blocked = bool(params.get("blocked", params.get("enabled", True)))
    return _from_api(client.set_key_block(blocked))


def android_set_background_keepalive(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cmd = params.get("cmd")
    package = str(params.get("package") or "").strip()
    if cmd is not None:
        return _from_api(client.set_background_keepalive(package, cmd=int(cmd)))
    enabled = bool(params.get("enabled", True))
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.set_background_keepalive(package, enabled))


def android_query_background_keepalive(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.query_background_keepalive())


def android_add_background_keepalive(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.add_background_keepalive(package))


def android_remove_background_keepalive(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.remove_background_keepalive(package))


def android_update_background_keepalive(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.update_background_keepalive(package))


BACKUP_APP_METADATA = ActionMetadata(
    description="备份指定的安卓应用数据。",
    params_schema={
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "应用包名"},
            "save_to": {"type": "string", "description": "备份保存路径"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
        "required": ["package"],
    },
)


def android_backup_app(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or params.get("pkg") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    save_to = str(params.get("save_to") or params.get("saveto") or "")
    return _from_api(client.backup_app(package, save_to))


RESTORE_APP_METADATA = ActionMetadata(
    description="从备份路径恢复安卓应用数据。",
    params_schema={
        "type": "object",
        "properties": {
            "backup_path": {"type": "string", "description": "备份文件路径"},
            "device_ip": {"type": "string", "description": "设备 IP"},
        },
        "required": ["backup_path"],
    },
)


def android_restore_app(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    backup_path = str(params.get("backup_path") or params.get("backuppath") or "").strip()
    if not backup_path:
        return _err("invalid_params", "backup_path is required")
    return _from_api(client.restore_app(backup_path))


def android_upload_google_cert(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cert_path = str(params.get("cert_path") or "").strip()
    if not cert_path:
        return _err("invalid_params", "cert_path is required")
    return _from_api(client.upload_google_cert(cert_path))


# ------------------------------------------------------------------ #
# App 管理
# ------------------------------------------------------------------ #


def android_batch_install_apps(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    zip_path = str(params.get("zip_path") or params.get("file") or "").strip()
    if zip_path:
        return _from_api(client.install_apks(zip_path=zip_path))
    paths_raw = params.get("app_paths") or params.get("apks") or []
    if isinstance(paths_raw, str):
        paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
    else:
        paths = [str(p).strip() for p in paths_raw if str(p).strip()]
    if not paths:
        return _err("invalid_params", "app_paths is required")
    return _from_api(client.install_apks(apk_paths=paths))


def android_export_app_info(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.backup_app(package, str(params.get("save_to") or "")))


def android_import_app_info(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    data_path = str(
        params.get("data_path") or params.get("backuppath") or params.get("backup_path") or ""
    ).strip()
    if not data_path:
        return _err("invalid_params", "data_path is required")
    return _from_api(client.restore_app(data_path))


# ------------------------------------------------------------------ #
# 通话/位置/ADB/Google/模块/摄像头
# ------------------------------------------------------------------ #


def android_get_call_records(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    query = {
        key: value
        for key, value in params.items()
        if key
        not in {
            "device_ip",
            "api_port",
            "timeout_seconds",
        }
        and value is not None
    }
    return _from_api(client.get_call_records(**query))


def android_ip_geolocation(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    language = str(params.get("language") or params.get("launage") or "")
    return _from_api(client.ip_geolocation(ip=str(params.get("ip") or ""), language=language))


def android_query_adb(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cmd = params.get("cmd")
    if cmd is not None and int(cmd) != 1:
        return _from_api(client.switch_adb_permission(int(cmd) == 2))
    return _from_api(client.query_adb_permission())


def android_switch_adb(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cmd = params.get("cmd")
    if cmd is not None:
        return _from_api(client.switch_adb_permission(int(cmd) == 2))
    return _from_api(client.switch_adb_permission(bool(params.get("enabled", True))))


def android_get_google_id(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cmd = params.get("cmd")
    return _from_api(client.get_google_id(int(cmd)) if cmd is not None else client.get_google_id())


def android_set_google_id(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    adid = str(params.get("adid") or "").strip()
    cmd = params.get("cmd")
    if not adid and cmd is not None and int(cmd) == 2:
        return _from_api(client.generate_google_id())
    if not adid:
        return _err("invalid_params", "adid is required")
    return _from_api(client.set_google_id(adid, cmd=int(cmd) if cmd is not None else 1))


def android_install_magisk(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    cmd = str(params.get("cmd") or "").strip()
    module = str(params.get("module") or params.get("moduler") or params.get("adid") or "").strip()
    if cmd or module:
        if not cmd:
            cmd = "install"
        if not module:
            module = "magisk"
        return _from_api(client.module_manager(cmd, module))
    return _from_api(client.install_magisk())


def android_camera_hot_start(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(
        client.camera_hot_start(
            enabled=bool(params.get("enabled", True)),
            path=str(params.get("path") or ""),
        )
    )


def android_autoclick(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    action = str(params.get("action") or "").strip()
    if action:
        return _from_api(
            client.autoclick_action(
                action=action,
                x=params.get("x"),
                y=params.get("y"),
                finger_id=int(params.get("finger_id") or params.get("id") or 0),
                code=str(params.get("code") or ""),
            )
        )
    return _from_api(
        client.autoclick(
            enabled=bool(params.get("enabled", True)),
            interval_ms=params.get("interval_ms"),
        )
    )


def android_get_root_allowed_apps(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    return _from_api(client.get_root_allowed_apps())


def android_set_root_allowed_app(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")
    package = str(params.get("package") or "").strip()
    if not package:
        return _err("invalid_params", "package is required")
    return _from_api(client.set_root_allowed_app(package, bool(params.get("allowed", True))))
