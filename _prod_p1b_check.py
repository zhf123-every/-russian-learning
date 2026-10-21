# -*- coding: utf-8 -*-
"""P1-B 生产验证：用生产 SECRET_KEY 签 admin token，验证 save/get 接口 + 表结构，测后清理"""
import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from auth_lib import create_token

PROD = "https://russian-learning-jetq.onrender.com"
SECRET_KEY = "f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68"
TOKEN = create_token(SECRET_KEY, "u_c0bc17d7b20b45799721", "admin", 3600)

def post(path, body, timeout=90):
    body = dict(body); body["token"] = TOKEN
    req = urllib.request.Request(PROD + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"ok": False}

ts = int(time.time())
uid = "prod_check_%d" % ts
s, j = post("/api/learning/progress/save", {"items": [
    {"course_id": "pack_prodtest", "unit_id": uid + "_a", "mode": "practice", "seq_index": 3, "unit_index": 2, "difficulty": "advanced", "status": 0, "ts": ts * 1000},
    {"course_id": "pack_prodtest", "unit_id": uid + "_a", "mode": "speaking", "seq_index": 0, "unit_index": 0, "difficulty": "easy", "status": 1, "ts": ts * 1000},
]})
print("save:", s, j.get("ok"), "count=", j.get("count"))

s, j = post("/api/learning/progress", {"course_id": "pack_prodtest"})
print("get:", s, j.get("ok"), "items=", len(j.get("items", [])))
for it in j.get("items", []):
    print("  -", it.get("unit_id"), "|", it.get("mode"), "| status=", it.get("status"), "| seq=", it.get("seq_index"))

s, j = post("/api/learning/progress", {})
print("get all:", s, j.get("ok"), "items=", len(j.get("items", [])))

# 清理（直连库）
import pymysql
from urllib.parse import urlparse
p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("DELETE FROM quest_learning_progress WHERE course_id='pack_prodtest'")
    print("清理:", cur.rowcount)
conn.commit(); conn.close()
