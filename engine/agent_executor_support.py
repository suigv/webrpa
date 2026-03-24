from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from core.credentials_loader import generate_twofa_code

from .agent_executor_types import AgentExecutorConfig

_SAFE_PART_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_TEXT_ENTRY_STATE_IDS = frozenset({"account", "password", "two_factor"})
_PLANNER_DISALLOWED_ACTIONS = frozenset({"ui.observe_transition"})
_LOGIN_STAGE_ORDER = {
    "login_entry": 0,
    "account": 1,
    "password": 2,
    "two_factor": 3,
    "home": 4,
}
_TEXT_ENTRY_FOCUS_QUERIES = {
    "account": (
        "账户输入页面中的用户名/手机号/邮箱输入框，或可直接输入账号的文本框区域。"
        "优先返回输入框中心点，不要返回下一步按钮。"
    ),
    "password": (
        "密码输入页面中的密码输入框或密码文本框区域。优先返回输入框中心点，不要返回登录/继续按钮。"
    ),
    "two_factor": (
        "2FA 或验证码输入页面中的验证码输入框、单个数字输入格，或可输入验证码的文本框区域。"
        "优先返回输入框中心点，不要返回确认/继续按钮。"
    ),
}
_TEXT_ENTRY_SUBMIT_QUERIES = {
    "account": (
        "当前页面中用于提交已填写标识字段并推进流程的主操作控件。"
        "优先返回页面主按钮、键盘动作键或明显的前进控件中心点，不要返回输入框。"
    ),
    "password": (
        "当前页面中用于提交已填写密文字段并推进流程的主操作控件。"
        "优先返回页面主按钮、键盘动作键或明显的前进控件中心点，不要返回输入框。"
    ),
    "two_factor": (
        "当前页面中用于提交已填写验证码并推进流程的主操作控件。"
        "优先返回页面主按钮、键盘动作键或明显的确认控件中心点，不要返回输入框。"
    ),
}
_SUBMIT_LOCATE_TOKENS = (
    "next",
    "continue",
    "submit",
    "sign in",
    "log in",
    "login",
    "登录",
    "下一步",
    "继续",
    "提交",
)
_FOCUS_LOCATE_TOKENS = ("输入框", "文本框", "edittext", "text field", "field")
_HISTORY_DIGEST_WINDOW = 5
_DYNAMIC_STEP_EXTENSION_MIN = 3
_DYNAMIC_STEP_EXTENSION_CAP = 6
_DYNAMIC_STEP_PROGRESS_WINDOW = 4
_DEFAULT_APP_LEVEL_MAX_STEPS = 12
_ACTION_CONTRACT_ERROR_CODES = frozenset(
    {
        "invalid_image",
        "invalid_json",
        "invalid_key",
        "invalid_params",
        "invalid_response",
    }
)
_PLANNER_INPUT_ALIASES = (
    ("acc", ("acc", "account")),
    ("pwd", ("pwd", "password")),
    ("two_factor_code", ("two_factor_code",)),
    ("fa2_secret", ("fa2_secret", "twofa_secret")),
    ("email", ("email",)),
    ("phone", ("phone",)),
    ("username", ("username",)),
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _json_safe(value: object, *, string_limit: int = 4000) -> object:
    if isinstance(value, (bytes, bytearray)):
        return {"byte_length": len(value)}
    if isinstance(value, str):
        return value if len(value) <= string_limit else f"{value[:string_limit]}…"
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item, string_limit=string_limit) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_safe(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item, string_limit=string_limit) for item in value]
    return value


