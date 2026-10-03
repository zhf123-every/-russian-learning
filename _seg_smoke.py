# -*- coding: utf-8 -*-
"""P1 端到端冒烟：
1) 本地（无 AI_API_KEY）：POST /api/admin/segments/llm-segment → 预期 {ok:false,fallback:true}（真链路：鉴权→参数→缓存查询→LLM 不可用回退）
2) 生产（真 LLM）：POST 生产 llm-segment → 预期 {ok:true,segments,translation}；再用前端 verifySegments 等价逻辑二次校验拼接==俄语化原句
"""
import io, json, time, urllib.request

P = r'C:\Users\张宏飞\Desktop\website_source\russian-learning-frontend-main\scripts\_seg_smoke_payload.json'
payloads = json.load(io.open(P, encoding='utf-8'))
LOCAL = 'http://127.0.0.1:8000/api/admin/segments/llm-segment'
PROD = 'https://russian-learning-jetq.onrender.com/api/admin/segments/llm-segment'
LOCAL_ADMIN_KEY = 'local-p0-admin-key'
PROD_SECRET = 'f1af671f29f125467d69431d87dc7f5cc1a039aea236dd3c75f38c8be69e2c68'
PROD_UID = 'u_c0bc17d7b20b45799721'

def _post(url, body, token=None, admin_key=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))

def _prod_token():
    import jwt as _jwt
    now = int(time.time())
    return _jwt.encode({'sub': PROD_UID, 'role': 'admin', 'iat': now, 'exp': now + 600},
                       PROD_SECRET, algorithm='HS256')

def _verify_segments_rebuilt(groups, tokens, russianized):
    """前端 verifySegments 等价逻辑：按索引机械截取重建，逐字符 == 俄语化原句"""
    rebuilt = ' '.join(' '.join(tokens[i] for i in g['indexes']) for g in groups)
    return rebuilt == russianized, rebuilt

print('== 1) 本地链路骨架冒烟（无 AI_API_KEY） ==')
for p in payloads:
    body = {k: p[k] for k in ('sentence_hash', 'russian_text', 'tokens', 'difficulty')}
    try:
        r = _post(LOCAL, body, admin_key=LOCAL_ADMIN_KEY)
        ok = r.get('ok') is False and r.get('fallback') is True
        print('  [%s] -> ok=%s fallback=%s EXPECT_OK=%s' % (p['sentence'], r.get('ok'), r.get('fallback'), ok))
    except Exception as e:
        print('  [%s] LOCAL ERROR: %s' % (p['sentence'], e))

print('== 2) 生产真 LLM 冒烟 ==')
tok = _prod_token()
for p in payloads:
    body = {k: p[k] for k in ('sentence_hash', 'russian_text', 'tokens', 'difficulty')}
    try:
        r = _post(PROD, body, token=tok)
    except Exception as e:
        print('  [%s] PROD ERROR: %s' % (p['sentence'], e))
        continue
    if r.get('ok') is True and isinstance(r.get('segments'), list):
        match, rebuilt = _verify_segments_rebuilt(r['segments'], p['tokens'], p['russian_text'])
        print('  [%s] -> ok=%s segments=%d translation=%r VERIFY_MATCH=%s' % (
            p['sentence'], r.get('ok'), len(r['segments']), r.get('translation'), match))
        if not match:
            print('    REBUILT=%r' % rebuilt)
    else:
        print('  [%s] -> 非预期响应: ok=%s fallback=%s pending=%s' % (
            p['sentence'], r.get('ok'), r.get('fallback'), r.get('pending')))
