# -*- coding: utf-8 -*-
"""P1-E 数据看板联调验证：admin 调 stats、非 admin 403、字段完整性"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"
PASS = 0; FAIL = 0

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
            return e.code, {"ok": False}

def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print("  ✓ %s %s" % (name, extra))
    else: FAIL += 1; print("  ✗ %s %s" % (name, extra))

print("== P1-E 数据看板验证 ==")

# 1) 注册非 admin 用户
uname = "p1e_test_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
check("注册测试用户", s == 200 and j.get("ok"))
utoken = j.get("token", "")

# 2) learner 调 stats → 403
s, j = post("/api/admin/dashboard/stats", {}, token=utoken)
check("learner 被拒(403)", s == 403)

# 3) admin 调 stats → 200
s, j = post("/api/admin/dashboard/stats", {}, token=ADMIN_TOKEN)
check("admin 调 stats 成功", s == 200 and j.get("ok"))
st = j.get("stats", {})
check("users.total >= 1", st.get("users", {}).get("total", 0) >= 1, "total=%s" % st.get("users", {}).get("total"))
check("users.roles 含 admin", "admin" in st.get("users", {}).get("roles", {}))
check("users.new_7d 存在", "new_7d" in st.get("users", {}))
check("users.trend 存在", isinstance(st.get("users", {}).get("trend"), dict))
check("courses.packs/units 存在", "packs" in st.get("courses", {}) and "units" in st.get("courses", {}))
lr = st.get("learning", {})
check("learning.records 存在", "records" in lr, "records=%s" % lr.get("records"))
check("learning.avg_accuracy 存在", "avg_accuracy" in lr)
check("learning.active_users_7d 存在", "active_users_7d" in lr)
check("ratings 存在", isinstance(st.get("ratings"), dict))
check("top_courses 存在", isinstance(st.get("top_courses"), list))

# 4) adminKey 兼容
s, j = post("/api/admin/dashboard/stats", {"adminKey": "local-p0-admin-key"})
check("adminKey 放行", s == 200 and j.get("ok"))

# 5) 清理测试用户
import pymysql
from urllib.parse import urlparse
p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
for attempt in range(3):
    try:
        conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                               database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                               connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s", (uname,))
            r = cur.fetchone()
            if r:
                cur.execute("DELETE FROM users WHERE id=%s", (r[0],))
                print("  清理测试用户:", cur.rowcount)
        conn.commit(); conn.close()
        break
    except Exception as e:
        print("  清理连接失败(%d): %s" % (attempt + 1, e))
        time.sleep(15)

print("\n== 结果: %d 通过 / %d 失败 ==" % (PASS, FAIL))
