# -*- coding: utf-8 -*-
"""P0 后端验证：
1) auth_lib 纯函数单测（哈希/校验/JWT/用户名/角色）
2) server.py Handler 级 mock 测试（假 DB 连接，覆盖 register/login/me/_check_admin 双轨/日志埋点）
说明：真实 MySQL 接口联调需部署后进行（本地无 DATABASE_URL）。
"""
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auth_lib
from auth_lib import (
    hash_password, verify_password, create_token, decode_token,
    validate_username, extract_bearer, BACKEND_ROLES,
)


# ---------- 1. auth_lib 纯函数 ----------
class TestAuthLib(unittest.TestCase):
    def test_hash_verify(self):
        h = hash_password("abc123")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("abc123", h))
        self.assertFalse(verify_password("abc124", h))
        self.assertFalse(verify_password("abc123", "garbage"))

    def test_hash_salt_unique(self):
        self.assertNotEqual(hash_password("abc123"), hash_password("abc123"))

    def test_jwt_roundtrip(self):
        t = create_token("secret", "u_123", "admin", ttl=3600)
        self.assertIsNotNone(t)
        p = decode_token("secret", t)
        self.assertEqual(p["sub"], "u_123")
        self.assertEqual(p["role"], "admin")
        self.assertIsNone(decode_token("wrong", t))

    def test_jwt_expired(self):
        t = create_token("secret", "u_1", "admin", ttl=-10)
        self.assertIsNone(decode_token("secret", t))

    def test_validate_username(self):
        self.assertTrue(validate_username("ivan")[0])
        self.assertTrue(validate_username("张宏飞")[0])
        self.assertFalse(validate_username("ab")[0])          # 过短
        self.assertFalse(validate_username("has space")[0])   # 含空格
        self.assertFalse(validate_username("bad@name")[0])    # 非法字符

    def test_extract_bearer(self):
        self.assertEqual(extract_bearer({"Authorization": "Bearer tok1"}), "tok1")
        self.assertEqual(extract_bearer({}, {"token": "tok2"}), "tok2")
        self.assertIsNone(extract_bearer({}))

    def test_roles(self):
        self.assertIn("admin", BACKEND_ROLES)
        self.assertIn("editor", BACKEND_ROLES)
        self.assertIn("viewer", BACKEND_ROLES)
        self.assertNotIn("learner", BACKEND_ROLES)


# ---------- 2. server.py Handler mock ----------
class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []
        self._dict = False

    def execute(self, sql, args=None):
        self.executed.append((sql, args))
        return 0

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, rows=None, dict_rows=None):
        self._rows = rows or []
        self._dict_rows = dict_rows
        self.committed = False
        self.closed = False

    def cursor(self, cursor=None):
        if cursor is not None:  # DictCursor 模式
            return FakeCursor(self._dict_rows)
        return FakeCursor(self._rows)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_handler():
    """构造一个可调用的 Handler 实例（绕过 BaseHTTPRequestHandler 的 socket 依赖）。"""
    import server
    h = object.__new__(server.Handler)
    h.headers = {"Authorization": ""}
    h.client_address = ("127.0.0.1", 12345)
    h.wfile = types.SimpleNamespace(write=lambda b: None, flush=lambda: None)
    h._sent = []

    # 重写 _json / _log_op，避免真实写库与真实响应头
    def _json(code, obj):
        h._sent.append((code, obj))
        return {"code": code, "body": obj}
    h._json = _json

    real_log_op = server.Handler._log_op
    def _log_op(data, action, target_type="", target_id="", detail=None):
        h._logs = getattr(h, "_logs", [])
        h._logs.append((action, target_type, target_id))
    h._log_op = _log_op

    return h, server


