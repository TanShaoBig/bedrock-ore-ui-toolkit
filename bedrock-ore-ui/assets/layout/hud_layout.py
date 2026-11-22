# -*- coding: utf-8 -*-
"""Client-independent HUD layout math. Runs under the ModSDK Python 2.7 runtime."""
from __future__ import division
import json
import math

# Stable ID -> label, unscaled logical size, initial position in usable travel.
BUTTONS = {
    "entry": ("控件测试", (68, 18), (0.98, 0.15)),
    "layout": ("按钮布局", (54, 18), (0.98, 0.28)),
}
CONFIG_KEY = "orelab_hud_layout_v1"
PREFIX = "OREHUD1:"
LIMITS = {"x": (0, 1), "y": (0, 1), "scale": (0.6, 1.6), "alpha": (0.2, 1)}


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def defaults():
    return {key: dict(x=pos[0], y=pos[1], scale=1.0, alpha=1.0)
            for key, (_, size, pos) in BUTTONS.items()}


def normalize(data, strict=False):
    result = defaults()
    if not strict and (data is None or data == {}):
        return result
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("buttons"), dict):
        raise ValueError("unsupported HUD layout")
    buttons = data["buttons"]
    if strict and set(buttons) != set(result):
        raise ValueError("button set mismatch")
    for key, record in result.items():
        item = buttons.get(key)
        if not isinstance(item, dict):
            if strict:
                raise ValueError("invalid button")
            continue
        for field, (lo, hi) in LIMITS.items():
            try:
                raw = item[field]
                if isinstance(raw, bool):
                    raise ValueError()
                value = float(raw)
                if math.isinf(value) or math.isnan(value) or (strict and not lo <= value <= hi):
                    raise ValueError()
                record[field] = clamp(value, lo, hi)
            except (TypeError, ValueError, OverflowError, KeyError):
                if strict:
                    raise ValueError("invalid " + field)
    return result


def payload(layout):
    return {"version": 1, "buttons": {k: dict(v) for k, v in layout.items()}}


def encode(layout):
    return PREFIX + json.dumps(payload(layout), separators=(",", ":"), sort_keys=True)


def decode(text):
    if not text or len(text) > 16384 or not text.startswith(PREFIX):
        raise ValueError("invalid layout code")
    return normalize(json.loads(text[len(PREFIX):]), strict=True)


def geometry(key, item, area):
    base = BUTTONS[key][1]
    size = tuple(min(extent, max(1, int(round(raw * item["scale"]))))
                 for raw, extent in zip(base, area))
    travel = tuple(extent - length for extent, length in zip(area, size))
    pos = (item["x"] * travel[0], item["y"] * travel[1])
    return pos, size, travel


def drag_position(item, origin, delta, travel):
    for i, field in enumerate(("x", "y")):
        if travel[i] > 0:
            item[field] = clamp((origin[i] + delta[i]) / travel[i], 0.0, 1.0)
