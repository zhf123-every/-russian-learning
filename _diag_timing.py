# -*- coding: utf-8 -*-
"""计时验证：走 5173 注册第二个账号（learner），确认是否因响应慢导致前端12s超时"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:5173"
body = {"username": "timing_test_01", "password": "test123456"}
req = urllib.request.Request(
    BASE + "/api/auth/register",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"}, method="POST",
)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        dt = time.time() - t0
        print("耗时 %.1fs => HTTP %s %s" % (dt, r.status, r.read().decode()))
except urllib.error.HTTPError as e:
    print("耗时 %.1fs => HTTP %s %s" % (time.time() - t0, e.code, e.read().decode()))
except Exception as e:
    print("耗时 %.1fs => 失败: %s" % (time.time() - t0, e))
