# -*- coding: utf-8 -*-
"""最小化对照：register→create→manual-pay，对比 verify 的 already_paid 现象"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None, timeout=120):
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
            return e.code, {"ok": False}

uname = "p1d_min_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
utoken = j["token"]
print("注册:", s, j.get("ok"))
s, j = post("/api/order/create", {"plan_key": "month"}, token=utoken)
print("下单:", s, j.get("ok"), j.get("order_no"))
ono = j.get("order_no", "")
s, j = post("/api/order/manual-pay", {"order_no": ono}, token=ADMIN_TOKEN)
print("manual-pay:", s, json.dumps(j, ensure_ascii=False))
