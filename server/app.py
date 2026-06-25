# -*- coding: utf-8 -*-
"""
app.py - Flask 服务端入口
========================

架构：服务端渲染 → 15000 字节原始位图 → ESP32 直接刷屏

启动: python app.py
访问:
  http://localhost:5000/                   欢迎页
  http://localhost:5000/preview            浏览器预览（拉 PNG）
  http://localhost:5000/api/screen        15000 字节 raw buffer（ESP32 拉这个）
  http://localhost:5000/api/screen.png    PNG 图片（浏览器预览用）
  http://localhost:5000/api/info          JSON 当前数据
"""

import io
import time
from flask import Flask, Response, render_template, jsonify, request

import data
import renderer


app = Flask(__name__)
_renderer = renderer.Renderer()
WIDTH, HEIGHT = 400, 300
BUF_SIZE = WIDTH * HEIGHT // 8  # 15000


def _apply_delay():
    """
    如果请求带了 ?delay=N（秒），服务端 sleep N 秒后再返回。
    用于 ESP32 提前发起请求，让服务端"等到整点"再渲染。
    """
    delay_raw = request.args.get("delay")
    if delay_raw is None:
        return
    try:
        delay = float(delay_raw)
    except ValueError:
        return
    if delay > 0:
        time.sleep(delay)


# ============================================================
# 路由
# ============================================================

@app.route("/")
def index():
    return (
        "<h1>墨水屏时钟 - 服务端</h1>"
        "<ul>"
        "<li><a href='/preview'>/preview</a> - 浏览器预览（拉 PNG）</li>"
        "<li><a href='/api/screen_raw.png'>/api/screen_raw.png</a> - <b>1:1 原始图</b>（400x300 灰度）</li>"
        "<li><a href='/api/screen_2x.png'>/api/screen_2x.png</a> - <b>2x 高清图</b>（800x600渲染→400x300，文字更平滑）</li>"
        "<li><a href='/api/screen.png'>/api/screen.png</a> - 1-bit PNG（ESP32 用 1:1）</li>"
        "<li><a href='/api/screen_2x'>/api/screen_2x</a> - 15000 字节 raw（ESP32 用 2x 渲染）</li>"
        "<li><a href='/api/info'>/api/info</a> - JSON 当前数据</li>"
        "</ul>"
        "<p>4 区布局：时间 / 当前天气 / 7 日天气 / 古诗</p>"
        "<p><b>对比：</b>2x 渲染文字边缘更平滑，适合浏览；1:1 原始用于 ESP32</p>"
    )


@app.route("/api/screen")
def api_screen():
    """
    核心接口：返回 15000 字节 raw binary (MONO_HLSB 格式)

    ESP32 端直接:
        r = urequests.get(SERVER_URL)
        epd.display_frame(r.content)

    查询参数:
        refresh=1 - 强制刷新天气（用于全刷时）
        env_temp=25.5 - 现场温度传感器数据
    """
    try:
        _apply_delay()
        from flask import request
        force_refresh = request.args.get("refresh", "0") == "1"
        env_temp = request.args.get("env_temp")
        if env_temp is not None:
            data.ENV_TEMP = float(env_temp)
        print(f"[env_temp] {data.ENV_TEMP}°C")
        payload = data.collect(force_refresh=force_refresh, client_time=request.args.get("client_time"))
        img, _ = _renderer.render(payload)  # (1bit, raw)
        buf = renderer.to_buffer(img)

        assert len(buf) == BUF_SIZE, f"长度 {len(buf)}，期望 {BUF_SIZE}"

        return Response(
            buf,
            mimetype="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Render-Time-Ms": str(int(time.time() * 1000) % 100000),
            },
        )
    except Exception as e:
        app.logger.exception("渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen.png")
