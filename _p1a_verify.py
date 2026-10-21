# -*- coding: utf-8 -*-
"""P1-A 用户管理接口联调验证（本地后端连生产库，测试用户全链路后清理）"""
import json
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_UID = "u_c0bc17d7b20b45799721"   # 1462528906 admin
ADMIN_TOKEN = create_token(SECRET_KEY, ADMIN_UID, "admin", 3600)
BASE = "http://localhost:8000"
PASS = 0
FAIL = 0

def post(path, body, token=None, timeout=90):
    if token:
        body = dict(body)
        body["token"] = token
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
    if cond:
        PASS += 1
        print("  ✓ %s %s" % (name, extra))
    else:
        FAIL += 1
        print("  ✗ %s %s" % (name, extra))

print("== P1-A 联调验证 ==")

# 1) 注册临时测试用户
uname = "p1a_test_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
check("注册测试用户", s == 200 and j.get("ok"), uname)
test_uid = (j.get("user") or {}).get("id", "")
check("拿到测试用户 id", bool(test_uid))
learner_token = j.get("token", "")

# 2) 权限：learner 调管理接口应 403
s, j = post("/api/admin/users", {"page": 1, "size": 10}, token=learner_token)
check("learner 调列表被拒(403)", s == 403)

# 3) admin 列表
s, j = post("/api/admin/users", {"page": 1, "size": 10}, token=ADMIN_TOKEN)
check("admin 列表成功", s == 200 and j.get("ok") and isinstance(j.get("rows"), list))
check("列表不含 password_hash", all("password_hash" not in r for r in j.get("rows", [])))
total = j.get("total", 0)
check("total 正确(>=2)", total >= 2, "total=%s" % total)

# 4) 改角色 learner -> editor
s, j = post("/api/admin/users/role", {"id": test_uid, "role": "editor"}, token=ADMIN_TOKEN)
check("改角色 editor", s == 200 and j.get("ok"))
s, j = post("/api/auth/login", {"username": uname, "password": "pass-123456"})
check("editor 可登录", s == 200 and (j.get("user") or {}).get("role") == "editor")

# 5) 非法角色拒绝
s, j = post("/api/admin/users/role", {"id": test_uid, "role": "superadmin"}, token=ADMIN_TOKEN)
check("非法角色被拒(400)", s == 400)

# 6) 改回 learner
s, j = post("/api/admin/users/role", {"id": test_uid, "role": "learner"}, token=ADMIN_TOKEN)
check("改回 learner", s == 200 and j.get("ok"))

# 7) 禁用 -> 登录应 401
s, j = post("/api/admin/users/status", {"id": test_uid, "status": 0}, token=ADMIN_TOKEN)
check("禁用成功", s == 200 and j.get("ok"))
s, j = post("/api/auth/login", {"username": uname, "password": "pass-123456"})
check("禁用后登录被拒(403)", s in (401, 403), "code=%s" % s)

# 8) 启用 -> 登录成功
s, j = post("/api/admin/users/status", {"id": test_uid, "status": 1}, token=ADMIN_TOKEN)
check("启用成功", s == 200 and j.get("ok"))
s, j = post("/api/auth/login", {"username": uname, "password": "pass-123456"})
check("启用后登录成功", s == 200)

# 9) 重置密码（指定新密码）
s, j = post("/api/admin/users/reset-password", {"id": test_uid, "new_password": "new-pass-888"}, token=ADMIN_TOKEN)
check("重置密码成功", s == 200 and j.get("ok"))
s, j = post("/api/auth/login", {"username": uname, "password": "new-pass-888"})
check("新密码可登录", s == 200)

# 10) 防锁死：把最后一名 admin 降级应被拒
s, j = post("/api/admin/users/role", {"id": ADMIN_UID, "role": "editor"}, token=ADMIN_TOKEN)
check("最后一个 admin 降级被拒(400)", s == 400)

# 11) 防锁死：禁用最后一个 admin 应被拒
s, j = post("/api/admin/users/status", {"id": ADMIN_UID, "status": 0}, token=ADMIN_TOKEN)
check("最后一个 admin 禁用被拒(400)", s == 400)

# 12) 防锁死：admin 不能改自己角色
s, j = post("/api/admin/users/role", {"id": ADMIN_UID, "role": "viewer"}, token=ADMIN_TOKEN)
check("admin 改自己被拒(400)", s == 400)

# 13) 不存在用户
s, j = post("/api/admin/users/role", {"id": "u_nonexist", "role": "viewer"}, token=ADMIN_TOKEN)
check("不存在用户返回 404", s == 404)

# 14) 旧 adminKey 兼容：管理接口放行
s, j = post("/api/admin/users", {"page": 1, "size": 10, "adminKey": "local-p0-admin-key"})
check("旧 adminKey 调列表放行", s == 200 and j.get("ok"))

# 15) 操作日志埋点（查最新几条）
import pymysql
from urllib.parse import urlparse
DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"
p = urlparse(DSN.split("?")[0])
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT action, username, detail FROM admin_operation_logs ORDER BY created_at DESC LIMIT 6")
    logs = cur.fetchall()
actions = [l[0] for l in logs]
check("日志含 user_role_update", "user_role_update" in actions)
check("日志含 user_status_update", "user_status_update" in actions)
check("日志含 user_password_reset", "user_password_reset" in actions)
print("  最近日志:", logs[:3])
conn.close()

# 16) 清理测试用户（SQL 删除）
p = urlparse(DSN.split("?")[0])
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("DELETE FROM users WHERE id=%s", (test_uid,))
    print("  清理测试用户:", cur.rowcount)
conn.commit()
conn.close()

print("\n== 结果: %d 通过 / %d 失败 ==" % (PASS, FAIL))