def _safe_path_part(value: object, *, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    sanitized = _SAFE_PART_RE.sub("-", raw).strip("-._")
    return sanitized or default


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                result.append(item_str)
        return result
    return []


def _int_in_range(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise ValueError("must be an integer")
    parsed = int(str(value))
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"must be between {minimum} and {maximum}")
    return parsed


def _has_app_level_context(payload: Mapping[str, object]) -> bool:
    app_id = str(payload.get("app_id") or "").strip().lower()
    package = str(payload.get("package") or payload.get("package_name") or "").strip()
    app_states = payload.get("_app_states")
    has_state_profile = isinstance(app_states, (list, Mapping))
    return bool(package or has_state_profile or (app_id and app_id != "default"))


def _default_max_steps(payload: Mapping[str, object]) -> tuple[int, bool]:
    if payload.get("max_steps") not in (None, ""):
        return (
            _int_in_range(payload.get("max_steps"), default=8, minimum=1, maximum=100),
            True,
        )
    if _has_app_level_context(payload):
        return _DEFAULT_APP_LEVEL_MAX_STEPS, True
    return 8, True


def _stable_fingerprint(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _params_summary(params: object, *, max_len: int = 80) -> str:
    if not params:
        return "{}"
    try:
        raw = json.dumps(params, ensure_ascii=False, separators=(",", ":"), default=str)
        return raw if len(raw) <= max_len else raw[:max_len] + "…"
    except Exception:
        return str(params)[:max_len]


def _build_history_digest(
    history: list[dict[str, object]],
    *,
    window: int = _HISTORY_DIGEST_WINDOW,
) -> list[dict[str, object]]:
    recent = history[-window:] if len(history) > window else history
    digest: list[dict[str, object]] = []
    for entry in recent:
        result = entry.get("result")
        result_dict = result if isinstance(result, dict) else {}
        digest.append(
            {
                "step": entry.get("step_index"),
                "action": str(entry.get("action") or ""),
                "params_summary": _params_summary(entry.get("params")),
                "ok": bool(result_dict.get("ok", True)),
                "message": str(result_dict.get("message") or "")[:120],
            }
        )
    return digest


def _build_reflection(
    last_action: dict[str, object] | None,
    *,
    repeated_action_count: int,
) -> dict[str, object]:
    reflection: dict[str, object] = {}
    if last_action is not None:
        action = str(last_action.get("action") or "").strip()
        result = last_action.get("result")
        result_dict = result if isinstance(result, dict) else {}
        result_data = _json_dict(result_dict.get("data"))
        if action == "ai.locate_point" and result_dict.get("ok") is True:
            x = result_data.get("x")
            y = result_data.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                reflection["locate_point_ready"] = True
                reflection["locate_point"] = {"x": int(x), "y": int(y)}
                reflection["suggestion"] = (
                    "上一步已经定位到可交互坐标。若当前页面没有明显变化，"
                    "优先直接使用这些坐标执行 ui.click，而不是再次定位。"
                )
        if result_dict.get("ok") is False:
            reflection["last_action_failed"] = True
            reflection["failure_code"] = str(result_dict.get("code") or "unknown")
            reflection["failure_message"] = str(result_dict.get("message") or "")[:200]
            if bool(result_data.get("effect_uncertain")):
                reflection["effect_uncertain"] = True
                reflection["suggestion"] = (
                    "上一步动作返回失败，但界面可能已经发生变化。"
                    "先根据当前观察判断页面是否跳转或出现新元素，不要假设动作完全未生效。"
                )
            else:
                reflection["suggestion"] = (
                    "上一步动作执行失败。请分析失败原因，考虑使用不同的方法、参数或目标元素。"
                    "避免简单重复上一步的操作。"
                )
    if repeated_action_count >= 2:
        reflection["repeated_action_detected"] = True
        reflection["repeated_count"] = repeated_action_count
        reflection["suggestion"] = (
            f"你已经连续 {repeated_action_count} 次选择了相同的动作和参数组合。"
            "这很可能表明当前策略无效。请审视屏幕状态，尝试完全不同的交互路径。"
        )
    return reflection


def _action_fingerprint(action_name: str, params: dict[str, object]) -> str:
    return _stable_fingerprint({"a": action_name, "p": params})


def _is_non_mutating_action(last_action: Mapping[str, object] | None) -> bool:
    action = str(_json_dict(last_action).get("action") or "").strip()
    if action in {
        "ai.locate_point",
        "ui.dump_node_xml",
        "ui.dump_node_xml_ex",
        "ui.capture_compressed",
        "ui.screenshot",
    }:
        return True
    if action != "ai.locate_point":
        return False
    result = _json_dict(_json_dict(last_action).get("result"))
    return bool(result.get("ok"))


def _observation_state_id(observation_payload: object) -> str:
    observation = _json_dict(observation_payload)
    state = _json_dict(observation.get("state"))
    return str(state.get("state_id") or "").strip()


def _observation_confidence(observation_payload: object) -> float | None:
    observation = _json_dict(observation_payload)
    evidence = _json_dict(observation.get("evidence"))
    raw_confidence = evidence.get("confidence")
    if isinstance(raw_confidence, (int, float)):
        return float(raw_confidence)
    return None


def _observation_requires_fallback(*, observation_ok: bool, observation_payload: object) -> bool:
    if not observation_ok:
        return True
    if _observation_state_id(observation_payload) == "unknown":
        return True
    confidence = _observation_confidence(observation_payload)
    return confidence is not None and confidence <= 0.0


def _prioritize_action(actions: list[str], action_name: str) -> list[str]:
    if action_name not in actions:
        return actions
    return [action_name, *[item for item in actions if item != action_name]]


def _planner_allowed_actions(
    *,
    allowed_actions: list[str],
    last_action: Mapping[str, object] | None,
    observation_payload: Mapping[str, object] | None,
    previous_state_id: str,
    observation_requires_fallback: bool,
    navigation_available: bool,
) -> list[str]:
    actions = [
        action for action in allowed_actions if action and action not in _PLANNER_DISALLOWED_ACTIONS
    ]
    if not navigation_available:
        actions = [action for action in actions if action != "ui.navigate_to"]
    action = str(_json_dict(last_action).get("action") or "").strip()
    result = _json_dict(_json_dict(last_action).get("result"))
    result_data = _json_dict(result.get("data"))
    current_state_id = _observation_state_id(observation_payload)
    if observation_requires_fallback and "ai.locate_point" in actions:
        actions = _prioritize_action(actions, "ai.locate_point")
    if (
        action == "ui.swipe"
        and not bool(result.get("ok"))
        and bool(result_data.get("effect_uncertain"))
        and observation_requires_fallback
        and "ai.locate_point" in actions
    ):
        actions = [item for item in actions if item != "ui.swipe"] or actions
        actions = _prioritize_action(actions, "ai.locate_point")
    if (
        action == "ai.locate_point"
        and bool(result.get("ok"))
        and isinstance(result_data.get("x"), (int, float))
        and isinstance(result_data.get("y"), (int, float))
        and "ui.click" in actions
    ):
        actions = [item for item in actions if item not in {"ai.locate_point", "ui.swipe"}] or [
            "ui.click"
        ]
        actions = _prioritize_action(actions, "ui.click")
    if (
        observation_requires_fallback
        and current_state_id in _TEXT_ENTRY_STATE_IDS
        and not _text_entry_ready_under_fallback(
            last_action=last_action,
            current_state_id=current_state_id,
            previous_state_id=previous_state_id,
        )
    ):
        actions = [item for item in actions if item != "ui.input_text"] or actions
        actions = [item for item in actions if item != "ui.key_press"] or actions
        if "ai.locate_point" in actions:
            actions = _prioritize_action(actions, "ai.locate_point")
        elif "ui.click" in actions:
            actions = _prioritize_action(actions, "ui.click")
    return actions


def _business_completion_hint(
    *,
    goal: str,
    previous_state_id: str,
    observation_payload: Mapping[str, object] | None,
    last_action: Mapping[str, object] | None,
) -> str:
    normalized_goal = str(goal or "").strip().lower()
    if not normalized_goal:
        return ""
    if not any(token in normalized_goal for token in ("返回主页", "回到主页", "返回首页", "回到首页", "回主页")):
        return ""
    if not any(token in normalized_goal for token in ("如果", "若", "没有", "无", "完成后")):
        return ""
    current_state_id = _observation_state_id(observation_payload)
    if current_state_id != "home":
        return ""
    if previous_state_id in {"", "home", "unknown"}:
        return ""
    action = str(_json_dict(last_action).get("action") or "").strip()
    if action in {"", "ui.dump_node_xml", "ui.dump_node_xml_ex", "ui.screenshot"}:
        return ""
    result = _json_dict(_json_dict(last_action).get("result"))
    if not bool(result.get("ok")):
        return ""
    return "已返回主页，且目标描述包含分支后回到主页的完成条件。"


def _login_stage_rank(state_id: str) -> int:
    return _LOGIN_STAGE_ORDER.get(str(state_id or "").strip(), -1)


def _fallback_xml_text(fallback_evidence: Mapping[str, object]) -> str:
    ui_xml = _json_dict(fallback_evidence.get("ui_xml"))
    content = str(ui_xml.get("content") or "")
    if content:
        return content
    save_path = str(ui_xml.get("save_path") or "").strip()
    if not save_path:
        return ""
    try:
        return Path(save_path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _infer_login_stage_from_last_action(last_action: Mapping[str, object] | None) -> str:
    result = _json_dict(_json_dict(last_action).get("result"))
    result_data = _json_dict(result.get("data"))
    raw = _json_dict(result_data.get("raw"))
    for candidate in (
        raw.get("page"),
        result_data.get("page"),
        raw.get("stage"),
        result_data.get("stage"),
    ):
        value = str(candidate or "").strip().lower()
        if value in {"login_entry", "account", "password", "two_factor", "home"}:
            return value
    return ""


def _infer_login_stage_from_fallback_xml(fallback_evidence: Mapping[str, object]) -> str:
    xml_text = _fallback_xml_text(fallback_evidence).lower()
    if not xml_text:
        return ""
    verification_text_tokens = len(
        re.findall(
            r"(verification code|verification|authenticator|one[- ]time code|otp|2fa|two[- ]factor|验证码|校验码|动态码)",
            xml_text,
        )
    )
    password_fields = len(re.findall(r'password="true"', xml_text))
    password_tokens = len(re.findall(r'resource-id="[^"]*password[^"]*"', xml_text))
    verification_tokens = len(
        re.findall(r'resource-id="[^"]*(otp|code|token|verify)[^"]*"', xml_text)
    )
    edit_fields = len(re.findall(r'class="android\.widget\.edittext"', xml_text))
    buttons = len(re.findall(r'class="android\.widget\.(button|imagebutton)"', xml_text))
    list_views = len(re.findall(r'class="androidx\.recyclerview\.widget\.recyclerview"', xml_text))
    scroll_views = len(re.findall(r'class="android\.widget\.scrollview"', xml_text))
    if password_fields >= 1 or password_tokens >= 1:
        return "password"
    if edit_fields >= 4 or verification_tokens >= 1 or verification_text_tokens >= 1:
        return "two_factor"
    if edit_fields >= 1:
        return "account"
    if buttons >= 2 and edit_fields == 0:
        return "login_entry"
    if list_views >= 1 and edit_fields == 0 and scroll_views == 0:
        return "home"
    return ""


def _apply_fallback_state_hint(
    observation_payload: object,
    fallback_evidence: Mapping[str, object],
    last_action: Mapping[str, object] | None,
) -> dict[str, object]:
    observation = _json_dict(observation_payload)
    if not observation:
        return {}
    if _observation_state_id(observation) not in {"", "unknown"}:
        return observation
    inferred_state = _infer_login_stage_from_last_action(
        last_action
    ) or _infer_login_stage_from_fallback_xml(fallback_evidence)
    if not inferred_state:
        return observation
    state = _json_dict(observation.get("state"))
    state["state_id"] = inferred_state
    observation["state"] = state
    evidence = _json_dict(observation.get("evidence"))
    evidence["text"] = inferred_state
    evidence["summary"] = f"fallback inferred login stage '{inferred_state}' from ui_xml"
    confidence = evidence.get("confidence")
    if not isinstance(confidence, (int, float)) or float(confidence) <= 0.0:
        evidence["confidence"] = 0.35
    observation["evidence"] = evidence
    raw_details = _json_dict(observation.get("raw_details"))
    raw_details["fallback_state_hint"] = inferred_state
    raw_details["fallback_state_source"] = "ui_xml"
    observation["raw_details"] = raw_details
    return observation


def _fallback_indicates_loading(fallback_evidence: Mapping[str, object]) -> bool:
    xml_text = _fallback_xml_text(fallback_evidence).lower()
    if not xml_text:
        return False
    loading_copy = len(
        re.findall(
            r"(loading|please wait|processing|signing in|正在载入|正在加载|加载中|载入中|请稍候|請稍候|处理中|處理中)",
            xml_text,
        )
    )
    loading_widgets = len(
        re.findall(
            r'(android:id/progress|class="android\.widget\.progressbar"|resource-id="[^"]*(progress|loading|spinner)[^"]*")',
            xml_text,
        )
    )
    return loading_widgets >= 1 or (loading_copy >= 1 and "progressbar" in xml_text)


def _stabilize_fallback_state_hint(
    observation_payload: object,
    *,
    previous_state_id: str,
    last_action: Mapping[str, object] | None,
) -> dict[str, object]:
    observation = _json_dict(observation_payload)
    if not observation:
        return {}
    raw_details = _json_dict(observation.get("raw_details"))
    fallback_source = str(raw_details.get("fallback_state_source") or "").strip()
    if not fallback_source:
        return observation
    current_state_id = _observation_state_id(observation)
    previous_state_id = str(previous_state_id or "").strip()
    if not current_state_id or not previous_state_id or current_state_id == previous_state_id:
        return observation
    action = str(_json_dict(last_action).get("action") or "").strip()
    result = _json_dict(_json_dict(last_action).get("result"))
    if not bool(result.get("ok")) or action not in {"ui.key_press", "ui.click"}:
        return observation
    if (
        previous_state_id in {"password", "two_factor"}
        and current_state_id in {"account", "login_entry"}
        and _login_stage_rank(current_state_id) < _login_stage_rank(previous_state_id)
    ):
        state = _json_dict(observation.get("state"))
        state["state_id"] = previous_state_id
        observation["state"] = state
        evidence = _json_dict(observation.get("evidence"))
        evidence["text"] = previous_state_id
        evidence["summary"] = (
            f"stabilized fallback stage '{previous_state_id}' after submit-style action; "
            f"ignored regressive hint '{current_state_id}'"
        )
        confidence = evidence.get("confidence")
        if not isinstance(confidence, (int, float)) or float(confidence) < 0.4:
            evidence["confidence"] = 0.4
        observation["evidence"] = evidence
        raw_details["fallback_state_hint"] = previous_state_id
        raw_details["fallback_state_original_hint"] = current_state_id
        raw_details["fallback_state_source"] = "stabilized_after_submit"
        observation["raw_details"] = raw_details
    return observation


def _planner_inputs(payload: Mapping[str, object]) -> dict[str, object]:
    resolved: dict[str, object] = {}
    for target_key, aliases in _PLANNER_INPUT_ALIASES:
        for alias in aliases:
            value = payload.get(alias)
            if value not in (None, ""):
                resolved[target_key] = value
                break
    return resolved


def _planner_visible_inputs(planner_inputs: Mapping[str, object]) -> dict[str, object]:
    visible_inputs = {
        str(key): value
        for key, value in planner_inputs.items()
        if value not in (None, "") and str(key) != "fa2_secret"
    }
    resolved_two_factor_code = generate_twofa_code(planner_inputs.get("fa2_secret"))
    if resolved_two_factor_code:
        visible_inputs["two_factor_code"] = resolved_two_factor_code
    return visible_inputs


def _rewrite_two_factor_input_params(
    action_name: str,
    action_params: Mapping[str, object],
    observation_state: Mapping[str, object] | None,
    planner_inputs: Mapping[str, object],
) -> dict[str, object]:
    next_params = {str(key): value for key, value in action_params.items()}
    if action_name != "ui.input_text":
        return next_params
    observation_dict = _json_dict(observation_state)
    state_dict = _json_dict(observation_dict.get("state"))
    if str(state_dict.get("state_id") or "").strip() != "two_factor":
        return next_params
    secret = str(planner_inputs.get("fa2_secret") or "").strip()
    resolved_two_factor_code = generate_twofa_code(secret)
    if not resolved_two_factor_code:
        return next_params
    current_text = str(next_params.get("text") or "").strip()
    raw_two_factor_code = str(planner_inputs.get("two_factor_code") or "").strip()
    looks_like_totp = current_text.isdigit() and len(current_text) in {6, 8}
    if (
        current_text
        and current_text not in {secret, raw_two_factor_code, resolved_two_factor_code}
        and not looks_like_totp
    ):
        return next_params
    next_params["text"] = resolved_two_factor_code
    return next_params


def _normalize_locate_point_params(
    action_name: str,
    action_params: Mapping[str, object],
) -> dict[str, object]:
    next_params = {str(key): value for key, value in action_params.items()}
    if action_name != "ai.locate_point":
        return next_params
    if any(
        next_params.get(key) for key in ("prompt", "query", "instruction", "text", "description")
    ):
        return next_params
    goal = str(next_params.get("goal") or "").strip()
    if goal:
        next_params["query"] = goal
    return next_params


def _rewrite_text_entry_locate_params(
    action_name: str,
    action_params: Mapping[str, object],
    observation_state: Mapping[str, object] | None,
    *,
    last_action: Mapping[str, object] | None,
    previous_state_id: str,
    observation_requires_fallback: bool,
) -> dict[str, object]:
    next_params = {str(key): value for key, value in action_params.items()}
    if action_name != "ai.locate_point" or not observation_requires_fallback:
        return next_params
    state_id = _observation_state_id(observation_state)
    if state_id not in _TEXT_ENTRY_STATE_IDS:
        return next_params
    if _is_submit_keypress(last_action) and previous_state_id == state_id:
        submit_query = _TEXT_ENTRY_SUBMIT_QUERIES.get(state_id)
        if submit_query:
            for key in ("prompt", "query", "instruction", "text", "description"):
                if key in next_params:
                    next_params[key] = submit_query
                    break
            else:
                next_params["query"] = submit_query
        return next_params
    locate_text = " ".join(
        str(next_params.get(key) or "").strip().lower()
        for key in ("prompt", "query", "instruction", "text", "description")
    )
    if (
        state_id == "account"
        and locate_text
        and not any(token in locate_text for token in _FOCUS_LOCATE_TOKENS)
        and any(token in locate_text for token in _SUBMIT_LOCATE_TOKENS)
    ):
        submit_query = _TEXT_ENTRY_SUBMIT_QUERIES.get(state_id)
        if submit_query:
            for key in ("prompt", "query", "instruction", "text", "description"):
                if key in next_params:
                    next_params[key] = submit_query
                    break
            else:
                next_params["query"] = submit_query
        return next_params
    if _text_entry_ready_under_fallback(
        last_action=last_action,
        current_state_id=state_id,
        previous_state_id=previous_state_id,
    ):
        return next_params
    focus_query = _TEXT_ENTRY_FOCUS_QUERIES.get(state_id)
    if not focus_query:
        return next_params
    for key in ("prompt", "query", "instruction", "text", "description"):
        if key in next_params:
            next_params[key] = focus_query
            break
    else:
        next_params["query"] = focus_query
    return next_params


def _text_entry_ready_under_fallback(
    *,
    last_action: Mapping[str, object] | None,
    current_state_id: str,
    previous_state_id: str,
) -> bool:
    if current_state_id not in _TEXT_ENTRY_STATE_IDS:
        return True
    action = str(_json_dict(last_action).get("action") or "").strip()
    result = _json_dict(_json_dict(last_action).get("result"))
    if not bool(result.get("ok")):
        return False
    if action == "ui.input_text":
        return previous_state_id == current_state_id
    if action in {"ui.click", "selector_click_one", "node_click", "browser.click"}:
        return previous_state_id == current_state_id
    return False


def _is_submit_keypress(last_action: Mapping[str, object] | None) -> bool:
    action = str(_json_dict(last_action).get("action") or "").strip()
    if action != "ui.key_press":
        return False
    result = _json_dict(_json_dict(last_action).get("result"))
    if not bool(result.get("ok")):
        return False
    params = _json_dict(_json_dict(last_action).get("params"))
    return str(params.get("key") or "").strip().lower() == "enter"


def _observation_certainty(observation_payload: object, *, observation_ok: bool) -> str:
    if observation_ok:
        return "authoritative"
    observation = _json_dict(observation_payload)
    raw_details = _json_dict(observation.get("raw_details"))
    if str(raw_details.get("fallback_state_source") or "").strip():
        return "fallback_inferred"
    return "unknown"


def _observation_source(observation_payload: object, *, operation: str) -> str:
    observation = _json_dict(observation_payload)
    raw_details = _json_dict(observation.get("raw_details"))
    fallback_source = str(raw_details.get("fallback_state_source") or "").strip()
    if fallback_source:
        return fallback_source
    return operation or "match_state"


def _should_wait_through_loading_overlay(
    *,
    last_action: Mapping[str, object] | None,
    fallback_evidence: Mapping[str, object],
) -> bool:
    if not _fallback_indicates_loading(fallback_evidence):
        return False
    action = str(_json_dict(last_action).get("action") or "").strip()
    if action in {"", "ai.locate_point"}:
        return False
    result = _json_dict(_json_dict(last_action).get("result"))
    return bool(result.get("ok"))


def _dynamic_step_extension_size(base_max_steps: int) -> int:
    return min(_DYNAMIC_STEP_EXTENSION_CAP, max(_DYNAMIC_STEP_EXTENSION_MIN, base_max_steps // 4))


def _recent_observation_progress_score(
    history: list[dict[str, object]],
    *,
    last_observation: Mapping[str, object],
    window: int = _DYNAMIC_STEP_PROGRESS_WINDOW,
) -> int:
    recent = history[-window:] if len(history) > window else history
    fingerprints = [
        _stable_fingerprint(_json_dict(entry.get("observation")))
        for entry in recent
        if _json_dict(entry.get("observation"))
    ]
    last_observation_data = _json_dict(last_observation.get("data"))
    if last_observation_data:
        fingerprints.append(_stable_fingerprint(last_observation_data))
    return len(set(fingerprints))


def _recent_successful_mutation_count(
    history: list[dict[str, object]],
    *,
    window: int = _DYNAMIC_STEP_PROGRESS_WINDOW,
) -> int:
    recent = history[-window:] if len(history) > window else history
    count = 0
    for entry in recent:
        result = _json_dict(entry.get("result"))
        if not bool(result.get("ok")) or _is_non_mutating_action(entry):
            continue
        count += 1
    return count


def _is_action_contract_error(result_payload: Mapping[str, object] | None) -> bool:
    result = _json_dict(result_payload)
    if bool(result.get("ok")):
        return False
    code = str(result.get("code") or "").strip().lower()
    return code in _ACTION_CONTRACT_ERROR_CODES or code.startswith("invalid_")


def _dynamic_step_extension_reason(
    *,
    config: AgentExecutorConfig,
    history: list[dict[str, object]],
    last_observation: Mapping[str, object],
    last_action: Mapping[str, object] | None,
    stagnant_observation_count: int,
    repeated_action_count: int,
) -> str:
    if not history or last_action is None:
        return ""
    result = _json_dict(_json_dict(last_action).get("result"))
    if _is_action_contract_error(result):
        return ""
    if stagnant_observation_count >= max(1, config.stagnant_limit - 1):
        return ""
    if repeated_action_count >= 3:
        return ""
    fallback_evidence = _json_dict(last_observation.get("fallback_evidence"))
    if _fallback_indicates_loading(fallback_evidence):
        return "loading_overlay"
    if _is_submit_keypress(last_action):
        current_state_id = _observation_state_id(_json_dict(last_observation.get("data")))
        if current_state_id in {"unknown", "home"}:
            return "submit_transition_pending"
    progress_score = _recent_observation_progress_score(history, last_observation=last_observation)
    if progress_score >= 3:
        return "recent_progress"
    if (
        repeated_action_count <= 1
        and progress_score >= 2
        and _recent_successful_mutation_count(history) > 0
    ):
        return "successful_progress_signal"
    return ""


def _needs_form_submit(
    last_action: Mapping[str, object] | None,
    observation_state: Mapping[str, object] | None,
    *,
    previous_state_id: str,
) -> bool:
    observation_dict = _json_dict(observation_state)
    state_dict = _json_dict(observation_dict.get("state"))
    state_id = str(state_dict.get("state_id") or "").strip()
    if state_id not in _TEXT_ENTRY_STATE_IDS:
        return False
    action = str(_json_dict(last_action).get("action") or "").strip()
    if action != "ui.input_text":
        return False
    result = _json_dict(_json_dict(last_action).get("result"))
    return bool(result.get("ok")) and previous_state_id == state_id


def _submit_compensation_query(
    last_action: Mapping[str, object] | None,
    observation_state: Mapping[str, object] | None,
    *,
    previous_state_id: str,
) -> str:
    if not _is_submit_keypress(last_action):
        return ""
    observation_dict = _json_dict(observation_state)
    state_id = _observation_state_id(observation_dict)
    if state_id not in _TEXT_ENTRY_STATE_IDS or previous_state_id != state_id:
        return ""
    return _TEXT_ENTRY_SUBMIT_QUERIES.get(state_id, "")


def _vlm_allowed_action_types(allowed_actions: list[str]) -> set[str]:
    mapping = {
        "ui.click": "click",
        "ui.input_text": "type",
        "ui.swipe": "scroll",
        "ui.long_click": "long_press",
        "ui.key_press": "key",
    }
    allowed: set[str] = set()
    for action in allowed_actions:
        mapped = mapping.get(action)
        if mapped:
            allowed.add(mapped)
    allowed.add("finished")
    return allowed
