from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Iterable
import xml.etree.ElementTree as ET

from core.port_calc import calculate_ports
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc


def _is_rpc_enabled() -> bool:
    return os.getenv("MYT_ENABLE_RPC", "1") != "0"


def _resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    payload: Dict[str, Any] = dict(context.payload) if isinstance(context.payload, dict) else {}
    target_obj = payload.get("_target")
    target: Dict[str, Any] = target_obj if isinstance(target_obj, dict) else {}

    device_ip = str(params.get("device_ip") or payload.get("device_ip") or target.get("device_ip") or "").strip()
    if not device_ip:
        raise ValueError("device_ip is required")

    if "rpa_port" in params:
        return device_ip, int(params["rpa_port"])
    target_rpa_port = target.get("rpa_port")
    if target_rpa_port is not None:
        return device_ip, int(target_rpa_port)

    cloud_index = int(params.get("cloud_index") or payload.get("cloud_index") or target.get("cloud_id") or 1)
    device_index = int(params.get("device_index") or payload.get("device_index") or target.get("device_id") or 1)
    cloud_machines_per_device = int(
        params.get("cloud_machines_per_device") or payload.get("cloud_machines_per_device") or 1
    )
    _, rpa_port = calculate_ports(
        device_index=device_index,
        cloud_index=cloud_index,
        cloud_machines_per_device=cloud_machines_per_device,
    )
    return device_ip, rpa_port


def _connect_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    if not _is_rpc_enabled():
        return None, ActionResult(ok=False, code="rpc_disabled", message="MYT_ENABLE_RPC=0")
    try:
        device_ip, rpa_port = _resolve_connection_params(params, context)
    except ValueError as exc:
        return None, ActionResult(ok=False, code="invalid_params", message=str(exc))

    rpc = MytRpc()
    connected = rpc.init(device_ip, rpa_port, int(params.get("connect_timeout", 5)))
    if not connected:
        return None, ActionResult(ok=False, code="rpc_connect_failed", message=f"connect failed: {device_ip}:{rpa_port}")
    return rpc, None


def _query_any_text_contains(rpc: MytRpc, texts: Iterable[str], timeout_ms: int = 900) -> bool:
    selector = rpc.create_selector()
    if selector is None:
        return False
    try:
        for text in texts:
            value = str(text).strip()
            if not value:
                continue
            rpc.clear_selector(selector)
            rpc.addQuery_TextContainWith(selector, value)
            node = rpc.execQueryOne(selector)
            if node:
                return True
    finally:
        rpc.free_selector(selector)
    return False


def _detect_x_login_stage_with_rpc(rpc: MytRpc) -> str:
    try:
        focus, ok = rpc.exec_cmd("dumpsys window | grep mCurrentFocus")
        focus_text = str(focus or "").lower()
        if ok and focus_text:
            if any(key in focus_text for key in ("home", "mainactivity", "timeline")):
                return "home"
            if any(key in focus_text for key in ("loginchallenges", "verification", "two-factor")):
                return "two_factor"
    except Exception:
        pass

    if _query_any_text_contains(rpc, ["captcha", "arkose", "verify you are human", "prove you are human"]):
        return "captcha"
    if _query_any_text_contains(rpc, ["verification code", "验证码", "two-factor", "2fa", "enter your code"]):
        return "two_factor"
    if _query_any_text_contains(rpc, ["password", "密码", "forgot password", "忘记密码"]):
        return "password"
    if _query_any_text_contains(
        rpc,
        [
            "已有账号",
            "创建账号",
            "查看世界正在发生的新鲜事",
            "phone, email, or username",
            "用户名",
            "电子邮件",
        ],
    ):
        return "account"
    if _query_any_text_contains(rpc, ["home", "主页", "for you", "关注"]):
        return "home"
    return "unknown"


def _parse_bounds(raw: str) -> dict[str, int]:
    try:
        first, second = str(raw or "").split("][", 1)
        left_top = first.lstrip("[")
        right_bottom = second.rstrip("]")
        left, top = [int(part) for part in left_top.split(",", 1)]
        right, bottom = [int(part) for part in right_bottom.split(",", 1)]
        return {"left": left, "top": top, "right": right, "bottom": bottom}
    except Exception:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}


def _join_candidate_texts(node: ET.Element) -> tuple[str, str]:
    texts: list[str] = []
    descs: list[str] = []
    for child in node.iter():
        text = str(child.attrib.get("text") or "").strip()
        desc = str(child.attrib.get("content-desc") or "").strip()
        if text and text not in texts:
            texts.append(text)
        if desc and desc not in descs:
            descs.append(desc)
    return " | ".join(texts), " | ".join(descs)


