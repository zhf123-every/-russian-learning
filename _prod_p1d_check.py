# -*- coding: utf-8 -*-
"""P1-D 生产验证：套餐/下单/手动确认/VIP 状态/订单管理（生产 Render + TiDB）"""
import json, sys, time, urllib.request, urllib.error, datetime
sys.path.insert(0, ".")
from auth_lib import create_token

PROD = "https://russian-learning-jetq.onrender.com"
SECRET_KEY = "f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68"
ADMIN_UID = "u_c0bc17d7b20b45799721"
ADMIN_TOKEN = create_token(SECRET_KEY, ADMIN_UID, "admin", 3600)

def post(path, body, token=None, timeout=180):
    if token:
        body = dict(body); body["token"] = token
    req = urllib.request.Request(PROD + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    for a in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read().decode())
            except Exception: return e.code, {"ok": False}
        except Exception as e:
            print("  [retry %d] %s" % (a + 1, repr(e)[:120])); time.sleep(8)
    return 0, {"ok": False}

ok = 0; fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name, extra)
    else: fail += 1; print("  ✗", name, extra)

print("== P1-D 生产验证 ==")
s, j = post("/api/vip/plans", {})
check("套餐 4 档", s == 200 and j.get("ok") and len(j.get("plans")) == 4, "pay_ready=%s" % j.get("pay_ready"))

uname = "p1d_prod_%d" % int(time.time())
s, j = post("/api/auth/register", {"username": uname, "password": "pass-123456"})
utoken = j.get("token", "")
check("注册测试用户", s == 200 and j.get("ok"), uname)

s, j = post("/api/vip/status", {}, token=utoken)
check("未购 VIP 状态", s == 200 and j.get("ok") and j.get("is_vip") is False)

s, j = post("/api/order/create", {"plan_key": "month"}, token=utoken)
ono = j.get("order_no", "")
check("下单 month", s == 200 and j.get("ok") and ono, "order=%s" % ono)

s, j = post("/api/order/manual-pay", {"order_no": ono}, token=ADMIN_TOKEN)
check("手动确认发放", s == 200 and j.get("ok") and j.get("vip_expire_at"), "expire=%s" % j.get("vip_expire_at"))

s, j = post("/api/vip/status", {}, token=utoken)
check("VIP 生效 is_vip", s == 200 and j.get("ok") and j.get("is_vip") is True, "days_left=%s" % j.get("days_left"))

s, j = post("/api/order/create", {"plan_key": "lifetime"}, token=utoken)
ono2 = j.get("order_no", "")
s, j = post("/api/order/manual-pay", {"order_no": ono2}, token=ADMIN_TOKEN)
check("终身发放", s == 200 and j.get("ok") and j.get("vip_expire_at"), "expire=%s" % j.get("vip_expire_at"))

s, j = post("/api/vip/status", {}, token=utoken)
check("终身 level=lifetime", s == 200 and j.get("ok") and j.get("level") == "lifetime", "days=%s" % j.get("days_left"))

s, j = post("/api/admin/orders", {"page": 1, "size": 5, "q": uname}, token=ADMIN_TOKEN)
check("订单管理命中", s == 200 and j.get("ok") and j.get("total") >= 2, "total=%s" % j.get("total"))

s, j = post("/api/admin/orders", {}, token=utoken)
check("learner 订单列表 403", s == 403)

# 清理生产库测试数据（直连 TiDB）
try:
    import pymysql
    from urllib.parse import urlparse
    p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
    for a in range(3):
        try:
            conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                                   database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                                   connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE username LIKE 'p1d_prod_%'")
                ids = [r[0] for r in cur.fetchall()]
                if ids:
                    cur.execute("DELETE FROM orders WHERE user_id IN (%s)" % ",".join(["%s"] * len(ids)), ids)
                    cur.execute("DELETE FROM users WHERE id IN (%s)" % ",".join(["%s"] * len(ids)), ids)
                    print("清理生产测试数据:", len(ids))
                else:
                    print("无生产残留")
            conn.commit(); conn.close()
            break
        except Exception as e:
            print("清理失败(%d): %s" % (a + 1, e)); time.sleep(10)
except Exception as e:
    print("清理跳过:", e)

print("== 结果: %d 通过 / %d 失败 ==" % (ok, fail))
sys.exit(1 if fail else 0)
