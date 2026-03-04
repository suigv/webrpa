from typing import Any, Dict, TypedDict

class TouchPoint(TypedDict):
    x: int
    y: int

class Selector(TypedDict, total=False):
    text: str
    text_contains: str
    clickable: bool
    id: str
    class_name: str

class Node(TypedDict, total=False):
    text: str
    id: str
    class_name: str
    package: str
    desc: str
    bound: Dict[str, int]

class ActionResult(TypedDict, total=False):
    ok: bool
    code: str
    message: str
    data: Dict[str, Any]
