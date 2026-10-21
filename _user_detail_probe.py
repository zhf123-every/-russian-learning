# 用户详情接口生产探针 v2（无需密码：验证路由已部署 + 鉴权生效）
# 未注册路由 → 404 非 JSON；已注册但未鉴权 → 403 JSON
import json, urllib.request, sys

BASE = "https://russian-learning-jetq.onrender.com"

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Connection": "close",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# 1) 未鉴权调用 detail（路由存在则应返回 403 JSON）
st, body = post("/api/admin/users/detail", {"id": "x"})
try:
    j = json.loads(body)
    is_json = True
except Exception:
    is_json = False
print("未鉴权 detail:", st, "JSON=", is_json, (j.get("error") if is_json else body[:80]))
ok1 = st == 403 and is_json and j.get("error")

# 2) 不存在的路由对照（应 404，且不是我们的 JSON 格式）
st2, body2 = post("/api/admin/users/detail_nonexistent", {})
try:
    j2 = json.loads(body2)
    is_json2 = True
except Exception:
    is_json2 = False
print("对照不存在路由:", st2, "JSON=", is_json2)

print("== 路由已部署并鉴权生效:", ok1, "==")
sys.exit(0 if ok1 else 1)
