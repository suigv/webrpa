from typing import Callable, NotRequired, TypedDict

class TouchPoint(TypedDict):
    finger_id: NotRequired[int]
    x: int
    y: int
    duration: NotRequired[int]

class Selector(TypedDict, total=False):
    text: str
    text_contains: str
    text_contains_with: str
    clickable: bool
    id: str
    desc: str
    class_name: str
    package: str
    bounds: tuple[int, int, int, int]

class Node(TypedDict, total=False):
    text: str
    id: str
    class_name: str
    package: str
    desc: str
    bound: dict[str, int]
    children: list[object]

class ActionResult(TypedDict, total=False):
    ok: bool
    code: str
    message: str
    data: dict[str, object]


class ExecutionContext(TypedDict, total=False):
    payload: dict[str, object]
    vars: dict[str, object]
    last_result: ActionResult | None
    browser: object | None
    pc: int
    transitions: int
    jumped: bool
    should_cancel: Callable[[], bool] | None
