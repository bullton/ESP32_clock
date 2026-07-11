# -*- coding: utf-8 -*-
"""
renderer.py - 墨水屏渲染核心
==========================

完美方案（2026-06-21）：
  1. 字体：NotoSerifSC-VF（Google 高质量宋体，笔画精致）
  2. 渲染：2x 超采样（800×600 渲染 → LANCZOS 缩回 400×300）
     效果 = 亚像素抗锯齿，文字边缘极其平滑
  3. 二值化：干净阈值（无抖动），白区纯净无噪声
  4. 天气图标：纯 Pillow 几何绘制（精准控制，永不越界）
  5. emoji 改用 ASCII 字符（稳定可靠）
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont

try:
    import freetype
    HAVE_FREETYPE = True
except ImportError:
    HAVE_FREETYPE = False


W, H = 400, 300
WHITE = 255
BLACK = 0


# ============================================================
# 全局 mono 文本渲染（用 FreeType FT_LOAD_TARGET_MONO，无抗锯齿）
# ============================================================
def mono_text(img, xy, text, font, fill=BLACK):
    """用 FreeType mono 模式在 1-bit 图像上画文字（替代 draw.text）"""
    if not HAVE_FREETYPE:
        ImageDraw.Draw(img).text(xy, text, font=font, fill=fill)
        return
    try:
        size_px = font.size
        path = font.path
        m = get_mono(path, size_px)
        m.draw_text(img, xy, text, fill=fill)
    except Exception:
        ImageDraw.Draw(img).text(xy, text, font=font, fill=fill)


# Monkey-patch ImageDraw.Draw.text 使用 mono 渲染（笔画绝对等粗）
_original_text = ImageDraw.ImageDraw.text

def _patched_text(self, xy, text, fill=None, font=None, anchor=None, spacing=4, align="left", direction=None, features=None, language=None, stroke_width=0, stroke_fill=None, embedded_color=False):
    """用 mono 模式替代默认 draw.text"""
    if font is not None and HAVE_FREETYPE and hasattr(font, 'size') and hasattr(font, 'path'):
        try:
            m = get_mono(font.path, font.size)
            x, y = xy[0], xy[1]
            # 简化的 baseline 处理：原 draw.text 用左上角，mono_text 也用
            m.draw_text(self.im, (x, y), text, fill=fill if fill is not None else BLACK)
            return
        except Exception:
            pass
    return _original_text(self, xy, text, fill=fill, font=font, anchor=anchor,
                         spacing=spacing, align=align, direction=direction,
                         features=features, language=language,
                         stroke_width=stroke_width, stroke_fill=stroke_fill,
                         embedded_color=embedded_color)

ImageDraw.ImageDraw.text = _patched_text


# ============================================================
# FreeType 单色位图渲染（无抗锯齿，笔画绝对等粗）
# ============================================================
class MonoTextRenderer:
    """用 FreeType FT_LOAD_TARGET_MONO 渲染文本，无抗锯齿"""
    def __init__(self, font_path, size_px):
        self.face = freetype.Face(font_path)
        # size in 1/64 points
        self.face.set_char_size(size_px * 64)
        self.size_px = size_px
        self.ascent = self.face.size.ascender // 64
        self.descent = -self.face.size.descender // 64

    def text_size(self, text):
        """返回 (width, height)"""
        w = 0
        for ch in text:
            self.face.load_char(ch, freetype.FT_LOAD_TARGET_MONO)
            w += self.face.glyph.advance.x // 64
        return w, self.ascent + self.descent

    def draw_text(self, img, xy, text, fill=BLACK):
        """在 1-bit 图像上画文本"""
        x, y_baseline = xy
        for ch in text:
            self.face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
            bitmap = self.face.glyph.bitmap
            w, h = bitmap.width, bitmap.rows
            if w > 0 and h > 0:
                # 解包 1-bit packed buffer
                row_bytes = (w + 7) // 8
                buf = bytes(bitmap.buffer)
                # paste each pixel
                bx = self.face.glyph.bitmap_left
                by = y_baseline - self.face.glyph.bitmap_top
                for row in range(h):
                    for col in range(w):
                        byte_idx = row * row_bytes + (col // 8)
                        bit_mask = 0x80 >> (col % 8)
                        if byte_idx < len(buf) and (buf[byte_idx] & bit_mask):
                            px = bx + col
                            py = by + row
                            if 0 <= px < img.width and 0 <= py < img.height:
                                img.putpixel((px, py), fill)
            x += self.face.glyph.advance.x // 64


# 缓存 MonoTextRenderer 实例
_mono_cache = {}

def get_mono(font_path, size_px):
    key = (font_path, size_px)
    if key not in _mono_cache:
        _mono_cache[key] = MonoTextRenderer(font_path, size_px)
    return _mono_cache[key]


# ============================================================
# 字体（按优先级找高质量字体）
# ============================================================

def _find_font_paths():
    """找字体路径（不创建字体实例）"""
    ch_paths = [
        # 文泉驿正黑（等粗笔画，高分辨率显示效果好）
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "文泉驿正黑"),
        # 思源黑体
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "思源黑体 Regular"),
        (r"C:\Windows\Fonts\NotoSansSC-VF.ttf",      "思源黑体"),
        # 微软雅黑粗体
        ("/home/bullton/apps/clock/msyhbd.ttc",     "微软雅黑粗"),
        (r"C:\Windows\Fonts\msyhbd.ttc",             "微软雅黑粗"),
    ]
    ch_bold_paths = [
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "文泉驿正黑"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",   "思源黑体 Bold"),
        (r"C:\Windows\Fonts\NotoSansSC-VF.ttf",   "思源黑体"),
        ("/home/bullton/apps/clock/msyhbd.ttc",     "微软雅黑粗"),
        (r"C:\Windows\Fonts\msyhbd.ttc",           "微软雅黑粗"),
    ]
    emoji_paths = [
        r"C:\Windows\Fonts\seguiemj.ttf",
        r"C:\Windows\Fonts\seguisym.ttf",
    ]
    time_paths = [
        r"C:\Windows\Fonts\ariblk.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    ch_path = None
    for p, name in ch_paths:
        if os.path.exists(p):
            ch_path = p
            print(f"    中文字体: {name} ({os.path.basename(p)})")
            break

    emoji_path = None
    for p in emoji_paths:
        if os.path.exists(p):
            emoji_path = p
            break

    time_path = None
    for p in time_paths:
        if os.path.exists(p):
            time_path = p
            break

    ch_bold_path = None
    for p, name in ch_bold_paths:
        if os.path.exists(p):
            ch_bold_path = p
            print(f"    中文字体粗体: {name} ({os.path.basename(p)})")
            break

    return ch_path, emoji_path, time_path, ch_bold_path


_font_paths = None

def load_fonts():
    """返回各字号字体（每个字号独立创建实例）"""
    global _font_paths
    if _font_paths is None:
        _font_paths = _find_font_paths()

    ch_path, emoji_path, time_path, ch_bold_path = _font_paths

    if ch_path is None:
        default = ImageFont.load_default()
        return {k: default for k in "time title title_bold body small weather tiny date tab icon icon_big wi wi_big".split()}

    wi_path = os.path.join(os.path.dirname(__file__), "weathericons-regular-webfont.ttf")
    time_font_path = time_path if time_path else (r"C:\Windows\Fonts\ariblk.ttf" if os.path.exists(r"C:\Windows\Fonts\ariblk.ttf") else ch_path)
    bold_path = ch_bold_path if ch_bold_path else ch_path

    return {
        "time":     ImageFont.truetype(time_font_path, 56),
        "title":    ImageFont.truetype(ch_path, 20),
        "title_bold": ImageFont.truetype(bold_path, 20),
        "body":     ImageFont.truetype(ch_path, 18),
        "small":    ImageFont.truetype(ch_path, 16),
        "weather":  ImageFont.truetype(ch_path, 12),
        "tiny":     ImageFont.truetype(ch_path, 10),
        "date":     ImageFont.truetype(ch_path, 12),
        "tab":      ImageFont.truetype(ch_path, 12),
        "icon":     ImageFont.truetype(emoji_path, 20) if emoji_path else ImageFont.truetype(ch_path, 20),
        "icon_big": ImageFont.truetype(emoji_path, 32) if emoji_path else ImageFont.truetype(ch_path, 32),
        "wi":       ImageFont.truetype(wi_path, 20) if os.path.exists(wi_path) else None,
        "wi_big":   ImageFont.truetype(wi_path, 36) if os.path.exists(wi_path) else None,
    }


def load_fonts_2x():
    """返回 2x 分辨率字体（字号翻倍）"""
    global _font_paths
    if _font_paths is None:
        _font_paths = _find_font_paths()

    ch_path, emoji_path, time_path, ch_bold_path = _font_paths

    if ch_path is None:
        default = ImageFont.load_default()
        return {k: default for k in "time title title_bold body small weather tiny date tab icon icon_big wi wi_big".split()}

    wi_path = os.path.join(os.path.dirname(__file__), "weathericons-regular-webfont.ttf")
    time_font_path = time_path if time_path else (r"C:\Windows\Fonts\ariblk.ttf" if os.path.exists(r"C:\Windows\Fonts\ariblk.ttf") else ch_path)
    bold_path = ch_bold_path if ch_bold_path else ch_path

    return {
        "time":     ImageFont.truetype(time_font_path, 112),
        "title":    ImageFont.truetype(ch_path, 40),
        "title_bold": ImageFont.truetype(bold_path, 40),
        "body":     ImageFont.truetype(ch_path, 36),
        "small":    ImageFont.truetype(ch_path, 32),
        "weather":  ImageFont.truetype(ch_path, 24),
        "tiny":     ImageFont.truetype(ch_path, 20),
        "date":     ImageFont.truetype(ch_path, 24),
        "tab":      ImageFont.truetype(ch_path, 24),
        "icon":     ImageFont.truetype(emoji_path, 40) if emoji_path else ImageFont.truetype(ch_path, 40),
        "icon_big": ImageFont.truetype(emoji_path, 64) if emoji_path else ImageFont.truetype(ch_path, 64),
        "wi":       ImageFont.truetype(wi_path, 40) if os.path.exists(wi_path) else None,
        "wi_big":   ImageFont.truetype(wi_path, 72) if os.path.exists(wi_path) else None,
    }


# ============================================================
# 天气图标绘制（纯几何，绝对不越界）
# ============================================================

WI_MAP = {
    "sunny":    0xF00D,
    "cloudy":   0xF00C,
    "overcast": 0xF013,
    "rain":     0xF019,
    "storm":    0xF01E,
    "snow":     0xF076,
    "fog":      0xF003,
}

def _draw_sun(draw, cx, cy, r, fill):
    """画太阳：中心 + 8 条光线"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    ray_len = r * 0.6
    ray_w = max(1, r // 4)
    for angle in range(0, 360, 45):
        import math
        rad = math.radians(angle)
        x1 = cx + int(round(r * 0.85 * math.cos(rad)))
        y1 = cy + int(round(r * 0.85 * math.sin(rad)))
        x2 = cx + int(round((r + ray_len) * math.cos(rad)))
        y2 = cy + int(round((r + ray_len) * math.sin(rad)))
        draw.line([(x1, y1), (x2, y2)], fill=fill, width=ray_w)

def _draw_cloud(draw, cx, cy, r, fill):
    """画云朵：三个圆 + 底部平铺"""
    draw.ellipse([cx - r*1.4, cy - r*0.6, cx - r*0.2, cy + r*0.6], fill=fill)
    draw.ellipse([cx - r*0.7, cy - r*1.1, cx + r*0.7, cy + r*0.3], fill=fill)
    draw.ellipse([cx + r*0.1, cy - r*0.7, cx + r*1.2, cy + r*0.5], fill=fill)
    draw.rectangle([cx - r*1.5, cy, cx + r*1.3, cy + r*0.5], fill=fill)

def _draw_rain(draw, cx, cy, r, fill):
    """画雨滴：云 + 三条短线"""
    _draw_cloud(draw, cx, cy - r*0.2, r, fill)
    drop_y = cy + r
    for dx in [-r*0.5, 0, r*0.5]:
        draw.line([(cx + dx, drop_y), (cx + dx - r*0.2, drop_y + r*0.7)], fill=fill, width=max(1, r//3))

def _draw_storm(draw, cx, cy, r, fill):
    """画雷阵雨：云 + 闪电"""
    _draw_cloud(draw, cx, cy - r*0.2, r, fill)
    # 闪电
    import math
    pts = [
        (cx - r*0.1, cy - r*0.5),
        (cx + r*0.3, cy + r*0.1),
        (cx - r*0.1, cy + r*0.1),
        (cx + r*0.2, cy + r*0.8),
    ]
    draw.line(pts, fill=fill, width=max(1, r//4))

def _draw_snow(draw, cx, cy, r, fill):
    """画雪：云 + 雪花点"""
    _draw_cloud(draw, cx, cy - r*0.2, r, fill)
    for dx, dy in [(-r*0.4, r*0.5), (r*0.3, r*0.6), (0, r*0.8)]:
        draw.ellipse([cx+dx-r*0.2, cy+dy-r*0.2, cx+dx+r*0.2, cy+dy+r*0.2], fill=fill)

def _draw_fog(draw, cx, cy, r, fill):
    """画雾：三条波浪线"""
    import math
    for i, offset in enumerate([0, r*0.5, r]):
        y = cy + offset - r*0.5
        for x0 in range(cx - r*2, cx + r*2, r // 2):
            x1 = x0 + r // 2
            y1 = y + (r//4 if (x0//(r//2)) % 2 == 0 else -r//4)
            draw.line([(x0, y), (x1, y1)], fill=fill, width=max(1, r//4))

def _draw_wind_arrow(draw, cx, cy, size, deg, fill):
    """画风向箭头 (cx,cy) 为中心, deg为风向角度(北为0,顺时针)
       size: 箭头总大小"""
    import math
    r = size // 2
    rad = math.radians(deg - 90)
    x2 = cx + int(round(r * 0.7 * math.cos(rad)))
    y2 = cy + int(round(r * 0.7 * math.sin(rad)))
    rad1 = math.radians(deg - 90 - 30)
    rad2 = math.radians(deg - 90 + 30)
    x3 = cx + int(round(r * 0.35 * math.cos(rad1)))
    y3 = cy + int(round(r * 0.35 * math.sin(rad1)))
    x4 = cx + int(round(r * 0.35 * math.cos(rad2)))
    y4 = cy + int(round(r * 0.35 * math.sin(rad2)))
    draw.line([(cx, cy), (x2, y2)], fill=fill, width=max(1, size//6))
    draw.line([(x2, y2), (x3, y3)], fill=fill, width=max(1, size//6))
    draw.line([(x2, y2), (x4, y4)], fill=fill, width=max(1, size//6))

def draw_weather_icon(draw, cond, cx, cy, size, fill):
    """根据天气状况在 (cx, cy) 居中画图标"""
    r = size // 2
    if cond == "sunny":
        _draw_sun(draw, cx, cy, r, fill)
    elif cond == "cloudy" or cond == "overcast":
        _draw_cloud(draw, cx, cy, r, fill)
    elif cond == "rain":
        _draw_rain(draw, cx, cy, r, fill)
    elif cond == "storm":
        _draw_storm(draw, cx, cy, r, fill)
    elif cond == "snow":
        _draw_snow(draw, cx, cy, r, fill)
    elif cond == "fog":
        _draw_fog(draw, cx, cy, r, fill)
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


# ============================================================
# 布局（400x300 坐标）
# ============================================================

class Layout:
    W, H = 400, 300
    M = 8                     # 边距 px

    TOP_Y    = 12             # 顶部栏（字 baseline）
    DIV1_Y   = 32             # 分隔线1（Title底边）

    MAIN_TOP    = 36          # 主区域（时间+天气）顶部
    MAIN_BOTTOM = 127         # 主区域底部（91px高，+12）
    TIME_X2     = 196         # 时间右边界
    WEATHER_X1  = 204         # 天气左边界
    DIV2_Y      = 128         # 分隔线2（MAIN与FCST分隔，+12）

    FCST_Y      = 135         # 7日预报顶部（+12）
    FCST_H      = 74           # 7日预报高度
    FCST_BOTTOM = 206         # 7日预报底部（+12，上移8px）
    DIV3_Y      = 216         # 分隔线3（FCST与BOTTOM分隔，与BOTTOM_TOP重合）
    BOTTOM_TOP  = 212         # 古诗区域顶部（+12）
    BOTTOM_BOT  = 289         # 古诗区域底部（距底3px）
    TAB_H       = 24          # 底部菜单tab高度（上移4px）


# ============================================================
# 布局 2x（800x600 坐标）
# ============================================================

class Layout2x:
    W, H = 800, 600
    M = 16                    # 边距 px

    TOP_Y    = 24             # 顶部栏
    DIV1_Y   = 64             # 分隔线1（Title底边，2x）

    MAIN_TOP    = 72          # 主区域（时间+天气）顶部
    MAIN_BOTTOM = 254         # 主区域底部（+24 in 2x）
    TIME_X2     = 392         # 时间右边界
    WEATHER_X1  = 408         # 天气左边界
    DIV2_Y      = 256         # 分隔线2（MAIN与FCST分隔，+24）

    FCST_Y      = 270         # 7日预报顶部（+24）
    FCST_H      = 148         # 7日预报高度（2x of 74）
    FCST_BOTTOM = 412         # 7日预报底部（+24，上移8px）
    DIV3_Y      = 432         # 分隔线3（FCST与BOTTOM分隔，与BOTTOM_TOP重合）
    BOTTOM_TOP  = 424         # 古诗区域顶部（+24）
    BOTTOM_BOT  = 578         # 古诗区域底部（2x of 289）
    TAB_H       = 48          # 底部菜单tab高度（2x，上移4px）


# ============================================================
# Renderer 2x（高分辨率渲染）
# ============================================================

class Renderer2x:
    def __init__(self):
        self.fonts = load_fonts_2x()
        self.L = Layout2x()

    def _text_size(self, text, font):
        try:
            l, t, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), text, font=font)
            return r - l, b - t
        except AttributeError:
            return ImageDraw.Draw(Image.new("1", (1, 1))).textsize(text, font=font)

    def _hline(self, draw, y, x1=None, x2=None, w=1):
        x1 = x1 or self.L.M
        x2 = x2 or (self.L.W - self.L.M)
        draw.line([(x1, y), (x2, y)], fill=BLACK, width=w)

    def _vline(self, draw, x, y1, y2, w=1):
        draw.line([(x, y1), (x, y2)], fill=BLACK, width=w)

    def _centered_y(self, font, text, zone_top, zone_bottom):
        l, top, r, b = font.getbbox(text)
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        zone_center = (zone_top + zone_bottom) // 2
        return zone_center - visual_center_offset

    def _draw_border(self, draw):
        w = 2
        draw.rectangle([0, 0, self.L.W - 1, self.L.H - 1], outline=BLACK, width=w)

    def _draw_top_bar(self, draw, data):
        now = data["now"]
        city = data["current"]["city"]
        f = self.fonts["small"]
        f_tiny = self.fonts["tiny"]
        zone_center = (self.L.TOP_Y + self.L.DIV1_Y) // 2
        l, top, r, b = f.getbbox("Test")
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        y = zone_center - visual_center_offset
        date_x = self.L.M + 8
        holiday = now.get("holiday", "")
        # 始终用完整日期（含年份）
        date_str = now["date_cn"]
        draw.text((date_x, y), date_str, font=f, fill=BLACK)
        # 假期名紧跟日期后（小字体）
        holiday_end_x = date_x + self._text_size(date_str, f)[0]
        if holiday:
            date_tw, _ = self._text_size(date_str, f)
            l2, top2, r2, b2 = f_tiny.getbbox(holiday)
            visual_h2 = b2 - top2
            visual_center_offset2 = top2 + visual_h2 // 2
            y2 = zone_center - visual_center_offset2
            draw.text((date_x + date_tw + 6, y2), holiday, font=f_tiny, fill=BLACK)
            holiday_end_x = date_x + date_tw + 6 + self._text_size(holiday, f_tiny)[0]
        # 星期放在日期/假期之后
        wd = now["weekday_cn"]
        tw, _ = self._text_size(wd, f)
        wd_x = holiday_end_x + 8
        draw.text((wd_x, y), wd, font=f, fill=BLACK)
        # 城市+WiFi 在最右
        rssi = data.get("rssi")
        tw, _ = self._text_size(city, f)
        right_edge = self.L.W - self.L.M - 8
        city_x = right_edge - tw
        wifi_w = self._draw_wifi_icon(draw, city_x - 4, y, rssi)
        draw.text((city_x, y), city, font=f, fill=BLACK)
        self._hline(draw, self.L.DIV1_Y)

    def _draw_wifi_icon(self, draw, x, y, rssi):
        """在(x,y)位置画WiFi信号图标，x是右边界，y是文字基线，返回图标宽度"""
        icon_w = 12
        dot_r = 1
        cx = x - icon_w // 2
        dot_cy = y + 14
        dot_cx = cx
        draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill=BLACK)
        arcs = 3 if rssi is None or rssi >= -50 else (2 if rssi >= -70 else 1)
        radii = [2, 4, 6]
        for i in range(arcs):
            r = radii[i]
            top = dot_cy - r * 2
            left = dot_cx - r
            right = dot_cx + r
            draw.arc([left, top, right, top + r * 2], 180, 360, fill=BLACK, width=1)
        return icon_w

    def _draw_time(self, draw, data):
        t = data["now"]["time_str"]
        f = self.fonts["time"]
        tw, th = self._text_size(t, f)

        left_x1 = self.L.M + 8
        left_x2 = self.L.TIME_X2 - 8
        cx = (left_x1 + left_x2) // 2

        l, top, r, b = f.getbbox(t)
        visual_height = b - top
        visual_center_offset = top + visual_height // 2

        zone_center_y = (self.L.MAIN_TOP + self.L.MAIN_BOTTOM) // 2
        y = zone_center_y - visual_center_offset
        x = cx - tw // 2
        draw.text((x, y), t, font=f, fill=BLACK)

    def _draw_current_weather(self, draw, data):
        cw = data["current"]
        f_wi_big = self.fonts["wi_big"]
        f_w = self.fonts["weather"]

        zone_top = self.L.MAIN_TOP
        zone_bot = self.L.MAIN_BOTTOM

        env_temp = cw.get("env_temp") or cw.get("temp", 25.0)
        feels_like = cw.get("feels_like", cw["temp"])
        cond_str = cw["cond_cn"]
        wind_str = cw.get("wind", "")
        pressure_str = f'{cw["pressure"]}hPa'
        humidity_str = f'{cw.get("humidity", 0)}%'

        l, bbox_top, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), "温", font=f_w)
        margin = 4
        row_gap = 2
        row1_y = zone_top + margin - bbox_top

        row1_str = f'实时温度：{env_temp:.1f}°'
        row2_str = f'体感温度：{feels_like}°'
        row3_str = f'实时天气：{cond_str}'
        row4_str = f'风向风力：{wind_str}'
        row5_str = f'气压湿度：{pressure_str} / {humidity_str}'

        _, h1 = self._text_size(row1_str, f_w)
        row2_y = row1_y + h1 + row_gap
        _, h2 = self._text_size(row2_str, f_w)
        row3_y = row2_y + h2 + row_gap
        _, h3 = self._text_size(row3_str, f_w)
        row4_y = row3_y + h3 + row_gap
        _, h4 = self._text_size(row4_str, f_w)
        row5_y = row4_y + h4 + row_gap
        _, h5 = self._text_size(row5_str, f_w)

        col_x1 = self.L.WEATHER_X1 + 8
        col_x2 = self.L.W - self.L.M - 8
        col_w = col_x2 - col_x1

        text_col_x2 = col_x2 - col_w // 3 - 8

        three_rows_top = row1_y
        three_rows_bot = row3_y + h3
        three_rows_h = three_rows_bot - three_rows_top
        icon_cy = (three_rows_top + three_rows_bot) // 2

        icon_char = chr(WI_MAP.get(cw["cond"], 0xF00D))
        icon_bbox = f_wi_big.getbbox(icon_char)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]
        icon_cx = (text_col_x2 + col_x2) // 2
        y_icon = icon_cy - icon_h // 2 - icon_bbox[1]
        draw.text((icon_cx - icon_w // 2, y_icon), icon_char, font=f_wi_big, fill=BLACK)

        draw.text((col_x1, row1_y), row1_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row2_y), row2_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row3_y), row3_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row4_y), row4_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row5_y), row5_str, font=f_w, fill=BLACK)

    def _draw_weekly_forecast(self, draw, data):
        weekly = data["weekly"]
        col_w = (self.L.W - 2 * self.L.M) // 7
        x_start = self.L.M
        f_tiny = self.fonts["tiny"]
        f_date = self.fonts["date"]
        f_wi = self.fonts["wi"]

        if f_wi:
            max_wi_h = 0
            for day in weekly:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_h = wi_bbox[3] - wi_bbox[1]
                max_wi_h = max(max_wi_h, wi_h)

        _, base_lh = self._text_size("今日", f_date)
        label_y = self.L.FCST_Y

        for i, day in enumerate(weekly):
            cx = x_start + i * col_w + col_w // 2

            lbl = day["date_str"]
            lw, lh = self._text_size(lbl, f_date)
            draw.text((cx - lw // 2, label_y), lbl, font=f_date, fill=BLACK)

            icon_y = label_y + base_lh + 16
            if f_wi:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_w = wi_bbox[2] - wi_bbox[0]
                wi_h = wi_bbox[3] - wi_bbox[1]
                y_offset = (max_wi_h - wi_h) // 2
                draw.text((cx - wi_w // 2, icon_y + y_offset), icon_char, font=f_wi, fill=BLACK)
                temp_y = icon_y + max_wi_h + 16
            else:
                icon_sz = 32
                draw_weather_icon(draw, day["cond"], cx, icon_y + icon_sz // 2, icon_sz, BLACK)
                temp_y = icon_y + icon_sz + 16

            t_str = f'{day["high"]}°/{day["low"]}°'
            tw, th = self._text_size(t_str, f_tiny)
            draw.text((cx - tw // 2, temp_y), t_str, font=f_tiny, fill=BLACK)

    TABS = ["古诗", "英文佳句", "AI额度", "天文信息", "公众假期", "菜单三", "菜单四"]

    def _draw_menu_bar(self, draw, data):
        selected = data.get("selected_tab", "古诗")
        f_tab = self.fonts["tab"]
        tab_w = (self.L.W - 2 * self.L.M) / len(self.TABS)
        x_start = self.L.M
        for i, tab in enumerate(self.TABS):
            tx = x_start + int(i * tab_w)
            is_selected = (tab == selected)
            fill = BLACK if is_selected else WHITE
            next_tx = x_start + int((i + 1) * tab_w)
            draw.rectangle((tx, self.L.BOTTOM_TOP, next_tx, self.L.BOTTOM_TOP + self.L.TAB_H), fill=fill, outline=BLACK)
            tw, th = self._text_size(tab, f_tab)
            draw.text((tx + (next_tx - tx - tw) // 2, self.L.BOTTOM_TOP + (self.L.TAB_H - th) // 2), tab, font=f_tab, fill=WHITE if is_selected else BLACK)

    def _draw_poem(self, draw, data):
        poem = data["poem"]
        f = self.fonts["weather"]
        lines = poem.split('\n')

        line_widths = []
        for line in lines:
            text = f'「{line}」'
            tw, th = self._text_size(text, f)
            line_widths.append((text, tw))

        zone_h = self.L.BOTTOM_BOT - self.L.BOTTOM_TOP - self.L.TAB_H
        font_size = getattr(f, 'size', 12)
        ideal_line = font_size + 4
        ideal_gap = 4
        ideal_h = len(lines) * ideal_line + (len(lines) - 1) * ideal_gap
        scale = min(1.0, (zone_h - 1) / ideal_h)
        line_h = max(font_size, int(ideal_line * scale))
        gap = max(1, int(ideal_gap * scale))
        total_h = len(lines) * line_h + (len(lines) - 1) * gap
        if total_h > zone_h:
            gap = max(1, (zone_h - len(lines) * line_h) // (len(lines) - 1))
            total_h = len(lines) * line_h + (len(lines) - 1) * gap

        content_top = self.L.BOTTOM_TOP + self.L.TAB_H
        zone_center_y = (content_top + self.L.BOTTOM_BOT) // 2
        y = zone_center_y - total_h // 2

        for i, (text, tw) in enumerate(line_widths):
            x = (self.L.W - tw) // 2
            draw.text((x, y), text, font=f, fill=BLACK)
            y += line_h + gap

    def _wrap_text(self, text, font, max_width):
        """只按 \\n 换行；段落超出 max_width 时按字符强制换行"""
        if not text:
            return []
        lines = []
        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            tw, _ = self._text_size(paragraph, font)
            if tw <= max_width:
                lines.append(paragraph)
            else:
                current = ""
                for ch in paragraph:
                    test = current + ch
                    tw, _ = self._text_size(test, font)
                    if tw > max_width and current:
                        lines.append(current)
                        current = ch
                    else:
                        current = test
                if current:
                    lines.append(current)
        return lines

    def _draw_bottom_text(self, draw, data):
        bottom = data.get("bottom", "")
        weather_warning = data.get("weather_warning", {})
        flw_warning = data.get("flw_warning", "")
        minute = data.get("now", {}).get("minute", 0)

        warning_details = []
        if isinstance(weather_warning, dict):
            warning_details = weather_warning.get("details", []) or []
        elif isinstance(weather_warning, str):
            if weather_warning:
                warning_details = [{"text": weather_warning.split("\n"), "name": "警告", "icon": None, "code": "", "subtype": None}]

        f = self.fonts["weather"]
        content_top = self.L.BOTTOM_TOP + 4
        content_bot = self.L.BOTTOM_BOT - 4
        max_width = self.L.W - 32
        line_height = f.size + 4
        zone_h = content_bot - content_top
        max_lines = max(1, zone_h // line_height)

        icon_margin = 8
        icon_size_full = zone_h - icon_margin * 2

        def wrap_into_pages(text, page_max_w):
            if not text:
                return [[]]
            lines = self._wrap_text(text, f, page_max_w)
            if len(lines) <= max_lines:
                return [lines]
            return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]

        # Build warning pages: list of (text_lines, icons_list)
        warning_pages = []
        n_w = len(warning_details)

        if n_w == 0:
            pass
        elif n_w == 1:
            w = warning_details[0]
            icons = [w["icon"]] if w.get("icon") else []
            text = "\n".join((w.get("text", []) or [])[:2])
            if icons:
                pmw = max_width - (icon_size_full + 8)
            else:
                pmw = max_width
            for chunk in wrap_into_pages(text, pmw):
                warning_pages.append((chunk, icons))
        elif n_w == 2:
            icons = [w.get("icon") for w in warning_details if w.get("icon")]
            parts = []
            for w in warning_details:
                parts.extend((w.get("text", []) or [])[:2])
            text = "\n".join(parts)
            text_x_offset = 2 * icon_size_full + 4 + 8
            pmw = max_width - text_x_offset + 16
            for chunk in wrap_into_pages(text, pmw):
                warning_pages.append((chunk, icons))
        else:
            icons = [w.get("icon") for w in warning_details if w.get("icon")]
            warning_pages.append(([], icons))
            parts = []
            for w in warning_details:
                parts.extend((w.get("text", []) or [])[:2])
            text = "\n".join(parts)
            for chunk in wrap_into_pages(text, max_width):
                warning_pages.append((chunk, []))

        pages = []
        pages.extend(warning_pages)
        if flw_warning:
            for chunk in wrap_into_pages(flw_warning, max_width):
                pages.append((chunk, []))
        if bottom:
            for chunk in wrap_into_pages(bottom, max_width):
                pages.append((chunk, []))

        if not pages:
            return

        page_idx = minute % len(pages)
        lines, icons = pages[page_idx]
        n_icons = len(icons)

        if n_icons == 0:
            text_x = 16
            text_max_w = max_width
            icon_size = 0
            icon_y_for_text = 0
        elif n_icons == 1:
            icon_size = icon_size_full
            text_x = 16 + icon_size + 8
            text_max_w = max_width - (icon_size + 8)
        elif n_icons == 2:
            icon_size = icon_size_full
            text_x = 16 + 2 * icon_size + 4 + 8
            text_max_w = max_width - (2 * icon_size + 4 + 8)
        else:
            gap = 4
            icon_size = min(icon_size_full, (max_width - (n_icons - 1) * gap) // n_icons)
            total_w = n_icons * icon_size + (n_icons - 1) * gap
            start_x = (self.L.W - total_w) // 2
            icon_y_for_text = 0
            text_x = 16
            text_max_w = max_width

        if n_icons >= 3 and not lines:
            icon_y = content_top + (zone_h - icon_size) // 2
            for i, icon_name in enumerate(icons):
                ix = start_x + i * (icon_size + gap)
                self._draw_warning_icon(draw, icon_name, (ix, icon_y), icon_size)
            return

        if not lines:
            return

        total_h = line_height * len(lines)
        y_start = content_top + (zone_h - total_h) // 2 + 6

        max_text_h = line_height * max_lines
        y_start_max = content_top + (zone_h - max_text_h) // 2 + 6
        icon_y = y_start_max

        if n_icons == 1:
            self._draw_warning_icon(draw, icons[0], (16, icon_y), icon_size_full)
        elif n_icons == 2:
            icon1_x = 16
            icon2_x = icon1_x + icon_size_full + 4
            self._draw_warning_icon(draw, icons[0], (icon1_x, icon_y), icon_size_full)
            self._draw_warning_icon(draw, icons[1], (icon2_x, icon_y), icon_size_full)

        for i, line in enumerate(lines):
            l, top, r, b = f.getbbox(line)
            visual_h = b - top
            y = y_start + i * line_height + (line_height - visual_h) // 2 - top
            draw.text((text_x, y), line, font=f, fill=BLACK)

    def _draw_warning_icon(self, draw, icon_name, pos, size):
        import os
        icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon")
        icon_path = os.path.join(icon_dir, icon_name)
        if not os.path.exists(icon_path):
            return
        try:
            from PIL import Image
            img = Image.open(icon_path).convert("L")
            img = img.resize((size, size), Image.LANCZOS)
            draw._image.paste(img, pos)
        except Exception as e:
            print(f"[renderer] 加载图标失败 {icon_name}: {e}")

    def draw(self, data):
        img = Image.new("L", (self.L.W, self.L.H), WHITE)
        draw = ImageDraw.Draw(img)
        self._draw_border(draw)
        self._draw_top_bar(draw, data)

        self._hline(draw, self.L.DIV1_Y)

        mid_x = (self.L.TIME_X2 + self.L.WEATHER_X1) // 2
        self._draw_time(draw, data)
        self._draw_current_weather(draw, data)
        self._vline(draw, mid_x, self.L.MAIN_TOP, self.L.MAIN_BOTTOM)
        self._hline(draw, self.L.DIV2_Y)

        self._draw_weekly_forecast(draw, data)
        self._hline(draw, self.L.DIV3_Y)

        self._draw_bottom_text(draw, data)

        return img

    def render(self, data=None):
        if data is None:
            import data as _data
            data = _data.collect()
        img = self.draw(data)
        return img


# ============================================================
# Renderer
# ============================================================

class Renderer:
    def __init__(self):
        self.fonts = load_fonts()
        self.L = Layout()

    def _text_size(self, text, font):
        try:
            l, t, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), text, font=font)
            return r - l, b - t
        except AttributeError:
            return ImageDraw.Draw(Image.new("1", (1, 1))).textsize(text, font=font)

    def _hline(self, draw, y, x1=None, x2=None, w=1):
        x1 = x1 or self.L.M
        x2 = x2 or (self.L.W - self.L.M)
        draw.line([(x1, y), (x2, y)], fill=BLACK, width=w)

    def _vline(self, draw, x, y1, y2, w=1):
        draw.line([(x, y1), (x, y2)], fill=BLACK, width=w)

    def _centered_y(self, font, text, zone_top, zone_bottom):
        """计算文字绘制 y 坐标，使文字视觉中心对齐到 zone 中心"""
        l, top, r, b = font.getbbox(text)
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        zone_center = (zone_top + zone_bottom) // 2
        return zone_center - visual_center_offset

    def _text_left(self, draw, x, y, text, font):
        draw.text((x, y), text, font=font, fill=BLACK)

    def _text_right(self, draw, x, y, text, font):
        tw, _ = self._text_size(text, font)
        draw.text((x - tw, y), text, font=font, fill=BLACK)

    def _draw_border(self, draw):
        m = self.L.M
        draw.rectangle([m, m, self.L.W - m, self.L.H - m], outline=BLACK, width=1)

    def _draw_top_bar(self, draw, data):
        now = data["now"]
        city = data["current"]["city"]
        f = self.fonts["small"]
        f_tiny = self.fonts["tiny"]
        zone_center = (self.L.TOP_Y + self.L.DIV1_Y) // 2
        l, top, r, b = f.getbbox("Test")
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        y = zone_center - visual_center_offset
        date_x = self.L.M + 8
        holiday = now.get("holiday", "")
        # 始终用完整日期（含年份）
        date_str = now["date_cn"]
        draw.text((date_x, y), date_str, font=f, fill=BLACK)
        holiday_end_x = date_x + self._text_size(date_str, f)[0]
        if holiday:
            date_tw, _ = self._text_size(date_str, f)
            l2, top2, r2, b2 = f_tiny.getbbox(holiday)
            visual_h2 = b2 - top2
            visual_center_offset2 = top2 + visual_h2 // 2
            y2 = zone_center - visual_center_offset2
            draw.text((date_x + date_tw + 6, y2), holiday, font=f_tiny, fill=BLACK)
            holiday_end_x = date_x + date_tw + 6 + self._text_size(holiday, f_tiny)[0]
        # 星期放在日期/假期之后
        wd = now["weekday_cn"]
        tw, _ = self._text_size(wd, f)
        wd_x = holiday_end_x + 8
        draw.text((wd_x, y), wd, font=f, fill=BLACK)
        rssi = data.get("rssi")
        tw, _ = self._text_size(city, f)
        right_edge = self.L.W - self.L.M - 8
        city_x = right_edge - tw
        wifi_w = self._draw_wifi_icon(draw, city_x - 8, y, rssi)
        draw.text((city_x, y), city, font=f, fill=BLACK)
        self._hline(draw, self.L.DIV1_Y)

    def _draw_wifi_icon(self, draw, x, y, rssi):
        """在(x,y)位置画WiFi信号图标，x是右边界，y是文字基线，返回图标宽度"""
        icon_w = 12
        dot_r = 1
        cx = x - icon_w // 2
        dot_cy = y + 14
        dot_cx = cx
        draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill=BLACK)
        arcs = 3 if rssi is None or rssi >= -50 else (2 if rssi >= -70 else 1)
        radii = [2, 4, 6]
        for i in range(arcs):
            r = radii[i]
            top = dot_cy - r * 2
            left = dot_cx - r
            right = dot_cx + r
            draw.arc([left, top, right, top + r * 2], 180, 360, fill=BLACK, width=1)
        return icon_w

    def _draw_time(self, draw, data):
        t = data["now"]["time_str"]
        f = self.fonts["time"]
        tw, th = self._text_size(t, f)

        left_x1 = self.L.M + 4
        left_x2 = self.L.TIME_X2 - 4
        cx = (left_x1 + left_x2) // 2

        l, top, r, b = f.getbbox(t)
        visual_height = b - top
        visual_center_offset = top + visual_height // 2

        zone_center_y = (self.L.MAIN_TOP + self.L.MAIN_BOTTOM) // 2
        y = zone_center_y - visual_center_offset
        x = cx - tw // 2
        draw.text((x, y), t, font=f, fill=BLACK)

    def _draw_current_weather(self, draw, data):
        cw = data["current"]
        f_wi_big = self.fonts["wi_big"]
        f_w = self.fonts["weather"]

        zone_top = self.L.MAIN_TOP
        zone_bot = self.L.MAIN_BOTTOM

        env_temp = cw.get("env_temp") or cw.get("temp", 25.0)
        feels_like = cw.get("feels_like", cw["temp"])
        cond_str = cw["cond_cn"]
        wind_str = cw.get("wind", "")
        pressure_str = f'{cw["pressure"]}hPa'
        humidity_str = f'{cw.get("humidity", 0)}%'

        l, bbox_top, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), "温", font=f_w)
        margin = 8
        row_gap = 3
        row1_y = zone_top + margin - bbox_top

        row1_str = f'实时温度：{env_temp:.1f}°'
        row2_str = f'体感温度：{feels_like}°'
        row3_str = f'实时天气：{cond_str}'
        row4_str = f'风向风力：{wind_str}'
        row5_str = f'气压湿度：{pressure_str} / {humidity_str}'

        _, h1 = self._text_size(row1_str, f_w)
        row2_y = row1_y + h1 + row_gap
        _, h2 = self._text_size(row2_str, f_w)
        row3_y = row2_y + h2 + row_gap
        _, h3 = self._text_size(row3_str, f_w)
        row4_y = row3_y + h3 + row_gap
        _, h4 = self._text_size(row4_str, f_w)
        row5_y = row4_y + h4 + row_gap
        _, h5 = self._text_size(row5_str, f_w)

        col_x1 = self.L.WEATHER_X1 + 8
        col_x2 = self.L.W - self.L.M - 8
        col_w = col_x2 - col_x1

        text_col_x2 = col_x2 - col_w // 3 - 8

        three_rows_top = row1_y
        three_rows_bot = row3_y + h3
        three_rows_h = three_rows_bot - three_rows_top
        icon_cy = (three_rows_top + three_rows_bot) // 2

        icon_char = chr(WI_MAP.get(cw["cond"], 0xF00D))
        icon_bbox = f_wi_big.getbbox(icon_char)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]
        icon_cx = (text_col_x2 + col_x2) // 2
        y_icon = icon_cy - icon_h // 2 - icon_bbox[1]
        draw.text((icon_cx - icon_w // 2, y_icon), icon_char, font=f_wi_big, fill=BLACK)

        draw.text((col_x1, row1_y), row1_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row2_y), row2_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row3_y), row3_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row4_y), row4_str, font=f_w, fill=BLACK)
        draw.text((col_x1, row5_y), row5_str, font=f_w, fill=BLACK)

    def _draw_weekly_forecast(self, draw, data):
        weekly = data["weekly"]
        col_w = (self.L.W - 2 * self.L.M) // 7
        x_start = self.L.M
        f_tiny = self.fonts["tiny"]
        f_date = self.fonts["date"]
        f_wi = self.fonts["wi"]

        if f_wi:
            max_wi_h = 0
            for day in weekly:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_h = wi_bbox[3] - wi_bbox[1]
                max_wi_h = max(max_wi_h, wi_h)

        _, base_lh = self._text_size("今日", f_date)
        label_y = self.L.FCST_Y

        for i, day in enumerate(weekly):
            cx = x_start + i * col_w + col_w // 2

            lbl = day["date_str"]
            lw, lh = self._text_size(lbl, f_date)
            draw.text((cx - lw // 2, label_y), lbl, font=f_date, fill=BLACK)

            icon_y = label_y + base_lh + 8
            if f_wi:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_w = wi_bbox[2] - wi_bbox[0]
                wi_h = wi_bbox[3] - wi_bbox[1]
                y_offset = (max_wi_h - wi_h) // 2
                draw.text((cx - wi_w // 2, icon_y + y_offset), icon_char, font=f_wi, fill=BLACK)
                temp_y = icon_y + max_wi_h + 8
            else:
                icon_sz = 16
                draw_weather_icon(draw, day["cond"], cx, icon_y + icon_sz // 2, icon_sz, BLACK)
                temp_y = icon_y + icon_sz + 8

            t_str = f'{day["high"]}°/{day["low"]}°'
            tw, th = self._text_size(t_str, f_tiny)
            draw.text((cx - tw // 2, temp_y), t_str, font=f_tiny, fill=BLACK)

    TABS = ["古诗", "英文佳句", "AI额度", "天文信息", "公众假期", "菜单三", "菜单四"]

    def _draw_menu_bar(self, draw, data):
        selected = data.get("selected_tab", "古诗")
        f_tab = self.fonts["tab"]
        tab_w = (self.L.W - 2 * self.L.M) / len(self.TABS)
        x_start = self.L.M
        for i, tab in enumerate(self.TABS):
            tx = x_start + int(i * tab_w)
            is_selected = (tab == selected)
            fill = BLACK if is_selected else WHITE
            next_tx = x_start + int((i + 1) * tab_w)
            draw.rectangle((tx, self.L.BOTTOM_TOP, next_tx, self.L.BOTTOM_TOP + self.L.TAB_H), fill=fill, outline=BLACK)
            tw, th = self._text_size(tab, f_tab)
            draw.text((tx + (next_tx - tx - tw) // 2, self.L.BOTTOM_TOP + (self.L.TAB_H - th) // 2), tab, font=f_tab, fill=WHITE if is_selected else BLACK)

    def _draw_poem(self, draw, data):
        poem = data["poem"]
        f = self.fonts["weather"]
        lines = poem.split('\n')

        line_widths = []
        for line in lines:
            text = f'「{line}」'
            tw, th = self._text_size(text, f)
            line_widths.append((text, tw))

        zone_h = self.L.BOTTOM_BOT - self.L.BOTTOM_TOP - self.L.TAB_H
        line_h = 9
        gap = 5
        total_h = len(lines) * line_h + (len(lines) - 1) * gap

        content_top = self.L.BOTTOM_TOP + self.L.TAB_H
        zone_center_y = (content_top + self.L.BOTTOM_BOT) // 2
        y = zone_center_y - total_h // 2

        for i, (text, tw) in enumerate(line_widths):
            x = (self.L.W - tw) // 2
            draw.text((x, y), text, font=f, fill=BLACK)
            y += line_h + gap

    def _draw_countdown(self, draw, data):
        cds = data.get("countdowns", [])
        if not cds:
            return
        parts = []
        for it in cds[:2]:
            label = f'{it["name"]}'
            if it["days"] == 0:
                label += " 今天!"
            else:
                label += f" {it['days']}天"
            parts.append(label)
        line = "    ".join(parts)
        f = self.fonts["small"]
        tw, _ = self._text_size(line, f)

        right_x1 = self.L.FOOT_X1 + 8
        right_x2 = self.L.W - self.L.M - 8
        cx = (right_x1 + right_x2) // 2
        x = cx - tw // 2
        content_top = self.L.BOTTOM_TOP + self.L.TAB_H
        y = self._centered_y(f, line, content_top, self.L.BOTTOM_BOT)
        draw.text((x, y), line, font=f, fill=BLACK)

    def _wrap_text(self, text, font, max_width):
        """只按 \\n 换行；段落超出 max_width 时按字符强制换行"""
        if not text:
            return []
        lines = []
        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            tw, _ = self._text_size(paragraph, font)
            if tw <= max_width:
                lines.append(paragraph)
            else:
                current = ""
                for ch in paragraph:
                    test = current + ch
                    tw, _ = self._text_size(test, font)
                    if tw > max_width and current:
                        lines.append(current)
                        current = ch
                    else:
                        current = test
                if current:
                    lines.append(current)
        return lines

    def _draw_bottom_text(self, draw, data):
        bottom = data.get("bottom", "")
        weather_warning = data.get("weather_warning", {})
        flw_warning = data.get("flw_warning", "")
        minute = data.get("now", {}).get("minute", 0)

        warning_details = []
        if isinstance(weather_warning, dict):
            warning_details = weather_warning.get("details", []) or []
        elif isinstance(weather_warning, str):
            if weather_warning:
                warning_details = [{"text": weather_warning.split("\n"), "name": "警告", "icon": None, "code": "", "subtype": None}]

        f = self.fonts["weather"]
        content_top = self.L.BOTTOM_TOP + 4
        content_bot = self.L.BOTTOM_BOT - 4
        max_width = self.L.W - 32
        line_height = f.size + 4
        zone_h = content_bot - content_top
        max_lines = max(1, zone_h // line_height)

        icon_margin = 4
        icon_size_full = zone_h - icon_margin * 2

        def wrap_into_pages(text, page_max_w):
            if not text:
                return [[]]
            lines = self._wrap_text(text, f, page_max_w)
            if len(lines) <= max_lines:
                return [lines]
            return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]

        warning_pages = []
        n_w = len(warning_details)

        if n_w == 0:
            pass
        elif n_w == 1:
            w = warning_details[0]
            icons = [w["icon"]] if w.get("icon") else []
            text = "\n".join((w.get("text", []) or [])[:2])
            if icons:
                pmw = max_width - (icon_size_full + 4)
            else:
                pmw = max_width
            for chunk in wrap_into_pages(text, pmw):
                warning_pages.append((chunk, icons))
        elif n_w == 2:
            icons = [w.get("icon") for w in warning_details if w.get("icon")]
            parts = []
            for w in warning_details:
                parts.extend((w.get("text", []) or [])[:2])
            text = "\n".join(parts)
            text_x_offset = 2 * icon_size_full + 4 + 8
            pmw = max_width - text_x_offset + 16
            for chunk in wrap_into_pages(text, pmw):
                warning_pages.append((chunk, icons))
        else:
            icons = [w.get("icon") for w in warning_details if w.get("icon")]
            warning_pages.append(([], icons))
            parts = []
            for w in warning_details:
                parts.extend((w.get("text", []) or [])[:2])
            text = "\n".join(parts)
            for chunk in wrap_into_pages(text, max_width):
                warning_pages.append((chunk, []))

        pages = []
        pages.extend(warning_pages)
        if flw_warning:
            for chunk in wrap_into_pages(flw_warning, max_width):
                pages.append((chunk, []))
        if bottom:
            for chunk in wrap_into_pages(bottom, max_width):
                pages.append((chunk, []))

        if not pages:
            return

        page_idx = minute % len(pages)
        lines, icons = pages[page_idx]
        n_icons = len(icons)

        if n_icons == 0:
            text_x = 16
            text_max_w = max_width
            icon_size = 0
        elif n_icons == 1:
            icon_size = icon_size_full
            text_x = 16 + icon_size + 4
            text_max_w = max_width - (icon_size + 4)
        elif n_icons == 2:
            icon_size = icon_size_full
            text_x = 16 + 2 * icon_size + 4 + 8
            text_max_w = max_width - (2 * icon_size + 4 + 8)
        else:
            gap = 4
            icon_size = min(icon_size_full, (max_width - (n_icons - 1) * gap) // n_icons)
            total_w = n_icons * icon_size + (n_icons - 1) * gap
            start_x = (self.L.W - total_w) // 2
            text_x = 16
            text_max_w = max_width

        if n_icons >= 3 and not lines:
            icon_y = content_top + (zone_h - icon_size) // 2
            for i, icon_name in enumerate(icons):
                ix = start_x + i * (icon_size + gap)
                self._draw_warning_icon(draw, icon_name, (ix, icon_y), icon_size)
            return

        if not lines:
            return

        total_h = line_height * len(lines)
        y_start = content_top + (zone_h - total_h) // 2 + 6

        max_text_h = line_height * max_lines
        y_start_max = content_top + (zone_h - max_text_h) // 2 + 6
        icon_y = y_start_max

        if n_icons == 1:
            self._draw_warning_icon(draw, icons[0], (16, icon_y), icon_size_full)
        elif n_icons == 2:
            icon1_x = 16
            icon2_x = icon1_x + icon_size_full + 4
            self._draw_warning_icon(draw, icons[0], (icon1_x, icon_y), icon_size_full)
            self._draw_warning_icon(draw, icons[1], (icon2_x, icon_y), icon_size_full)

        for i, line in enumerate(lines):
            l, top, r, b = f.getbbox(line)
            visual_h = b - top
            y = y_start + i * line_height + (line_height - visual_h) // 2 - top
            draw.text((text_x, y), line, font=f, fill=BLACK)

    def _draw_warning_icon(self, draw, icon_name, pos, size):
        import os
        icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon")
        icon_path = os.path.join(icon_dir, icon_name)
        if not os.path.exists(icon_path):
            return
        try:
            from PIL import Image
            img = Image.open(icon_path).convert("L")
            img = img.resize((size, size), Image.LANCZOS)
            draw._image.paste(img, pos)
        except Exception as e:
            print(f"[renderer] 加载图标失败 {icon_name}: {e}")

    def draw(self, data):
        img = Image.new("1", (W, H), 1)  # 1 = WHITE in 1-bit mode
        draw = ImageDraw.Draw(img)
        self._draw_border(draw)
        self._draw_top_bar(draw, data)

        self._hline(draw, self.L.DIV1_Y)

        mid_x = (self.L.TIME_X2 + self.L.WEATHER_X1) // 2
        self._draw_time(draw, data)
        self._draw_current_weather(draw, data)
        self._vline(draw, mid_x, self.L.MAIN_TOP, self.L.MAIN_BOTTOM)
        self._hline(draw, self.L.DIV2_Y)

        self._draw_weekly_forecast(draw, data)
        self._hline(draw, self.L.DIV3_Y)

        self._draw_bottom_text(draw, data)

        return img

    def render(self, data=None):
        if data is None:
            import data as _data
            data = _data.collect()
        img = self.draw(data)
        return img, img.convert("L")


# ============================================================
# 全局便捷函数
# ============================================================

_renderer = None

def render(data=None):
    """返回 (img_1bit, img_800_raw) 元组"""
    global _renderer
    if _renderer is None:
        _renderer = Renderer()
    return _renderer.render(data)


def render_raw(data=None):
    """只返回 400x300 灰度原图"""
    global _renderer
    if _renderer is None:
        _renderer = Renderer()
    _, img_hi = _renderer.render(data)
    return img_hi


def render_hires(data=None):
    """2x 超采样：先在 800x600 渲染灰度，再缩到 400x300 并二值化"""
    if data is None:
        import data as _data
        data = _data.collect()

    r = Renderer2x()
    img_big = r.render(data)

    # 缩到 400x300：LANCZOS 平滑
    img_small = img_big.resize((W, H), Image.LANCZOS)

    # 灰度 → 1bit：Floyd-Steinberg 抖动（比硬阈值更平滑）
    img_gray_small = img_small.convert("L")
    img_1bit_small = img_gray_small.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    # 在缩小后的图上重画分割线（避免 1px 线被 LANCZOS 平均掉）
    draw = ImageDraw.Draw(img_1bit_small)
    for y in (Layout2x.DIV1_Y // 2, Layout2x.DIV2_Y // 2, Layout2x.DIV3_Y // 2):
        draw.line([(Layout.M, y), (Layout.W - Layout.M, y)], fill=BLACK, width=1)

    return img_1bit_small, img_small


def to_png_bytes(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_buffer(img, selected_tab="古诗", tabs=None):
    """PIL 1-bit Image → 15000 字节
    e-paper 用 0=BLACK, 1=WHITE 标准位序，直接 tobytes 即可"""
    expected = W * H // 8
    raw = img.tobytes()
    if len(raw) != expected:
        raise ValueError(f"位图长度 {len(raw)}，期望 {expected}")
    return bytes(raw)


def render_buffer(data=None):
    """一次性渲染并返回 15000 字节 raw buffer"""
    img = render(data)
    selected = data.get("selected_tab", "古诗") if data else "古诗"
    return to_buffer(img, selected_tab=selected)


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import data
    print("加载字体...")
    sample = data.collect()
    print("渲染中（2x 超采样）...")
    img = render(sample)
    img.save("sample.png", "PNG")
    buf = to_buffer(img)
    print(f"sample.png OK  模式={img.mode}  尺寸={img.size}  buffer={len(buf)} bytes")
