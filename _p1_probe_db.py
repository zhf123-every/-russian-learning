# -*- coding: utf-8 -*-
"""只读探查生产库：现有表 + 关键表结构（P1 审查用）"""
import time
import pymysql
from urllib.parse import urlparse

DSN = "mysql://3YfVDvhdkmKchdq.root:Xwfvl1gRh6KYeqCG@gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/russian_learning"
p = urlparse(DSN.split("?")[0])

def connect():
    for attempt in (1, 2):
        try:
            return pymysql.connect(host=p.hostname, port=p.port, user=p.username, password=p.password,
                                   database=p.path.lstrip("/"), ssl={"ssl_disabled": False},
                                   connect_timeout=60, read_timeout=60, write_timeout=60,
                                   charset="utf8mb4")
        except pymysql.err.OperationalError as e:
            if attempt == 1 and e.args and e.args[0] in (2013, 2003, 10060):
                print("TiDB 休眠唤醒中，等 15s 重试...")
                time.sleep(15)
                continue
            raise

c = connect()
cur = c.cursor()
cur.execute("SHOW TABLES")
tables = [r[0] for r in cur.fetchall()]
print("== 现有表 (%d) ==" % len(tables))
for t in tables:
    print(" -", t)

for t in ("users", "admin_operation_logs", "square_items", "progress", "orders", "courses", "course_units"):
    if t not in tables:
        continue
    print("\n== %s 结构 ==" % t)
    cur.execute("SHOW CREATE TABLE %s" % t)
    print(cur.fetchone()[1][:2500])
c.close()
