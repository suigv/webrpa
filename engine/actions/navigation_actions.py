from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from engine.actions import ui_state_actions
from engine.models.runtime import ActionResult, ExecutionContext


@dataclass(frozen=True)
class RouteDefinition:
    route_id: str
    display_name: str
    state_profile_id: str
    platform: str
    current_state_ids: tuple[str, ...]
    arrival_state_ids: tuple[str, ...]


@dataclass(frozen=True)
class RouteAttempt:
    attempt_id: str
    description: str
    action: str
    params: dict[str, object]


@dataclass(frozen=True)
class RouteHop:
    hop_id: str
    from_route: str
    to_route: str
    attempts: tuple[RouteAttempt, ...]


def _coerce_state_ids(raw: object, *, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return fallback
    if isinstance(raw, str):
        values = tuple(part.strip() for part in raw.split(",") if part.strip())
        return values or fallback
    if isinstance(raw, (list, tuple)):
        values = tuple(str(part).strip() for part in raw if str(part).strip())
        return values or fallback
    return fallback


def _common_params(params: dict[str, object], context: ExecutionContext) -> dict[str, object]:
    common = params.get("common_params")
    if isinstance(common, dict):
        return dict(common)
    session_common = context.get_session_default("common_params")
    if isinstance(session_common, dict):
        return dict(session_common)
    return {}


def _resolve_route_state_profile_id(raw: dict[str, object]) -> str:
    return str(raw.get("state_profile_id") or raw.get("binding_id") or "").strip()


def _route_profile_identity(route: RouteDefinition) -> dict[str, str]:
    return {"state_profile_id": route.state_profile_id}


def _build_routes(
    params: dict[str, object], context: ExecutionContext
) -> tuple[dict[str, RouteDefinition], ActionResult | None]:
    raw_routes = params.get("routes") or context.get_session_default("routes")
    if not isinstance(raw_routes, dict) or not raw_routes:
        return {}, ActionResult(ok=False, code="invalid_params", message="routes is required")

    routes: dict[str, RouteDefinition] = {}
    for route_id, raw in raw_routes.items():
        if not route_id:
            continue
        if not isinstance(raw, dict):
            return {}, ActionResult(
                ok=False, code="invalid_params", message=f"invalid route definition: {route_id}"
            )
        state_profile_id = _resolve_route_state_profile_id(raw)
        if not state_profile_id:
            return {}, ActionResult(
                ok=False,
                code="invalid_params",
                message=f"state_profile_id is required for route: {route_id}",
            )
        display_name = str(raw.get("display_name") or route_id).strip() or str(route_id)
        platform = str(raw.get("platform") or "native").strip().lower() or "native"
        current_state_ids = _coerce_state_ids(
            raw.get("current_state_ids"), fallback=("available", "missing")
        )
        arrival_state_ids = _coerce_state_ids(
            raw.get("arrival_state_ids"), fallback=current_state_ids
        )
        routes[str(route_id)] = RouteDefinition(
            route_id=str(route_id),
            display_name=display_name,
            state_profile_id=state_profile_id,
            platform=platform,
            current_state_ids=current_state_ids,
            arrival_state_ids=arrival_state_ids,
        )
    if not routes:
        return {}, ActionResult(ok=False, code="invalid_params", message="routes is required")
    return routes, None


def _build_hops(
    params: dict[str, object], context: ExecutionContext
) -> tuple[tuple[RouteHop, ...], ActionResult | None]:
    raw_hops = params.get("hops") or context.get_session_default("hops") or []
    if not isinstance(raw_hops, list):
        return (), ActionResult(ok=False, code="invalid_params", message="hops must be a list")
    if not raw_hops:
        return (), None

    hops: list[RouteHop] = []
    for idx, raw in enumerate(raw_hops):
        if not isinstance(raw, dict):
            return (), ActionResult(
                ok=False, code="invalid_params", message=f"invalid hop definition at index {idx}"
            )
        from_route = str(raw.get("from_route") or "").strip()
        to_route = str(raw.get("to_route") or "").strip()
        if not from_route or not to_route:
            return (), ActionResult(
                ok=False,
                code="invalid_params",
                message=f"from_route/to_route required at hop index {idx}",
            )
        hop_id = str(raw.get("hop_id") or f"{from_route}_to_{to_route}").strip()
        raw_attempts = raw.get("attempts")
        if not isinstance(raw_attempts, list) or not raw_attempts:
            return (), ActionResult(
                ok=False, code="invalid_params", message=f"attempts required at hop index {idx}"
            )

        attempts: list[RouteAttempt] = []
        for attempt_idx, attempt_raw in enumerate(raw_attempts):
            if not isinstance(attempt_raw, dict):
                return (), ActionResult(
                    ok=False,
                    code="invalid_params",
                    message=f"invalid attempt at hop {hop_id} index {attempt_idx}",
                )
            action = str(attempt_raw.get("action") or "").strip()
            if not action:
                return (), ActionResult(
                    ok=False,
                    code="invalid_params",
                    message=f"action required at hop {hop_id} index {attempt_idx}",
                )
            attempt_id = str(attempt_raw.get("attempt_id") or f"{hop_id}_{attempt_idx}").strip()
            description = str(attempt_raw.get("description") or action).strip()
            attempt_params = attempt_raw.get("params")
            if attempt_params is None:
                attempt_params = {}
            if not isinstance(attempt_params, dict):
                return (), ActionResult(
                    ok=False,
                    code="invalid_params",
                    message=f"invalid params at hop {hop_id} index {attempt_idx}",
                )
            attempts.append(
                RouteAttempt(
                    attempt_id=attempt_id,
                    description=description,
                    action=action,
                    params=dict(attempt_params),
                )
            )
        hops.append(
            RouteHop(
                hop_id=hop_id,
                from_route=from_route,
                to_route=to_route,
                attempts=tuple(attempts),
            )
        )
    return tuple(hops), None


def _build_graph(hops: tuple[RouteHop, ...]) -> dict[str, tuple[RouteHop, ...]]:
    graph: dict[str, tuple[RouteHop, ...]] = {}
    for hop in hops:
        existing = graph.get(hop.from_route, ())
        graph[hop.from_route] = (*existing, hop)
    return graph


def _probe_route(
    route: RouteDefinition,
    params: dict[str, object],
    context: ExecutionContext,
    state_ids: tuple[str, ...],
) -> dict[str, object]:
    probe_params = {
        **_common_params(params, context),
        "platform": route.platform,
        **_route_profile_identity(route),
        "expected_state_ids": list(state_ids),
    }
    result = ui_state_actions.ui_match_state(probe_params, context)
    state = result.data.get("state") or {}
    state_id = str(getattr(state, "get", lambda *_: "unknown")("state_id") or "unknown")
    return {
        **_route_profile_identity(route),
        "matched": bool(result.ok and state_id in state_ids),
        "code": result.code,
        "state_id": state_id,
        "message": result.message,
    }


def _resolve_current_route(
    routes: dict[str, RouteDefinition], params: dict[str, object], context: ExecutionContext
) -> dict[str, object]:
    matched_routes: list[str] = []
    probes: dict[str, dict[str, object]] = {}
    for route_id, route in routes.items():
        probe = _probe_route(route, params, context, state_ids=route.current_state_ids)
        probes[route_id] = probe
        if probe["matched"]:
            matched_routes.append(route_id)
    if len(matched_routes) == 1:
        return {"route_id": matched_routes[0], "probes": probes}
    return {"route_id": None, "probes": probes}


def _resolve_path(
    graph: dict[str, tuple[RouteHop, ...]], start: str, target: str
) -> list[RouteHop]:
    queue: deque[tuple[str, list[RouteHop]]] = deque([(start, [])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        for hop in graph.get(node, ()):  # pragma: no branch
            next_path = [*path, hop]
            if hop.to_route == target:
                return next_path
            if hop.to_route in visited:
                continue
            visited.add(hop.to_route)
            queue.append((hop.to_route, next_path))
    return []


def _run_attempt(
    attempt: RouteAttempt, params: dict[str, object], context: ExecutionContext
) -> ActionResult:
    from engine.action_registry import resolve_action

    handler = resolve_action(attempt.action)
    merged_params = {**_common_params(params, context), **attempt.params}
    return handler(merged_params, context)


def _execute_hop(
    routes: dict[str, RouteDefinition],
    hop: RouteHop,
    params: dict[str, object],
    context: ExecutionContext,
    *,
    active_route: str,
) -> dict[str, object]:
    attempts: list[dict[str, object]] = []
    destination = routes[hop.to_route]
    for attempt in hop.attempts:
        action_result = _run_attempt(attempt, params, context)
        attempts.append(
            {
                "attempt_id": attempt.attempt_id,
                "description": attempt.description,
                "action_ok": action_result.ok,
                "action_code": action_result.code,
                "action_message": action_result.message,
            }
        )
        destination_probe = _probe_route(
            destination, params, context, state_ids=destination.arrival_state_ids
        )
        attempts[-1]["postcondition"] = destination_probe
        if destination_probe["matched"]:
            return {
                "code": "ok",
                "message": f"reached {destination.display_name}",
                "attempts": attempts,
            }

    observed_route = _resolve_current_route(routes, params, context)
    observed_id = observed_route["route_id"]
    if observed_id is not None and observed_id != active_route:
        observed = routes[str(observed_id)]
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


def navigate_to(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    routes, err = _build_routes(params, context)
    if err is not None:
        return err
    hops, err = _build_hops(params, context)
    if err is not None:
        return err

    target = str(params.get("target") or "").strip()
    if not target:
        return ActionResult(ok=False, code="invalid_params", message="target is required")
    route = routes.get(target)
    if route is None:
        return ActionResult(
            ok=False, code="target_unreachable", message=f"unsupported navigation target: {target}"
        )

    current_route = _resolve_current_route(routes, params, context)
    if current_route["route_id"] is None:
        probes_obj = current_route.get("probes")
        probes = probes_obj if isinstance(probes_obj, dict) else {}
        diag_msg = " | ".join(
            f"{key}:{value.get('state_id', '?')}" for key, value in probes.items()
        )
        return ActionResult(
            ok=False,
            code="unknown_current_state",
            message=f"unable to determine current state. probes: {diag_msg}",
            data={"target": target, "probes": probes},
        )

    current_id = str(current_route["route_id"])
    if current_id == target:
        return ActionResult(
            ok=True,
            code="ok",
            message=f"already at {route.display_name}",
            data={"target": target, "current_route": current_id, "noop": True, "path": []},
        )

    graph = _build_graph(hops)
    path = _resolve_path(graph, current_id, target)
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
        hop_result = _execute_hop(routes, hop, params, context, active_route=active_route)
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
        data={
            "target": target,
            "current_route": active_route,
            "noop": False,
            "path": [hop.hop_id for hop in path],
            "history": history,
        },
    )
