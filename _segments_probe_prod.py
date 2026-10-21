# P0 segments 生产探针 v2（无需密码：路由存在性 + 鉴权生效 + 公开读可用）
import json, urllib.request, urllib.error, sys

BASE = "https://russian-learning-jetq.onrender.com"

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "Connection": "close"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Connection": "close"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# 1) 未鉴权 check → 403 JSON（路由存在+鉴权生效）
st, body = post("/api/admin/segments/check", {"sentences": [{"sentence_hash": "x", "difficulty": "easy"}]})
try:
    j = json.loads(body); is_json = True
except Exception:
    is_json = False; j = {}
print("未鉴权 check:", st, "JSON=", is_json, (j.get("error") if is_json else body[:80]))
ok1 = st == 403 and is_json and "无权限" in (j.get("error") or "")

# 2) 对照不存在路由 → 404
st2, body2 = post("/api/admin/segments/check_nonexistent", {"sentences": []})
try:
    j2 = json.loads(body2); is_json2 = True
except Exception:
    is_json2 = False
print("对照不存在路由:", st2, "JSON=", is_json2)

# 3) 公开读：缺参 → 400；带不存在 id → 200 items=[]
st3, body3 = get("/api/segments")
try:
    j3 = json.loads(body3); is_json3 = True
except Exception:
    is_json3 = False
print("公开读 缺参:", st3, "JSON=", is_json3, (j3.get("error") if is_json3 else body3[:60]))
st4, body4 = get("/api/segments?course_id=probe_no_course&unit_id=probe_no_unit")
try:
    j4 = json.loads(body4); is_json4 = True
except Exception:
    is_json4 = False
print("公开读 空课时:", st4, "JSON=", is_json4, "items=", (len(j4.get("items", [])) if is_json4 else body4[:60]))
ok2 = is_json4 and st4 == 200 and isinstance(j4.get("items"), list)

print("== 路由已部署:", ok1 and ok2, "==")
sys.exit(0 if (ok1 and ok2) else 1)
