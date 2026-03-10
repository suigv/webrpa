from __future__ import annotations

import time
from typing import Any, Dict

from engine.actions import _rpc_bootstrap
from engine.actions import _state_detection_support as _support
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc


def _is_rpc_enabled() -> bool:
    return _rpc_bootstrap.is_rpc_enabled()


def _resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    return _rpc_bootstrap.resolve_connection_params(params, context)


def _connect_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    rpc, err = _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=_is_rpc_enabled,
        resolve_params=_resolve_connection_params,
        rpc_factory=MytRpc,
    )
    return rpc, err


def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)


def _query_any_text_contains(rpc: MytRpc, texts: Any, timeout_ms: int = 900) -> bool:
    return _support.query_any_text_contains(rpc, texts, timeout_ms)


def _detect_x_login_stage_with_rpc(rpc: MytRpc) -> str:
    return _support.detect_x_login_stage_with_rpc(rpc)


def _parse_bounds(raw: str) -> dict[str, int]:
    return _support.parse_bounds(raw)


def _join_candidate_texts(node: Any) -> tuple[str, str]:
    return _support.join_candidate_texts(node)


def _node_has_media(node: Any) -> bool:
    return _support.node_has_media(node)


def _candidate_from_element(node: Any) -> dict[str, Any] | None:
    return _support.candidate_from_element(node)


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return _support.candidate_identity(candidate)


def _extract_candidates_from_xml(
    xml_text: str,
    package: str = "",
    row_id_contains: str = ":id/row",
    min_top: int = 220,
    max_bottom: int = 2200,
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    return _support.extract_candidates_from_xml(xml_text, package, row_id_contains, min_top, max_bottom, max_candidates)


def _dump_xml_for_candidates(rpc: MytRpc, timeout_ms: int = 2500) -> str:
    return _support.dump_xml_for_candidates(rpc, timeout_ms)


def _normalize_dm_text(raw: str) -> str:
    return _support.normalize_dm_text(raw)


def _extract_last_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", max_left: int = 540) -> dict[str, Any] | None:
    return _support.extract_last_dm_message_from_xml(xml_text, package, max_left)


def _extract_last_outbound_dm_message_from_xml(xml_text: str, package: str = "com.twitter.android", min_left: int = 540) -> dict[str, Any] | None:
    return _support.extract_last_outbound_dm_message_from_xml(xml_text, package, min_left)


def _extract_follow_targets_from_xml(
    xml_text: str,
    package: str = "com.twitter.android",
    min_top: int = 350,
) -> list[dict[str, Any]]:
    return _support.extract_follow_targets_from_xml(xml_text, package, min_top)


def _extract_unread_dm_targets_from_xml(
    xml_text: str,
    package: str = "com.twitter.android",
    min_top: int = 250,
) -> list[dict[str, Any]]:
    return _support.extract_unread_dm_targets_from_xml(xml_text, package, min_top)


def _extract_candidates_action(params: Dict[str, Any], context: ExecutionContext, row_id_contains: str) -> ActionResult:
    return _support.extract_candidates_action(
        params,
        context,
        row_id_contains=row_id_contains,
        connect_rpc=_connect_rpc,
        close_rpc=_close_rpc,
    )


def detect_x_login_stage(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        stage = _detect_x_login_stage_with_rpc(rpc) if rpc is not None else "unknown"
        return ActionResult(ok=True, code="ok", data={"stage": stage})
    finally:
        _close_rpc(rpc)


def wait_x_login_stage(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
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
        _close_rpc(rpc)


def extract_timeline_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    # 优先匹配通用的 list 标识，不再硬编码 :id/row
    return _extract_candidates_action(params, context, row_id_contains=":id/")


def extract_search_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _extract_candidates_action(params, context, row_id_contains=":id/row")


def collect_blogger_candidates(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _support.collect_blogger_candidates(
        params,
        context,
        connect_rpc=_connect_rpc,
        close_rpc=_close_rpc,
        time_module=time,
    )


def open_candidate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
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
        _close_rpc(rpc)


def extract_dm_last_message(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        message = _extract_last_dm_message_from_xml(
            xml_text=xml_text,
            package=package,
            max_left=int(params.get("max_left", 540) or 540),
        )
        if message is None:
            return ActionResult(ok=False, code="dm_message_missing", message="no dm message extracted")
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        _close_rpc(rpc)


def extract_dm_last_outbound_message(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        message = _extract_last_outbound_dm_message_from_xml(
            xml_text=xml_text,
            package=package,
            min_left=int(params.get("min_left", 540) or 540),
        )
        if message is None:
            return ActionResult(ok=False, code="dm_outbound_message_missing", message="no outbound dm message extracted")
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        _close_rpc(rpc)


def extract_follow_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        targets = _extract_follow_targets_from_xml(
            xml_text=xml_text,
            package=package,
            min_top=int(params.get("min_top", 350) or 350),
        )
        if not targets:
            return ActionResult(ok=False, code="follow_targets_missing", message="no follow targets extracted", data={"targets": [], "count": 0})
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        _close_rpc(rpc)


def follow_visible_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        targets = _extract_follow_targets_from_xml(
            xml_text=xml_text,
            package=package,
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
        _close_rpc(rpc)


def extract_unread_dm_targets(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        targets = _extract_unread_dm_targets_from_xml(
            xml_text=xml_text,
            package=package,
            min_top=int(params.get("min_top", 250) or 250),
        )
        if not targets:
            return ActionResult(ok=False, code="unread_dm_missing", message="no unread dm targets extracted", data={"targets": [], "count": 0})
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        _close_rpc(rpc)


def open_first_unread_dm(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _dump_xml_for_candidates(rpc, int(params.get("timeout_ms", 2500)))
        package = str(params.get("package") or context.get_session_default("package") or "com.twitter.android").strip()
        targets = _extract_unread_dm_targets_from_xml(
            xml_text=xml_text,
            package=package,
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
        _close_rpc(rpc)
