# -*- coding: utf-8 -*-
import io, json, urllib.request, time

def post(url, payload, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
        return r.status, body, round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), round(time.time() - t0, 1)
    except Exception as e:
        return 0, str(e), round(time.time() - t0, 1)

url = "https://russian-learning-jetq.onrender.com/api/course-split"
with io.open(r"C:\Users\张宏飞\Desktop\website_source\走遍俄罗斯课程素材\走遍俄罗斯-整书粘贴版-批次A.txt", encoding="utf-8") as f:
    batchA = f.read()

s, body, sec = post(url, {"title": "走遍俄罗斯", "category": "教材同步", "level": "A1", "text": batchA})
print("HTTP", s, "耗时", sec, "秒")
print(body[:800])
