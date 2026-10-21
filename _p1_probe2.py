# -*- coding: utf-8 -*-
"""P1 审查：查课程/学习记录表结构与数据量"""
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
                time.sleep(15)
                continue
            raise

c = connect()
cur = c.cursor()
for t in ("quest_learning_records", "quest_courses", "quest_course_packs"):
    print("== %s 结构 ==" % t)
    cur.execute("SHOW CREATE TABLE %s" % t)
    print(cur.fetchone()[1][:2200])
    cur.execute("SELECT COUNT(*) FROM %s" % t)
    print("数据量: %s\n" % cur.fetchone()[0])
c.close()
