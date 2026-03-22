from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import cast

from engine.actions import _rpc_bootstrap, sdk_config_support
from engine.actions import _state_detection_support as _support
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters import mytRpc as MytRpcModule
from hardware_adapters.mytRpc import MytRpc

Params = dict[str, object]
Candidate = dict[str, object]


def _is_rpc_enabled() -> bool:
    return _rpc_bootstrap.is_rpc_enabled()


def _resolve_connection_params(params: Params, context: ExecutionContext) -> tuple[str, int]:
    return _rpc_bootstrap.resolve_connection_params(params, context)


def _connect_rpc(
    params: Params, context: ExecutionContext
) -> tuple[MytRpc | None, ActionResult | None]:
    def _is_enabled_for_factory() -> bool:
        return _is_rpc_enabled() or MytRpc is not MytRpcModule.MytRpc

    rpc, err = _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=_is_enabled_for_factory,
        resolve_params=_resolve_connection_params,
        rpc_factory=MytRpc,
        result_factory=ActionResult,
        error_type_env=ErrorType.ENV_ERROR,
        error_type_business=ErrorType.BUSINESS_ERROR,
    )
    return rpc, err


def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)


def _int_from_param(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(cast(int, value))
    if isinstance(value, (int, float)):
        return int(cast(float, value))
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _resolve_center(candidate: Mapping[str, object]) -> tuple[int, int]:
    center = candidate.get("center")
    if isinstance(center, Mapping):
        center_map = cast(Mapping[str, object], center)
        x = _int_from_param(center_map.get("x"), 0)
        y = _int_from_param(center_map.get("y"), 0)
        return x, y
    bound = candidate.get("bound")
    if isinstance(bound, Mapping):
        bound_map = cast(Mapping[str, object], bound)
        left = _int_from_param(bound_map.get("left"), 0)
        right = _int_from_param(bound_map.get("right"), 0)
        top = _int_from_param(bound_map.get("top"), 0)
        bottom = _int_from_param(bound_map.get("bottom"), 0)
        return int((left + right) / 2), int((top + bottom) / 2)
    return 0, 0


def _coerce_text_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, Iterable):
        return [str(part).strip() for part in raw if str(part).strip()]
    value = str(raw).strip()
    return [value] if value else []


def _resolve_package(params: Params, context: ExecutionContext) -> str:
    return str(
        params.get("package")
        or context.get_session_default("package")
        or context.payload.get("package")
        or ""
    ).strip()


def _resolve_injected_stage_patterns(context: ExecutionContext) -> dict[str, object] | None:
    raw_patterns = (
        context.get_session_default("stage_patterns")
        or context.get_session_default("_app_stage_patterns")
        or context.payload.get("stage_patterns")
        or context.payload.get("_app_stage_patterns")
    )
    return raw_patterns if isinstance(raw_patterns, dict) else None


def _load_state_action_defaults_document() -> dict[str, object]:
    try:
        defaults_doc = sdk_config_support.load_state_action_defaults_document()
    except Exception:
        return {}
    return defaults_doc if isinstance(defaults_doc, dict) else {}


DEFAULT_LOGIN_STAGE_ORDER = ("captcha", "two_factor", "account", "password", "login_entry", "home")


def _normalize_stage_entry(raw: object) -> dict[str, list[str]]:
    if raw is None:
        return {"resource_ids": [], "focus_markers": [], "text_markers": []}
    if isinstance(raw, dict):
        return {
            "resource_ids": _coerce_text_list(
                raw.get("resource_ids") or raw.get("resource_id_markers")
            ),
            "focus_markers": _coerce_text_list(
                raw.get("focus_markers") or raw.get("window_markers")
            ),
            "text_markers": _coerce_text_list(raw.get("text_markers") or raw.get("texts")),
        }
    # Allow shorthand list/string as text markers
    return {"resource_ids": [], "focus_markers": [], "text_markers": _coerce_text_list(raw)}


