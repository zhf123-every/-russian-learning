# -*- coding: utf-8 -*-
"""P1-F 单发探针：负价格 / 恢复默认 逐条打印"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None):
    if token:
        body = dict(body); body["token"] = token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Connection": "close"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        print(path, r.status, r.read().decode()[:400]); return
    except urllib.error.HTTPError as e:
        print(path, e.code, e.read().decode()[:400]); return
    except Exception as e:
        print(path, "ERR", repr(e)[:200])

print("--- 当前 vip/plans ---"); post("/api/vip/plans", {})
print("--- 负价格 ---")
post("/api/admin/settings/save", {"vip_plans": {"month": {"amount_cents": -100}}}, token=ADMIN_TOKEN)
print("--- 负价格后再读 ---"); post("/api/vip/plans", {})
print("--- 恢复默认(4套餐) ---")
post("/api/admin/settings/save", {
    "site": {"site_name": "看视频学俄语", "site_subtitle": "Russian Learning", "announcement": ""},
    "vip_plans": {"month": {"name": "月付", "amount_cents": 2900, "months": 1, "tag": "月付 29 元"},
                  "quarter": {"name": "季付", "amount_cents": 8500, "months": 3, "tag": "季付 85 元"},
                  "year": {"name": "年付", "amount_cents": 34500, "months": 12, "tag": "年付 345 元"},
                  "lifetime": {"name": "终身", "amount_cents": 108800, "months": None, "tag": "终身 1088 元"}},
}, token=ADMIN_TOKEN)
print("--- 恢复后再读 ---"); post("/api/vip/plans", {})
