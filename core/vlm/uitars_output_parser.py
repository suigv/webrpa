from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedAction:
    """Single action parsed from UI-TARS model output."""
    raw_action: str          # e.g. "click"
    args: dict[str, Any] = field(default_factory=dict)
    # Resolved pixel coordinates (populated after coords_to_pixel)
    x: int | None = None
    y: int | None = None
    x_pct: float | None = None
    y_pct: float | None = None
    coord_space: str = "pct"  # "pct" or "pixel"


@dataclass
class UITARSOutput:
    """Structured output from a single UI-TARS inference step."""
    thought: str             # <think>...</think> or empty
    raw_text: str            # full model output text
    actions: list[ParsedAction] = field(default_factory=list)


@dataclass
class UITarsAction:
    """Single mapped action for downstream execution or distillation."""
    raw_text: str
    raw_action: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    x: int | None = None
    y: int | None = None
    x_pct: float | None = None
    y_pct: float | None = None
    coord_space: str = "pct"

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "raw_action": self.raw_action,
            "action": self.action,
            "params": dict(self.params),
            "x": self.x,
            "y": self.y,
            "x_pct": self.x_pct,
            "y_pct": self.y_pct,
            "coord_space": self.coord_space,
        }


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches <think>...</think> (optional, non-greedy)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

# Matches   Action: click(start_box='<|box_start|>(x,y)<|box_end|>')
# or        Action: type(content='hello world')
# Captures action name + raw argument string
_ACTION_LINE_RE = re.compile(
    r"Action:\s*(\w+)\((.*)\)\s*$",
    re.MULTILINE | re.DOTALL,
)

# Matches a kwarg like key='value' or key="value"
_KWARG_STR_RE = re.compile(r"(\w+)='([^']*)'|(\w+)=\"([^\"]*)\"", re.DOTALL)

