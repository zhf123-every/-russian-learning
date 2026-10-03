# -*- coding: utf-8 -*-
"""本地 llm-segment 单点冒烟（无 AI_API_KEY → 预期 fallback:true）"""
import io, json, urllib.request

P = r'C:\Users\张宏飞\Desktop\website_source\russian-learning-frontend-main\scripts\_seg_smoke_payload.json'
payloads = json.load(io.open(P, encoding='utf-8'))
LOCAL = 'http://127.0.0.1:8000/api/admin/segments/llm-segment'

def _post(url, body):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode('utf-8'))

for p in payloads:
    body = {k: p[k] for k in ('sentence_hash', 'russian_text', 'tokens', 'difficulty')}
    body['adminKey'] = 'local-p0-admin-key'
    try:
        status, r = _post(LOCAL, body)
        print('[%s] HTTP %d -> ok=%s fallback=%s' % (p['sentence'], status, r.get('ok'), r.get('fallback')))
    except Exception as e:
        print('[%s] ERROR: %s' % (p['sentence'], e))
