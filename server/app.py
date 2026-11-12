# -*- coding: utf-8 -*-
"""
app.py - Flask 服务端入口
========================

架构：服务端渲染 → 15000 字节原始位图 → ESP32 直接刷屏

启动: python app.py
访问:
  http://localhost:5000/console        统一后台（需登录）
  http://localhost:5000/login          登录
  http://localhost:5000/api/screen     15000 字节 raw buffer（ESP32 拉这个）
  http://localhost:5000/api/screen.png PNG 图片（设备与预览用）
  http://localhost:5000/api/info       JSON 当前数据（需登录）
"""

import time
from urllib.parse import quote

from flask import (
    Flask, Response, render_template, jsonify, request,
    session, redirect,
)

import auth
import data
import renderer
import styles
import symbols


app = Flask(__name__)
app.secret_key = auth.secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME="clock_admin",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
)

WIDTH, HEIGHT = 400, 300
BUF_SIZE = WIDTH * HEIGHT // 8  # 15000


# ============================================================
# 登录保护
# ============================================================

PUBLIC_PATHS = {
    "/login",
    "/favicon.ico",
    "/api/screen",
    "/api/screen_2x",
    "/api/screen.png",
    "/api/screen_2x.png",
    "/api/screen_raw.png",
    "/api/time",
    "/api/health",
}


def _is_public(path):
    return path in PUBLIC_PATHS or path.startswith("/static/")


def _safe_next(target, fallback="/console"):
    if not target or not target.startswith("/") or target.startswith("//"):
        return fallback
    return target


@app.before_request
def _require_login():
    path = request.path
    if _is_public(path):
        return None
    if session.get("auth"):
        return None
    if path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if path in ("/", "/console"):
        return redirect("/login")
    return redirect("/login?next=" + quote(path))


def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "?"


# ============================================================
# 后台页面
# ============================================================