# Matches coordinate pair inside box tags: (x,y)  — percentage 0-1000
_BOX_COORD_RE = re.compile(
    r"<\|box_start\|>\s*\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)\s*<\|box_end\|>"
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_kwargs(raw_args: str) -> dict[str, str]:
    """Extract keyword arguments from a raw argument string."""
    result: dict[str, str] = {}
    for m in _KWARG_STR_RE.finditer(raw_args):
        if m.group(1):
            result[m.group(1)] = m.group(2)
        else:
            result[m.group(3)] = m.group(4)
    return result


def _extract_coord(value: str) -> tuple[float, float] | None:
    """Extract (x, y) percentage coordinates from a box-tag string."""
    m = _BOX_COORD_RE.search(value)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_uitars_output(text: str) -> UITARSOutput:
    """
    Parse raw UI-TARS model output into a structured UITARSOutput.

    Handles formats:
      - <think>...</think>\nAction: click(start_box='<|box_start|>(x,y)<|box_end|>')
      - Action: type(content='hello')
      - Action: scroll(start_box='...', direction='down', step_count='3')
      - Action: finished()
    """
    # 1. Extract thought
    think_match = _THINK_RE.search(text)
    thought = think_match.group(1).strip() if think_match else ""

    # 2. Extract all actions
    actions: list[ParsedAction] = []
    for m in _ACTION_LINE_RE.finditer(text):
        action_name = m.group(1).strip()
        raw_args = m.group(2).strip()
        kwargs = _parse_kwargs(raw_args)

        pa = ParsedAction(raw_action=action_name, args=kwargs)

        # Resolve coordinates from start_box / end_box
        for box_key in ("start_box", "end_box"):
            if box_key in kwargs:
                coord = _extract_coord(kwargs[box_key])
                if coord and pa.x is None:   # first coord wins for x/y
                    pa.x_pct = float(coord[0])
                    pa.y_pct = float(coord[1])
                    pa.x = int(coord[0])
                    pa.y = int(coord[1])

        actions.append(pa)

    return UITARSOutput(thought=thought, raw_text=text, actions=actions)


def coords_to_pixel(
    x_pct: int | float,
    y_pct: int | float,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """
    Convert UI-TARS percentage coordinates (0-1000 scale) to pixel coordinates.

    UI-TARS uses a 1000x1000 normalised coordinate space.
    """
    px = int(x_pct / 1000.0 * screen_width)
    py = int(y_pct / 1000.0 * screen_height)
    return px, py


def _clamp(value: int, *, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value


# ---------------------------------------------------------------------------
# Mapping: UI-TARS action -> project atomic action
# ---------------------------------------------------------------------------

# Keys: UI-TARS action names (lowercase)
# Values: project atomic action strings used by the engine
_ACTION_MAP: dict[str, str] = {
    "click": "ui.click",
    "left_click": "ui.click",
    "double_click": "ui.click",
    "right_click": "ui.click",
    "type": "ui.input_text",
    "scroll": "ui.swipe",
    "swipe": "ui.swipe",
    "key": "ui.key_press",
    "press": "ui.key_press",
    "long_press": "ui.long_click",
    "wait": "ui.wait",
    "finished": "task.finished",
    "call_user": "task.call_user",
}


def map_to_atomic_action(
    pa: ParsedAction,
    *,
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> dict[str, Any]:
    """
    Map a ParsedAction to a project atomic action dict compatible with
    the engine's step_record / distiller format.

    Returns a dict with keys:
      chosen_action  - str, e.g. "ui.click"
      action_params  - dict of parameters
    """
    atomic = _ACTION_MAP.get(pa.raw_action.lower(), pa.raw_action)

    params: dict[str, Any] = {}

    # Coordinates (convert pct -> px when screen size is known)
    if (
        pa.x_pct is not None
        and pa.y_pct is not None
        and screen_width
        and screen_height
        and pa.x_pct <= 1000
        and pa.y_pct <= 1000
    ):
        px, py = coords_to_pixel(pa.x_pct, pa.y_pct, screen_width, screen_height)
        params["x"] = px
        params["y"] = py
        pa.x = px
        pa.y = py
        pa.coord_space = "pixel"
    elif pa.x is not None and pa.y is not None:
        px = int(pa.x)
        py = int(pa.y)
        if screen_width and screen_height:
            px = _clamp(px, low=0, high=int(screen_width) - 1)
            py = _clamp(py, low=0, high=int(screen_height) - 1)
        params["x"] = px
        params["y"] = py
        pa.x = px
        pa.y = py
        pa.coord_space = "pixel"

    # Text input
    if "content" in pa.args:
        params["text"] = pa.args["content"]
    elif "text" in pa.args:
        params["text"] = pa.args["text"]

    # Scroll direction / steps
    if atomic == "ui.swipe":
        direction = str(pa.args.get("direction") or "").strip().lower()
        step_raw = pa.args.get("step_count")
        try:
            steps = int(step_raw) if step_raw is not None else 1
        except ValueError:
            steps = 1
        steps = max(1, steps)

        width = int(screen_width or 0)
        height = int(screen_height or 0)
        if width > 0 and height > 0:
            base_delta = int(height * 0.25)
            delta = max(100, base_delta) * steps
            start_x = params.get("x", int(width * 0.5))
            start_y = params.get("y", int(height * 0.5))
        else:
            delta = 300 * steps
            start_x = params.get("x", 500)
            start_y = params.get("y", 500)

        end_x, end_y = start_x, start_y
        if direction == "up":
            end_y = start_y - delta
        elif direction == "down":
            end_y = start_y + delta
        elif direction == "left":
            end_x = start_x - delta
        elif direction == "right":
            end_x = start_x + delta

        params.update({
            "x0": int(start_x),
            "y0": int(start_y),
            "x1": int(end_x),
            "y1": int(end_y),
            "duration": 300,
        })

    # Key / shortcut
    if "key" in pa.args:
        params["key"] = str(pa.args["key"]).lower()

    # Long press duration
    if atomic == "ui.long_click" and "duration" in pa.args:
        try:
            params["duration"] = float(pa.args["duration"])
        except (TypeError, ValueError):
            pass

    # Passthrough remaining unknown args
    known = {"content", "text", "start_box", "end_box", "direction", "step_count", "key", "duration"}
    for k, v in pa.args.items():
        if k not in known:
            params[k] = v

    return {"chosen_action": atomic, "action_params": params}


class UITarsOutputParser:
    """Parse UI-TARS text output and map to atomic actions."""

    def parse(
        self,
        raw_text: str,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> UITarsAction:
        parsed = parse_uitars_output(raw_text or "")
        if not parsed.actions:
            return UITarsAction(
                raw_text=raw_text or "",
                raw_action="",
                action="",
                params={},
            )

        action = parsed.actions[0]
        mapped = map_to_atomic_action(action, screen_width=screen_width, screen_height=screen_height)
        return UITarsAction(
            raw_text=raw_text or "",
            raw_action=action.raw_action,
            action=str(mapped.get("chosen_action") or ""),
            params=dict(mapped.get("action_params") or {}),
            x=action.x,
            y=action.y,
            x_pct=action.x_pct,
            y_pct=action.y_pct,
            coord_space=action.coord_space,
        )
