# -*- coding: utf-8 -*-
"""验证 square_submit 在 TiDB 上是否可用（ON CONFLICT 语法兼容性）+ 日志埋点。
用管理员身份提交一条测试记录再删除，全程无痕。"""
import json
import sys
import time
import uuid
import urllib.request
import urllib.error

sys.path.insert(0, ".")
from auth_lib import create_token

SECRET_KEY = "local-p0-verify-9f2c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"
UID = "u_c0bc17d7b20b45799721"  # 1462528906 管理员
TOKEN = create_token(SECRET_KEY, UID, "admin", 3600)
BASE = "http://localhost:5173"


def uuid_hex():
    return uuid.uuid4().hex[:16]


TID = "sq_test_" + uuid_hex()


def post(path, body, timeout=90):
    body["token"] = TOKEN
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8"), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), time.time() - t0
    except Exception as e:
        return 0, "失败: %s" % e, time.time() - t0


item = {
    "id": TID,
    "title": "【联调测试】请忽略",
    "category": "test",
    "level": "beginner",
    "videoUrl": "",
    "thumbnail": "",
    "description": "P0 联调自动测试，写入后立即删除",
    "author": "1462528906",
    "tags": ["p0-test"],
    "sentences": [],
    "createdAt": int(time.time() * 1000),
}
print("== 1) square_submit (期望: 保存成功并埋日志) ==")
s, body, dt = post("/api/square/submit", item)
print("HTTP %s (%.1fs) %s" % (s, dt, body))

print("== 2) square_delete (期望: 删除成功并埋日志) ==")
s, body, dt = post("/api/square/delete", {"id": TID})
print("HTTP %s (%.1fs) %s" % (s, dt, body))

print("== 3) 查操作日志 ==")
import pymysql
from urllib.parse import urlparse
DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"
p = urlparse(DSN.split("?")[0])
conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                       database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                       connect_timeout=60, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT action, username, target_type, detail FROM admin_operation_logs ORDER BY created_at DESC LIMIT 5")
    for r in cur.fetchall():
        print(r)
conn.close()
