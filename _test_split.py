# -*- coding: utf-8 -*-
import io, json, urllib.request

def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)

url = "https://russian-learning-jetq.onrender.com/api/course-split"

# 用例1：批次A全文（含 Урок N 标题行）
with io.open(r"C:\Users\张宏飞\Desktop\website_source\走遍俄罗斯课程素材\走遍俄罗斯-整书粘贴版-批次A.txt", encoding="utf-8") as f:
    batchA = f.read()

# 用例2：模拟用户贴的（无标题行，只有词表）
nohead = batchA.splitlines()
nohead = [l for l in nohead if not l.startswith("Урок")]
nohead_txt = "\n".join(nohead)

for name, text in [("含标题-批次A全文", batchA), ("无标题-仅词表", nohead_txt)]:
    s, body = post(url, {"title": "走遍俄罗斯", "category": "教材同步", "level": "A1", "text": text[:1200]})
    print("==== 用例:", name, "HTTP", s)
    print(body[:600])
    print()