def _node_has_media(node: ET.Element) -> bool:
    for child in node.iter():
        class_name = str(child.attrib.get("class") or "")
        resource_id = str(child.attrib.get("resource-id") or "")
        desc = str(child.attrib.get("content-desc") or "").lower()
        if "ImageView" in class_name or "media" in resource_id.lower():
            return True
        if any(token in desc for token in ("image", "photo", "video", "gif", "照片", "图片", "画像", "動画")):
            return True
    return False


def _candidate_from_element(node: ET.Element) -> dict[str, Any] | None:
    bound = _parse_bounds(node.attrib.get("bounds", ""))
    text, desc = _join_candidate_texts(node)
    combined = " ".join(part for part in (text, desc) if part).strip()
    if not combined:
        return None
    return {
        "text": text,
        "desc": desc,
        "resource_id": str(node.attrib.get("resource-id") or ""),
        "class_name": str(node.attrib.get("class") or ""),
        "package": str(node.attrib.get("package") or ""),
        "bound": bound,
        "height": max(0, int(bound.get("bottom", 0)) - int(bound.get("top", 0))),
        "has_media": _node_has_media(node),
    }


def _candidate_identity(candidate: dict[str, Any]) -> str:
    text = str(candidate.get("text") or "").strip()
    desc = str(candidate.get("desc") or "").strip()
    combined = " ".join(part for part in (text, desc) if part).strip()
    username_matches = re.findall(r"@([A-Za-z0-9_]{1,32})", combined)
    if username_matches:
        return f"user:{username_matches[0].lower()}"
    if combined:
        normalized = " ".join(combined.lower().split())
        return f"text:{normalized}"
    bound = candidate.get("bound", {})
    return f"bound:{int(bound.get('top', 0))}:{int(bound.get('bottom', 0))}"


def _extract_candidates_from_xml(
    xml_text: str,
    package: str = "",
    row_id_contains: str = ":id/row",
    min_top: int = 220,
    max_bottom: int = 2200,
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    def _accept(candidate: dict[str, Any]) -> bool:
        bound = candidate.get("bound", {})
        top = int(bound.get("top", 0))
        bottom = int(bound.get("bottom", 0))
        if package and candidate.get("package") not in {"", package}:
            return False
        if top < min_top or bottom > max_bottom:
            return False
        if len(str(candidate.get("text") or candidate.get("desc") or "").strip()) < 4:
            return False
        return True

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    for node in root.iter("node"):
        resource_id = str(node.attrib.get("resource-id") or "")
        if row_id_contains and row_id_contains not in resource_id:
            continue
        candidate = _candidate_from_element(node)
        if candidate is None or not _accept(candidate):
            continue
        bound = candidate["bound"]
        key = (str(candidate.get("text") or candidate.get("desc") or ""), int(bound.get("top", 0)), int(bound.get("bottom", 0)))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            return candidates

    if candidates:
        return candidates

    for node in root.iter("node"):
        candidate = _candidate_from_element(node)
        if candidate is None or not _accept(candidate):
            continue
        bound = candidate["bound"]
        key = (str(candidate.get("text") or candidate.get("desc") or ""), int(bound.get("top", 0)), int(bound.get("bottom", 0)))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            break
    return candidates


def _dump_xml_for_candidates(rpc: MytRpc, timeout_ms: int = 2500) -> str:
    xml_text = rpc.dump_node_xml_ex(False, timeout_ms)
    if xml_text:
        return xml_text
    fallback = rpc.dump_node_xml(False)
    return str(fallback or "")


def _normalize_dm_text(raw: str) -> str:
    cleaned = str(raw or "").replace("\u200e", "").replace("\u200f", "").strip()
    if "：" in cleaned:
        cleaned = cleaned.split("：", 1)[1].strip()
    elif ": " in cleaned:
        cleaned = cleaned.split(": ", 1)[1].strip()
    elif ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1].strip()
    return cleaned.strip()


