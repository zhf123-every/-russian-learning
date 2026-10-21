# -*- coding: utf-8 -*-
"""只调 check 一次：老 segments 缓存表 DB 可用性"""
import json, time, urllib.request
import jwt as _jwt

BASE = 'https://russian-learning-jetq.onrender.com'
SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
UID = 'u_c0bc17d7b20b45799721'

now = int(time.time())
tok = _jwt.encode({'sub': UID, 'role': 'admin', 'iat': now, 'exp': now + 600}, SECRET, algorithm='HS256')
body = {'sentences': [{'sentence_hash': 'b186482aedd7d79f', 'difficulty': 'easy'}]}
req = urllib.request.Request(BASE + '/api/admin/segments/check', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print('check ->', r.status, r.read().decode('utf-8')[:400])
except urllib.error.HTTPError as e:
    print('check HTTP', e.code, '->', e.read().decode('utf-8', 'replace')[:400])
except Exception as e:
    print('check ERROR ->', repr(e)[:300])
