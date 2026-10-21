# -*- coding: utf-8 -*-
"""调试禁用接口"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None, timeout=90):
    if token:
        body = dict(body); body["token"] = token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"raw": e.read().decode()[:200]}

# 注册一个测试用户
uname = "dbg_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
print("注册:", s, j.get("ok"))
uid = (j.get("user") or {}).get("id", "")

print("禁用 status=0 ->", post("/api/admin/users/status", {"id": uid, "status": 0}, token=ADMIN_TOKEN))
print("登录(禁用后) ->", post("/api/auth/login", {"username": uname, "password": "pass-123456"})[0:2])
print("启用 status=1 ->", post("/api/admin/users/status", {"id": uid, "status": 1}, token=ADMIN_TOKEN))
print("登录(启用后) ->", post("/api/auth/login", {"username": uname, "password": "pass-123456"})[0:2])

# 清理
import pymysql
from urllib.parse import urlparse
p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
conn.commit(); conn.close()
print("已清理测试用户")
