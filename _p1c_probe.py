# -*- coding: utf-8 -*-
"""逐个单发探针：每个请求独立进程级连接，打印原始响应"""
import json, sys, time, urllib.request, urllib.error
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
        print(path, r.status, r.read().decode()[:300]); return
    except urllib.error.HTTPError as e:
        print(path, e.code, e.read().decode()[:300]); return
    except Exception as e:
        print(path, "ERR", repr(e)[:200])

print("--- 1 tree(种子) ---"); post("/api/categories/tree", {})
print("--- 2 save 新增 ---"); post("/api/admin/categories/save", {"name": "探针分类", "sub_name": "探子1", "sort_order": 999}, token=ADMIN_TOKEN)
print("--- 3 tree(应含探针) ---"); post("/api/categories/tree", {})
print("--- 4 list 定位 ---"); post("/api/admin/categories/list", {}, token=ADMIN_TOKEN)
print("--- 5 save 停用 ---"); post("/api/admin/categories/save", {"name": "探针分类", "sub_name": "探子1", "sort_order": 999, "is_active": 0}, token=ADMIN_TOKEN)
print("--- 6 tree(应无探针) ---"); post("/api/categories/tree", {})
print("--- 7 未登录 save ---"); post("/api/admin/categories/save", {"name": "x", "sub_name": "y"})
print("--- 8 未登录 list ---"); post("/api/admin/categories/list", {})
print("--- 9 清理 ---"); post("/api/admin/categories/delete", {"name": "探针分类"}, token=ADMIN_TOKEN)
