# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error
PROD = "https://russian-learning-jetq.onrender.com"
def post(path, body):
    req = urllib.request.Request(PROD + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=180)
        print(path, r.status, r.read().decode()[:500])
    except urllib.error.HTTPError as e:
        print(path, e.code, e.read().decode()[:500])
    except Exception as e:
        print(path, "ERR", repr(e))
post("/api/vip/plans", {})