def _extract_last_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", max_left: int = 540) -> dict[str, Any] | None:
    if not xml_text.strip():
        return None
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    matches: list[dict[str, Any]] = []
    for node in root.iter("node"):
        node_package = str(node.attrib.get("package") or "")
        if package and node_package not in {"", package}:
            continue
        desc = str(node.attrib.get("content-desc") or "").strip()
        text = str(node.attrib.get("text") or "").strip()
        raw = desc or text
        if not raw:
            continue
        if all(token not in raw for token in ("：", ": ")):
            continue
        bound = _parse_bounds(node.attrib.get("bounds", ""))
        if int(bound.get("left", 0)) >= max_left:
            continue
        message = _normalize_dm_text(raw)
        if not message:
            continue
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        matches.append(
            {
                "message": message,
                "raw": raw,
                "bound": bound,
                "center_y": center_y,
            }
        )

    if not matches:
        return None
    matches.sort(key=lambda item: item["center_y"], reverse=True)
    return matches[0]


def _extract_last_outbound_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", min_left: int = 540) -> dict[str, Any] | None:
    if not xml_text.strip():
        return None
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    matches: list[dict[str, Any]] = []
    for node in root.iter("node"):
        node_package = str(node.attrib.get("package") or "")
        if package and node_package not in {"", package}:
            continue
        desc = str(node.attrib.get("content-desc") or "").strip()
        text = str(node.attrib.get("text") or "").strip()
        raw = desc or text
        if not raw:
            continue
        bound = _parse_bounds(node.attrib.get("bounds", ""))
        if int(bound.get("left", 0)) < min_left:
            continue
        message = _normalize_dm_text(raw)
        if not message:
            continue
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        matches.append(
            {
                "message": message,
                "raw": raw,
                "bound": bound,
                "center_y": center_y,
            }
        )

    if not matches:
        return None
    matches.sort(key=lambda item: item["center_y"], reverse=True)
    return matches[0]


def _extract_follow_targets_from_xml(
    xml_text: str,
    package: str = "com.twitter.android",
    min_top: int = 350,
) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    button_texts = {"follow", "フォローする", "关注", "關注"}
    targets: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for node in root.iter("node"):
        node_package = str(node.attrib.get("package") or "")
        if package and node_package not in {"", package}:
            continue
        text = str(node.attrib.get("text") or "").strip()
        if text.lower() not in button_texts and text not in button_texts:
            continue
        bound = _parse_bounds(node.attrib.get("bounds", ""))
        top = int(bound.get("top", 0))
        if top < min_top:
            continue
        center_x = int((int(bound.get("left", 0)) + int(bound.get("right", 0))) / 2)
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        key = (center_x, center_y)
        if key in seen:
            continue
        seen.add(key)
        targets.append({"text": text, "bound": bound, "center": {"x": center_x, "y": center_y}})

    targets.sort(key=lambda item: int(item["bound"].get("top", 0)))
    return targets


def _extract_unread_dm_targets_from_xml(
    xml_text: str,
    package: str = "com.twitter.android",
    min_top: int = 250,
) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    markers = ("未読", "unread")
    targets: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for node in root.iter("node"):
        node_package = str(node.attrib.get("package") or "")
        if package and node_package not in {"", package}:
            continue
        text = str(node.attrib.get("text") or "").strip()
        desc = str(node.attrib.get("content-desc") or "").strip()
        combined = f"{text} {desc}".lower()
        if not any(marker in combined for marker in markers):
            continue
        bound = _parse_bounds(node.attrib.get("bounds", ""))
        top = int(bound.get("top", 0))
        if top < min_top:
            continue
        center_x = int((int(bound.get("left", 0)) + int(bound.get("right", 0))) / 2)
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        key = (center_x, center_y)
        if key in seen:
            continue
        seen.add(key)
        targets.append({"text": text, "desc": desc, "bound": bound, "center": {"x": center_x, "y": center_y}})

    targets.sort(key=lambda item: int(item["bound"].get("top", 0)))
    return targets


def _extract_candidates_action(params: Dict[str, Any], context: ExecutionContext, row_id_contains: str) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        candidates = _extract_candidates_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            row_id_contains=str(params.get("row_id_contains") or row_id_contains).strip(),
            min_top=int(params.get("min_top", 220) or 220),
            max_bottom=int(params.get("max_bottom", 2200) or 2200),
            max_candidates=int(params.get("max_candidates", 12) or 12),
        )
        if not candidates:
            return ActionResult(ok=False, code="no_candidates", message="no candidates extracted", data={"candidates": [], "count": 0})
        return ActionResult(ok=True, code="ok", data={"candidates": candidates, "count": len(candidates)})
    finally:
        if rpc is not None:
            rpc.close()


