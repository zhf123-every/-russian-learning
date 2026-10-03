# -*- coding: utf-8 -*-
"""
P0 登录与 RBAC 基础库（纯函数，不依赖数据库）。
- 密码：PBKDF2-HMAC-SHA256（600k 迭代 + 随机盐），格式 pbkdf2_sha256$iter$salt$hex
- 令牌：JWT HS256（PyJWT），payload {sub, role, iat, exp}
本文件只放无副作用函数，便于本地单元测试。
"""
import hashlib
import hmac
import secrets
import re
import time

try:
    import jwt as _pyjwt
    _PYJWT_OK = True
except Exception:  # pragma: no cover - 依赖未安装时的降级
    _pyjwt = None
    _PYJWT_OK = False

# 密码哈希迭代次数（OWASP 推荐 PBKDF2-HMAC-SHA256 >= 600k）
ITERATIONS = 600_000
# 令牌默认有效期：7 天
DEFAULT_TTL = 7 * 24 * 3600

# 角色体系：learner=普通学习者（可登录同步进度，无后台权限）
#           admin=管理员全权 / editor=课程编辑 / viewer=只读看板
ROLES = ("admin", "editor", "viewer", "learner")
# 可进入管理后台的角色
BACKEND_ROLES = ("admin", "editor", "viewer")
# 管理写操作所需的最小角色（P0 阶段沿用 adminKey 时代的管理口径：后台角色皆可）
ADMIN_WRITE_ROLES = ("admin", "editor", "viewer")


def pyjwt_available():
    return _PYJWT_OK


def hash_password(password: str) -> str:
    """生成带盐 PBKDF2 哈希：pbkdf2_sha256$iter$salt$hex"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    )
    return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt, dk.hex())


def verify_password(password: str, stored: str) -> bool:
    """恒定时间比对，避免时序攻击。格式不符返回 False。"""
    try:
        algo, iter_s, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iter_s)
        )
        return hmac.compare_digest(dk.hex(), expected)
    except Exception:
        return False


def validate_username(username):
    """(ok, err) 用户名 3-64 位，仅字母/数字/下划线/中文，不含空白"""
    name = (username or "").strip()
    if len(name) < 3 or len(name) > 64:
        return False, "用户名需 3-64 个字符"
    if re.search(r"\s", name):
        return False, "用户名不能包含空格"
    if not re.match(r"^[\w\u4e00-\u9fa5]+$", name, re.UNICODE):
        return False, "用户名只能包含字母、数字、下划线或中文"
    return True, ""


def create_token(secret, user_id, role, ttl=None):
    """签发 JWT。secret 为空或 PyJWT 缺失时返回 None。"""
    if not secret or not _PYJWT_OK:
        return None
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + (ttl or DEFAULT_TTL),
    }
    try:
        return _pyjwt.encode(payload, secret, algorithm="HS256")
    except Exception:
        return None


def decode_token(secret, token):
    """校验 JWT。失败返回 None。"""
    if not secret or not _PYJWT_OK or not token:
        return None
    try:
        return _pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


def extract_bearer(headers, data=None):
    """从 Authorization: Bearer xxx 或 body token 字段取 token。"""
    token = ""
    auth_h = (headers or {}).get("Authorization") or ""
    if auth_h.startswith("Bearer "):
        token = auth_h[7:].strip()
    if not token and isinstance(data, dict):
        token = (data.get("token") or "").strip()
    return token or None
