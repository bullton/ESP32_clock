# -*- coding: utf-8 -*-
"""
data.py - 数据层
===============

职责：把"数据从哪来"和"数据怎么画"分开。
"""

import datetime
import hashlib
import time
import zoneinfo
import requests

# ============================================================
# ⚙️ 配置区
# ============================================================

TZ_NAME = "Asia/Shanghai"          # 时区
CITY_NAME = "中国香港"             # 显示在城市名
CITY_QUERY = "Hong Kong,HK"        # OpenWeatherMap 查询用
USE_MOCK_WEATHER = False           # True=模拟数据 / False=真实 API

# OpenWeatherMap API Key（去 https://openweathermap.org/api 免费注册）
OWM_API_KEY = "30176d92a2e604078d274b5ad11abce0"

# 现场温度（DS18B20 传感器实测，None 表示未获取）
ENV_TEMP = None

# 模拟天气配置（USE_MOCK_WEATHER=True 时生效）
MOCK_CURRENT = {
    "cond":      "sunny",
    "temp":      26,
    "feels_like": 27,
    "humidity":   45,
    "wind":      "东南风 2级",
    "pressure":  1013,
}

WEEKLY_FORECAST = [
    {"date_offset": 0, "cond": "sunny",   "high": 28, "low": 19},
    {"date_offset": 1, "cond": "cloudy",  "high": 26, "low": 18},
    {"date_offset": 2, "cond": "rain",    "high": 23, "low": 17},
    {"date_offset": 3, "cond": "storm",   "high": 22, "low": 17},
    {"date_offset": 4, "cond": "cloudy",  "high": 25, "low": 18},
    {"date_offset": 5, "cond": "sunny",   "high": 29, "low": 20},
    {"date_offset": 6, "cond": "sunny",   "high": 30, "low": 21},
]

IMPORTANT_DATES = [
    {"name": "妈妈生日",  "date": "2026-09-15", "icon": "🎂"},
    {"name": "暑假开始",  "date": "2026-07-15", "icon": "🏖"},
    {"name": "开学",      "date": "2026-09-01", "icon": "🎒"},
]

# ============================================================
# 天气翻译表
# ============================================================

WEATHER_TABLE = {
    "sunny":    ("晴",    "☀"),
    "cloudy":   ("多云",  "☁"),
    "overcast": ("阴",    "☁"),
    "rain":     ("小雨",  "☂"),
    "storm":    ("雷阵雨", "⚡"),
    "snow":     ("雪",    "❄"),
    "fog":      ("雾",    "≋"),
}

# OpenWeatherMap 天气码映射到简化条件
OWM_TO_COND = {
    # 晴
    800: "sunny",
    # 多云
    801: "cloudy",
    802: "cloudy",
    803: "cloudy",
    804: "overcast",
    # 雨
    500: "rain",
    501: "rain",
    502: "rain",
    503: "rain",
    504: "rain",
    511: "rain",
    # 雷阵雨
    200: "storm",
    201: "storm",
    202: "storm",
    210: "storm",
    211: "storm",
    212: "storm",
    221: "storm",
    230: "storm",
    231: "storm",
    232: "storm",
    # 雪
    600: "snow",
    601: "snow",
    602: "snow",
    611: "snow",
    612: "snow",
    613: "snow",
    615: "snow",
    616: "snow",
    620: "snow",
    621: "snow",
    622: "snow",
    # 雾
    701: "fog",
    711: "fog",
    721: "fog",
    731: "fog",
    741: "fog",
    751: "fog",
    761: "fog",
    762: "fog",
    771: "fog",
    781: "fog",
}


def _owm_code_to_cond(code):
    """把 OpenWeatherMap 天气码转成简化条件"""
    return OWM_TO_COND.get(code, "sunny")


# ============================================================
# 1. 时间
# ============================================================

_time_cache = None
_last_minute = -1

