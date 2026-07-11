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
# 香港公众假期 2026-2027
# ============================================================
HK_HOLIDAYS = {
    2026: [
        ("2026-01-01", "元旦"),
        ("2026-01-29", "农历新年"),
        ("2026-01-30", "农历新年"),
        ("2026-01-31", "农历新年"),
        ("2026-02-01", "农历新年补假"),
        ("2026-04-04", "清明节"),
        ("2026-04-05", "清明节补假"),
        ("2026-05-01", "劳动节"),
        ("2026-05-03", "佛诞补假"),
        ("2026-05-05", "佛诞"),
        ("2026-05-26", "端午节"),
        ("2026-05-31", "端午节补假"),
        ("2026-07-01", "香港回归纪念日"),
        ("2026-09-08", "中秋节"),
        ("2026-09-09", "中秋节翌日"),
        ("2026-10-01", "国庆日"),
        ("2026-10-02", "国庆日补假"),
        ("2026-10-07", "重阳节"),
        ("2026-10-08", "重阳节补假"),
        ("2026-12-25", "圣诞节"),
        ("2026-12-26", "圣诞节翌日"),
    ],
    2027: [
        ("2027-01-01", "元旦"),
        ("2027-02-17", "农历新年"),
        ("2027-02-18", "农历新年"),
        ("2027-02-19", "农历新年"),
        ("2027-02-20", "农历新年"),
        ("2027-02-21", "农历新年补假"),
        ("2027-04-05", "清明节"),
        ("2027-04-06", "清明节补假"),
        ("2027-05-01", "劳动节"),
        ("2027-05-03", "劳动节补假"),
        ("2027-05-26", "佛诞"),
        ("2027-06-15", "端午节"),
        ("2027-06-16", "端午节补假"),
        ("2027-07-01", "香港回归纪念日"),
        ("2027-09-15", "中秋节"),
        ("2027-09-16", "中秋节翌日"),
        ("2027-10-01", "国庆日"),
        ("2027-10-04", "国庆日补假"),
        ("2027-10-07", "重阳节"),
        ("2027-12-25", "圣诞节"),
        ("2027-12-26", "圣诞节翌日"),
        ("2027-12-27", "圣诞节补假"),
    ],
}

def get_holidays_month(year, month):
    """获取指定月份的公众假期"""
    holidays = HK_HOLIDAYS.get(year, [])
    lines = []
    for date_str, name in holidays:
        y, m, d = map(int, date_str.split("-"))
        if y == year and m == month:
            lines.append(f"{d}日 {name}")
    return lines if lines else [f"{month}月无公众假期"]


def get_today_holiday(year, month, day):
    """获取指定日期的公众假期名称；不是假期返回空字符串"""
    date_key = f"{year:04d}-{month:02d}-{day:02d}"
    holidays = HK_HOLIDAYS.get(year, [])
    for date_str, name in holidays:
        if date_str == date_key:
            return name
    return ""

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
    "wind_deg":  135,
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
            "holiday":    get_today_holiday(t.year, t.month, t.day),
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
            "wind_deg":  MOCK_CURRENT["wind_deg"],
            "pressure":   MOCK_CURRENT["pressure"],
            "env_temp":  _data_module.ENV_TEMP if hasattr(_data_module, 'ENV_TEMP') and _data_module.ENV_TEMP is not None else MOCK_CURRENT["temp"],
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
            "wind_deg":  wind_deg,
            "pressure":   data["main"]["pressure"],
            "env_temp":  _data_module.ENV_TEMP if hasattr(_data_module, 'ENV_TEMP') and _data_module.ENV_TEMP is not None else int(round(data["main"]["temp"])),
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
            "wind_deg":  MOCK_CURRENT["wind_deg"],
            "pressure":   MOCK_CURRENT["pressure"],
            "env_temp":  _data_module.ENV_TEMP if hasattr(_data_module, 'ENV_TEMP') and _data_module.ENV_TEMP is not None else MOCK_CURRENT["temp"],
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
# 香港天文台天气警告/预报 (flw)
# ============================================================

