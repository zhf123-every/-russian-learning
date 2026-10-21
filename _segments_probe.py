# P1 segments 接口本地探针 v3（upsert / 占位行 / llm-segment 幂等 / translation / status 命名）
import json, urllib.request, urllib.error, sys, hashlib

BASE = "http://127.0.0.1:8000"
ADMIN_KEY = "local-p0-admin-key"
H1 = hashlib.sha256("Я люблю книгу.".encode()).hexdigest()[:16]
H2 = hashlib.sha256("Он читает книгу в школе.".encode()).hexdigest()[:16]
H3 = hashlib.sha256("Этому городу уже 500 лет.".encode()).hexdigest()[:16]
CID, UID = "course_probe_1", "unit_probe_1"

def post(path, body, admin=True):
    payload = dict(body)
    if admin:
        payload["adminKey"] = ADMIN_KEY
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Connection": "close"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Connection": "close"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

results = []
def check(name, cond, extra=""):
    results.append((name, cond, extra))
    print(("PASS" if cond else "FAIL"), name, extra)

# 1) 未鉴权 → 403
st, j = post("/api/admin/segments/check", {"sentences": []}, admin=False)
check("未鉴权 check 403", st == 403, f"{st} {j.get('error')}")

# 2) 空列表 → 400
st, j = post("/api/admin/segments/check", {"sentences": []})
check("空 sentences 400", st == 400, f"{st}")

# 3) llm-segment 未命中 + 无 key → fallback:true（本地无 AI_API_KEY）
st, j = post("/api/admin/segments/llm-segment",
             {"sentence_hash": H3, "russian_text": "Этому городу уже пятьсот лет.",
              "tokens": ["Этому", "городу", "уже", "пятьсот", "лет."], "difficulty": "easy"})
check("llm-segment 未命中无key fallback", st == 200 and j.get("fallback") is True, f"{st} {j}")

# 4) llm-segment 缺参 → 400
st, j = post("/api/admin/segments/llm-segment", {"sentence_hash": H3})
check("llm-segment 缺参 400", st == 400, f"{st}")

# 5) save 两句（句1 easy 带 translation；句2 hard）——upsert 写入
items = [
    {"sentence_hash": H1, "sentence": "Я люблю книгу.", "difficulty": "easy",
     "translation": "我爱书。",
     "segments": [{"sort_order": 0, "text": "Я люблю", "type": "phrase", "chinese": "我爱"},
                  {"sort_order": 1, "text": "книгу.", "type": "word", "chinese": "书。"}]},
    {"sentence_hash": H2, "sentence": "Он читает книгу в школе.", "difficulty": "hard",
     "segments": [{"sort_order": 0, "text": "Он читает", "type": "phrase", "chinese": "他读"},
                  {"sort_order": 1, "text": "книгу", "type": "word", "chinese": "书"},
                  {"sort_order": 2, "text": "в школе.", "type": "prep_phrase", "chinese": "在学校。"}]},
]
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID, "items": items})
check("save 2 句", st == 200 and j.get("saved") == 2, f"{st} {j}")

# 6) check 命中（出参 status 命名）
st, j = post("/api/admin/segments/check", {"sentences": [{"sentence_hash": H1, "difficulty": "easy"},
                                                        {"sentence_hash": H2, "difficulty": "hard"}]})
c = j.get("cached", [])
check("check 命中 2 + status 字段", st == 200 and len(c) == 2 and all("status" in x and "review_status" not in x for x in c), f"{c}")

# 7) llm-segment 命中 ok cache → cached 文本组 + translation（不调 LLM）
st, j = post("/api/admin/segments/llm-segment",
             {"sentence_hash": H1, "russian_text": "Я люблю книгу.",
              "tokens": ["Я", "люблю", "книгу."], "difficulty": "easy"})
check("llm-segment 命中缓存", st == 200 and j.get("cached") is True and len(j.get("segments", [])) == 2 and j.get("translation") == "我爱书。", f"{st} cached={j.get('cached')} segs={len(j.get('segments', []))} trans={j.get('translation')}")

# 8) 公开读：translation 透传 + status 字段
st, j = get(f"/api/segments?course_id={CID}&unit_id={UID}")
items = j.get("items", [])
g1 = next((x for x in items if x["sentence_hash"] == H1), None)
check("read 2 组 + translation 透传", st == 200 and len(items) == 2 and g1 and g1.get("translation") == "我爱书。" and all("status" in x for x in items), f"items={len(items)} trans={g1.get('translation') if g1 else None}")

# 9) 重复 save 幂等（upsert：cache 不新增行）
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H1, "sentence": "Я люблю книгу.", "difficulty": "easy",
               "translation": "我爱书。",
               "segments": [{"sort_order": 0, "text": "Я", "type": "word", "chinese": "我"},
                            {"sort_order": 1, "text": "люблю книгу.", "type": "phrase", "chinese": "爱书。"}]}]})
st2, j2 = post("/api/admin/segments/check", {"sentences": [{"sentence_hash": H1, "difficulty": "easy"}]})
check("重复 save 幂等（cache 仍 1 条）", st == 200 and len(j2.get("cached", [])) == 1, f"{j2.get('cached')}")

