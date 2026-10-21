# -*- coding: utf-8 -*-
"""补充探针：id 更新停用 + 未登录鉴权码确认"""
import json, sys, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token
SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
ADMIN_TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)
BASE = "http://localhost:8000"

def post(path, body, token=None):
    if token:
        body = dict(body); body["token"] = token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Connection": "close"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {"ok": False}

print("--- 新增 ---")
s, j = post("/api/admin/categories/save", {"name": "停用测试", "sub_name": "子1", "sort_order": 998}, token=ADMIN_TOKEN)
print(s, j)
print("--- list 定位 ---")
s, j = post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
tid = next((r["id"] for r in j.get("rows", []) if r["name"] == "停用测试" and r["sub_name"] == "子1"), "")
print("tid:", tid)
print("--- 带 id 停用 ---")
s, j = post("/api/admin/categories/save", {"id": tid, "name": "停用测试", "sub_name": "子1", "sort_order": 998, "is_active": 0}, token=ADMIN_TOKEN)
print(s, j)
print("--- tree 应无 ---")
s, j = post("/api/categories/tree", {})
hit = any(c["name"] == "停用测试" for c in j.get("tree", []))
print("tree 含停用测试:", hit, "（期望 False）")
print("--- 未登录 admin 接口状态码 ---")
s, j = post("/api/admin/categories/list", {})
print("未登录 list:", s, j)
s, j = post("/api/admin/users/list", {})
print("未登录 users/list:", s, j)
print("--- 清理 ---")
s, j = post("/api/admin/categories/delete", {"name": "停用测试"}, token=ADMIN_TOKEN)
print(s, j)