def _extract_app_stage_patterns(config: object) -> dict[str, dict[str, list[str]]]:
    if not isinstance(config, dict):
        return {}

    raw_patterns = config.get("stage_patterns")
    if isinstance(raw_patterns, dict):
        return {
            str(stage_id).strip(): _normalize_stage_entry(entry)
            for stage_id, entry in raw_patterns.items()
            if str(stage_id).strip()
        }

    selectors = config.get("selectors")
    if not isinstance(selectors, dict):
        return {}

    patterns: dict[str, dict[str, list[str]]] = {}
    for stage_id, entry in selectors.items():
        stage_key = str(stage_id or "").strip()
        if not stage_key or not isinstance(entry, dict):
            continue
        if any(
            key in entry
            for key in (
                "resource_ids",
                "resource_id_markers",
                "focus_markers",
                "window_markers",
                "text_markers",
                "texts",
                "content_descs",
                "p95_text_markers",
            )
        ):
            normalized = _normalize_stage_entry(entry)
            normalized["text_markers"] = (
                _coerce_text_list(entry.get("p95_text_markers"))
                + normalized["text_markers"]
                + _coerce_text_list(entry.get("content_descs"))
            )
            patterns[stage_key] = {
                "resource_ids": normalized["resource_ids"],
                "focus_markers": normalized["focus_markers"],
                "text_markers": list(dict.fromkeys(normalized["text_markers"])),
            }
    return patterns


def _resolve_login_stage_patterns(
    params: Params, context: ExecutionContext
) -> tuple[dict[str, dict[str, list[str]]], tuple[str, ...]]:
    raw_patterns = params.get("stage_patterns") or _resolve_injected_stage_patterns(context)
    patterns: dict[str, dict[str, list[str]]] = {}

    if isinstance(raw_patterns, dict):
        for stage, entry in raw_patterns.items():
            stage_id = str(stage or "").strip()
            if not stage_id:
                continue
            patterns[stage_id] = _normalize_stage_entry(entry)

    defaults_doc = {}
    try:
        defaults_doc = sdk_config_support.load_login_stage_patterns_document()
    except Exception:
        defaults_doc = {}
    default_patterns_raw = (
        defaults_doc.get("stage_patterns") if isinstance(defaults_doc, dict) else None
    )
    default_patterns = default_patterns_raw if isinstance(default_patterns_raw, dict) else {}
    default_order_raw = defaults_doc.get("stage_order") if isinstance(defaults_doc, dict) else None
    default_order = tuple(_coerce_text_list(default_order_raw)) or DEFAULT_LOGIN_STAGE_ORDER

    for stage in default_order:
        default_entry = _normalize_stage_entry(default_patterns.get(stage))
        if stage not in patterns:
            patterns[stage] = {
                "resource_ids": [],
                "focus_markers": [],
                "text_markers": default_entry.get("text_markers", []),
            }
        else:
            if not any(patterns[stage].values()):
                patterns[stage]["text_markers"] = default_entry.get("text_markers", [])

    order_raw = params.get("stage_order") or context.get_session_default("stage_order")
    order = _coerce_text_list(order_raw) if order_raw is not None else []
    if not order:
        order = [stage for stage in default_order if stage in patterns] + [
            stage for stage in patterns if stage not in default_order
        ]
    return patterns, tuple(order)


def _detect_login_stage_with_rpc(rpc: MytRpc, params: Params, context: ExecutionContext) -> str:
    patterns, order = _resolve_login_stage_patterns(params, context)

    # 1. Capture XML once and use it for both resource_ids and text_markers
    xml_str = ""
    xml_index: dict[str, tuple[str, ...]] | None = None
    try:
        # Use common helper to get XML (handles fallbacks)
        xml_str = _support.dump_xml_for_candidates(rpc)
        xml_index = _support.build_xml_match_index(xml_str)
    except Exception:
        pass

    if xml_index:
        # Check resource IDs
        for stage in order:
            for marker in patterns.get(stage, {}).get("resource_ids", []):
                if _support.xml_index_contains_resource_id(xml_index, marker):
                    return stage
        for stage in order:
            markers = patterns.get(stage, {}).get("text_markers", [])
            if not markers:
                continue
            for m in markers:
                if _support.xml_index_contains_visible_text(xml_index, m):
                    return stage
    elif str(xml_str or "").strip():
        xml_lower = str(xml_str).lower()
        for stage in order:
            for marker in patterns.get(stage, {}).get("resource_ids", []):
                needle = str(marker or "").strip().lower()
                if needle and needle in xml_lower:
                    return stage
        for stage in order:
            for marker in patterns.get(stage, {}).get("text_markers", []):
                needle = str(marker or "").strip().lower()
                if needle and needle in xml_lower:
                    return stage

    # 2. Check focus markers (requires separate dumpsys call)
    try:
        if any(patterns.get(stage, {}).get("focus_markers") for stage in order):
            focus, ok = rpc.exec_cmd("dumpsys window | grep mCurrentFocus")
            focus_text = str(focus or "").lower()
            if ok and focus_text:
                for stage in order:
                    markers = [
                        m.lower() for m in patterns.get(stage, {}).get("focus_markers", []) if m
                    ]
                    if markers and any(marker in focus_text for marker in markers):
                        return stage
    except Exception:
        pass

    if not xml_index and not str(xml_str or "").strip():
        for stage in order:
            markers = patterns.get(stage, {}).get("text_markers", [])
            if markers and _support.query_any_text_contains(rpc, markers):
                return stage

    return "unknown"


