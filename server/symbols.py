# -*- coding: utf-8 -*-
"""
symbols.py - 底栏可用的符号 / 表情清单，以及墨水屏降级规则
=========================================================

墨水屏是 1-bit 单色屏，中文字体（文泉驿 / 思源黑体）只覆盖 GBK 字符集。
彩色 emoji 无法直接显示，所以这里维护两件事：

1. SYMBOL_GROUPS —— 后台编辑器里的符号面板，全部选用 GBK 内字符，保证能画出来。
2. EMOJI_MAP     —— 常见 emoji 到单色文字的降级表，保存文本时自动替换。

如果服务器上放了真正的表情字体（server/fonts/*.ttf，文件名含 emoji），
渲染器会优先使用字体，不再降级。
"""

# ============================================================
# 1. 符号面板（全部为 GBK 内字符）
# ============================================================

_MARKS = [
    "★", "☆", "●", "○", "◎", "◆", "◇", "■", "□", "▲", "△", "※", "〓",
    "⊙", "∵", "∴", "∞", "√", "≈", "≠", "≤", "≥", "±", "×", "÷",
    "°", "℃", "§", "№", "♂", "♀", "—", "…", "·",
]

_ARROWS = ["→", "←", "↑", "↓"]

_NUMBERS = [chr(0x2460 + i) for i in range(10)] + [chr(0x2160 + i) for i in range(12)]

_WEATHER = ["晴", "云", "阴", "雨", "雪", "雷", "风", "雾", "霜", "露", "潮", "冷", "热"]

_KAOMOJI = [
    "(^_^)", "(^o^)", "(>_<)", "(T_T)", "(=_=)", "(~_~)",
    "orz", "○_○", "⊙_⊙", "★_★", "(^◇^)",
]


def _group(gid, name, chars):
    return {"id": gid, "name": name, "items": [{"ch": c} for c in chars]}


# ============================================================
# 2. 常见 emoji 降级表
# ============================================================

EMOJI_MAP = {
    # 情绪
    "😀": "笑", "😃": "笑", "😄": "笑", "😁": "笑", "😊": "微笑", "🙂": "微笑",
    "😍": "爱", "🥰": "爱", "😘": "亲", "😢": "哭", "😭": "大哭", "😡": "怒",
    "😴": "睡", "🥳": "庆祝", "😎": "酷", "🤔": "想",
    # 手势
    "👍": "赞", "👎": "踩", "👏": "赞", "🙏": "谢", "🤝": "合作", "✌️": "耶",
    # 天气
    "☀️": "晴", "☀": "晴", "🌞": "晴", "🌤️": "晴", "⛅": "多云", "☁️": "云",
    "☁": "云", "🌧️": "雨", "🌧": "雨", "☔": "雨", "🌂": "雨", "❄️": "雪",
    "❄": "雪", "⛄": "雪", "🌩️": "雷", "⚡": "雷", "🌀": "台风", "🌈": "彩虹",
    "🌙": "夜", "🌛": "夜", "🌫️": "雾", "🔥": "火",
    # 节日与事件
    "🎂": "生日", "🍰": "蛋糕", "🎉": "庆祝", "🎊": "庆祝", "🎁": "礼物",
    "🎄": "圣诞", "🎈": "气球", "🏆": "奖", "🚀": "火箭", "⚠️": "注意",
    "⚠": "注意", "✅": "√", "✔️": "√", "❌": "×", "✖️": "×", "💡": "想法",
    "📌": "记录", "📝": "记录", "📖": "书", "✏️": "写", "✏": "写",
    "🔔": "提醒", "⏰": "闹钟", "⏳": "等待", "📅": "日期", "💤": "睡",
    # 生活
    "🍚": "饭", "🍜": "面", "🍵": "茶", "☕": "茶", "🏖️": "度假", "🏖": "度假",
    "🎒": "开学", "🐱": "猫", "🐶": "狗", "🎵": "♪", "🎶": "♪", "❤️": "爱",
    "❤": "爱", "💔": "伤心", "⭐": "★", "🌟": "★", "✨": "★",
}


# ============================================================
# 3. 面板数据
# ============================================================

def groups():
    """返回编辑器符号面板的分组（emoji 组附带降级目标）"""
    emoji_items = [{"ch": ch, "fallback": repl} for ch, repl in EMOJI_MAP.items()]
    return [
        _group("mark", "标记", _MARKS),
        _group("arrow", "箭头", _ARROWS),
        _group("number", "序号", _NUMBERS),
        _group("weather", "天气", _WEATHER),
        _group("kaomoji", "颜文字", _KAOMOJI),
        {"id": "emoji", "name": "表情", "items": emoji_items},
    ]


def palette():
    """给前端用的完整面板数据"""
    return {
        "groups": groups(),
        "emoji_map": EMOJI_MAP,
        "note": "墨水屏为单色屏；没有表情字体时，表情会按降级表显示为对应文字或符号。",
    }


# ============================================================
# 4. 降级与检查
# ============================================================

_SAFE = set(_MARKS) | set(_ARROWS) | set(_NUMBERS) | set(_WEATHER)
for _k in _KAOMOJI:
    _SAFE |= set(_k)

_SKIP = {"\ufe0f", "\ufe0e", "\u200d", "\u20e3"}
_SKIN = (0x1F3FB, 0x1F3FF)


def _is_emoji_like(ch):
    cp = ord(ch)
    if cp in (0x200d, 0x20e3, 0xfe0e, 0xfe0f):
        return False
    if _SKIN[0] <= cp <= _SKIN[1]:
        return True
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x1F1E6 <= cp <= 0x1F1FF
        or 0x2190 <= cp <= 0x21FF
        or cp in (0x203C, 0x2049, 0x2122, 0x2139)
    )


def sanitize(text):
    """把无法显示的 emoji 换成可显示的等价内容（幂等）"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ch in text:
        if ch in _SKIP:
            continue
        cp = ord(ch)
        if _SKIN[0] <= cp <= _SKIN[1]:
            continue
        if ch in _SAFE:
            out.append(ch)
            continue
        repl = EMOJI_MAP.get(ch)
        if repl is not None:
            out.append(repl)
            continue
        if _is_emoji_like(ch):
            out.append("·")
            continue
        out.append(ch)
    return "".join(out)


def analyze(text):
    """返回会被降级的字符，用于在编辑器里提示"""
    downgraded = []
    unsupported = []
    for ch in text or "":
        if ch in _SKIP or ch == "\n":
            continue
        if ch in _SAFE:
            continue
        if ch in EMOJI_MAP:
            downgraded.append({"ch": ch, "to": EMOJI_MAP[ch]})
        elif _is_emoji_like(ch):
            unsupported.append(ch)
    return {"downgraded": downgraded, "unsupported": unsupported}
