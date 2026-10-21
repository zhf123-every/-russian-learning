# -*- coding: utf-8 -*-
"""完整链路验证：register -> login -> me（走 5173 代理），最后清理测试账号"""
import json
import time
import urllib.request
import urllib.error
import pymysql
from urllib.parse import urlparse

BASE = "http://localhost:5173"


def post(path, body, timeout=90):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8"), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), time.time() - t0
    except Exception as e:
        return 0, "失败: %s" % e, time.time() - t0


# 1) 注册（learner，因为库里已有首 admin）
s, body, dt = post("/api/auth/register",
                   {"username": "timing_test_01", "password": "test123456", "nickname": "联调测试"})
print("register => HTTP %s (%.1fs) %s" % (s, dt, body))
j = json.loads(body) if body.startswith("{") else {}
token = (j.get("token") or "") if isinstance(j, dict) else ""

# 2) 登录
s, body, dt = post("/api/auth/login", {"username": "timing_test_01", "password": "test123456"})
print("login    => HTTP %s (%.1fs) %s" % (s, dt, body))
if not token:
    j2 = json.loads(body) if body.startswith("{") else {}
    token = (j2.get("token") or "") if isinstance(j2, dict) else ""

# 3) me
s, body, dt = post("/api/auth/me", {"token": token})
print("me       => HTTP %s (%.1fs) %s" % (s, dt, body))

# 4) 清理测试账号
DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"
p = urlparse(DSN.split("?")[0])
conn = pymysql.connect(host=p.hostname, port=p.port or 4000, user=p.username,
                       password=p.password, database=p.path.lstrip("/"),
                       ssl={"ssl_disabled": False}, connect_timeout=30, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("DELETE FROM users WHERE username='timing_test_01'")
    conn.commit()
    cur.execute("SELECT COUNT(*) AS c FROM users")
    row = cur.fetchone()
    print("清理后 users 记录数:", row[0] if isinstance(row, tuple) else row["c"])
conn.close()
