# -*- coding: utf-8 -*-
"""
auth.py - 后台单密码登录、会话密钥与失败限流
==========================================

密码以 PBKDF2-SHA256 哈希保存在 server/auth.json。
首次启动若文件不存在会自动创建，默认密码见 DEFAULT_PASSWORD，
启动日志里会打印提示；也可以在启动前设置环境变量 CLOCK_ADMIN_PASSWORD
接管密码（此时后台「修改密码」会被禁用）。
"""

import hashlib
import hmac
import json
import os
import secrets
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_PATH = os.path.join(BASE_DIR, "auth.json")

DEFAULT_PASSWORD = "clock2026"
ITERATIONS = 200_000

MAX_FAILS = 5          # 窗口内允许的失败次数
FAIL_WINDOW = 600      # 10 分钟
LOCK_SECONDS = 600     # 触发后锁定 10 分钟

_cfg = None
_secret = None
_fails = {}


# ============================================================
# 存储
# ============================================================

def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    ).hex()
    return {
        "algo": "pbkdf2_sha256",
        "iterations": ITERATIONS,
        "salt": salt,
        "hash": digest,
    }


def _load():
    try:
        with open(AUTH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(cfg):
    tmp = AUTH_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, AUTH_PATH)
    try:
        os.chmod(AUTH_PATH, 0o600)
    except OSError:
        pass


def init():
    """载入或创建配置；返回配置字典"""
    global _cfg
    if _cfg is not None:
        return _cfg

    cfg = _load()
    if not cfg or "secret" not in cfg or "password" not in cfg:
        cfg = {
            "secret": secrets.token_hex(32),
            "password": _hash_password(DEFAULT_PASSWORD),
            "created": _now(),
        }
        _save(cfg)
        print("[auth] 已生成 server/auth.json")
        print("[auth] 初始密码：%s  —— 登录后请到「账号」页修改" % DEFAULT_PASSWORD)

    _cfg = cfg
    return cfg


def secret_key():
    global _secret
    if _secret is None:
        _secret = init()["secret"]
    return _secret


# ============================================================
# 校验
# ============================================================

def env_managed():
    """密码是否由环境变量接管"""
    return bool(os.environ.get("CLOCK_ADMIN_PASSWORD"))


def verify(password):
    if not password:
        return False

    env_pw = os.environ.get("CLOCK_ADMIN_PASSWORD")
    if env_pw:
        return hmac.compare_digest(password, env_pw)

    rec = init()["password"]
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"),
        rec["salt"].encode("utf-8"), rec.get("iterations", ITERATIONS),
    ).hex()
    return hmac.compare_digest(digest, rec["hash"])


def change_password(old, new):
    """返回 (ok, message)"""
    if env_managed():
        return False, "当前密码由环境变量管理，界面无法修改"
    if not verify(old):
        return False, "原密码不正确"
    if len(new) < 6:
        return False, "新密码至少 6 位"
    if new == old:
        return False, "新密码不能与原密码相同"

    cfg = init()
    cfg["password"] = _hash_password(new)
    cfg["updated"] = _now()
    _save(cfg)
    return True, "密码已更新"


# ============================================================
# 失败限流
# ============================================================

def _prune(ip):
    now = time.time()
    hits = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    if hits:
        _fails[ip] = hits
    else:
        _fails.pop(ip, None)
    return hits


def locked_for(ip):
    """剩余锁定秒数，0 表示未锁定"""
    hits = _prune(ip)
    if len(hits) < MAX_FAILS:
        return 0
    return max(0, int(FAIL_WINDOW - (time.time() - hits[-1])))


def note_failure(ip):
    _prune(ip)
    _fails.setdefault(ip, []).append(time.time())


def clear_failures(ip):
    _fails.pop(ip, None)