def api_screen_png():
    """PNG 预览：转换后的 400x300 1-bit 图"""
    try:
        _apply_delay()
        env_temp = request.args.get("env_temp")
        if env_temp is not None:
            data.ENV_TEMP = float(env_temp)
        payload = data.collect(client_time=request.args.get("client_time"))
        img, _ = _renderer.render(payload)  # (1bit, raw800)
        png_bytes = renderer.to_png_bytes(img)
        return Response(
            png_bytes,
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("PNG 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen_raw.png")
def api_screen_raw_png():
    """原始设计图：400x300 灰度（用于对比）"""
    try:
        _apply_delay()
        payload = data.collect(client_time=request.args.get("client_time"))
        img_raw = renderer.render_raw(payload)  # 400x300 L 灰度图
        png_bytes = renderer.to_png_bytes(img_raw)
        return Response(
            png_bytes,
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("raw PNG 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen_2x")
def api_screen_2x():
    """
    2x 高分辨率渲染：800x600 → 缩放 → 15000 字节 raw binary
    先渲染大图再缩小，文字边缘更平滑

    查询参数:
        refresh=1 - 强制刷新天气（用于全刷时）
        env_temp=25.5 - 现场温度传感器数据
        client_time=2026-06-24T22:30:00 - 用客户端时间替代服务端时间
        delay=5 - 服务端 sleep N 秒后再返回（用于提前请求模式）
    """
    try:
        _apply_delay()
        from flask import request
        force_refresh = request.args.get("refresh", "0") == "1"
        env_temp = request.args.get("env_temp")
        if env_temp is not None:
            data.ENV_TEMP = float(env_temp)
        print(f"[env_temp] {data.ENV_TEMP}°C")
        payload = data.collect(force_refresh=force_refresh, client_time=request.args.get("client_time"))
        img_1bit, _ = renderer.render_hires(payload)
        buf = renderer.to_buffer(img_1bit)

        assert len(buf) == BUF_SIZE, f"长度 {len(buf)}，期望 {BUF_SIZE}"

        return Response(
            buf,
            mimetype="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Render-Time-Ms": str(int(time.time() * 1000) % 100000),
                "X-Mode": "2x-hires",
            },
        )
    except Exception as e:
        app.logger.exception("2x 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen_2x.png")
def api_screen_2x_png():
    """2x 高分辨率 PNG 预览"""
    try:
        _apply_delay()
        env_temp = request.args.get("env_temp")
        if env_temp is not None:
            data.ENV_TEMP = float(env_temp)
        payload = data.collect(client_time=request.args.get("client_time"))
        img_1bit, img_gray = renderer.render_hires(payload)
        png_bytes = renderer.to_png_bytes(img_gray)
        return Response(
            png_bytes,
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("2x PNG 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/preview")
def preview():
    return render_template("preview.html")


@app.route("/api/info")
def api_info():
    env_temp = request.args.get("env_temp")
    if env_temp is not None:
        data.ENV_TEMP = float(env_temp)
    payload = data.collect(client_time=request.args.get("client_time"))
    payload["now"]["datetime"] = payload["now"]["datetime"].isoformat()
    return jsonify(payload)


@app.route("/api/debug/layout")
def api_debug_layout():
    L = renderer.Layout
    return jsonify({
        "canvas": {"W": L.W, "H": L.H, "margin": L.M},
        "zones": {
            "top_bar":   {"y": L.TOP_Y},
            "time":      {"y": L.TIME_Y},
            "weather":   {"y": L.WEATHER_Y},
            "forecast":  {"y": L.FCST_Y},
            "poem":      {"y": L.POEM_Y},
            "countdown": {"y": L.FOOT_Y},
        },
        "dividers": {
            "div1": L.DIV1_Y, "div2": L.DIV2_Y,
            "div3": L.DIV3_Y, "div4": L.DIV4_Y, "div5": L.DIV5_Y,
        },
        "data_source": {
            "mock_weather": data.USE_MOCK_WEATHER,
            "city": data.CITY_NAME,
            "timezone": data.TZ_NAME,
        },
    })


@app.route("/api/health")
def api_health():
    return {"ok": True, "ts": int(time.time())}


@app.route("/api/test_fonts")
def api_test_fonts():
    """Test font rendering"""
    from PIL import Image, ImageDraw, ImageFont
    import os

    img = Image.new("L", (400, 300), 255)
    draw = ImageDraw.Draw(img)

    # Find fonts
    ch_path = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    wi_path = os.path.join(os.path.dirname(__file__), "weathericons-regular-webfont.ttf")

    fonts_info = {
        "ch_path_exists": os.path.exists(ch_path),
        "wi_path_exists": os.path.exists(wi_path),
        "ch_path": ch_path,
        "wi_path": wi_path,
    }

    try:
        if os.path.exists(ch_path):
            f_ch = ImageFont.truetype(ch_path, 24)
            draw.text((20, 20), "中文测试", font=f_ch, fill=0)
            fonts_info["ch_loaded"] = True
        else:
            fonts_info["ch_loaded"] = False
    except Exception as e:
        fonts_info["ch_error"] = str(e)
        fonts_info["ch_loaded"] = False

    try:
        if os.path.exists(wi_path):
            f_wi = ImageFont.truetype(wi_path, 36)
            # Draw sunny icon (0xF00D)
            icon_char = chr(0xF00D)
            draw.text((20, 60), icon_char, font=f_wi, fill=0)
            fonts_info["wi_loaded"] = True
        else:
            fonts_info["wi_loaded"] = False
    except Exception as e:
        fonts_info["wi_error"] = str(e)
        fonts_info["wi_loaded"] = False

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png")


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  墨水屏时钟 - 服务端")
    print("=" * 50)
    print("  浏览器:   http://localhost:5000/preview")
    print("  ESP32:   http://<本机IP>:5000/api/screen")
    print("  字节数:  15000 (400×300÷8, MONO_HLSB)")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
