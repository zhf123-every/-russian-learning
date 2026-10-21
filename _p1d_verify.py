# -*- coding: utf-8 -*-
"""P1-D 订单/VIP 联调验证：套餐、下单幂等、VIP 发放、手动确认、越权、订单列表"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_UID = "u_c0bc17d7b20b45799721"
ADMIN_TOKEN = create_token(SECRET_KEY, ADMIN_UID, "admin", 3600)
BASE = "http://localhost:8000"
PASS = 0; FAIL = 0

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

def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print("  ✓ %s %s" % (name, extra))
    else: FAIL += 1; print("  ✗ %s %s" % (name, extra))

print("== P1-D 订单/VIP 验证 ==")

# 1) 套餐（公开）
s, j = post("/api/vip/plans", {})
check("套餐 4 档", s == 200 and len(j.get("plans", [])) == 4, "pay_ready=%s" % j.get("pay_ready"))
AMT = {p["key"]: p["amount_cents"] for p in j.get("plans", [])}
check("月付 2900", AMT.get("month") == 2900)
check("年付 34000", AMT.get("year") == 34000)

# 2) 未登录下单 → 401
s, j = post("/api/order/create", {"plan_key": "month"})
check("未登录下单 401", s == 401)

# 3) 注册用户 → 下单 → 幂等复用 → 手动确认 → VIP
uname = "p1d_test_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
check("注册测试用户", s == 200 and j.get("ok"))
utoken = j.get("token", ""); uid = j.get("user", {}).get("id", "")

s, j = post("/api/order/create", {"plan_key": "month"}, token=utoken)
check("下单成功", s == 200 and j.get("ok"), "order=%s" % j.get("order_no"))
ono1 = j.get("order_no", "")
s, j2 = post("/api/order/create", {"plan_key": "month"}, token=utoken)
check("幂等复用同订单", j2.get("order_no") == ono1)

s, j = post("/api/order/status", {"order_no": ono1}, token=utoken)
check("查订单状态 created", s == 200 and j.get("order", {}).get("status") == "created")

# 篡改金额防护：非法套餐
s, j = post("/api/order/create", {"plan_key": "hack"}, token=utoken)
check("非法套餐被拒", s == 400)

# learner 不能调手动确认
s, j = post("/api/order/manual-pay", {"order_no": ono1}, token=utoken)
check("learner 手动确认 403", s == 403)

# admin 手动确认 → VIP 发放（月付 → 30 天）
s, j = post("/api/order/manual-pay", {"order_no": ono1}, token=ADMIN_TOKEN)
print("  [debug] manual-pay 完整响应:", json.dumps(j, ensure_ascii=False))
check("手动确认成功", s == 200 and j.get("ok"), "vip_expire_at=%s" % j.get("vip_expire_at"))
s, j = post("/api/vip/status", {}, token=utoken)
print("  [debug] vip/status 完整响应:", json.dumps(j, ensure_ascii=False))
check("VIP 已生效 is_vip", j.get("is_vip") is True, "days_left=%s" % j.get("days_left"))
check("VIP 天数 ~30", 28 <= j.get("days_left", 0) <= 31)

# 重复确认幂等
s, j = post("/api/order/manual-pay", {"order_no": ono1}, token=ADMIN_TOKEN)
check("重复确认 already_paid", s == 200 and j.get("already_paid") is True)

# 4) 年付叠加（重新下单年付 → 确认 → 到期延长 > 365 天）
s, j = post("/api/order/create", {"plan_key": "year"}, token=utoken)
ono2 = j.get("order_no", "")
post("/api/order/manual-pay", {"order_no": ono2}, token=ADMIN_TOKEN)
s, j = post("/api/vip/status", {}, token=utoken)
check("叠加后 ~395 天", 390 <= j.get("days_left", 0) <= 400, "days=%s" % j.get("days_left"))

# 5) 终身套餐
s, j = post("/api/order/create", {"plan_key": "lifetime"}, token=utoken)
ono3 = j.get("order_no", "")
post("/api/order/manual-pay", {"order_no": ono3}, token=ADMIN_TOKEN)
s, j = post("/api/vip/status", {}, token=utoken)
check("终身 level=lifetime", j.get("level") == "lifetime", "days=%s" % j.get("days_left"))

# 6) 订单列表（admin）
s, j = post("/api/admin/orders", {"q": uname}, token=ADMIN_TOKEN)
check("订单列表命中 3 单", s == 200 and j.get("total", 0) >= 3, "total=%s" % j.get("total"))
s, j = post("/api/admin/orders", {}, token=utoken)
check("learner 订单列表 403", s == 403)

# 7) 微信回调占位（未配置 → 503）
s, j = post("/api/pay/wechat/notify", {})
check("微信回调未配置 503", s == 503)

# 8) 清理
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
                cur.execute("DELETE FROM orders WHERE user_id=%s", (r[0],))
                cur.execute("DELETE FROM users WHERE id=%s", (r[0],))
                print("  清理订单/用户:", uname)
        conn.commit(); conn.close()
        break
    except Exception as e:
        print("  清理失败(%d): %s" % (attempt + 1, e))
        time.sleep(15)

print("\n== 结果: %d 通过 / %d 失败 ==" % (PASS, FAIL))
