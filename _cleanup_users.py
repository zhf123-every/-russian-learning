# -*- coding: utf-8 -*-
"""清理残留的 P1-A 测试用户（带 TiDB 唤醒+重试）"""
import time
import pymysql
from urllib.parse import urlparse

DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"

def connect():
    p = urlparse(DSN.split("?")[0])
    return pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                           database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                           connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")

for attempt in range(3):
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute("SELECT id, username FROM users WHERE username LIKE 'p1a_test_%' OR username LIKE 'dbg_%'")
            rows = cur.fetchall()
            print("残留测试用户:", rows)
            for uid, _ in rows:
                cur.execute("DELETE FROM users WHERE id=%s", (uid,))
            conn.commit()
            print("已清理 %d 个" % len(rows))
        conn.close()
        break
    except Exception as e:
        print("连接失败(%s): %s" % (attempt + 1, e))
        time.sleep(15)