def _resolve_follow_targets(
    rpc: MytRpc,
    params: Params,
    context: ExecutionContext,
) -> tuple[ActionResult | None, list[Candidate]]:
    xml_text = _support.dump_xml_for_candidates(
        rpc, _int_from_param(params.get("timeout_ms"), 2500)
    )
    default_follow_texts = _coerce_text_list(
        _load_state_action_defaults_document().get("follow_texts")
    )
    button_texts = _coerce_text_list(
        params.get("follow_texts")
        or params.get("button_texts")
        or context.get_session_default("follow_texts")
        or default_follow_texts
    )
    if not button_texts:
        return (
            ActionResult(ok=False, code="invalid_params", message="follow_texts is required"),
            [],
        )
    package = _resolve_package(params, context)
    targets = _support.extract_follow_targets_from_xml(
        xml_text=xml_text,
        package=package,
        min_top=_int_from_param(params.get("min_top"), 350),
        button_texts=button_texts,
    )
    return None, targets


def _resolve_unread_dm_targets(
    rpc: MytRpc,
    params: Params,
    context: ExecutionContext,
) -> tuple[ActionResult | None, list[Candidate]]:
    xml_text = _support.dump_xml_for_candidates(
        rpc, _int_from_param(params.get("timeout_ms"), 2500)
    )
    default_unread_markers = _coerce_text_list(
        _load_state_action_defaults_document().get("unread_markers")
    )
    markers = _coerce_text_list(
        params.get("unread_markers")
        or params.get("markers")
        or context.get_session_default("unread_markers")
        or default_unread_markers
    )
    if not markers:
        return (
            ActionResult(ok=False, code="invalid_params", message="unread_markers is required"),
            [],
        )
    package = _resolve_package(params, context)
    targets = _support.extract_unread_dm_targets_from_xml(
        xml_text=xml_text,
        package=package,
        min_top=_int_from_param(params.get("min_top"), 250),
        markers=markers,
    )
    return None, targets


