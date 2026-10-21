# -*- coding: utf-8 -*-
import urllib.request, urllib.error, json

BASE = "https://russian-learning-jetq.onrender.com"

def post(path, body, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]

s, b = post("/api/auth/me", {})
print("me POST 无token: HTTP", s, b)

# 注册一个联调测试账号（生产库，验证注册全链路；注册成功即证明 register 生产可用）
import time
u = "test_%d" % int(time.time())
s, b = post("/api/auth/register", {"username": u, "password": "test-pass-123"})
print("register 测试账号(%s): HTTP" % u, s, b)
if s == 200:
    s, b = post("/api/auth/login", {"username": u, "password": "test-pass-123"})
    print("login 测试账号: HTTP", s, b[:120])