def detect_x_login_stage(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        stage = _detect_x_login_stage_with_rpc(rpc) if rpc is not None else "unknown"
        return ActionResult(ok=True, code="ok", data={"stage": stage})
    finally:
        if rpc is not None:
            rpc.close()


def wait_x_login_stage(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        timeout_ms = int(params.get("timeout_ms", 15000))
        interval_ms = int(params.get("interval_ms", 700))
        stages_raw = params.get("target_stages") or []
        if isinstance(stages_raw, str):
            target_stages = {x.strip() for x in stages_raw.split(",") if x.strip()}
        elif isinstance(stages_raw, list):
            target_stages = {str(x).strip() for x in stages_raw if str(x).strip()}
        else:
            target_stages = set()
        if not target_stages:
            return ActionResult(ok=False, code="invalid_params", message="target_stages is required")

        started = time.monotonic()
        attempt = 0
        last_stage = "unknown"

        while (time.monotonic() - started) * 1000 <= timeout_ms:
            attempt += 1
            last_stage = _detect_x_login_stage_with_rpc(rpc) if rpc is not None else "unknown"
            if last_stage in target_stages:
                elapsed = int((time.monotonic() - started) * 1000)
                return ActionResult(
                    ok=True,
                    code="ok",
                    data={"stage": last_stage, "attempt": attempt, "elapsed_ms": elapsed, "target_stages": sorted(target_stages)},
                )
            time.sleep(max(0.05, interval_ms / 1000.0))

        elapsed = int((time.monotonic() - started) * 1000)
        return ActionResult(
            ok=False,
            code="stage_timeout",
            message=f"wait stage timeout, last stage: {last_stage}",
            data={"stage": last_stage, "attempt": attempt, "elapsed_ms": elapsed, "target_stages": sorted(target_stages)},
        )
    finally:
        if rpc is not None:
            rpc.close()


def extract_timeline_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _extract_candidates_action(params, context, row_id_contains=":id/row")


def extract_search_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _extract_candidates_action(params, context, row_id_contains=":id/row")


def collect_blogger_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        max_rounds = max(int(params.get("max_rounds", 3) or 3), 1)
        max_candidates = max(int(params.get("max_candidates", 10) or 10), 1)
        timeout_ms = int(params.get("timeout_ms", 2500) or 2500)
        settle_ms = max(int(params.get("settle_ms", 900) or 900), 0)
        swipe_duration_ms = max(int(params.get("swipe_duration_ms", 350) or 350), 0)
        package = str(params.get("package") or "com.twitter.android").strip()
        row_id_contains = str(params.get("row_id_contains") or ":id/row").strip()
        min_top = int(params.get("min_top", 220) or 220)
        max_bottom = int(params.get("max_bottom", 2200) or 2200)
        stop_when_stalled = bool(params.get("stop_when_stalled", True))

        swipe_x0 = int(params.get("swipe_x0", 540) or 540)
        swipe_y0 = int(params.get("swipe_y0", 1750) or 1750)
        swipe_x1 = int(params.get("swipe_x1", 540) or 540)
        swipe_y1 = int(params.get("swipe_y1", 620) or 620)

        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        rounds: list[dict[str, Any]] = []
        swipe_count = 0

        for round_index in range(max_rounds):
            xml_text = _dump_xml_for_candidates(rpc, timeout_ms)
            extracted = _extract_candidates_from_xml(
                xml_text=xml_text,
                package=package,
                row_id_contains=row_id_contains,
                min_top=min_top,
                max_bottom=max_bottom,
                max_candidates=max_candidates,
            )
            new_items = 0
            for candidate in extracted:
                identity = _candidate_identity(candidate)
                if identity in seen:
                    continue
                seen.add(identity)
                candidate_copy = dict(candidate)
                candidate_copy["identity"] = identity
                candidate_copy["round"] = round_index + 1
                collected.append(candidate_copy)
                new_items += 1
                if len(collected) >= max_candidates:
                    break

            rounds.append(
                {
                    "round": round_index + 1,
                    "extracted_count": len(extracted),
                    "new_count": new_items,
                    "total_count": len(collected),
                }
            )

            if len(collected) >= max_candidates:
                break
            if stop_when_stalled and round_index > 0 and new_items == 0:
                break
            if round_index >= max_rounds - 1:
                break

            swipe = getattr(rpc, "swipe", None)
            if not callable(swipe):
                break
            if not swipe(0, swipe_x0, swipe_y0, swipe_x1, swipe_y1, swipe_duration_ms):
                break
            swipe_count += 1
            if settle_ms:
                time.sleep(settle_ms / 1000.0)

        if not collected:
            return ActionResult(
                ok=False,
                code="no_candidates",
                message="no blogger candidates collected",
                data={"candidates": [], "count": 0, "rounds": rounds, "swipe_count": swipe_count},
            )
        return ActionResult(
            ok=True,
            code="ok",
            data={"candidates": collected, "count": len(collected), "rounds": rounds, "swipe_count": swipe_count},
        )
    finally:
        if rpc is not None:
            rpc.close()


def open_candidate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        center = candidate.get("center")
        if isinstance(center, dict) and "x" in center and "y" in center:
            x = int(center.get("x", 0))
            y = int(center.get("y", 0))
        else:
            bound = candidate.get("bound", {})
            x = int((int(bound.get("left", 0)) + int(bound.get("right", 0))) / 2)
            y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        touch_click = getattr(rpc, "touchClick", None)
        if not callable(touch_click):
            return ActionResult(ok=False, code="open_candidate_failed", message="touchClick not available", data={"candidate": candidate})
        ok = touch_click(0, x, y)
        if not ok:
            return ActionResult(ok=False, code="open_candidate_failed", message="touchClick failed", data={"candidate": candidate, "x": x, "y": y})
        return ActionResult(ok=True, code="ok", data={"candidate": candidate, "x": x, "y": y})
    finally:
        if rpc is not None:
            rpc.close()


def extract_dm_last_message(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        message = _extract_last_dm_message_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            max_left=int(params.get("max_left", 540) or 540),
        )
        if message is None:
            return ActionResult(ok=False, code="dm_message_missing", message="no dm message extracted")
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        if rpc is not None:
            rpc.close()


def extract_dm_last_outbound_message(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        message = _extract_last_outbound_dm_message_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            min_left=int(params.get("min_left", 540) or 540),
        )
        if message is None:
            return ActionResult(ok=False, code="dm_outbound_message_missing", message="no outbound dm message extracted")
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        if rpc is not None:
            rpc.close()


def extract_follow_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        targets = _extract_follow_targets_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            min_top=int(params.get("min_top", 350) or 350),
        )
        if not targets:
            return ActionResult(ok=False, code="follow_targets_missing", message="no follow targets extracted", data={"targets": [], "count": 0})
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        if rpc is not None:
            rpc.close()


def follow_visible_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        targets = _extract_follow_targets_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            min_top=int(params.get("min_top", 350) or 350),
        )
        max_clicks = max(int(params.get("max_clicks", 3) or 3), 1)
        delay_ms = max(int(params.get("delay_ms", 1200) or 1200), 0)

        clicked_targets: list[dict[str, Any]] = []
        for target in targets[:max_clicks]:
            center = target.get("center", {})
            x = int(center.get("x", 0))
            y = int(center.get("y", 0))
            if not rpc.touchClick(0, x, y):
                continue
            clicked_targets.append(target)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)

        if not clicked_targets:
            return ActionResult(ok=False, code="follow_click_failed", message="no visible follow targets clicked", data={"targets": targets, "count": len(targets), "clicked_count": 0})
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets), "clicked_targets": clicked_targets, "clicked_count": len(clicked_targets)})
    finally:
        if rpc is not None:
            rpc.close()