class TestAuthHandlers(unittest.TestCase):
    def setUp(self):
        import server as srv
        self.srv = srv
        srv.SECRET_KEY = "test-secret-key-0123456789abcdef"  # >=32字节，避免 PyJWT 警告
        srv.ADMIN_KEY = "test-admin-key"
        srv.TOKEN_TTL = 3600
        srv.DATABASE_URL = "mysql://mock:mock@127.0.0.1:3306/mock"  # 桩库地址（_quest_conn 被替换）

    def _stub_user_by_id(self):
        """按 uid 返回角色：含 '_l' 的为 learner，其余为 admin。"""
        def _get(uid):
            role = "learner" if "_l" in (uid or "") else "admin"
            return {
                "id": uid, "username": "boss", "password_hash": "", "role": role,
                "nickname": "", "avatar": "", "email": None, "status": 1, "created_at": 0,
            }
        return _get

    def test_register_first_is_admin(self):
        srv = self.srv
        srv._quest_conn = lambda: FakeConn()
        srv._auth_get_user_by_username = lambda u: None
        srv._auth_count_users = lambda: 0
        h, _ = make_handler()
        resp = h._handle_auth_register({"username": "boss", "password": "pass123"})
        body = resp["body"]
        self.assertTrue(body["ok"])
        self.assertEqual(body["user"]["role"], "admin")
        self.assertTrue(body["user"]["isFirstAdmin"])
        self.assertTrue(body["token"])

    def test_register_later_is_learner(self):
        srv = self.srv
        srv._quest_conn = lambda: FakeConn()
        srv._auth_get_user_by_username = lambda u: None
        srv._auth_count_users = lambda: 3
        h, _ = make_handler()
        resp = h._handle_auth_register({"username": "student1", "password": "pass123"}).get("body")
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["user"]["role"], "learner")

    def test_register_duplicate(self):
        srv = self.srv
        srv._auth_get_user_by_username = lambda u: {"id": "u_x", "username": u}
        h, _ = make_handler()
        resp = h._handle_auth_register({"username": "dup", "password": "pass123"}).get("body")
        self.assertFalse(resp["ok"])
        self.assertEqual(resp.get("error"), "用户名已存在")

    def test_login_wrong_password(self):
        srv = self.srv
        srv._auth_get_user_by_username = lambda u: {
            "id": "u_1", "username": u, "password_hash": hash_password("right123"),
            "role": "admin", "nickname": "", "avatar": "", "status": 1,
        }
        h, _ = make_handler()
        resp = h._handle_auth_login({"username": "boss", "password": "wrong"}).get("body")
        self.assertFalse(resp["ok"])
        self.assertEqual(resp.get("error"), "用户名或密码错误")

    def test_login_ok_and_token(self):
        srv = self.srv
        srv._auth_get_user_by_username = lambda u: {
            "id": "u_1", "username": u, "password_hash": hash_password("right123"),
            "role": "editor", "nickname": "老王", "avatar": "", "status": 1,
        }
        h, _ = make_handler()
        resp = h._handle_auth_login({"username": "boss", "password": "right123"}).get("body")
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["user"]["role"], "editor")
        payload = decode_token(srv.SECRET_KEY, resp["token"])
        self.assertEqual(payload["sub"], "u_1")

    def test_check_admin_dual_mode(self):
        srv = self.srv
        srv._auth_get_user_by_id = self._stub_user_by_id()
        h, _ = make_handler()
        # JWT 路径
        tok = create_token(srv.SECRET_KEY, "u_1", "admin", 3600)
        h.headers = {"Authorization": "Bearer " + tok}
        self.assertIsNone(h._check_admin({}))
        # adminKey 兼容路径
        h.headers = {"Authorization": ""}
        self.assertIsNone(h._check_admin({"adminKey": "test-admin-key"}))
        # 错误密钥
        self.assertIsNotNone(h._check_admin({"adminKey": "bad"}))
        # learner 无后台权限（uid 含 _l → 桩返回 learner 角色）
        tok_l = create_token(srv.SECRET_KEY, "u_2_l", "learner", 3600)
        h.headers = {"Authorization": "Bearer " + tok_l}
        self.assertIsNotNone(h._check_admin({}))

    def test_auth_me(self):
        srv = self.srv
        srv._auth_get_user_by_id = self._stub_user_by_id()
        h, _ = make_handler()
        h.headers = {"Authorization": ""}
        resp = h._handle_auth_me({}).get("body")
        self.assertFalse(resp["ok"])  # 未登录
        # 角色以 DB 为准（token 里的 role 不直接采信）
        tok = create_token(srv.SECRET_KEY, "u_1", "viewer", 3600)
        h.headers = {"Authorization": "Bearer " + tok}
        resp = h._handle_auth_me({}).get("body")
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["user"]["role"], "admin")  # 桩 DB 返回 admin
        # learner 也能查到自己（登录态正常）
        tok_l = create_token(srv.SECRET_KEY, "u_9_l", "learner", 3600)
        h.headers = {"Authorization": "Bearer " + tok_l}
        resp = h._handle_auth_me({}).get("body")
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["user"]["role"], "learner")

    def test_square_submit_writes_log(self):
        srv = self.srv
        srv._auth_get_user_by_id = self._stub_user_by_id()
        srv._quest_conn = lambda: FakeConn()
        srv._square_submit = lambda item: None
        srv._get_minio_client = lambda: None
        h, _ = make_handler()
        tok = create_token(srv.SECRET_KEY, "u_1", "admin", 3600)
        h.headers = {"Authorization": "Bearer " + tok}
        resp = h._handle_square_submit({"id": "sq_1", "title": "测试"})
        self.assertTrue(resp["body"]["ok"])
        self.assertEqual(h._logs[-1][0], "square_submit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
