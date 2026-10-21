# -*- coding: utf-8 -*-
"""从 bkrs_dict.json 生成前端中文补全词典 dict-zh.js（单字词）"""
import json, os

SRC = r'C:\Users\张宏飞\Desktop\website_source\backend_live\bkrs_dict.json'
DST = r'C:\Users\张宏飞\Desktop\website_source\russian-learning-frontend-main\public\dict-zh.js'

src = json.load(open(SRC, encoding='utf-8'))
out = {}
for k, v in src.items():
    if ' ' in k or '-' in k or not k.strip():
        continue
    t = (v.get('translation') or '').strip()
    if not t:
        continue
    out[k] = t

with open(DST, 'w', encoding='utf-8') as f:
    f.write('/* 中文释义补全词典：来自 БКРС 俄汉词典数据（单字词） */\n')
    f.write('window.RU_DICT_ZH=')
    f.write(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    f.write(';\n')

print('written entries:', len(out))
print('size MB: %.1f' % (os.path.getsize(DST) / 1048576))
