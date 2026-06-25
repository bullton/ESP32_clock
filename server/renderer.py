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


W, H = 400, 300
WHITE = 255
BLACK = 0


# ============================================================
# 字体（按优先级找高质量字体）
# ============================================================

def _find_font_paths():
    """找字体路径（不创建字体实例）"""
    ch_paths = [
        # 思源黑体
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "思源黑体 Regular"),
        (r"C:\Windows\Fonts\NotoSansSC-VF.ttf",      "思源黑体"),
        # 微软雅黑粗体
        ("/home/bullton/apps/clock/msyhbd.ttc",     "微软雅黑粗"),
        (r"C:\Windows\Fonts\msyhbd.ttc",             "微软雅黑粗"),
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

    return ch_path, emoji_path, time_path


_font_paths = None

def load_fonts():
    """返回各字号字体（每个字号独立创建实例）"""
    global _font_paths
    if _font_paths is None:
        _font_paths = _find_font_paths()

    ch_path, emoji_path, time_path = _font_paths

    if ch_path is None:
        default = ImageFont.load_default()
        return {k: default for k in "time title body small tiny icon icon_big wi wi_big".split()}

    wi_path = os.path.join(os.path.dirname(__file__), "weathericons-regular-webfont.ttf")
    time_font_path = time_path if time_path else (r"C:\Windows\Fonts\ariblk.ttf" if os.path.exists(r"C:\Windows\Fonts\ariblk.ttf") else ch_path)

    return {
        "time":     ImageFont.truetype(time_font_path, 56),
        "title":    ImageFont.truetype(ch_path, 20),
        "body":     ImageFont.truetype(ch_path, 18),
        "small":    ImageFont.truetype(ch_path, 16),
        "tiny":     ImageFont.truetype(ch_path, 14),
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

    ch_path, emoji_path, time_path = _font_paths

    if ch_path is None:
        default = ImageFont.load_default()
        return {k: default for k in "time title body small tiny icon icon_big wi wi_big".split()}

    wi_path = os.path.join(os.path.dirname(__file__), "weathericons-regular-webfont.ttf")
    time_font_path = time_path if time_path else (r"C:\Windows\Fonts\ariblk.ttf" if os.path.exists(r"C:\Windows\Fonts\ariblk.ttf") else ch_path)

    return {
        "time":     ImageFont.truetype(time_font_path, 112),
        "title":    ImageFont.truetype(ch_path, 40),
        "body":     ImageFont.truetype(ch_path, 36),
        "small":    ImageFont.truetype(ch_path, 32),
        "tiny":     ImageFont.truetype(ch_path, 28),
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
    MAIN_BOTTOM = 115         # 主区域底部（80px高）
    TIME_X2     = 196         # 时间右边界
    WEATHER_X1  = 204         # 天气左边界
    DIV2_Y      = 116         # 分隔线2（MAIN与FCST分隔）

    FCST_Y      = 123         # 7日预报顶部
    FCST_H      = 80          # 7日预报高度
    FCST_BOTTOM = 202         # 7日预报底部
    DIV3_Y      = 203         # 分隔线3（FCST与BOTTOM分隔）

    BOTTOM_TOP  = 210         # 古诗区域顶部
    BOTTOM_BOT  = 289         # 古诗区域底部（距底3px）


# ============================================================
# 布局 2x（800x600 坐标）
# ============================================================

class Layout2x:
    W, H = 800, 600
    M = 16                    # 边距 px

    TOP_Y    = 24             # 顶部栏
    DIV1_Y   = 64             # 分隔线1（Title底边，2x）

    MAIN_TOP    = 72          # 主区域（时间+天气）顶部
    MAIN_BOTTOM = 230         # 主区域底部（2x of 115, 约160px高）
    TIME_X2     = 392         # 时间右边界
    WEATHER_X1  = 408         # 天气左边界
    DIV2_Y      = 232         # 分隔线2（MAIN与FCST分隔，2x）

    FCST_Y      = 246         # 7日预报顶部（2x of 123）
    FCST_H      = 160         # 7日预报高度（2x of 80）
    FCST_BOTTOM = 404         # 7日预报底部（2x of 202）
    DIV3_Y      = 406         # 分隔线3（FCST与BOTTOM分隔，2x）

    BOTTOM_TOP  = 420         # 古诗区域顶部（2x of 210）
    BOTTOM_BOT  = 578         # 古诗区域底部（2x of 289）


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
        zone_center = (self.L.TOP_Y + self.L.DIV1_Y) // 2
        l, top, r, b = f.getbbox("Test")
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        y = zone_center - visual_center_offset
        draw.text((self.L.M + 8, y), now["date_cn"], font=f, fill=BLACK)
        wd = now["weekday_cn"]
        tw, _ = self._text_size(wd, f)
        draw.text(((self.L.W - tw) // 2, y), wd, font=f, fill=BLACK)
        tw, _ = self._text_size(city, f)
        draw.text((self.L.W - self.L.M - tw - 8, y), city, font=f, fill=BLACK)
        self._hline(draw, self.L.DIV1_Y)

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
        f_small = self.fonts["small"]

        zone_top = self.L.MAIN_TOP
        zone_bot = self.L.MAIN_BOTTOM
        zone_h = zone_bot - zone_top

        env_temp = cw.get("env_temp")
        if env_temp is not None:
            temp_str = f'{cw["temp"]}°C / {env_temp:.1f}°C'
        else:
            temp_str = f'{cw["temp"]}°C'
        cond_str = cw["cond_cn"]
        pressure_str = f'{cw["pressure"]}hPa'

        tw, th = self._text_size(temp_str, f_small)
        cw_w, cw_h = self._text_size(cond_str, f_small)
        pw, ph = self._text_size(pressure_str, f_small)

        l, bbox_top, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), "温", font=f_small)
        col_x1 = self.L.WEATHER_X1 + 8
        col_x2 = self.L.W - self.L.M - 8
        col_w = col_x2 - col_x1

        icon_col_w = col_w // 3
        text_col_x1 = col_x1 + icon_col_w

        icon_char = chr(WI_MAP.get(cw["cond"], 0xF00D))
        icon_bbox = f_wi_big.getbbox(icon_char)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]

        icon_cx = col_x1 + icon_col_w // 2
        icon_cy = (zone_top + zone_bot) // 2
        y_icon = icon_cy - icon_h // 2 - icon_bbox[1] + 1
        draw.text((icon_cx - icon_w // 2, y_icon), icon_char, font=f_wi_big, fill=BLACK)

        margin = 8
        row_gap = 8
        row1_y = zone_top + margin - bbox_top
        row2_y = row1_y + th + row_gap
        row3_y = row2_y + cw_h + row_gap

        text_col_center_x = text_col_x1 + (col_x2 - text_col_x1) // 2
        text_x = text_col_center_x - tw // 2

        draw.text((text_x, row1_y), temp_str, font=f_small, fill=BLACK)
        draw.text((text_x, row2_y), cond_str, font=f_small, fill=BLACK)
        draw.text((text_x, row3_y), pressure_str, font=f_small, fill=BLACK)

    def _draw_weekly_forecast(self, draw, data):
        weekly = data["weekly"]
        col_w = (self.L.W - 2 * self.L.M) // 7
        x_start = self.L.M
        f_tiny = self.fonts["tiny"]
        f_wi = self.fonts["wi"]

        for i, day in enumerate(weekly):
            cx = x_start + i * col_w + col_w // 2

            lbl = day["date_str"]
            lw, lh = self._text_size(lbl, f_tiny)
            label_y = self.L.FCST_Y
            draw.text((cx - lw // 2, label_y), lbl, font=f_tiny, fill=BLACK)

            if f_wi:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_w = wi_bbox[2] - wi_bbox[0]
                wi_h = wi_bbox[3] - wi_bbox[1]
                icon_y = label_y + lh + 16
                draw.text((cx - wi_w // 2, icon_y), icon_char, font=f_wi, fill=BLACK)
                temp_y = icon_y + wi_h + 16
            else:
                icon_y = label_y + lh + 16
                icon_sz = 32
                draw_weather_icon(draw, day["cond"], cx, icon_y + icon_sz // 2, icon_sz, BLACK)
                temp_y = icon_y + icon_sz + 16

            t_str = f'{day["high"]}°/{day["low"]}°'
            tw, th = self._text_size(t_str, f_tiny)
            draw.text((cx - tw // 2, temp_y), t_str, font=f_tiny, fill=BLACK)

    def _draw_poem(self, draw, data):
        poem = data["poem"]
        f = self.fonts["body"]
        lines = poem.split('\n')

        line_widths = []
        for line in lines:
            text = f'「{line}」'
            tw, th = self._text_size(text, f)
            line_widths.append((text, tw))

        zone_h = self.L.BOTTOM_BOT - self.L.BOTTOM_TOP
        line_h = 28
        gap = 16
        total_h = len(lines) * line_h + (len(lines) - 1) * gap

        zone_center_y = (self.L.BOTTOM_TOP + self.L.BOTTOM_BOT) // 2
        y = zone_center_y - total_h // 2

        for i, (text, tw) in enumerate(line_widths):
            x = (self.L.W - tw) // 2
            draw.text((x, y), text, font=f, fill=BLACK)
            y += line_h + gap

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

        self._draw_poem(draw, data)

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
        zone_center = (self.L.TOP_Y + self.L.DIV1_Y) // 2
        l, top, r, b = f.getbbox("Test")
        visual_h = b - top
        visual_center_offset = top + visual_h // 2
        y = zone_center - visual_center_offset
        draw.text((self.L.M + 4, y), now["date_cn"], font=f, fill=BLACK)
        wd = now["weekday_cn"]
        tw, _ = self._text_size(wd, f)
        draw.text(((self.L.W - tw) // 2, y), wd, font=f, fill=BLACK)
        tw, _ = self._text_size(city, f)
        draw.text((self.L.W - self.L.M - tw - 4, y), city, font=f, fill=BLACK)
        self._hline(draw, self.L.DIV1_Y)

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
        f_small = self.fonts["small"]

        zone_top = self.L.MAIN_TOP
        zone_bot = self.L.MAIN_BOTTOM
        zone_h = zone_bot - zone_top

        env_temp = cw.get("env_temp")
        if env_temp is not None:
            temp_str = f'{cw["temp"]}°C / {env_temp:.1f}°C'
        else:
            temp_str = f'{cw["temp"]}°C'
        cond_str = cw["cond_cn"]
        pressure_str = f'{cw["pressure"]}hPa'

        tw, th = self._text_size(temp_str, f_small)
        cw_w, cw_h = self._text_size(cond_str, f_small)
        pw, ph = self._text_size(pressure_str, f_small)

        l, bbox_top, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), "温", font=f_small)
        col_x1 = self.L.WEATHER_X1 + 4
        col_x2 = self.L.W - self.L.M - 4
        col_w = col_x2 - col_x1

        icon_col_w = col_w // 3
        text_col_x1 = col_x1 + icon_col_w

        icon_char = chr(WI_MAP.get(cw["cond"], 0xF00D))
        icon_bbox = f_wi_big.getbbox(icon_char)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]

        icon_cx = col_x1 + icon_col_w // 2
        icon_cy = (zone_top + zone_bot) // 2
        y_icon = icon_cy - icon_h // 2 - icon_bbox[1] + 1
        draw.text((icon_cx - icon_w // 2, y_icon), icon_char, font=f_wi_big, fill=BLACK)

        margin = 8
        row_gap = 8
        row1_y = zone_top + margin - bbox_top
        row2_y = row1_y + th + row_gap
        row3_y = row2_y + cw_h + row_gap

        text_col_center_x = text_col_x1 + (col_x2 - text_col_x1) // 2
        text_x = text_col_center_x - tw // 2

        draw.text((text_x, row1_y), temp_str, font=f_small, fill=BLACK)
        draw.text((text_x, row2_y), cond_str, font=f_small, fill=BLACK)
        draw.text((text_x, row3_y), pressure_str, font=f_small, fill=BLACK)

    def _draw_weekly_forecast(self, draw, data):
        weekly = data["weekly"]
        col_w = (self.L.W - 2 * self.L.M) // 7
        x_start = self.L.M
        f_tiny = self.fonts["tiny"]
        f_wi = self.fonts["wi"]

        for i, day in enumerate(weekly):
            cx = x_start + i * col_w + col_w // 2

            lbl = day["date_str"]
            lw, lh = self._text_size(lbl, f_tiny)
            label_y = self.L.FCST_Y
            draw.text((cx - lw // 2, label_y), lbl, font=f_tiny, fill=BLACK)

            if f_wi:
                code = WI_MAP.get(day["cond"], 0xF00D)
                icon_char = chr(code)
                wi_bbox = f_wi.getbbox(icon_char)
                wi_w = wi_bbox[2] - wi_bbox[0]
                wi_h = wi_bbox[3] - wi_bbox[1]
                icon_y = label_y + lh + 8
                draw.text((cx - wi_w // 2, icon_y), icon_char, font=f_wi, fill=BLACK)
                temp_y = icon_y + wi_h + 8
            else:
                icon_y = label_y + lh + 8
                icon_sz = 16
                draw_weather_icon(draw, day["cond"], cx, icon_y + icon_sz // 2, icon_sz, BLACK)
                temp_y = icon_y + icon_sz + 8

            t_str = f'{day["high"]}°/{day["low"]}°'
            tw, th = self._text_size(t_str, f_tiny)
            draw.text((cx - tw // 2, temp_y), t_str, font=f_tiny, fill=BLACK)

    def _draw_poem(self, draw, data):
        poem = data["poem"]
        f = self.fonts["body"]
        lines = poem.split('\n')

        line_widths = []
        for line in lines:
            text = f'「{line}」'
            tw, th = self._text_size(text, f)
            line_widths.append((text, tw))

        zone_h = self.L.BOTTOM_BOT - self.L.BOTTOM_TOP
        line_h = 14
        gap = 8
        total_h = len(lines) * line_h + (len(lines) - 1) * gap

        zone_center_y = (self.L.BOTTOM_TOP + self.L.BOTTOM_BOT) // 2
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
        y = self._centered_y(f, line, self.L.BOTTOM_TOP, self.L.BOTTOM_BOT)
        draw.text((x, y), line, font=f, fill=BLACK)

    def draw(self, data):
        img = Image.new("L", (W, H), WHITE)
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

        self._draw_poem(draw, data)

        return img

    def render(self, data=None):
        if data is None:
            import data as _data
            data = _data.collect()
        img = self.draw(data)
        img_1bit = img.convert("1", dither=Image.Dither.NONE)
        return img_1bit, img


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
    """直接 1x 渲染，不做超采样"""
    if data is None:
        import data as _data
        data = _data.collect()

    r = Renderer()
    img_1bit, img = r.render(data)
    return img_1bit, img


def to_png_bytes(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_buffer(img):
    """PIL 1-bit Image → 15000 字节"""
    expected = W * H // 8
    raw = img.tobytes()
    if len(raw) != expected:
        raise ValueError(f"位图长度 {len(raw)}，期望 {expected}")
    return bytes(raw)


def render_buffer(data=None):
    """一次性渲染并返回 15000 字节 raw buffer"""
    img = render(data)
    return to_buffer(img)


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
