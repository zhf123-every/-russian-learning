# -*- coding: utf-8 -*-
"""排查：1) 查生产库 users 表当前记录数 2) 走 5173 测 register 路由(非法输入应400)"""
import json
import os
import urllib.request
import urllib.error
import pymysql

# 1) 直查数据库（连接串与本地后端一致）
DSN = os.environ.get("DATABASE_URL", "")
if not DSN:
    # 从本地后端环境读不到，直接内嵌（仅排查用，不落盘）
    DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"

from urllib.parse import urlparse
clean = DSN.split("?")[0]
p = urlparse(clean)
try:
    conn = pymysql.connect(
        host=p.hostname, port=p.port or 4000, user=p.username, password=p.password,
        database=p.path.lstrip("/"), ssl={"ssl_disabled": False}, connect_timeout=30, charset="utf8mb4",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM users")
        row = cur.fetchone()
        print("users 表记录数:", row[0] if isinstance(row, tuple) else row)
        cur.execute("SHOW TABLES LIKE 'users'")
        print("users 表存在:", cur.fetchone() is not None)
    conn.close()
except Exception as e:
    print("直查数据库失败:", e)

# 2) 走 5173 测 register 非法输入
req = urllib.request.Request(
    "http://localhost:5173/api/auth/register",
    data=json.dumps({"username": "bad name!", "password": "123456"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}, method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("proxy register(非法) => HTTP", r.status, r.read().decode())
except urllib.error.HTTPError as e:
    print("proxy register(非法) => HTTP", e.code, e.read().decode())
except Exception as e:
    print("proxy register(非法) => 网络失败:", e)
