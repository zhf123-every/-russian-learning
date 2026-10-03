# -*- coding: utf-8 -*-
"""生产 /api/ai 冒烟：判断生产 LLM 整体可用性（与 llm-segment fallback 对照）"""
import json, time, urllib.request
import jwt as _jwt

PROD = 'https://russian-learning-jetq.onrender.com/api/ai'
PROD_SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
PROD_UID = 'u_c0bc17d7b20b45799721'

now = int(time.time())
tok = _jwt.encode({'sub': PROD_UID, 'role': 'admin', 'iat': now, 'exp': now + 600}, PROD_SECRET, algorithm='HS256')
body = {
    'messages': [
        {'role': 'system', 'content': '你是俄语助教，只回答 JSON。'},
        {'role': 'user', 'content': '把单词 Я 和 люблю 组成一句话，只输出 JSON：{"russian":"Я люблю."}'},
    ],
    'json': True,
}
data = json.dumps(body, ensure_ascii=False).encode('utf-8')
req = urllib.request.Request(PROD, data=data, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode('utf-8'))
    print('HTTP OK ->', json.dumps(resp, ensure_ascii=False)[:400])
except urllib.error.HTTPError as e:
    print('HTTP %d ->' % e.code, e.read().decode('utf-8', 'replace')[:400])
except Exception as e:
    print('ERROR:', e)
