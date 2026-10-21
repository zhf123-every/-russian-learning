# -*- coding: utf-8 -*-
"""P1-A 生产验证：用生产 SECRET_KEY 签 admin token，调生产接口"""
import json, sys, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

PROD = "https://russian-learning-jetq.onrender.com"
SECRET_KEY = "f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68"
ADMIN_UID = "u_c0bc17d7b20b45799721"
TOKEN = create_token(SECRET_KEY, ADMIN_UID, "admin", 3600)

def post(path, body, timeout=90):
    body = dict(body); body["token"] = TOKEN
    req = urllib.request.Request(PROD + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"ok": False}

s, j = post("/api/auth/me", {})
print("me:", s, j.get("ok"), (j.get("user") or {}).get("role"))

s, j = post("/api/admin/users", {"page": 1, "size": 10})
print("admin/users:", s, j.get("ok"), "total=", j.get("total"))
if j.get("rows"):
    for r in j["rows"][:3]:
        print("  -", r.get("username"), "|", r.get("role"), "| status=", r.get("status"), "| 含password_hash?", "password_hash" in r)

# 错误 token 应 403
req = urllib.request.Request(PROD + "/api/admin/users",
    data=json.dumps({"page": 1, "size": 10, "token": "bad.token.here"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    r = urllib.request.urlopen(req, timeout=90)
    print("bad token:", r.status)
except urllib.error.HTTPError as e:
    print("bad token:", e.code, e.read().decode()[:120])
