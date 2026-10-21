# -*- coding: utf-8 -*-
"""复现 month 发放：打印每步响应 + 直查 users.vip_expire_at"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
import pymysql
from urllib.parse import urlparse

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

uname = "p1d_m_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
utoken = j["token"]; uid = j["user"]["id"]
print("注册:", s, uid)

s, j = post("/api/order/create", {"plan_key": "month"}, token=utoken)
print("下单:", s, j)
ono = j.get("order_no", "")

s, j = post("/api/order/manual-pay", {"order_no": ono}, token=ADMIN_TOKEN)
print("手动确认:", s, j)

s, j = post("/api/vip/status", {}, token=utoken)
print("VIP状态:", s, j)

p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT vip_expire_at FROM users WHERE id=%s", (uid,))
    print("库里 vip_expire_at:", cur.fetchone()[0])
    cur.execute("SELECT order_no, status, plan_key, paid_at FROM orders WHERE user_id=%s", (uid,))
    print("订单:", cur.fetchall())
    cur.execute("DELETE FROM orders WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
conn.commit(); conn.close()
print("已清理")
