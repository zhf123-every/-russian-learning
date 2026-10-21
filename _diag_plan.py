# -*- coding: utf-8 -*-
"""对照诊断：plan（sentence_slot_plans 表，P4-B 在用）vs check（老缓存表）——定位建表链断点"""
import json, time, urllib.request
import jwt as _jwt

BASE = 'https://russian-learning-jetq.onrender.com'
SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
UID = 'u_c0bc17d7b20b45799721'

tok = _jwt.encode({'sub': UID, 'role': 'admin', 'iat': int(time.time()), 'exp': int(time.time()) + 600}, SECRET, algorithm='HS256')

def post(path, body, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8')[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:300]
    except Exception as e:
        return -1, repr(e)[:200]

# plan 需要 sentence_hash/russian_text/tokens/difficulty
s, b = post('/api/admin/segments/plan', {
    'sentence_hash': 'b186482aedd7d79f', 'russian_text': 'Я люблю еду',
    'tokens': ['Я', 'люблю', 'еду'], 'difficulty': 'easy'})
print('plan(老表 sentence_slot_plans) ->', s, b)