def _no_store(html):
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.route("/")
def index():
    return redirect("/console")


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = _client_ip()
    wait = auth.locked_for(ip)
    error = ""

    if request.method == "POST":
        if wait:
            error = "尝试次数过多，请 %d 分钟后再试" % max(1, wait // 60)
        elif auth.verify(request.form.get("password", "")):
            auth.clear_failures(ip)
            session.clear()
            session["auth"] = True
            session["login_at"] = int(time.time())
            session.permanent = True
            return redirect(_safe_next(request.args.get("next") or request.form.get("next")))
        else:
            auth.note_failure(ip)
            wait = auth.locked_for(ip)
            error = "密码不正确" if not wait else "尝试次数过多，请 %d 分钟后再试" % max(1, wait // 60)

    if session.get("auth"):
        return redirect("/console")
    return _no_store(render_template(
        "login.html",
        error=error,
        next_path=_safe_next(request.args.get("next"), ""),
        env_managed=auth.env_managed(),
    ))


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect("/login")


@app.route("/console")
def console():
    return _no_store(render_template("console.html", env_managed=auth.env_managed()))


# 旧地址保持可用
@app.route("/admin")
def legacy_admin():
    return redirect("/console#content")


@app.route("/preview")
def legacy_preview():
    return redirect("/console#screen")


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# ============================================================
# 渲染辅助
# ============================================================

def _wait_until_next_minute():
    """等待到下一分钟整点，返回下次请求间隔秒数。"""
    now = time.time()
    local = time.localtime(now)
    sec = local[5]
    BASELINE = 50

    if sec < BASELINE:
        wait_sec = 0
        next_interval = BASELINE - sec
    else:
        wait_sec = 60 - sec
        next_interval = BASELINE

    if wait_sec > 0:
        time.sleep(wait_sec)

    return next_interval


def _apply_env_temp():
    env_temp = request.args.get("env_temp")
    if env_temp is not None:
        try:
            data.ENV_TEMP = float(env_temp)
        except ValueError:
            pass
    return data.ENV_TEMP


def _profile_arg(profile_id, threshold=None):
    """后台预览用：指定字体方案，可选覆盖阈值；缺省用当前保存的方案"""
    profile = styles.get(profile_id) if profile_id else styles.current()
    if threshold not in (None, ""):
        try:
            profile = dict(profile)
            profile["threshold"] = max(0.30, min(0.70, float(threshold)))
        except (TypeError, ValueError):
            pass
    return profile


# ============================================================
# 设备接口（公开）
# ============================================================

@app.route("/api/screen")
def api_screen():
    """核心接口：返回 15000 字节 raw binary (MONO_HLSB 格式)"""
    try:
        next_interval = _wait_until_next_minute()
        force_refresh = request.args.get("refresh", "0") == "1"
        _apply_env_temp()
        print(f"[env_temp] {data.ENV_TEMP}°C")
        payload = data.collect(force_refresh=force_refresh)
        img, _ = renderer.render(payload, styles.current())  # (1bit, raw)
        buf = renderer.to_buffer(img)

        assert len(buf) == BUF_SIZE, f"长度 {len(buf)}，期望 {BUF_SIZE}"

        return Response(
            buf,
            mimetype="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Next-Request-In": str(next_interval),
            },
        )
    except Exception as e:
        app.logger.exception("渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen.png")
def api_screen_png():
    """PNG 预览：1x 400x300"""
    try:
        _apply_env_temp()
        payload = data.collect()
        img, _ = renderer.render(payload, styles.current())
        return Response(
            renderer.to_png_bytes(img),
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
        payload = data.collect()
        img_raw = renderer.render_raw(payload, styles.current())
        return Response(
            renderer.to_png_bytes(img_raw),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("raw PNG 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/screen_2x")
def api_screen_2x():
    """2x 高分辨率渲染后缩小到 15000 字节 raw binary"""
    try:
        next_interval = _wait_until_next_minute()
        force_refresh = request.args.get("refresh", "0") == "1"
        _apply_env_temp()
        print(f"[env_temp] {data.ENV_TEMP}°C")
        payload = data.collect(force_refresh=force_refresh)
        img_1bit, _ = renderer.render_hires(payload, styles.current())
        buf = renderer.to_buffer(img_1bit)

        assert len(buf) == BUF_SIZE, f"长度 {len(buf)}，期望 {BUF_SIZE}"

        return Response(
            buf,
            mimetype="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Next-Request-In": str(next_interval),
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
        _apply_env_temp()
        payload = data.collect()
        _, img_gray = renderer.render_hires(payload, styles.current())
        return Response(
            renderer.to_png_bytes(img_gray),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("2x PNG 渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/health")
def api_health():
    return {"ok": True, "ts": int(time.time())}


@app.route("/api/time")
def api_time():
    """服务器当前时间（Asia/Shanghai，UTC+8），供 ESP32 校正 RTC"""
    import datetime
    import zoneinfo
    now_utc = datetime.datetime.now(zoneinfo.ZoneInfo("UTC"))
    now_local = now_utc.astimezone(zoneinfo.ZoneInfo("Asia/Shanghai"))
    return {
        "ts": int(time.time()),
        "iso": now_local.isoformat(),
    }


# ============================================================
# 后台接口（需登录）
# ============================================================

@app.route("/api/info")
def api_info():
    _apply_env_temp()
    payload = data.collect()
    payload["now"]["datetime"] = payload["now"]["datetime"].isoformat()
    return jsonify(payload)


@app.route("/api/bottom_content")
def api_bottom_content_get():
    return jsonify({"content": data.load_bottom_content()})


@app.route("/api/bottom_content", methods=["POST"])
def api_bottom_content_save():
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")
    if not isinstance(content, str):
        return jsonify({"ok": False, "error": "内容格式不正确"}), 400
    data.save_bottom_content(content)
    return jsonify({"ok": True, "saved": symbols.sanitize(content)})


@app.route("/api/console/palette")
def api_console_palette():
    return jsonify(symbols.palette())


@app.route("/api/console/analyze", methods=["POST"])
def api_console_analyze():
    payload = request.get_json(silent=True) or {}
    return jsonify(symbols.analyze(payload.get("content", "")))


@app.route("/api/console/preview", methods=["POST"])
def api_console_preview():
    """用未保存的文本渲染一屏，只显示自定义文本页"""
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")
    if not isinstance(content, str):
        return jsonify({"ok": False, "error": "内容格式不正确"}), 400

    try:
        text = symbols.sanitize(content)
        preview = data.collect(bottom_override=text)
        preview["weather_warning"] = {}
        preview["flw_warning"] = ""
        preview["now"]["minute"] = 0

        profile = _profile_arg(payload.get("profile"), payload.get("threshold"))
        hires = bool(payload.get("hires"))
        if hires:
            img_1bit, gray = renderer.render_hires(preview, profile)
            img = gray
        else:
            img, gray = renderer.render(preview, profile)

        return Response(
            renderer.to_png_bytes(img),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("预览渲染失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/console/styles")
def api_console_styles():
    return jsonify({
        "current": styles.current_id(),
        "threshold": styles.threshold(),
        "profiles": styles.list_profiles(),
    })


@app.route("/api/console/styles", methods=["POST"])
def api_console_styles_save():
    payload = request.get_json(silent=True) or {}
    profile_id = payload.get("profile")
    ok, message, profile = styles.set_profile(profile_id, payload.get("threshold"))
    if not ok:
        return jsonify({"ok": False, "message": message}), 400
    return jsonify({"ok": True, "message": message, "profile": profile})


@app.route("/api/console/style_preview")
def api_console_style_preview():
    """方案对比缩略图：不保存，按指定方案渲染当前画面"""
    try:
        profile = _profile_arg(request.args.get("profile"), request.args.get("threshold"))
        payload = data.collect()
        img, _ = renderer.render(payload, profile)
        return Response(
            renderer.to_png_bytes(img),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        app.logger.exception("方案预览失败")
        return Response(f"render error: {e}", status=503, mimetype="text/plain")


@app.route("/api/debug/layout")
def api_debug_layout():
    L = renderer.Layout
    return jsonify({
        "canvas": {"W": L.W, "H": L.H, "margin": L.M},
        "zones": {
            "top_bar":  {"y": L.TOP_Y, "h": L.DIV1_Y - L.TOP_Y},
            "main":     {"y": L.MAIN_TOP, "h": L.MAIN_BOTTOM - L.MAIN_TOP},
            "forecast": {"y": L.FCST_Y, "h": L.FCST_BOTTOM - L.FCST_Y},
            "bottom":   {"y": L.BOTTOM_TOP, "h": L.BOTTOM_BOT - L.BOTTOM_TOP},
        },
        "dividers": {
            "div1": L.DIV1_Y, "div2": L.DIV2_Y, "div3": L.DIV3_Y,
        },
        "columns": {
            "time_x2": L.TIME_X2, "weather_x1": L.WEATHER_X1,
        },
        "data_source": {
            "mock_weather": data.USE_MOCK_WEATHER,
            "city": data.CITY_NAME,
            "timezone": data.TZ_NAME,
        },
    })


@app.route("/api/account")
def api_account():
    login_at = session.get("login_at")
    return jsonify({
        "env_managed": auth.env_managed(),
        "login_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(login_at)) if login_at else "",
        "password_hint": "由环境变量 CLOCK_ADMIN_PASSWORD 管理" if auth.env_managed() else "保存在 server/auth.json",
    })


@app.route("/api/account/password", methods=["POST"])
def api_account_password():
    payload = request.get_json(silent=True) or {}
    ok, message = auth.change_password(
        str(payload.get("old", "")), str(payload.get("new", ""))
    )
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    print("=" * 52)
    print("  墨水屏时钟 - 服务端")
    print("=" * 52)
    print("  后台     http://localhost:5000/console")
    print("  ESP32    http://<本机IP>:5000/api/screen")
    print("  字节数   15000 (400×300÷8, MONO_HLSB)")
    print("  按 Ctrl+C 停止")
    print("=" * 52)
    app.run(host="0.0.0.0", port=5000, debug=False)
