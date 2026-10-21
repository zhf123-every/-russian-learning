# -*- coding: utf-8 -*-
"""P1-E 生产验证：admin token 调 stats"""
import json, sys, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

PROD = "https://russian-learning-jetq.onrender.com"
SECRET_KEY = "f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68"
TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)

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

s, j = post("/api/admin/dashboard/stats", {})
print("stats:", s, j.get("ok"))
st = j.get("stats") or {}
print("users:", st.get("users"))
print("courses:", st.get("courses"))
print("learning:", st.get("learning"))
print("ratings:", st.get("ratings"))
print("top_courses:", st.get("top_courses"))