def now(tz_name=TZ_NAME, client_time=None):
    """返回当前时间（dict），整分时才更新

    client_time: 可选，ESP32 传入的本地时间字符串 "YYYY-MM-DDTHH:MM:SS"。
                如果提供，用它替代服务端时间（避免 fetch+display 期间时间漂移）。
    """
    global _time_cache, _last_minute
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = None

    if client_time:
        # 用客户端时间（更准，因为 ESP32 在 fetch 开始时刻就锁定了时间）
        try:
            t = datetime.datetime.fromisoformat(client_time)
        except Exception:
            t = datetime.datetime.now(tz)
    else:
        t = datetime.datetime.now(tz)

    # 整分时才更新（分钟变化或首次调用）
    if _time_cache is None or t.minute != _last_minute:
        _time_cache = {
            "datetime":   t,
            "hour":       t.hour,
            "minute":     t.minute,
            "second":     t.second,
            "year":       t.year,
            "month":      t.month,
            "day":        t.day,
            "weekday":    t.weekday(),
            "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][t.weekday()],
            "date_cn":    f"{t.year}年{t.month}月{t.day}日",
            "time_str":   f"{t.hour:02d}:{t.minute:02d}",
            "iso":        t.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _last_minute = t.minute
    return _time_cache


# ============================================================
# 2. 天气
# ============================================================

def current_weather():
    """当前天气"""
    import data as _data_module
    if USE_MOCK_WEATHER:
        cond = MOCK_CURRENT["cond"]
        return {
            "city":      CITY_NAME,
            "cond":      cond,
            "cond_cn":   WEATHER_TABLE[cond][0],
            "icon":      WEATHER_TABLE[cond][1],
            "temp":      MOCK_CURRENT["temp"],
            "feels_like": MOCK_CURRENT["feels_like"],
            "humidity":  MOCK_CURRENT["humidity"],
            "wind":      MOCK_CURRENT["wind"],
            "pressure":   MOCK_CURRENT["pressure"],
            "env_temp":  _data_module.ENV_TEMP,
        }

    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY_QUERY}&appid={OWM_API_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        data = r.json()

        weather_code = data["weather"][0]["id"]
        cond = _owm_code_to_cond(weather_code)
        wind_deg = data["wind"].get("deg", 0)
        wind_dir = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"][int((wind_deg + 22.5) // 45) % 8]
        wind_speed = data["wind"].get("speed", 0)
        wind_level = min(int(wind_speed * 3.6 / 1.5 + 0.5), 12)  # m/s 转风级

        return {
            "city":      CITY_NAME,
            "cond":      cond,
            "cond_cn":   WEATHER_TABLE[cond][0],
            "icon":      WEATHER_TABLE[cond][1],
            "temp":      int(round(data["main"]["temp"])),
            "feels_like": int(round(data["main"]["feels_like"])),
            "humidity":  data["main"]["humidity"],
            "wind":      f"{wind_dir} {wind_level}级",
            "pressure":   data["main"]["pressure"],
            "env_temp":  _data_module.ENV_TEMP,
        }
    except Exception as e:
        print(f"天气 API 失败: {e}")
        # fallback 到模拟数据
        cond = MOCK_CURRENT["cond"]
        return {
            "city":      CITY_NAME,
            "cond":      cond,
            "cond_cn":   WEATHER_TABLE[cond][0],
            "icon":      WEATHER_TABLE[cond][1],
            "temp":      MOCK_CURRENT["temp"],
            "feels_like": MOCK_CURRENT["feels_like"],
            "humidity":  MOCK_CURRENT["humidity"],
            "wind":      MOCK_CURRENT["wind"],
            "pressure":   MOCK_CURRENT["pressure"],
            "env_temp":  _data_module.ENV_TEMP,
        }


def weekly_forecast():
    """未来 7 天预报"""
    if USE_MOCK_WEATHER:
        today = datetime.date.today()
        out = []
        for item in WEEKLY_FORECAST:
            d = today + datetime.timedelta(days=item["date_offset"])
            cond = item["cond"]
            if item["date_offset"] == 0:
                date_str = "今日"
            else:
                date_str = f"{d.month}/{d.day}"
            out.append({
                "date_str": date_str,
                "cond":       cond,
                "cond_cn":    WEATHER_TABLE[cond][0],
                "icon":       WEATHER_TABLE[cond][1],
                "high":       item["high"],
                "low":        item["low"],
            })
        return out

    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={CITY_QUERY}&appid={OWM_API_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        data = r.json()

        daily = {}
        for item in data["list"]:
            dt = datetime.datetime.fromtimestamp(item["dt"])
            day_key = dt.strftime("%Y-%m-%d")
            if day_key not in daily:
                daily[day_key] = {"temps": [], "codes": []}
            daily[day_key]["temps"].append(item["main"]["temp"])
            daily[day_key]["codes"].append(item["weather"][0]["id"])

        today = datetime.date.today()
        out = []
        for i in range(7):
            d = today + datetime.timedelta(days=i)
            day_key = d.strftime("%Y-%m-%d")
            if day_key in daily:
                temps = daily[day_key]["temps"]
                codes = daily[day_key]["codes"]
                cond_code = max(set(codes), key=codes.count)
                cond = _owm_code_to_cond(cond_code)
            else:
                temps = [20, 25]
                cond = "sunny"

            if i == 0:
                date_str = "今日"
            else:
                date_str = f"{d.month}/{d.day}"

            out.append({
                "date_str": date_str,
                "cond":     cond,
                "cond_cn":  WEATHER_TABLE[cond][0],
                "icon":     WEATHER_TABLE[cond][1],
                "high":     int(round(max(temps))),
                "low":      int(round(min(temps))),
            })
        return out
    except Exception as e:
        print(f"预报 API 失败: {e}")
        return weekly_forecast.__wrapped__()


# 保留模拟版本供 fallback 用
weekly_forecast.__wrapped__ = lambda: [
    {
        "date_str": "今日" if i == 0 else f"{(today := datetime.date.today() + datetime.timedelta(days=i)).month}/{(today := datetime.date.today() + datetime.timedelta(days=i)).day}",
        "cond": WEEKLY_FORECAST[i]["cond"],
        "cond_cn": WEATHER_TABLE[WEEKLY_FORECAST[i]["cond"]][0],
        "icon": WEATHER_TABLE[WEEKLY_FORECAST[i]["cond"]][1],
        "high": WEEKLY_FORECAST[i]["high"],
        "low": WEEKLY_FORECAST[i]["low"],
    }
    for i in range(7)
]


# ============================================================
# 3. 古诗（每日一首，同一天不变）
# ============================================================

POEMS = [
    "白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。",
]


def daily_poem():
    seed = datetime.date.today().isoformat()
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(POEMS)
    return POEMS[idx]


# ============================================================
# 4. 倒计时
# ============================================================

def countdowns(limit=3):
    today = datetime.date.today()
    items = []
    for it in IMPORTANT_DATES:
        target = datetime.date.fromisoformat(it["date"])
        delta = (target - today).days
        if delta >= 0:
            items.append({
                "name": it["name"],
                "icon": it["icon"],
                "days": delta,
                "date": it["date"],
            })
    items.sort(key=lambda x: x["days"])
    return items[:limit]


# ============================================================
# 5. 天气缓存（减少 API 请求）
# ============================================================

_weather_cache = None
_weather_cache_time = 0
WEATHER_CACHE_TTL = 300  # 天气缓存 5 分钟

def _get_weather(force_refresh=False):
    """获取天气（带缓存）"""
    global _weather_cache, _weather_cache_time
    now = time.time()
    if force_refresh or _weather_cache is None or (now - _weather_cache_time) > WEATHER_CACHE_TTL:
        _weather_cache = {
            "current": current_weather(),
            "weekly": weekly_forecast(),
        }
        _weather_cache_time = now
        print(f"[天气] 刷新缓存 (force={force_refresh})")
    else:
        print(f"[天气] 使用缓存 (age={int(now - _weather_cache_time)}s)")
    result = _weather_cache
    result["current"]["env_temp"] = ENV_TEMP
    return result


# ============================================================
# 6. 一站式入口
# ============================================================

def collect(force_refresh=False, client_time=None):
    weather = _get_weather(force_refresh)
    return {
        "now":       now(client_time=client_time),
        "current":   weather["current"],
        "weekly":    weather["weekly"],
        "poem":      daily_poem(),
        "countdowns": countdowns(),
    }
