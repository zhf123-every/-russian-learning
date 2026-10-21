# -*- coding: utf-8 -*-
"""P1-F 生产验证：settings 公开/管理、价格动态化、恢复默认"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
SECRET_KEY = "f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "https://russian-learning-jetq.onrender.com"

def post(path, body, token=None, retries=4):
    if token:
        body = dict(body); body["token"] = token
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Connection": "close"}, method="POST")
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read().decode())
            except Exception: return e.code, {"ok": False}
        except Exception as e:
            if i == retries - 1: return 0, {"ok": False, "error": repr(e)[:120]}
            time.sleep(20)

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name, extra)
    else: fail += 1; print("  ✗", name, extra)

print("== P1-F 生产验证 ==")
s, j = post("/api/settings/public", {})
plans = {p["key"]: p for p in j.get("plans", [])}
check("公开设置 site", s == 200 and j.get("ok") and j.get("site", {}).get("site_name") == "看视频学俄语")
check("默认价格", plans.get("month", {}).get("amount_cents") == 2900 and plans.get("lifetime", {}).get("amount_cents") == 108800)

s, j = post("/api/admin/settings/get", {}, token=ADMIN_TOKEN)
check("admin 读设置", s == 200 and j.get("ok") and j.get("vip_plans", {}).get("year", {}).get("amount_cents") == 34500)

# 临时改价 → 生效 → 恢复默认
s, j = post("/api/admin/settings/save", {"vip_plans": {"month": {"name": "月付", "amount_cents": 1999, "months": 1, "tag": "月付 19.99 元"}}}, token=ADMIN_TOKEN)
check("改价保存", s == 200 and j.get("ok"))
s, j = post("/api/vip/plans", {})
plans = {p["key"]: p for p in j.get("plans", [])}
check("新价生效于 vip/plans", plans.get("month", {}).get("amount_cents") == 1999)
s, j = post("/api/admin/settings/save", {"vip_plans": {"month": {"name": "月付", "amount_cents": 2900, "months": 1, "tag": "月付 29 元"}}}, token=ADMIN_TOKEN)
check("恢复默认", s == 200 and j.get("ok"))
s, j = post("/api/vip/plans", {})
plans = {p["key"]: p for p in j.get("plans", [])}
check("默认价已恢复", plans.get("month", {}).get("amount_cents") == 2900)

s, j = post("/api/admin/settings/save", {"site": {"site_name": "x"}})
check("未登录 save 403", s == 403)

print("== 结果: %d 通过 / %d 失败 ==" % (ok, fail))
sys.exit(1 if fail else 0)
