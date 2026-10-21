# -*- coding: utf-8 -*-
"""通过前端 dev proxy (5173) 验证 auth 接口链路"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:5173"


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
    ("proxy login 空表(期望401)", {"username": "nobody", "password": "123456"}, "/api/auth/login"),
    ("proxy me 未登录(期望401)", {}, "/api/auth/me"),
    ("proxy adminKey 正确(期望200 ok:true)", {"adminKey": "local-p0-admin-key"}, "/api/admin/check"),
]
for name, body, path in cases:
    status, text = post(path, body)
    print("%s => HTTP %s %s" % (name, status, text))
