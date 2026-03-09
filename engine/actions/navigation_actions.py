from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from engine.models.runtime import ActionResult, ExecutionContext


@dataclass(frozen=True)
class RouteDefinition:
    route_id: str
    display_name: str
    binding_id: str
    current_state_ids: tuple[str, ...] = ("available", "missing")
    arrival_state_ids: tuple[str, ...] = ("available", "missing")


@dataclass(frozen=True)
class RouteAttempt:
    attempt_id: str
    description: str
    runner: Callable[[dict[str, object], ExecutionContext], ActionResult]


@dataclass(frozen=True)
class RouteHop:
    hop_id: str
    from_route: str
    to_route: str
    attempts: tuple[RouteAttempt, ...]


_ROUTES: dict[str, RouteDefinition] = {
    "home_timeline": RouteDefinition(
        route_id="home_timeline",
        display_name="home timeline",
        binding_id="timeline_candidates",
    ),
    "search_results": RouteDefinition(
        route_id="search_results",
        display_name="search results",
        binding_id="search_candidates",
    ),
    "messages_inbox": RouteDefinition(
        route_id="messages_inbox",
        display_name="messages inbox",
        binding_id="dm_unread",
    ),
}


def _load_ui_scheme(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import sdk_actions

    return sdk_actions.load_ui_scheme(params, context)


def _load_ui_selector(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import sdk_actions

    return sdk_actions.load_ui_selector(params, context)


def _exec_command(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    return ui_actions.exec_command(params, context)


def _app_open(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    return ui_actions.app_open(params, context)


def _selector_click_one(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    return ui_actions.selector_click_one(params, context)


def _ui_match_state(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_state_actions

    return ui_state_actions.ui_match_state(params, context)


def _resolve_device_ip(params: dict[str, object], context: ExecutionContext) -> str:
    payload = context.payload
    return str(
        params.get("device_ip")
        or context.get_session_default("device_ip")
        or payload.get("device_ip")
        or ""
    ).strip()


def _resolve_package(params: dict[str, object], context: ExecutionContext) -> str:
    payload = context.payload
    return str(
        params.get("package")
        or context.get_session_default("package")
        or payload.get("package")
        or "com.twitter.android"
    ).strip()


def _build_common_params(params: dict[str, object], context: ExecutionContext) -> dict[str, object]:
    common: dict[str, object] = {}
    device_ip = _resolve_device_ip(params, context)
    package = _resolve_package(params, context)
    if device_ip:
        common["device_ip"] = device_ip
    if package:
        common["package"] = package
    return common


def _run_home_scheme(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    scheme = _load_ui_scheme({"key": "home"}, context)
    if not scheme.ok:
        return scheme
    command = str((scheme.data or {}).get("command") or "").strip()
    if not command:
        return ActionResult(ok=False, code="ui_scheme_invalid", message="home scheme missing command")
    return _exec_command({**_build_common_params(params, context), "command": command}, context)


def _run_open_app(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    return _app_open(_build_common_params(params, context), context)


def _run_home_tab_click(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    selector = _load_ui_selector({"key": "home.nav_home"}, context)
    if not selector.ok:
        return selector
    selector_params = {**_build_common_params(params, context), **dict(selector.data or {})}
    _ = selector_params.pop("key", None)
    _ = selector_params.pop("locale", None)
    return _selector_click_one(selector_params, context)


def _resolve_search_query(params: dict[str, object]) -> str:
    return str(params.get("query") or params.get("search_query") or "").strip()


def _run_search_scheme(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    query = _resolve_search_query(params)
    if not query:
        return ActionResult(ok=False, code="invalid_params", message="query is required for search_results")
    scheme = _load_ui_scheme({"key": "search_query", "kwargs": {"query": query}}, context)
    if not scheme.ok:
        return scheme
    command = str((scheme.data or {}).get("command") or "").strip()
    if not command:
        return ActionResult(ok=False, code="ui_scheme_invalid", message="search scheme missing command")
    return _exec_command({**_build_common_params(params, context), "command": command}, context)


def _run_messages_scheme(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    scheme = _load_ui_scheme({"key": "messages"}, context)
    if not scheme.ok:
        return scheme
    command = str((scheme.data or {}).get("command") or "").strip()
    if not command:
        return ActionResult(ok=False, code="ui_scheme_invalid", message="messages scheme missing command")
    return _exec_command({**_build_common_params(params, context), "command": command}, context)


def _run_messages_tab_click(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    selector = _load_ui_selector({"key": "dm.nav_messages"}, context)
    if not selector.ok:
        return selector
    selector_params = {**_build_common_params(params, context), **dict(selector.data or {})}
    _ = selector_params.pop("key", None)
    _ = selector_params.pop("locale", None)
    return _selector_click_one(selector_params, context)


_HOPS: tuple[RouteHop, ...] = (
    RouteHop(
        hop_id="home_to_search_results",
        from_route="home_timeline",
        to_route="search_results",
        attempts=(RouteAttempt("open_search_scheme", "open search results scheme", _run_search_scheme),),
    ),
    RouteHop(
        hop_id="search_to_home_timeline",
        from_route="search_results",
        to_route="home_timeline",
        attempts=(
            RouteAttempt("open_home_scheme", "open home timeline scheme", _run_home_scheme),
            RouteAttempt("open_app_home", "open app for home fallback", _run_open_app),
            RouteAttempt("tap_home_tab", "tap home tab fallback", _run_home_tab_click),
        ),
    ),
    RouteHop(
        hop_id="home_to_messages_inbox",
        from_route="home_timeline",
        to_route="messages_inbox",
        attempts=(
            RouteAttempt("open_messages_scheme", "open messages scheme", _run_messages_scheme),
            RouteAttempt("tap_messages_tab", "tap messages tab fallback", _run_messages_tab_click),
        ),
    ),
    RouteHop(
        hop_id="messages_to_home_timeline",
        from_route="messages_inbox",
        to_route="home_timeline",
        attempts=(
            RouteAttempt("open_home_scheme", "open home timeline scheme", _run_home_scheme),
            RouteAttempt("open_app_home", "open app for home fallback", _run_open_app),
            RouteAttempt("tap_home_tab", "tap home tab fallback", _run_home_tab_click),
        ),
    ),
)

_GRAPH: dict[str, tuple[RouteHop, ...]] = {}
for _hop in _HOPS:
    existing = _GRAPH.get(_hop.from_route, tuple())
    _GRAPH[_hop.from_route] = (*existing, _hop)


def navigate_to(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    target = str(params.get("target") or "").strip()
    route = _ROUTES.get(target)
    if route is None:
        return ActionResult(ok=False, code="target_unreachable", message=f"unsupported navigation target: {target or 'unknown'}")

    current_route = _resolve_current_route(params, context)
    if current_route["route_id"] is None:
        return ActionResult(
            ok=False,
            code="unknown_current_state",
            message="unable to determine current navigation state",
            data={"target": target, "probes": current_route["probes"]},
        )

    current_id = str(current_route["route_id"])
    if current_id == target:
        return ActionResult(
            ok=True,
            code="ok",
            message=f"already at {route.display_name}",
            data={"target": target, "current_route": current_id, "noop": True, "path": []},
        )

    path = _resolve_path(current_id, target)
    if not path:
        return ActionResult(
            ok=False,
            code="target_unreachable",
            message=f"no bounded route from {current_id} to {target}",
            data={"target": target, "current_route": current_id},
        )

    history: list[dict[str, object]] = []
    active_route = current_id
    for hop in path:
        hop_result = _execute_hop(hop, params, context, active_route=active_route)
        history.append(hop_result)
        if hop_result["code"] != "ok":
            return ActionResult(
                ok=False,
                code=str(hop_result["code"]),
                message=str(hop_result["message"]),
                data={
                    "target": target,
                    "current_route": active_route,
                    "hop": hop.hop_id,
                    "history": history,
                },
            )
        active_route = hop.to_route

    return ActionResult(
        ok=True,
        code="ok",
        message=f"navigated to {route.display_name}",
        data={"target": target, "current_route": active_route, "noop": False, "path": [hop.hop_id for hop in path], "history": history},
    )


def _resolve_current_route(params: dict[str, object], context: ExecutionContext) -> dict[str, object]:
    matched_routes: list[str] = []
    probes: dict[str, dict[str, object]] = {}
    for route_id, route in _ROUTES.items():
        probe = _probe_route(route, params, context, state_ids=route.current_state_ids)
        probes[route_id] = probe
        if probe["matched"]:
            matched_routes.append(route_id)
    if len(matched_routes) == 1:
        return {"route_id": matched_routes[0], "probes": probes}
    return {"route_id": None, "probes": probes}


def _probe_route(
    route: RouteDefinition,
    params: dict[str, object],
    context: ExecutionContext,
    *,
    state_ids: tuple[str, ...],
) -> dict[str, object]:
    result = _ui_match_state(
        {
            **_build_common_params(params, context),
            "platform": "native",
            "binding_id": route.binding_id,
            "expected_state_ids": list(state_ids),
        },
        context,
    )
    state = cast(dict[str, object], result.data.get("state") or {})
    state_id = str(state.get("state_id") or "unknown")
    return {
        "binding_id": route.binding_id,
        "matched": bool(result.ok and state_id in state_ids),
        "code": result.code,
        "state_id": state_id,
        "message": result.message,
    }


def _resolve_path(start: str, target: str) -> list[RouteHop]:
    queue: deque[tuple[str, list[RouteHop]]] = deque([(start, [])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        for hop in _GRAPH.get(node, ()):  # pragma: no branch - bounded table
            next_path = [*path, hop]
            if hop.to_route == target:
                return next_path
            if hop.to_route in visited:
                continue
            visited.add(hop.to_route)
            queue.append((hop.to_route, next_path))
    return []


def _execute_hop(
    hop: RouteHop,
    params: dict[str, object],
    context: ExecutionContext,
    *,
    active_route: str,
) -> dict[str, object]:
    attempts: list[dict[str, object]] = []
    destination = _ROUTES[hop.to_route]
    for attempt in hop.attempts:
        action_result = attempt.runner(params, context)
        attempts.append(
            {
                "attempt_id": attempt.attempt_id,
                "description": attempt.description,
                "action_ok": action_result.ok,
                "action_code": action_result.code,
                "action_message": action_result.message,
            }
        )
        destination_probe = _probe_route(destination, params, context, state_ids=destination.arrival_state_ids)
        attempts[-1]["postcondition"] = destination_probe
        if destination_probe["matched"]:
            return {"code": "ok", "message": f"reached {destination.display_name}", "attempts": attempts}

    observed_route = _resolve_current_route(params, context)
    observed_id = observed_route["route_id"]
    if observed_id is not None and observed_id != active_route:
        observed = _ROUTES[str(observed_id)]
        return {
            "code": "state_drift_detected",
            "message": f"navigation drifted to {observed.display_name} while targeting {destination.display_name}",
            "attempts": attempts,
            "observed_route": observed_id,
        }
    return {
        "code": "target_unreachable",
        "message": f"unable to reach {destination.display_name} from {active_route}",
        "attempts": attempts,
        "observed_route": observed_id,
    }
