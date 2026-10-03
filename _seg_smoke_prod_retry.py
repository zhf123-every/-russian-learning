# -*- coding: utf-8 -*-
"""生产 'Я люблю книгу.' 重试（DB 已热）+ 二次命中验证"""
import io, json, time, urllib.request
import jwt as _jwt

P = r'C:\Users\张宏飞\Desktop\website_source\russian-learning-frontend-main\scripts\_seg_smoke_payload.json'
p = [x for x in json.load(io.open(P, encoding='utf-8')) if x['sentence'] == 'Я люблю книгу.'][0]
PROD = 'https://russian-learning-jetq.onrender.com/api/admin/segments/llm-segment'
PROD_SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
PROD_UID = 'u_c0bc17d7b20b45799721'
now = int(time.time())
tok = _jwt.encode({'sub': PROD_UID, 'role': 'admin', 'iat': now, 'exp': now + 600}, PROD_SECRET, algorithm='HS256')

def _call():
    body = {k: p[k] for k in ('sentence_hash', 'russian_text', 'tokens', 'difficulty')}
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(PROD, data=data, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))

try:
    r = _call()
    rebuilt = ' '.join(' '.join(p['tokens'][i] for i in g['indexes']) for g in r.get('segments') or [])
    match = r.get('ok') is True and rebuilt == p['russian_text']
    print('[Я люблю книгу.] ok=%s cached=%s segments=%d translation=%r VERIFY_MATCH=%s' % (
        r.get('ok'), r.get('cached'), len(r.get('segments') or []), r.get('translation'), match))
except urllib.error.HTTPError as e:
    print('HTTP %d -> %s' % (e.code, e.read().decode('utf-8', 'replace')[:200]))
