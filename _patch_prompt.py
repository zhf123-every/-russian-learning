# -*- coding: utf-8 -*-
import io, sys

path = r"C:\Users\张宏飞\Desktop\website_source\backend_live\server.py"
with io.open(path, "r", encoding="utf-8") as f:
    src = f.read()

old = "4. 如果整个文本中找不到任何可识别的课标题，则把整段文本视为 1 课。"
new = "4. 如果整个文本中找不到任何可识别的课标题，则把整段文本视为 1 课：name 填「第一课」或文本主题，desc 填一句话简介，vocab 照常提取该文本里的生词表行。任何时候 lessons 都不能为空数组，至少返回 1 课。"

if src.count(old) != 1:
    print("ANCHOR_COUNT:", src.count(old))
    sys.exit(1)
src = src.replace(old, new)
with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("OK prompt strengthened")