_hko_cache = None
_hko_cache_time = 0
HKO_CACHE_TTL = 900  # 15 分钟

_flw_cache = None
_flw_cache_time = 0
FLW_CACHE_TTL = 900  # 15 分钟


# 天气警告图标映射 (warningStatementCode + subtype -> icon filename)
# 参考 HKO Open Data API 文档 v1.13
WARNING_ICON_MAP = {
    # 热带气旋信号
    ("WTCSGNL", "TC1"):   "01_tc1.png",
    ("WTCSGNL", "TC3"):   "02_tc3.png",
    ("WTCSGNL", "TC8NE"): "03_tc08ne.png",
    ("WTCSGNL", "TC8NW"): "04_tc08nw.png",
    ("WTCSGNL", "TC8SE"): "05_tc08se.png",
    ("WTCSGNL", "TC8SW"): "06_tc08sw.png",
    ("WTCSGNL", "TC9"):   "07_tc09.png",
    ("WTCSGNL", "TC10"):  "08_tc10.png",
    # 暴雨警告
    ("WRAIN", "WRAINA"):  "09_rain_amber.png",
    ("WRAIN", "WRAINR"):  "10_rain_red.png",
    ("WRAIN", "WRAINB"):  "11_rain_black.png",
    # 其他警告（无 subtype 时按 code 匹配）
    ("WTS",      None):   "12_thunderstorm.png",
    ("WFNTSA",   None):   "13_north_flood.png",
    ("WL",       None):   "14_landslide.png",
    ("WMSGNL",   None):   "15_strong_monsoon.png",
    ("WFROST",   None):   "16_frost.png",
    ("WFIRE",    "WFIREY"): "17_fire_yellow.png",
    ("WFIRE",    "WFIRER"): "18_fire_red.png",
    ("WCOLD",    None):   "19_cold.png",
    ("WHOT",     None):   "20_hot.png",
    ("WTMW",     None):   "21_tsunami.png",
}


def get_warning_icon(statement_code, subtype=None):
    """根据 warningStatementCode 和 subtype 返回图标文件名，没匹配返回 None"""
    key = (statement_code, subtype)
    if key in WARNING_ICON_MAP:
        return WARNING_ICON_MAP[key]
    # 退回只用 code 匹配
    key2 = (statement_code, None)
    return WARNING_ICON_MAP.get(key2)


def get_hko_warning(force_refresh=False):
    """获取香港天文台天气警告信息，带 15 分钟缓存

    返回 dict:
        {
            "details": [
                {
                    "code": "WTS",            # warningStatementCode
                    "subtype": None,           # subtype（如有）
                    "name": "雷暴警告",         # 警告名稱
                    "icon": "12_thunderstorm.png",  # 图标文件名
                    "text": ["警告内容..."]    # contents 列表
                },
                ...
            ]
        }
    """
    global _hko_cache, _hko_cache_time
    now = time.time()
    if force_refresh or _hko_cache is None or (now - _hko_cache_time) > HKO_CACHE_TTL:
        try:
            import requests as _requests
            r = _requests.get(
                "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warningInfo&lang=sc",
                headers={"Accept-Encoding": "gzip"},
                timeout=10,
            )
            if r.status_code == 200:
                import json
                j = json.loads(r.text)
                details_raw = j.get("details", []) or []
                details = []
                for item in details_raw:
                    code = item.get("warningStatementCode", "")
                    subtype = item.get("subtype")
                    icon = get_warning_icon(code, subtype)
                    details.append({
                        "code":    code,
                        "subtype": subtype,
                        "name":    (item.get("contents", []) or [""])[0] or code,
                        "icon":    icon,
                        "text":    item.get("contents", []) or [],
                    })
                _hko_cache = {"details": details}
                _hko_cache_time = now
                print(f"[HKO] 刷新警告缓存: {len(details)} 条")
            else:
                print(f"[HKO] 请求失败: {r.status_code}")
        except Exception as e:
            print(f"[HKO] 获取失败: {e}")
            if _hko_cache is None:
                _hko_cache = {"details": []}
    else:
        print(f"[HKO] 使用缓存 (age={int(now - _hko_cache_time)}s)")
    return _hko_cache if _hko_cache else {"details": []}


