# -*- coding: utf-8 -*-
"""本地 P0 接口非破坏性验证（不注册账号，首 admin 名额留给用户在浏览器操作）"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 0, "连接失败: %s" % e


cases = [
    ("1. health", "GET", None, "/health"),
    ("2. register 短密码(期望400)", "POST", {"username": "testuser", "password": "123"}, "/api/auth/register"),
    ("3. register 非法用户名(期望400)", "POST", {"username": "bad name!", "password": "123456"}, "/api/auth/register"),
    ("4. login 空表(期望401)", "POST", {"username": "nobody", "password": "123456"}, "/api/auth/login"),
    ("5. me 未登录(期望401)", "POST", {}, "/api/auth/me"),
    ("6. adminKey 错误(期望403)", "POST", {"adminKey": "wrong"}, "/api/admin/check"),
    ("7. adminKey 正确(期望200 ok)", "POST", {"adminKey": "local-p0-admin-key"}, "/api/admin/check"),
]

for name, method, body, path in cases:
    if method == "GET":
        try:
            with urllib.request.urlopen(BASE + path, timeout=30) as r:
                print("%s => HTTP %s %s" % (name, r.status, r.read().decode("utf-8")))
        except Exception as e:
            print("%s => 失败 %s" % (name, e))
    else:
        status, text = post(path, body)
        print("%s => HTTP %s %s" % (name, status, text))
