# -*- coding: utf-8 -*-
"""P1-B 学习记录上云联调验证：注册测试用户→保存断点→拉取→断言→清理"""
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

print("== P1-B 联调验证 ==")

# 1) 注册测试用户
uname = "p1b_test_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
check("注册测试用户", s == 200 and j.get("ok"), uname)
uid = (j.get("user") or {}).get("id", "")
utoken = j.get("token", "")

# 2) 未登录保存 → 401
s, j = post("/api/learning/progress/save", {"items": [{"unit_id": "u1", "mode": "practice"}]})
check("未登录保存被拒(401)", s == 401)

# 3) 登录批量保存 3 条（不同课时/模式）
items = [
    {"course_id": "c1", "unit_id": "unit_a", "mode": "practice", "seq_index": 3, "unit_index": 2, "difficulty": "advanced", "status": 0, "ts": 1000},
    {"course_id": "c1", "unit_id": "unit_a", "mode": "speaking", "seq_index": 1, "unit_index": 0, "difficulty": "easy", "status": 1, "ts": 2000},
    {"course_id": "c2", "unit_id": "unit_b", "mode": "dictation", "seq_index": 0, "unit_index": 0, "difficulty": "", "status": 0, "ts": 3000},
]
s, j = post("/api/learning/progress/save", {"items": items}, token=utoken)
check("批量保存成功", s == 200 and j.get("ok") and j.get("count") == 3)

# 4) 重复保存同 key（UPSERT 覆盖）
s, j = post("/api/learning/progress/save", {"items": [{"course_id": "c1", "unit_id": "unit_a", "mode": "practice", "seq_index": 5, "unit_index": 4, "status": 0, "ts": 9000}]}, token=utoken)
check("UPSERT 覆盖成功", s == 200 and j.get("ok"))

# 5) 拉取全部 → 3 条且 practice 为最新值
s, j = post("/api/learning/progress", {}, token=utoken)
check("拉取全部成功", s == 200 and j.get("ok") and len(j.get("items", [])) == 3)
m = {i["unit_id"] + "|" + i["mode"]: i for i in j.get("items", [])}
p = m.get("unit_a|practice", {})
check("UPSERT 生效(seq=5)", p.get("seq_index") == 5 and p.get("unit_index") == 4 and p.get("ts") == 9000)
check("speaking 完成标记 status=1", m.get("unit_a|speaking", {}).get("status") == 1)

# 6) 按课程过滤
s, j = post("/api/learning/progress", {"course_id": "c1"}, token=utoken)
check("按课程过滤(2条)", s == 200 and len(j.get("items", [])) == 2)

# 7) 用户隔离：admin 拉不到测试用户的数据
s, j = post("/api/learning/progress", {}, token=ADMIN_TOKEN)
check("用户隔离(admin 无数据)", s == 200 and len(j.get("items", [])) == 0)

# 8) course/complete 接 user_id
s, j = post("/api/course/complete", {"course_id": "c1", "completion_time": 120, "correct_count": 8, "total_count": 10, "max_combo": 5, "rating": "A"}, token=utoken)
check("course/complete 带用户保存", s == 200 and j.get("ok"))
s, j = post("/api/course/complete", {"course_id": "c2", "completion_time": 60, "correct_count": 5, "total_count": 10, "max_combo": 3, "rating": "B"})
check("course/complete 匿名仍可用", s == 200 and j.get("ok"))

# 9) 直连库核对 user_id 落库
import pymysql
from urllib.parse import urlparse
p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT user_id FROM quest_learning_records WHERE course_id='c1' ORDER BY created_at DESC LIMIT 1")
    r = cur.fetchone()
    check("完成记录 user_id 已落库", r and r[0] == uid)
    cur.execute("SELECT user_id FROM quest_learning_records WHERE course_id='c2' ORDER BY created_at DESC LIMIT 1")
    r2 = cur.fetchone()
    check("匿名记录 user_id 为空", r2 and r2[0] == "")
    # 清理测试数据
    cur.execute("DELETE FROM quest_learning_progress WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM quest_learning_records WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
conn.commit(); conn.close()
print("  已清理测试数据")

print("\n== 结果: %d 通过 / %d 失败 ==" % (PASS, FAIL))