def detect_login_stage(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        stage = _detect_login_stage_with_rpc(rpc, params, context)
        return ActionResult(ok=True, code="ok", data={"stage": stage})
    finally:
        _close_rpc(rpc)


def wait_login_stage(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        timeout_ms = _int_from_param(params.get("timeout_ms"), 15000)
        interval_ms = _int_from_param(params.get("interval_ms"), 700)
        stages_raw = params.get("target_stages")
        target_stages: set[str] = set()
        if isinstance(stages_raw, str):
            target_stages = {x.strip() for x in stages_raw.split(",") if x.strip()}
        elif isinstance(stages_raw, list):
            stage_items = cast(list[object], stages_raw)
            target_stages = {str(item).strip() for item in stage_items if str(item).strip()}
        if not target_stages:
            return ActionResult(
                ok=False, code="invalid_params", message="target_stages is required"
            )

        started = time.monotonic()
        attempt = 0
        last_stage = "unknown"

        context.check_cancelled()
        while (time.monotonic() - started) * 1000 <= timeout_ms:
            context.check_cancelled()
            attempt += 1
            last_stage = _detect_login_stage_with_rpc(rpc, params, context)
            context.check_cancelled()
            if last_stage in target_stages:
                elapsed = int((time.monotonic() - started) * 1000)
                return ActionResult(
                    ok=True,
                    code="ok",
                    data={
                        "stage": last_stage,
                        "attempt": attempt,
                        "elapsed_ms": elapsed,
                        "target_stages": sorted(target_stages),
                    },
                )
            context.check_cancelled()
            time.sleep(max(0.05, interval_ms / 1000.0))

        context.check_cancelled()
        elapsed = int((time.monotonic() - started) * 1000)
        return ActionResult(
            ok=False,
            code="stage_timeout",
            message=f"wait stage timeout, last stage: {last_stage}",
            data={
                "stage": last_stage,
                "attempt": attempt,
                "elapsed_ms": elapsed,
                "target_stages": sorted(target_stages),
            },
        )
    finally:
        _close_rpc(rpc)


def extract_timeline_candidates(params: Params, context: ExecutionContext) -> ActionResult:
    row_id_contains = str(
        params.get("row_id_contains") or context.get_session_default("row_id_contains") or ":id/"
    ).strip()
    return _support.extract_candidates_action(
        params,
        context,
        row_id_contains=row_id_contains,
        connect_rpc=_connect_rpc,
        close_rpc=_close_rpc,
    )


def extract_search_candidates(params: Params, context: ExecutionContext) -> ActionResult:
    row_id_contains = str(
        params.get("row_id_contains") or context.get_session_default("row_id_contains") or ":id/row"
    ).strip()
    return _support.extract_candidates_action(
        params,
        context,
        row_id_contains=row_id_contains,
        connect_rpc=_connect_rpc,
        close_rpc=_close_rpc,
    )


def collect_blogger_candidates(params: Params, context: ExecutionContext) -> ActionResult:
    return _support.collect_blogger_candidates(
        params,
        context,
        connect_rpc=_connect_rpc,
        close_rpc=_close_rpc,
        time_module=time,
    )


def open_candidate(params: Params, context: ExecutionContext) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        x, y = _resolve_center(cast(Mapping[str, object], candidate))
        touch_click = getattr(rpc, "touchClick", None)
        if not callable(touch_click):
            return ActionResult(
                ok=False,
                code="open_candidate_failed",
                message="touchClick not available",
                data={"candidate": candidate},
            )
        ok = touch_click(0, x, y)
        if not ok:
            return ActionResult(
                ok=False,
                code="open_candidate_failed",
                message="touchClick failed",
                data={"candidate": candidate, "x": x, "y": y},
            )
        return ActionResult(ok=True, code="ok", data={"candidate": candidate, "x": x, "y": y})
    finally:
        _close_rpc(rpc)


def extract_dm_last_message(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _support.dump_xml_for_candidates(
            rpc, _int_from_param(params.get("timeout_ms"), 2500)
        )
        separator_tokens = _coerce_text_list(
            params.get("separator_tokens")
            or params.get("message_separators")
            or context.get_session_default("dm_separator_tokens")
            or [": ", "："]
        )
        if not separator_tokens:
            return ActionResult(
                ok=False, code="invalid_params", message="separator_tokens is required"
            )
        package = _resolve_package(params, context)
        message = _support.extract_last_dm_message_from_xml(
            xml_text=xml_text,
            package=package,
            max_left=_int_from_param(params.get("max_left"), 540),
            separator_tokens=separator_tokens,
        )
        if message is None:
            return ActionResult(
                ok=False, code="dm_message_missing", message="no dm message extracted"
            )
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        _close_rpc(rpc)


def extract_dm_last_outbound_message(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        xml_text = _support.dump_xml_for_candidates(
            rpc, _int_from_param(params.get("timeout_ms"), 2500)
        )
        defaults_doc = _load_state_action_defaults_document()
        default_separator_tokens = (
            _coerce_text_list(defaults_doc.get("dm_separator_tokens"))
            if isinstance(defaults_doc, dict)
            else []
        )
        separator_tokens = _coerce_text_list(
            params.get("separator_tokens")
            or params.get("message_separators")
            or context.get_session_default("dm_separator_tokens")
            or default_separator_tokens
        )
        if not separator_tokens:
            return ActionResult(
                ok=False, code="invalid_params", message="separator_tokens is required"
            )
        package = _resolve_package(params, context)
        message = _support.extract_last_outbound_dm_message_from_xml(
            xml_text=xml_text,
            package=package,
            min_left=_int_from_param(params.get("min_left"), 540),
            separator_tokens=separator_tokens,
        )
        if message is None:
            return ActionResult(
                ok=False,
                code="dm_outbound_message_missing",
                message="no outbound dm message extracted",
            )
        return ActionResult(ok=True, code="ok", data=message)
    finally:
        _close_rpc(rpc)


def extract_follow_targets(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        invalid_result, targets = _resolve_follow_targets(rpc, params, context)
        if invalid_result is not None:
            return invalid_result
        if not targets:
            return ActionResult(
                ok=False,
                code="follow_targets_missing",
                message="no follow targets extracted",
                data={"targets": [], "count": 0},
            )
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        _close_rpc(rpc)


def follow_visible_targets(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        invalid_result, targets = _resolve_follow_targets(rpc, params, context)
        if invalid_result is not None:
            return invalid_result
        max_clicks = max(_int_from_param(params.get("max_clicks"), 3), 1)
        delay_ms = max(_int_from_param(params.get("delay_ms"), 1200), 0)

        clicked_targets: list[Candidate] = []
        for target in targets[:max_clicks]:
            x, y = _resolve_center(cast(Mapping[str, object], target))
            if not rpc.touchClick(0, x, y):
                continue
            clicked_targets.append(target)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)

        if not clicked_targets:
            return ActionResult(
                ok=False,
                code="follow_click_failed",
                message="no visible follow targets clicked",
                data={"targets": targets, "count": len(targets), "clicked_count": 0},
            )
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "targets": targets,
                "count": len(targets),
                "clicked_targets": clicked_targets,
                "clicked_count": len(clicked_targets),
            },
        )
    finally:
        _close_rpc(rpc)


def extract_unread_dm_targets(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        invalid_result, targets = _resolve_unread_dm_targets(rpc, params, context)
        if invalid_result is not None:
            return invalid_result
        if not targets:
            return ActionResult(
                ok=False,
                code="unread_dm_missing",
                message="no unread dm targets extracted",
                data={"targets": [], "count": 0},
            )
        return ActionResult(ok=True, code="ok", data={"targets": targets, "count": len(targets)})
    finally:
        _close_rpc(rpc)


def open_first_unread_dm(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        invalid_result, targets = _resolve_unread_dm_targets(rpc, params, context)
        if invalid_result is not None:
            return invalid_result
        if not targets:
            return ActionResult(
                ok=False,
                code="unread_dm_missing",
                message="no unread dm targets extracted",
                data={"targets": [], "count": 0},
            )
        first = cast(Mapping[str, object], targets[0])
        x, y = _resolve_center(first)
        touch_click = getattr(rpc, "touchClick", None)
        if touch_click is None:
            return ActionResult(
                ok=False,
                code="open_unread_dm_failed",
                message="touchClick not available",
                data={"target": first},
            )
        if not touch_click(0, x, y):
            return ActionResult(
                ok=False,
                code="open_unread_dm_failed",
                message="failed to open unread dm",
                data={"target": first},
            )
        return ActionResult(ok=True, code="ok", data={"target": first, "count": len(targets)})
    finally:
        _close_rpc(rpc)


def detect_app_stage(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        stage_patterns = {}
        raw_stage_patterns = params.get("stage_patterns") or _resolve_injected_stage_patterns(context)
        if isinstance(raw_stage_patterns, dict):
            stage_patterns = {
                str(stage_id).strip(): _normalize_stage_entry(entry)
                for stage_id, entry in raw_stage_patterns.items()
                if str(stage_id).strip()
            }

        if not stage_patterns:
            package = _resolve_package(params, context)
            app_name = (
                params.get("app")
                or sdk_config_support.app_from_package(package)
                or sdk_config_support.DEFAULT_APP_NAME
            )

            try:
                config = sdk_config_support.load_app_config_document(str(app_name))
                stage_patterns = _extract_app_stage_patterns(config)
            except Exception:
                stage_patterns = {}

        if not stage_patterns:
            return ActionResult(ok=True, code="ok", data={"stage": "unknown"})

        stage = _detect_login_stage_with_rpc(
            rpc,
            {"stage_patterns": stage_patterns, "stage_order": list(stage_patterns.keys())},
            context,
        )
        return ActionResult(ok=True, code="ok", data={"stage": stage})
    finally:
        _close_rpc(rpc)


def wait_app_stage(params: Params, context: ExecutionContext) -> ActionResult:
    rpc, err = _connect_rpc(params, context)
    if err:
        return err
    assert rpc is not None
    try:
        timeout_ms = _int_from_param(params.get("timeout_ms"), 10000)
        target_stages = set(_coerce_text_list(params.get("target_stages")))
        if not target_stages:
            return ActionResult(
                ok=False, code="invalid_params", message="target_stages is required"
            )

        started = time.monotonic()
        while (time.monotonic() - started) * 1000 <= timeout_ms:
            context.check_cancelled()
            res = detect_app_stage(params, context)
            if res.ok and res.data.get("stage") in target_stages:
                return res
            time.sleep(0.5)

        return ActionResult(ok=False, code="stage_timeout", message="wait app_stage timeout")
    finally:
        _close_rpc(rpc)
