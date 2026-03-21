from __future__ import annotations

from typing import Any, Callable


def apply_selector_query(
    selector: Any,
    params: dict[str, Any],
    *,
    to_int: Callable[[Any, int], int],
) -> tuple[bool, str | None, str | None]:
    query_type = str(params.get("type") or "").strip().lower()
    mode = str(params.get("mode") or "equal").strip().lower()
    value = str(params.get("value") or "")

    text_handlers = {
        "equal": selector.addQuery_Text,
        "contains": selector.addQuery_TextContain,
        "start_with": selector.addQuery_TextStartWith,
        "end_with": selector.addQuery_TextEndWith,
        "match": selector.addQuery_TextMatchWith,
    }
    id_handlers = {
        "equal": selector.addQuery_Id,
        "contains": selector.addQuery_IdContainWith,
        "start_with": selector.addQuery_IdStartWith,
        "end_with": selector.addQuery_IdEndWith,
        "match": selector.addQuery_IdMatchWith,
    }
    class_handlers = {
        "equal": selector.addQuery_Class,
        "contains": selector.addQuery_ClassContainWith,
        "start_with": selector.addQuery_ClassStartWith,
        "end_with": selector.addQuery_ClassEndWith,
        "match": selector.addQuery_ClassMatchWith,
    }
    desc_handlers = {
        "equal": selector.addQuery_Desc,
        "contains": selector.addQuery_DescContainWith,
        "start_with": selector.addQuery_DescStartWith,
        "end_with": selector.addQuery_DescEndWith,
        "match": selector.addQuery_DescMatchWith,
    }
    package_handlers = {
        "equal": selector.addQuery_Package,
        "contains": selector.addQuery_PackageContainWith,
        "start_with": selector.addQuery_PackageStartWith,
        "end_with": selector.addQuery_PackageEndWith,
        "match": selector.addQuery_PackageMatchWith,
    }

    if query_type == "text_contains":
        ok = selector.addQuery_TextContain(value)
    elif query_type == "text":
        handler = text_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported text mode: {mode}"
        ok = handler(value)
    elif query_type == "id":
        handler = id_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported id mode: {mode}"
        ok = handler(value)
    elif query_type == "class":
        handler = class_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported class mode: {mode}"
        ok = handler(value)
    elif query_type == "desc":
        handler = desc_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported desc mode: {mode}"
        ok = handler(value)
    elif query_type == "package":
        handler = package_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported package mode: {mode}"
        ok = handler(value)
    elif query_type == "bounds":
        ok = selector.addQuery_Bounds(
            to_int(params.get("left"), 0),
            to_int(params.get("top"), 0),
            to_int(params.get("right"), 0),
            to_int(params.get("bottom"), 0),
        )
    elif query_type == "bounds_inside":
        ok = selector.addQuery_BoundsInside(
            to_int(params.get("left"), 0),
            to_int(params.get("top"), 0),
            to_int(params.get("right"), 0),
            to_int(params.get("bottom"), 0),
        )
    elif query_type == "clickable":
        ok = selector.addQuery_Clickable(bool(params.get("enabled", True)))
    elif query_type == "enabled":
        ok = selector.addQuery_Enable(bool(params.get("enabled", True)))
    elif query_type == "checkable":
        ok = selector.addQuery_Checkable(bool(params.get("enabled", True)))
    elif query_type == "focusable":
        ok = selector.addQuery_Focusable(bool(params.get("enabled", True)))
    elif query_type == "focused":
        ok = selector.addQuery_Focused(bool(params.get("enabled", True)))
    elif query_type == "scrollable":
        ok = selector.addQuery_Scrollable(bool(params.get("enabled", True)))
    elif query_type == "long_clickable":
        ok = selector.addQuery_LongClickable(bool(params.get("enabled", True)))
    elif query_type == "password":
        ok = selector.addQuery_Password(bool(params.get("enabled", True)))
    elif query_type == "selected":
        ok = selector.addQuery_Selected(bool(params.get("enabled", True)))
    elif query_type == "visible":
        ok = selector.addQuery_Visible(bool(params.get("enabled", True)))
    elif query_type == "index":
        ok = selector.addQuery_Index(to_int(params.get("index"), 0))
    else:
        code = "invalid_params" if not query_type else "invalid_query_type"
        return False, code, f"unsupported selector query type: {query_type or 'empty'}"

    if not ok:
        return False, "query_add_failed", "failed to add selector query"
    return True, None, None
