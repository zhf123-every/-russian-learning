# -*- coding: utf-8 -*-
"""P1-C 生产验证：tree 公开接口 + admin CRUD（新增→清理）"""
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
            time.sleep(20)  # Render 冷启动/迁移窗口重试

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name, extra)
    else: fail += 1; print("  ✗", name, extra)

print("== P1-C 生产验证 ==")
s, j = post("/api/categories/tree", {})
tree = j.get("tree", [])
check("公开分类树", s == 200 and j.get("ok") and len(tree) >= 9, "主分类数=%d" % len(tree))
check("种子与前端体系对齐", any(c["name"] == "教材同步" and "走遍俄罗斯" in c["subs"] for c in tree))

s, j = post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
check("admin 全量列表", s == 200 and j.get("ok") and len(j.get("rows", [])) > 60, "行数=%d" % len(j.get("rows", [])))

s, j = post("/api/admin/categories/save", {"name": "生产探针", "sub_name": "子1", "sort_order": 997}, token=ADMIN_TOKEN)
check("新增", s == 200 and j.get("ok"))
s, j = post("/api/categories/tree", {})
check("树含新增", any(c["name"] == "生产探针" for c in j.get("tree", [])))
s, j = post("/api/admin/categories/delete", {"name": "生产探针"}, token=ADMIN_TOKEN)
check("整组删除清理", s == 200 and j.get("ok"))

s, j = post("/api/admin/categories/save", {"name": "x", "sub_name": "y"})
check("未登录被拒(403)", s == 403)

print("== 结果: %d 通过 / %d 失败 ==" % (ok, fail))
sys.exit(1 if fail else 0)
