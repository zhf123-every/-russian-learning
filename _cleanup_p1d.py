# -*- coding: utf-8 -*-
"""清理 P1-D 联调残留：p1d_ 前缀测试用户及其订单"""
import pymysql, time
from urllib.parse import urlparse
p = urlparse("mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning")
for attempt in range(3):
    try:
        conn = pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                               database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                               connect_timeout=60, read_timeout=60, write_timeout=60, charset="utf8mb4")
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username LIKE 'p1d_%'")
            ids = [r[0] for r in cur.fetchall()]
            if ids:
                cur.execute("DELETE FROM orders WHERE user_id IN (%s)" % ",".join(["%s"] * len(ids)), ids)
                cur.execute("DELETE FROM users WHERE id IN (%s)" % ",".join(["%s"] * len(ids)), ids)
                print("清理用户/订单:", cur.rowcount if cur.rowcount else len(ids))
            else:
                print("无残留")
        conn.commit(); conn.close()
        break
    except Exception as e:
        print("失败(%d): %s" % (attempt + 1, e)); time.sleep(15)
