from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable

from engine.models.runtime import ActionResult, ExecutionContext


def query_any_text_contains(rpc: Any, texts: Iterable[str], timeout_ms: int = 900) -> bool:
    _ = timeout_ms
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


def detect_x_login_stage_with_rpc(rpc: Any) -> str:
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

    if query_any_text_contains(rpc, ["captcha", "arkose", "verify you are human", "prove you are human"]):
        return "captcha"
    if query_any_text_contains(rpc, ["verification code", "验证码", "two-factor", "2fa", "enter your code"]):
        return "two_factor"
    if query_any_text_contains(rpc, ["password", "密码", "forgot password", "忘记密码"]):
        return "password"
    if query_any_text_contains(
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
    if query_any_text_contains(rpc, ["home", "主页", "for you", "关注"]):
        return "home"
    return "unknown"


def parse_bounds(raw: str) -> dict[str, int]:
    try:
        first, second = str(raw or "").split("][", 1)
        left_top = first.lstrip("[")
        right_bottom = second.rstrip("]")
        left, top = [int(part) for part in left_top.split(",", 1)]
        right, bottom = [int(part) for part in right_bottom.split(",", 1)]
        return {"left": left, "top": top, "right": right, "bottom": bottom}
    except Exception:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}


def join_candidate_texts(node: ET.Element) -> tuple[str, str]:
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


def node_has_media(node: ET.Element) -> bool:
    for child in node.iter():
        class_name = str(child.attrib.get("class") or "")
        resource_id = str(child.attrib.get("resource-id") or "")
        desc = str(child.attrib.get("content-desc") or "").lower()
        if "ImageView" in class_name or "media" in resource_id.lower():
            return True
        if any(token in desc for token in ("image", "photo", "video", "gif", "照片", "图片", "画像", "動画")):
            return True
    return False


def candidate_from_element(node: ET.Element) -> dict[str, Any] | None:
    bound = parse_bounds(node.attrib.get("bounds", ""))
    text, desc = join_candidate_texts(node)
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
        "has_media": node_has_media(node),
    }


def candidate_identity(candidate: dict[str, Any]) -> str:
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


def extract_candidates_from_xml(
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

    def accept(candidate: dict[str, Any]) -> bool:
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
        candidate = candidate_from_element(node)
        if candidate is None or not accept(candidate):
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
        candidate = candidate_from_element(node)
        if candidate is None or not accept(candidate):
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


def dump_xml_for_candidates(rpc: Any, timeout_ms: int = 2500) -> str:
    xml_text = rpc.dump_node_xml_ex(False, timeout_ms)
    if xml_text:
        return xml_text
    fallback = rpc.dump_node_xml(False)
    return str(fallback or "")


def normalize_dm_text(raw: str) -> str:
    cleaned = str(raw or "").replace("\u200e", "").replace("\u200f", "").strip()
    if "：" in cleaned:
        cleaned = cleaned.split("：", 1)[1].strip()
    elif ": " in cleaned:
        cleaned = cleaned.split(": ", 1)[1].strip()
    elif ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1].strip()
    return cleaned.strip()


def extract_last_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", max_left: int = 540) -> dict[str, Any] | None:
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
        bound = parse_bounds(node.attrib.get("bounds", ""))
        if int(bound.get("left", 0)) >= max_left:
            continue
        message = normalize_dm_text(raw)
        if not message:
            continue
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        matches.append({"message": message, "raw": raw, "bound": bound, "center_y": center_y})

    if not matches:
        return None
    matches.sort(key=lambda item: item["center_y"], reverse=True)
    return matches[0]


def extract_last_outbound_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", min_left: int = 540) -> dict[str, Any] | None:
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
        bound = parse_bounds(node.attrib.get("bounds", ""))
        if int(bound.get("left", 0)) < min_left:
            continue
        message = normalize_dm_text(raw)
        if not message:
            continue
        center_y = int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)
        matches.append({"message": message, "raw": raw, "bound": bound, "center_y": center_y})

    if not matches:
        return None
    matches.sort(key=lambda item: item["center_y"], reverse=True)
    return matches[0]


def extract_follow_targets_from_xml(xml_text: str, package: str = "com.twitter.android", min_top: int = 350) -> list[dict[str, Any]]:
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
        bound = parse_bounds(node.attrib.get("bounds", ""))
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


def extract_unread_dm_targets_from_xml(xml_text: str, package: str = "com.twitter.android", min_top: int = 250) -> list[dict[str, Any]]:
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
        bound = parse_bounds(node.attrib.get("bounds", ""))
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


def extract_candidates_action(params: dict[str, Any], context: ExecutionContext, *, row_id_contains: str, connect_rpc: Any, close_rpc: Any) -> ActionResult:
    rpc, err = connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        candidates = extract_candidates_from_xml(
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
        close_rpc(rpc)


def collect_blogger_candidates(params: dict[str, Any], context: ExecutionContext, *, connect_rpc: Any, close_rpc: Any, time_module: Any) -> ActionResult:
    rpc, err = connect_rpc(params, context)
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
            xml_text = dump_xml_for_candidates(rpc, timeout_ms)
            extracted = extract_candidates_from_xml(
                xml_text=xml_text,
                package=package,
                row_id_contains=row_id_contains,
                min_top=min_top,
                max_bottom=max_bottom,
                max_candidates=max_candidates,
            )
            new_items = 0
            for candidate in extracted:
                identity = candidate_identity(candidate)
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

            rounds.append({"round": round_index + 1, "extracted_count": len(extracted), "new_count": new_items, "total_count": len(collected)})

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
                time_module.sleep(settle_ms / 1000.0)

        if not collected:
            return ActionResult(ok=False, code="no_candidates", message="no blogger candidates collected", data={"candidates": [], "count": 0, "rounds": rounds, "swipe_count": swipe_count})
        return ActionResult(ok=True, code="ok", data={"candidates": collected, "count": len(collected), "rounds": rounds, "swipe_count": swipe_count})
    finally:
        close_rpc(rpc)
