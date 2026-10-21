# -*- coding: utf-8 -*-
"""生产 DB 可用性对照诊断：check（老 segments 缓存表） vs table-fill（新 slot_tables 表）"""
import json, time, urllib.request
import jwt as _jwt

BASE = 'https://russian-learning-jetq.onrender.com'
SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
UID = 'u_c0bc17d7b20b45799721'

now = int(time.time())
tok = _jwt.encode({'sub': UID, 'role': 'admin', 'iat': now, 'exp': now + 600}, SECRET, algorithm='HS256')

def post(path, body, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8')[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:400]
    except Exception as e:
        return -1, str(e)[:200]

s, b = post('/api/admin/segments/check', {'sentences': []})
print('check(空列表) ->', s, b)
s, b = post('/api/admin/segments/table-fill', {'sentence_hash': '0000000000000000', 'russian_text': 'Я люблю еду', 'tokens': ['Я', 'люблю', 'еду'], 'difficulty': 'easy', 'intents': []})
print('table-fill(空intents) ->', s, b)
