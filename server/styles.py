# -*- coding: utf-8 -*-
"""
styles.py - 字型/栅格化方案
==========================

墨水屏的字重与边缘观感由两个因素决定：
  1) 字体字重（regular / bold）
  2) 栅格化方式：直接单色绘制，或 N 倍超采样后按阈值二值化

后台可以选择不同方案对比，选择结果保存在 style.json，
设备下一次拉取 /api/screen 时生效。
"""

import json
import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.json")
_LOCK = threading.Lock()

DEFAULT_PROFILE = "classic"

PROFILES = [
    {
        "id": "classic",
        "label": "标准",
        "desc": "现在的线上效果，笔画偏细、小字有断笔",
        "weight": "regular",
        "aa": -1,
        "threshold": 0.5,
    },
    {
        "id": "bold",
        "label": "加粗",
        "desc": "换成粗体中文字形，笔画更实，边缘仍较硬",
        "weight": "bold",
        "aa": -1,
        "threshold": 0.5,
    },
    {
        "id": "smooth",
        "label": "平滑",
        "desc": "4× 超采样后按阈值取黑，斜线圆弧更顺，粗细可微调",
        "weight": "regular",
        "aa": 4,
        "threshold": 0.34,
    },
    {
        "id": "smooth_bold",
        "label": "平滑加粗",
        "desc": "粗体 + 4× 超采样，笔画最饱满，推荐",
        "weight": "bold",
        "aa": 4,
        "threshold": 0.33,
    },
    {
        "id": "heavy",
        "label": "超粗",
        "desc": "实验档：粗体 + 更低的取黑阈值，笔画最重，细小字可能粘连",
        "weight": "bold",
        "aa": 4,
        "threshold": 0.26,
    },
]

_BY_ID = {p["id"]: p for p in PROFILES}

_state = {"profile": DEFAULT_PROFILE, "threshold": None}


def _clamp_threshold(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0.30:
        return 0.30
    if number > 0.70:
        return 0.70
    return round(number, 3)


def _load():
    global _state
    try:
        with open(_PATH, "r", encoding="utf-8") as fp:
            saved = json.load(fp)
    except (OSError, ValueError):
        return
    profile = saved.get("profile")
    if profile in _BY_ID:
        _state["profile"] = profile
    _state["threshold"] = _clamp_threshold(saved.get("threshold"))


def _save():
    data = {"profile": _state["profile"], "threshold": _state["threshold"]}
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


_load()


def list_profiles():
    """给后台用的方案列表"""
    active = current()
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "desc": p["desc"],
            "weight": p["weight"],
            "aa": p["aa"],
            "threshold": p["threshold"],
            "current": p["id"] == active["id"],
        }
        for p in PROFILES
    ]


def get(profile_id):
    """返回方案副本（含生效阈值），未知 id 返回默认方案"""
    base = _BY_ID.get(profile_id) or _BY_ID[DEFAULT_PROFILE]
    profile = dict(base)
    if profile["aa"] > 0:
        override = _state["threshold"]
        profile["threshold"] = override if override is not None else base["threshold"]
    return profile


def current():
    return get(_state["profile"])


def current_id():
    return _state["profile"]


def threshold():
    return _state["threshold"]


def set_profile(profile_id, override_threshold=None):
    """切换方案，返回 (ok, message, profile)"""
    if profile_id not in _BY_ID:
        return False, "未知的方案", None

    clamped = _clamp_threshold(override_threshold)
    with _LOCK:
        _state["profile"] = profile_id
        if clamped is not None or override_threshold is None:
            _state["threshold"] = clamped
        try:
            _save()
        except OSError as exc:
            return False, f"保存失败：{exc}", None

    return True, "已切换，设备下次刷新时生效", current()
