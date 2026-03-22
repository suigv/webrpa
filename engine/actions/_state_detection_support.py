from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)


def _log_recoverable(message: str, *, exc: Exception | None = None, **details: object) -> None:
    parts = [f"{key}={value!r}" for key, value in details.items() if value is not None]
    if exc is not None:
        parts.append(f"exc={exc!r}")
    suffix = f" ({', '.join(parts)})" if parts else ""
    logger.debug("%s%s", message, suffix)


def _coerce_text_list(raw: Iterable[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [str(part).strip() for part in raw if str(part).strip()]


def _parse_xml_root(xml_text: str, *, log_message: str) -> ET.Element | None:
    if not xml_text.strip():
        return None
    try:
        return ET.fromstring(xml_text)
    except Exception as exc:
        _log_recoverable(log_message, exc=exc, xml_size=len(xml_text))
        return None


def _center_y_from_bound(bound: dict[str, int]) -> int:
    return int((int(bound.get("top", 0)) + int(bound.get("bottom", 0))) / 2)


def _node_raw_text(node: ET.Element) -> str:
    desc = str(node.attrib.get("content-desc") or "").strip()
    text = str(node.attrib.get("text") or "").strip()
    return desc or text


def _bound_center(bound: dict[str, int]) -> dict[str, int]:
    return {
        "x": int((int(bound.get("left", 0)) + int(bound.get("right", 0))) / 2),
        "y": _center_y_from_bound(bound),
    }


def _iter_eligible_nodes_with_bounds(
    root: ET.Element,
    *,
    package: str,
) -> Iterable[tuple[ET.Element, dict[str, int]]]:
    for node in root.iter("node"):
        node_package = str(node.attrib.get("package") or "")
        if package and node_package not in {"", package}:
            continue
        yield node, parse_bounds(node.attrib.get("bounds", ""))


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
            # 查 text 属性
            rpc.clear_selector(selector)
            rpc.addQuery_TextContainWith(selector, value)
            if rpc.execQueryOne(selector):
                return True
            # Some apps expose navigation labels via content-desc instead of text.
            rpc.clear_selector(selector)
            rpc.addQuery_DescContainWith(selector, value)
            if rpc.execQueryOne(selector):
                return True
    finally:
        rpc.free_selector(selector)
    return False


def build_xml_match_index(xml_text: str) -> dict[str, tuple[str, ...]] | None:
    raw = str(xml_text or "").strip()
    if not raw:
        return None

    visible_values: list[str] = []
    resource_ids: list[str] = []
    seen_visible: set[str] = set()
    seen_resource_ids: set[str] = set()

    def _collect(resource_id: str = "", visible_value: str = "") -> None:
        resource_id_norm = resource_id.strip().lower()
        if resource_id_norm and resource_id_norm not in seen_resource_ids:
            seen_resource_ids.add(resource_id_norm)
            resource_ids.append(resource_id_norm)

        visible_norm = visible_value.strip().lower()
        if visible_norm and visible_norm not in seen_visible:
            seen_visible.add(visible_norm)
            visible_values.append(visible_norm)

    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        _log_recoverable(
            "xml match index parse failed, falling back to attribute scan",
            exc=exc,
            xml_size=len(raw),
        )
        attr_pattern = re.compile(r'(resource-id|text|content-desc)="([^"]*)"')
        current_resource_id = ""
        for attr_name, attr_value in attr_pattern.findall(raw):
            if attr_name == "resource-id":
                current_resource_id = attr_value
                _collect(resource_id=attr_value)
            else:
                _collect(resource_id=current_resource_id, visible_value=attr_value)
        if not resource_ids and not visible_values:
            return None
        return {
            "resource_ids": tuple(resource_ids),
            "visible_values": tuple(visible_values),
        }

    for node in root.iter("node"):
        resource_id = str(node.attrib.get("resource-id") or "")
        _collect(resource_id=resource_id)

        for attr in ("text", "content-desc"):
            _collect(resource_id=resource_id, visible_value=str(node.attrib.get(attr) or ""))

    return {
        "resource_ids": tuple(resource_ids),
        "visible_values": tuple(visible_values),
    }


def xml_index_contains_resource_id(index: dict[str, tuple[str, ...]] | None, marker: str) -> bool:
    if not index:
        return False
    needle = str(marker or "").strip().lower()
    if not needle:
        return False
    return any(needle in resource_id for resource_id in index.get("resource_ids", ()))


def xml_index_contains_visible_text(index: dict[str, tuple[str, ...]] | None, marker: str) -> bool:
    if not index:
        return False
    needle = str(marker or "").strip().lower()
    if not needle:
        return False
    return any(needle in value for value in index.get("visible_values", ()))


def parse_bounds(raw: str) -> dict[str, int]:
    try:
        first, second = str(raw or "").split("][", 1)
        left_top = first.lstrip("[")
        right_bottom = second.rstrip("]")
        left, top = [int(part) for part in left_top.split(",", 1)]
        right, bottom = [int(part) for part in right_bottom.split(",", 1)]
        return {"left": left, "top": top, "right": right, "bottom": bottom}
    except Exception as exc:
        _log_recoverable("failed to parse bounds", exc=exc, raw=raw)
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
        if any(
            token in desc
            for token in ("image", "photo", "video", "gif", "照片", "图片", "画像", "動画")
        ):
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
    row_id_contains: str = "",
    min_top: int = 220,
    max_bottom: int = 2200,
    max_candidates: int = 12,
    fallback_resource_ids: Iterable[str] | None = None,
    fallback_desc_markers: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        _log_recoverable("candidate extraction XML parse failed", exc=exc, xml_size=len(xml_text))
        return []

    fallback_resource_id_set = {item for item in _coerce_text_list(fallback_resource_ids) if item}
    fallback_desc_marker_set = [
        item.lower() for item in _coerce_text_list(fallback_desc_markers) if item
    ]

    def accept(candidate: dict[str, Any]) -> bool:
        bound = candidate.get("bound", {})
        top = int(bound.get("top", 0))
        bottom = int(bound.get("bottom", 0))
        if package and candidate.get("package") not in {"", package}:
            return False
        if top < min_top or bottom > max_bottom:
            return False
        return len(str(candidate.get("text") or candidate.get("desc") or "").strip()) >= 4

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    for node in root.iter("node"):
        resource_id = str(node.attrib.get("resource-id") or "")
        class_name = str(node.attrib.get("class") or "")
        content_desc = str(node.attrib.get("content-desc") or "")

        fallback_resource_match = (
            bool(fallback_resource_id_set) and resource_id in fallback_resource_id_set
        )
        fallback_desc_match = False
        if fallback_desc_marker_set and "RecyclerView" in class_name:
            content_lower = content_desc.lower()
            fallback_desc_match = any(
                marker in content_lower for marker in fallback_desc_marker_set
            )

        is_match = (
            (row_id_contains and row_id_contains in resource_id)
            or fallback_resource_match
            or fallback_desc_match
        )

        if not is_match:
            continue

        candidate = candidate_from_element(node)
        if candidate is None or not accept(candidate):
            continue
        bound = candidate["bound"]
        key = (
            str(candidate.get("text") or candidate.get("desc") or ""),
            int(bound.get("top", 0)),
            int(bound.get("bottom", 0)),
        )
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
        key = (
            str(candidate.get("text") or candidate.get("desc") or ""),
            int(bound.get("top", 0)),
            int(bound.get("bottom", 0)),
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            break
    return candidates


def dump_xml_for_candidates(rpc: Any, timeout_ms: int = 2500) -> str:
    """获取 XML，增加完整性校验。如果 Ex 模式被截断，则尝试通过标准模式补救。"""
    # 1. 优先尝试带超时参数的 Ex 版本，防止挂起
    xml_text = rpc.dump_node_xml_ex(False, timeout_ms)

    # 2. 完整性检查：如果 XML 不为空但未闭合（不包含 </hierarchy>），说明被截断了
    if xml_text and "</hierarchy>" not in xml_text:
        _log_recoverable(
            "xml dump appears truncated, retrying standard dump",
            timeout_ms=timeout_ms,
            xml_size=len(str(xml_text)),
        )
        # 尝试使用标准模式补齐（虽然没有超时保护，但在 Ex 已预热的情况下通常能很快返回）
        full_xml = rpc.dump_node_xml(False)
        if full_xml and "</hierarchy>" in full_xml:
            return full_xml

    if xml_text:
        return xml_text

    _log_recoverable("extended xml dump empty, retrying standard dump", timeout_ms=timeout_ms)
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


def extract_last_dm_message_from_xml(
    xml_text: str,
    package: str = "",
    max_left: int = 540,
    separator_tokens: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    return _extract_last_dm_message(
        xml_text,
        package=package,
        separator_tokens=separator_tokens,
        log_message="inbound dm XML parse failed",
        accept_bound=lambda bound: int(bound.get("left", 0)) < max_left,
    )


def _extract_last_dm_message(
    xml_text: str,
    *,
    package: str,
    separator_tokens: Iterable[str] | None,
    log_message: str,
    accept_bound: Any,
) -> dict[str, Any] | None:
    root = _parse_xml_root(xml_text, log_message=log_message)
    if root is None:
        return None

    separator_tokens = _coerce_text_list(separator_tokens)
    if not separator_tokens:
        return None

    matches: list[dict[str, Any]] = []
    for node, bound in _iter_eligible_nodes_with_bounds(root, package=package):
        raw = _node_raw_text(node)
        if not raw:
            continue
        if all(token not in raw for token in separator_tokens):
            continue
        if not accept_bound(bound):
            continue
        message = normalize_dm_text(raw)
        if not message:
            continue
        center_y = _center_y_from_bound(bound)
        matches.append({"message": message, "raw": raw, "bound": bound, "center_y": center_y})

    if not matches:
        return None
    matches.sort(key=lambda item: item["center_y"], reverse=True)
    return matches[0]


def extract_last_outbound_dm_message_from_xml(
    xml_text: str,
    package: str = "",
    min_left: int = 540,
    separator_tokens: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    return _extract_last_dm_message(
        xml_text,
        package=package,
        separator_tokens=separator_tokens,
        log_message="outbound dm XML parse failed",
        accept_bound=lambda bound: int(bound.get("left", 0)) >= min_left,
    )


def extract_follow_targets_from_xml(
    xml_text: str,
    package: str = "",
    min_top: int = 350,
    button_texts: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    button_text_set = {text.lower() for text in _coerce_text_list(button_texts) if text}
    if not button_text_set:
        return []
    return _extract_centered_targets(
        xml_text,
        package=package,
        min_top=min_top,
        log_message="follow target XML parse failed",
        match_node=lambda node: (
            str(node.attrib.get("text") or "").strip().lower() in button_text_set
        ),
        build_target=lambda node, bound, center: {
            "text": str(node.attrib.get("text") or "").strip(),
            "bound": bound,
            "center": center,
        },
    )


def extract_unread_dm_targets_from_xml(
    xml_text: str,
    package: str = "",
    min_top: int = 250,
    markers: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    marker_set = [marker.lower() for marker in _coerce_text_list(markers) if marker]
    if not marker_set:
        return []
    return _extract_centered_targets(
        xml_text,
        package=package,
        min_top=min_top,
        log_message="unread dm XML parse failed",
        match_node=lambda node: any(
            marker
            in (
                f"{str(node.attrib.get('text') or '').strip()} "
                f"{str(node.attrib.get('content-desc') or '').strip()}"
            ).lower()
            for marker in marker_set
        ),
        build_target=lambda node, bound, center: {
            "text": str(node.attrib.get("text") or "").strip(),
            "desc": str(node.attrib.get("content-desc") or "").strip(),
            "bound": bound,
            "center": center,
        },
    )


def _extract_centered_targets(
    xml_text: str,
    *,
    package: str,
    min_top: int,
    log_message: str,
    match_node: Any,
    build_target: Any,
) -> list[dict[str, Any]]:
    root = _parse_xml_root(xml_text, log_message=log_message)
    if root is None:
        return []

    targets: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for node, bound in _iter_eligible_nodes_with_bounds(root, package=package):
        if not match_node(node):
            continue
        top = int(bound.get("top", 0))
        if top < min_top:
            continue
        center = _bound_center(bound)
        key = (center["x"], center["y"])
        if key in seen:
            continue
        seen.add(key)
        targets.append(build_target(node, bound, center))

    targets.sort(key=lambda item: int(item["bound"].get("top", 0)))
    return targets


def extract_candidates_action(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    row_id_contains: str,
    connect_rpc: Any,
    close_rpc: Any,
) -> ActionResult:
    rpc, err = connect_rpc(params, context)
    if err:
        return err
    try:
        xml_text = dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        candidates = extract_candidates_from_xml(
            xml_text=xml_text,
            package=str(
                params.get("package") or context.get_session_default("package") or ""
            ).strip(),
            row_id_contains=str(params.get("row_id_contains") or row_id_contains).strip(),
            min_top=int(params.get("min_top", 220) or 220),
            max_bottom=int(params.get("max_bottom", 2200) or 2200),
            max_candidates=int(params.get("max_candidates", 12) or 12),
            fallback_resource_ids=params.get("fallback_resource_ids"),
            fallback_desc_markers=params.get("fallback_desc_markers"),
        )
        if not candidates:
            return ActionResult(
                ok=False,
                code="no_candidates",
                message="no candidates extracted",
                data={"candidates": [], "count": 0},
            )
        return ActionResult(
            ok=True, code="ok", data={"candidates": candidates, "count": len(candidates)}
        )
    finally:
        close_rpc(rpc)


def collect_blogger_candidates(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    connect_rpc: Any,
    close_rpc: Any,
    time_module: Any,
) -> ActionResult:
    rpc, err = connect_rpc(params, context)
    if err:
        return err
    try:
        max_rounds = max(int(params.get("max_rounds", 3) or 3), 1)
        max_candidates = max(int(params.get("max_candidates", 10) or 10), 1)
        timeout_ms = int(params.get("timeout_ms", 2500) or 2500)
        settle_ms = max(int(params.get("settle_ms", 900) or 900), 0)
        swipe_duration_ms = max(int(params.get("swipe_duration_ms", 350) or 350), 0)
        package = str(params.get("package") or context.get_session_default("package") or "").strip()
        row_id_contains = str(params.get("row_id_contains") or "").strip()
        min_top = int(params.get("min_top", 220) or 220)
        max_bottom = int(params.get("max_bottom", 2200) or 2200)
        stop_when_stalled = bool(params.get("stop_when_stalled", True))

        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        rounds: list[dict[str, Any]] = []
        swipe_count = 0
        swipe_x0: int | None = None
        swipe_y0: int | None = None
        swipe_x1: int | None = None
        swipe_y1: int | None = None

        for round_index in range(max_rounds):
            xml_text = dump_xml_for_candidates(rpc, timeout_ms)
            if swipe_x0 is None:
                _sw: int = int(params.get("swipe_x0") or 0) or 0
                _sh_top: int = int(params.get("swipe_y0") or 0) or 0
                _sw2: int = int(params.get("swipe_x1") or 0) or 0
                _sh_bot: int = int(params.get("swipe_y1") or 0) or 0
                if not (_sw and _sh_top and _sw2 and _sh_bot):
                    _m = re.search(r'bounds="\[0,0\]\[(\d+),(\d+)\]"', xml_text)
                    if _m:
                        _w, _h = int(_m.group(1)), int(_m.group(2))
                        swipe_x0 = _sw or _w // 2
                        swipe_y0 = _sh_top or int(_h * 0.85)
                        swipe_x1 = _sw2 or _w // 2
                        swipe_y1 = _sh_bot or int(_h * 0.30)
                    else:
                        swipe_x0 = _sw or 540
                        swipe_y0 = _sh_top or 1750
                        swipe_x1 = _sw2 or 540
                        swipe_y1 = _sh_bot or 620
                else:
                    swipe_x0, swipe_y0, swipe_x1, swipe_y1 = _sw, _sh_top, _sw2, _sh_bot
            extracted = extract_candidates_from_xml(
                xml_text=xml_text,
                package=package,
                row_id_contains=row_id_contains,
                min_top=min_top,
                max_bottom=max_bottom,
                max_candidates=max_candidates,
                fallback_resource_ids=params.get("fallback_resource_ids"),
                fallback_desc_markers=params.get("fallback_desc_markers"),
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
                time_module.sleep(settle_ms / 1000.0)

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
            data={
                "candidates": collected,
                "count": len(collected),
                "rounds": rounds,
                "swipe_count": swipe_count,
            },
        )
    finally:
        close_rpc(rpc)


# ------------------------------------------------------------------ #
# XML 预处理
# ------------------------------------------------------------------ #


def preprocess_xml(xml: str, max_text_len: int = 0, max_desc_len: int = 0) -> str:
    """从原始 Android XML 中提取有效节点的关键属性，剥离噪音。

    max_text_len/max_desc_len 为 0 表示不截断，只做结构性过滤。
    具体阈值应从 app/state profile 配置中的 xml_filter 字段读取，不同 App 按需配置。
    """
    pkg_m = re.search(r'package="([^"]+)"', xml)
    app_pkg = pkg_m.group(1) if pkg_m else ""

    lines: list[str] = []
    for m in re.finditer(r"<node((?:[^>]|/>)*?)(?:/>|>)", xml):
        attrs_str = m.group(1)

        def get(attr: str, attrs: str = attrs_str) -> str:
            vm = re.search(rf'{attr}="([^"]*)"', attrs)
            return vm.group(1).strip() if vm else ""

        if app_pkg and get("package") and get("package") != app_pkg:
            continue
        if get("bounds") == "[0,0][0,0]":
            continue
        if (
            get("enabled") == "false"
            and not get("text")
            and not get("resource-id")
            and not get("content-desc")
        ):
            continue

        text = get("text")
        rid = get("resource-id")
        desc = get("content-desc")
        cls = get("class").split(".")[-1]
        clickable = get("clickable") == "true"

        if not text and not rid and not desc:
            continue
        if max_desc_len > 0 and len(desc) > max_desc_len:
            desc = ""
        if not text and not rid and not desc:
            continue
        if max_text_len > 0 and len(text) > max_text_len:
            text = text[:max_text_len] + "..."

        parts: list[str] = [cls] if cls else []
        if text:
            parts.append(f"text={text}")
        if rid:
            rid_short = rid.split(":id/")[-1] if ":id/" in rid else rid
            parts.append(f"id={rid_short}")
        if desc and desc != text:
            parts.append(f"desc={desc}")
        if clickable:
            parts.append("clickable")

        lines.append(" | ".join(parts))

    return "\n".join(lines)
