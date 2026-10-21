# -*- coding: utf-8 -*-
"""P1-C 联调：分类表种子/公开树/admin CRUD/停用/整组删除"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None, timeout=120):
    time.sleep(0.2)  # 本地 http.server 单线程响应竞态：请求间隔留喘息
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

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", name, extra)
    else: fail += 1; print("  ✗", name, extra)

print("== P1-C 课程分类联调 ==")
s, j = post("/api/categories/tree", {})
tree = j.get("tree", [])
check("公开分类树", s == 200 and j.get("ok") and len(tree) >= 9, "主分类数=%d" % len(tree))
check("教材同步子分类含走遍俄罗斯", s == 200 and any(c["name"] == "教材同步" and "走遍俄罗斯" in c["subs"] for c in tree))
check("子分类首项为全部", all(c["subs"][0] == "全部" for c in tree))

s, j = post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
rows = j.get("rows", [])
check("admin 全量列表", s == 200 and j.get("ok") and len(rows) > 60, "行数=%d" % len(rows))

# 新增主分类+子分类
s, j = post("/api/admin/categories/save", {"name": "测试分类", "sub_name": "测试子类", "sort_order": 999}, token=ADMIN_TOKEN)
check("新增子分类", s == 200 and j.get("ok"))
s, j = post("/api/admin/categories/save", {"name": "测试分类", "sub_name": "测试子类2", "sort_order": 999}, token=ADMIN_TOKEN)
check("新增子分类2", s == 200 and j.get("ok"))
s, j = post("/api/admin/categories/save", {"name": "测试分类", "sub_name": "测试子类", "sort_order": 999}, token=ADMIN_TOKEN)
check("重复新增被拒", s == 400)

# 树里应出现测试分类
s, j = post("/api/categories/tree", {})
check("树含测试分类", any(c["name"] == "测试分类" and "测试子类" in c["subs"] for c in j.get("tree", [])))

# 停用测试分类
s, j = post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
tid = next((r["id"] for r in j.get("rows", []) if r["name"] == "测试分类" and r["sub_name"] == "测试子类"), "")
check("定位测试分类 id", bool(tid), tid)
s, j = post("/api/admin/categories/save", {"id": tid, "name": "测试分类", "sub_name": "测试子类", "sort_order": 999, "is_active": 0}, token=ADMIN_TOKEN)
check("停用分类", s == 200 and j.get("ok"))
s, j = post("/api/categories/tree", {})
check("树中已隐藏停用项", not any(c["name"] == "测试分类" and "测试子类" in c["subs"] for c in j.get("tree", [])))

# 未登录/learner 越权（现有鉴权体系统一：无身份访问 admin 接口返回 403）
s, j = post("/api/admin/categories/save", {"name": "x", "sub_name": "y"}, token=None)
check("未登录 403", s == 403)
s, j = post("/api/admin/categories/list", {})
check("未登录列表 403", s == 403)

# 整组删除测试分类（含两个子分类）
s, j = post("/api/admin/categories/delete", {"name": "测试分类"}, token=ADMIN_TOKEN)
check("整组删除主分类", s == 200 and j.get("ok"))
s, j = post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
check("删除后无残留", not any(r["name"] == "测试分类" for r in j.get("rows", [])))

print("== 结果: %d 通过 / %d 失败 ==" % (ok, fail))
sys.exit(1 if fail else 0)
