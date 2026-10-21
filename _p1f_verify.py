# -*- coding: utf-8 -*-
"""P1-F 联调：settings 公开/管理读、VIP 价格动态化、站点信息、非法回滚、恢复默认"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None, timeout=120):
    time.sleep(0.2)
    if token:
        body = dict(body); body["token"] = token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Connection": "close"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {"ok": False}
    except Exception as e:
        return 0, {"ok": False, "error": repr(e)[:120]}

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name, extra)
    else: fail += 1; print("  ✗", name, extra)

print("== P1-F 系统设置联调 ==")
# 1) 公开设置（默认）
s, j = post("/api/settings/public", {})
plans = {p["key"]: p for p in j.get("plans", [])}
check("公开设置 site", s == 200 and j.get("ok") and j.get("site", {}).get("site_name"))
check("默认价格", plans.get("month", {}).get("amount_cents") == 2900 and plans.get("year", {}).get("amount_cents") == 34500,
      "month=%s year=%s" % (plans.get("month", {}).get("amount_cents"), plans.get("year", {}).get("amount_cents")))

# 2) /api/vip/plans（商城弹窗数据源）与公开一致
s, j = post("/api/vip/plans", {})
vplans = {p["key"]: p for p in j.get("plans", [])}
check("vip/plans 默认一致", vplans.get("lifetime", {}).get("amount_cents") == 108800)

# 3) admin 读全量
s, j = post("/api/admin/settings/get", {}, token=ADMIN_TOKEN)
check("admin 读设置", s == 200 and j.get("ok") and j.get("site") and j.get("vip_plans"))

# 4) 保存新价格（月付 19 元）+ 站点名
s, j = post("/api/admin/settings/save", {
    "site": {"site_name": "俄语学习站", "site_subtitle": "Test Sub", "announcement": "欢迎测试"},
    "vip_plans": {"month": {"name": "月付", "amount_cents": 1900, "months": 1, "tag": "月付 19 元"},
                  "quarter": {"amount_cents": 8500, "months": 3},
                  "year": {"amount_cents": 34500, "months": 12},
                  "lifetime": {"amount_cents": 108800, "months": None}},
}, token=ADMIN_TOKEN)
check("保存价格+站点", s == 200 and j.get("ok"))

# 5) 生效验证
s, j = post("/api/vip/plans", {})
vplans = {p["key"]: p for p in j.get("plans", [])}
check("月付新价生效", vplans.get("month", {}).get("amount_cents") == 1900)
check("年/终身未动", vplans.get("year", {}).get("amount_cents") == 34500 and vplans.get("lifetime", {}).get("amount_cents") == 108800)
s, j = post("/api/settings/public", {})
check("站点名已更新", j.get("site", {}).get("site_name") == "俄语学习站")

# 6) 非法输入被拒（负价格/错误结构）
s, j = post("/api/admin/settings/save", {"vip_plans": {"month": {"amount_cents": -100}}}, token=ADMIN_TOKEN)
check("负价格被拒", s == 400)
s, j = post("/api/admin/settings/save", {"vip_plans": {"month": "oops"}}, token=ADMIN_TOKEN)
check("错误结构被拒", s == 400)
s, j = post("/api/admin/settings/save", {"site": {"site_name": ""}}, token=ADMIN_TOKEN)
check("空站点名被拒", s == 400)
s, j = post("/api/admin/settings/save", {"vip_plans": {"month": {"amount_cents": 1900, "months": 1, "tag": "月付 19 元"}}}, token=ADMIN_TOKEN)
check("非法未破坏配置", s == 200)  # 单独合法保存应成功

# 7) 未登录被拒
s, j = post("/api/admin/settings/save", {"site": {"site_name": "x"}})
check("未登录 save 403", s == 403)

# 8) 恢复默认价格（避免污染后续测试）
s, j = post("/api/admin/settings/save", {
    "site": {"site_name": "看视频学俄语", "site_subtitle": "Russian Learning", "announcement": ""},
    "vip_plans": {"month": {"name": "月付", "amount_cents": 2900, "months": 1, "tag": "月付 29 元"},
                  "quarter": {"name": "季付", "amount_cents": 8500, "months": 3, "tag": "季付 85 元"},
                  "year": {"name": "年付", "amount_cents": 34500, "months": 12, "tag": "年付 345 元"},
                  "lifetime": {"name": "终身", "amount_cents": 108800, "months": None, "tag": "终身 1088 元"}},
}, token=ADMIN_TOKEN)
check("恢复默认价格", s == 200 and j.get("ok"))
s, j = post("/api/vip/plans", {})
vplans = {p["key"]: p for p in j.get("plans", [])}
check("默认价格已恢复", vplans.get("month", {}).get("amount_cents") == 2900)

print("== 结果: %d 通过 / %d 失败 ==" % (ok, fail))
sys.exit(1 if fail else 0)