def get_flw_warning(force_refresh=False):
    """获取香港天文台天气预报信息（flw API），带 15 分钟缓存

    返回 string（纯文本），包含 generalSituation 首句 + tcInfo
    """
    global _flw_cache, _flw_cache_time
    now = time.time()
    if force_refresh or _flw_cache is None or (now - _flw_cache_time) > FLW_CACHE_TTL:
        try:
            import requests as _requests
            r = _requests.get(
                "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=flw&lang=sc",
                headers={"Accept-Encoding": "gzip"},
                timeout=10,
            )
            if r.status_code == 200:
                import json
                j = json.loads(r.text)
                gs = j.get("generalSituation", "").strip()
                gs_first = gs.split("。")[0] + "。" if gs else ""
                tc = j.get("tcInfo", "").strip()
                parts = []
                if gs_first:
                    parts.append(gs_first)
                if tc:
                    parts.append(tc)
                _flw_cache = "\n".join(parts)
                _flw_cache_time = now
                print(f"[HKO] 刷新 flw 缓存: gs={bool(gs_first)} tc={bool(tc)}")
            else:
                print(f"[HKO] flw 请求失败: {r.status_code}")
        except Exception as e:
            print(f"[HKO] flw 获取失败: {e}")
            if _flw_cache is None:
                _flw_cache = ""
    else:
        print(f"[HKO] 使用 flw 缓存 (age={int(now - _flw_cache_time)}s)")
    return _flw_cache if _flw_cache else ""


# ============================================================
# 6. 一站式入口
# ============================================================

def tab_content(selected_tab, client_time=None):
    """根据选中标签返回对应内容"""
    poem = daily_poem()
    if selected_tab == "公众假期":
        now_ts = time.time() if client_time is None else _parse_client_time(client_time)
        local = datetime.datetime.fromtimestamp(now_ts, zoneinfo.ZoneInfo(TZ_NAME))
        holidays = get_holidays_month(local.year, local.month)
        return "\n".join(holidays)
    elif selected_tab == "天文信息":
        return "天文信息功能\n开发中..."
    elif selected_tab == "英文佳句":
        return "English quotes\ncoming soon..."
    elif selected_tab == "AI额度":
        return "AI额度功能\n开发中..."
    elif selected_tab == "菜单三":
        return "菜单三内容"
    elif selected_tab == "菜单四":
        return "菜单四内容"
    else:
        return poem

def _parse_client_time(client_time):
    """解析 client_time 字符串为 timestamp"""
    try:
        dt = datetime.datetime.fromisoformat(client_time.replace("T", " ").replace("Z", "+00:00"))
        return dt.timestamp()
    except:
        return time.time()

def collect(force_refresh=False, client_time=None, rssi=None):
    weather = _get_weather(force_refresh)
    bottom_custom = load_bottom_content()
    hko_warning = get_hko_warning(force_refresh)
    flw_warning = get_flw_warning(force_refresh)
    return {
        "now":           now(client_time=client_time),
        "current":       weather["current"],
        "weekly":        weather["weekly"],
        "countdowns":    countdowns(),
        "bottom":        bottom_custom,
        "weather_warning": hko_warning,  # dict: {"details": [...]}
        "flw_warning":   flw_warning,    # string (plain text)
        "rssi": rssi,
    }

def load_bottom_content():
    try:
        with open("bottom_content.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return ""