# 10) 组尾部裁剪：H1 由 2 块改为 2 块同序（此处验证 upsert 覆盖内容）
st, j = get(f"/api/segments?course_id={CID}&unit_id={UID}")
g1 = next((x for x in j.get("items", []) if x["sentence_hash"] == H1), None)
check("upsert 覆盖内容（2 块新文本）", g1 and len(g1["segments"]) == 2 and g1["segments"][0]["text"] == "Я", f"{[s['text'] for s in g1['segments']] if g1 else None}")
# 先 save 3 块再 save 2 块 → 旧 sort_order=2 行被裁剪
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H2, "difficulty": "hard",
               "segments": [{"sort_order": 0, "text": "Он читает", "type": "phrase", "chinese": "他读"},
                            {"sort_order": 1, "text": "книгу", "type": "word", "chinese": "书"},
                            {"sort_order": 2, "text": "в школе.", "type": "prep_phrase", "chinese": "在学校。"}]}]})
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H2, "difficulty": "hard",
               "segments": [{"sort_order": 0, "text": "Он читает книгу", "type": "chunk", "chinese": "他读书"},
                            {"sort_order": 1, "text": "в школе.", "type": "prep_phrase", "chinese": "在学校。"}]}]})
st, j = get(f"/api/segments?course_id={CID}&unit_id={UID}")
g2 = next((x for x in j.get("items", []) if x["sentence_hash"] == H2), None)
check("组尾部裁剪（3块→2块，无残留）", g2 and len(g2["segments"]) == 2 and all(s["sort_order"] < 2 for s in g2["segments"]), f"{[s['sort_order'] for s in g2['segments']] if g2 else None}")

# 11) pending 兜底标记（status 命名）+ pending 查询
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H2, "difficulty": "hard",
               "segments": [{"sort_order": 0, "text": "Он читает книгу", "type": "chunk", "chinese": "他读书"},
                            {"sort_order": 1, "text": "в школе.", "type": "prep_phrase", "chinese": "在学校。"}],
               "status": "pending"}]})
st2, j2 = post("/api/admin/segments/pending", {"course_id": CID, "unit_id": UID})
check("pending 标记可查（status 字段）", st == 200 and any(p["sentence_hash"] == H2 and p.get("status") == "pending" for p in j2.get("pending", [])), f"{j2.get('pending')}")
# pending 句重新生成 ok → 升级
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H2, "difficulty": "hard",
               "segments": [{"sort_order": 0, "text": "Он читает", "type": "phrase", "chinese": "他读"},
                            {"sort_order": 1, "text": "книгу в школе.", "type": "prep_phrase", "chinese": "在学校读书。"}],
               "status": "ok"}]})
st2, j2 = post("/api/admin/segments/pending", {"course_id": CID, "unit_id": UID})
check("pending→ok 升级后不再出现", st == 200 and not any(p["sentence_hash"] == H2 for p in j2.get("pending", [])), f"{j2.get('pending')}")

# 12) 占位行：save 无 segments 无 cache → 公开读 status='generating'、segments=[]
H4 = hashlib.sha256("Антон спросил Тома.".encode()).hexdigest()[:16]
st, j = post("/api/admin/segments/save", {"course_id": CID, "unit_id": UID,
    "items": [{"sentence_hash": H4, "difficulty": "easy"}]})
st2, j2 = get(f"/api/segments?course_id={CID}&unit_id={UID}")
g4 = next((x for x in j2.get("items", []) if x["sentence_hash"] == H4), None)
check("占位行 generating + segments 空", st == 200 and j.get("saved") == 1 and g4 and g4.get("status") == "generating" and g4["segments"] == [], f"saved={j.get('saved')} g={g4}")

# 13) pending 接口 status=generating 可筛
st, j = post("/api/admin/segments/pending", {"course_id": CID, "unit_id": UID, "status": "generating"})
check("pending(status=generating) 筛出占位句", any(p["sentence_hash"] == H4 for p in j.get("pending", [])), f"{j.get('pending')}")
st, j = post("/api/admin/segments/pending", {"course_id": CID, "unit_id": UID, "status": "all"})
check("pending(status=all) 包含 generating+pending", len(j.get("pending", [])) >= 2, f"{j.get('pending')}")

# 14) llm-segment 对 generating 的 cache：save 占位后再请求 llm-segment（无 key → fallback，而非 cached）
st, j = post("/api/admin/segments/llm-segment",
             {"sentence_hash": H4, "russian_text": "Антон спросил Тома.",
              "tokens": ["Антон", "спросил", "Тома."], "difficulty": "easy"})
check("llm-segment 占位句无key fallback（未写 ok cache）", st == 200 and j.get("fallback") is True, f"{st} {j}")

# 15) 删课时（事务内）→ 该课时清空；全局 cache 保留
st, j = post("/api/admin/segments/delete", {"course_id": CID, "unit_id": UID})
st2, j2 = get(f"/api/segments?course_id={CID}&unit_id={UID}")
st3, j3 = post("/api/admin/segments/check", {"sentences": [{"sentence_hash": H1, "difficulty": "easy"}]})
check("delete unit 清空该课时", st == 200 and j.get("deleted", 0) >= 1 and len(j2.get("items", [])) == 0, f"deleted={j.get('deleted')} read={len(j2.get('items', []))}")
check("delete 后全局 cache 仍命中", st3 == 200 and len(j3.get("cached", [])) == 1, f"{j3.get('cached')}")

# 16) 对照不存在路由 404
st, j = post("/api/admin/segments/nonexistent", {"course_id": CID})
check("对照 404", st == 404, f"{st}")

# 17) 清理：删 course（幂等，无残留行返回 0 合法）；之后该 course 无公开数据
st, j = post("/api/admin/segments/delete", {"course_id": CID})
st2, j2 = get(f"/api/segments?course_id={CID}&unit_id={UID}")
check("delete course 清理后无残留", st == 200 and isinstance(j.get("deleted", 0), int) and len(j2.get("items", [])) == 0, f"deleted={j.get('deleted')} read={len(j2.get('items', []))}")

print("==", "全部通过" if all(c for _, c, _ in results) else "存在失败", f"{sum(1 for _, c, _ in results if c)}/{len(results)}", "==")
sys.exit(0 if all(c for _, c, _ in results) else 1)