def extract_unread_dm_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        targets = _extract_unread_dm_targets_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            min_top=int(params.get("min_top", 250) or 250),
        )
        if not targets:
            return ActionResult(ok=False, code="unread_dm_missing", message="no unread dm targets extracted", data={"targets": [], "count": 0})
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        if rpc is not None:
            rpc.close()


def open_first_unread_dm(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        targets = _extract_unread_dm_targets_from_xml(
            xml_text=xml_text,
            package=str(params.get("package") or "com.twitter.android").strip(),
            min_top=int(params.get("min_top", 250) or 250),
        )
        if not targets:
            return ActionResult(ok=False, code="unread_dm_missing", message="no unread dm targets extracted", data={"targets": [], "count": 0})
        first = targets[0]
        center = first.get("center", {})
        x = int(center.get("x", 0))
        y = int(center.get("y", 0))
        touch_click = getattr(rpc, "touchClick", None)
        if touch_click is None:
            return ActionResult(ok=False, code="open_unread_dm_failed", message="touchClick not available", data={"target": first})
        if not touch_click(0, x, y):
            return ActionResult(ok=False, code="open_unread_dm_failed", message="failed to open unread dm", data={"target": first})
        return ActionResult(ok=True, code="ok", data={"target": first, "count": len(targets)})
    finally:
        if rpc is not None:
            rpc.close()
