# -*- coding: utf-8 -*-
"""
阶段2：句子分类器
输入：俄语句子列表 → 输出：每句的 tags + primary_tag
"""
import json
import urllib.request
import os

# 智谱 API
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-5.3-flash"

# 加载教学点字典
with open(os.path.join(os.path.dirname(__file__), "teaching_points.json"), "r", encoding="utf-8") as f:
    TEACHING_POINTS = json.load(f)


def call_glm(system_prompt, user_prompt, max_retries=3):
    """调用智谱 GLM-4-plus，返回 JSON dict。带 SSL 重试。"""
    import time

    if not ZHIPU_API_KEY:
        raise Exception("ZHIPU_API_KEY 未配置")

    payload = {
        "model": ZHIPU_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"}
    }
    data = json.dumps(payload).encode("utf-8")

    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(ZHIPU_URL, data=data, headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + ZHIPU_API_KEY,
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2)  # 间隔2秒重试
    raise last_err


def build_classify_prompt():
    """构建分类 Prompt：带上所有教学点定义"""
    points = TEACHING_POINTS["points"]
    levels = TEACHING_POINTS["levels"]

    # 教学点列表文本
    points_text = ""
    for pid, p in points.items():
        points_text += f"  {pid}: {p['name']} (难度{p['level']}) - {p['description']}\n"

    system_prompt = f"""你是俄语语法专家。你的任务是给俄语句子打语法教学点标签，并解析句子结构。

【教学点字典】
{points_text}

【规则】
1. 对每一句，列出它涉及的所有教学点（tags）
2. primary_tag = 所有涉及教学点里，难度 level 最高的那个
3. 难度等级：1=初级，2=中级，3=高级。数字越大越难。
4. 不要只选最容易的那个！primary_tag 必须是难度最高的！
5. 如果有多个难度相同的，选最核心、最能代表这句语法点的那个。

【常见误判清单】（重要！不要犯这些错误！）
- жить（住）不是运动动词（T36），它是普通第二变位法动词（T02）
- говорить（说）不是反身动词（T37），它是普通第二变位法动词（T02）
- Мне нужно + 不定式 是无人称句（T18），不是名词第三格（T21）
- 【最重要】只要句子末尾是问号（?），tags 里必须包含 T23，primary_tag 必须是 T23！不管里面还有什么其他成分！
- 疑问句的句子结构：question_word（кто/что/где 等）就是句子的主语或状语，必须放到 subject 里！不要单独放 question_word 字段！
  正确示例：Кто это? → subject = {{"lemma": "кто", "grammar": {{"case": "nom"}}}}, predicate = {{"lemma": "это", "grammar": {{}}}}
  错误示例：subject = {{"lemma": "это"}}, question_word = {{"lemma": "кто"}}
- 运动动词 T36 只包括：идти/пойти（T36a）、ехать/поехать（T36b）
- 其他动词一律不归 T36！
- T36a = идти/пойти（步行定向）
- T36b = ехать/поехать（乘车定向）

【句子结构解析】
同时输出句子的语法结构 structure，格式如下：

判断句（Это + 名词）：
{{
  "type": "judgment",
  "subject": {{"lemma": "это", "grammar": {{}}}},
  "predicate": {{"lemma": "мама", "grammar": {{"case": "nom", "gender": "fem", "number": "sing"}}}},
  "negation": false,
  "adverbial": []
}}

主谓宾（主语 + 动词 + 名词宾语）：
{{
  "type": "svo",
  "subject": {{"lemma": "я", "grammar": {{"case": "nom", "number": "sing", "person": "1"}}}},
  "verb": {{"lemma": "знать", "grammar": {{"person": "1", "number": "sing", "tense": "pres"}}}},
  "object": {{"lemma": "Иван", "grammar": {{"case": "acc", "gender": "masc", "number": "sing", "animacy": "anim"}}}},
  "negation": false,
  "adverbial": []
}}

状语：如果句子有时间/地点状语，放到 adverbial 数组里，每项含 type（time/place/manner）和 lemma。

【输出格式】
JSON:
{{
  "tags": ["T01", "T05", ...],
  "primary_tag": "T05",
  "reason": "为什么选这个当 primary_tag",
  "structure": {{...上面的结构...}}
}}
"""
    return system_prompt


def classify_one(sentence_ru, sentence_zh):
    """给单句打标签"""
    system_prompt = build_classify_prompt()
    user_prompt = f"句子：{sentence_ru}\n中文：{sentence_zh}\n\n请输出 tags 和 primary_tag。"

    result = call_glm(system_prompt, user_prompt)

    # 二次校验：确认 primary_tag 确实是 tags 里难度最高的
    tags = result.get("tags", [])
    primary = result.get("primary_tag", "")

    # ===== 兜底规则：疑问句强制归 T23（不管 tags 是不是空的）=====
    question_words = ["кто", "что", "где", "когда", "как", "почему", "какой", "какая", "какое", "какие"]
    first_word = sentence_ru.strip().lower().split()[0] if sentence_ru.strip() else ""
    if first_word in question_words or sentence_ru.strip().endswith("?"):
        if "T23" not in tags:
            tags.append("T23")
        primary = "T23"
        result["tags"] = tags
        result["primary_tag"] = primary

    if tags:
        points = TEACHING_POINTS["points"]

        # ===== 规则修正1：T25 代词第四格，只有真的有代词宾格时才算 =====
        # 代词宾格形式：меня/тебя/его/её/нас/вас/их
        pronoun_accusative = ["меня", "тебя", "его", "её", "нас", "вас", "их"]
        has_pronoun_acc = any(p in sentence_ru.lower() for p in pronoun_accusative)
        if not has_pronoun_acc and "T25" in tags:
            tags = [t for t in tags if t != "T25"]  # 移除 T25

        # ===== 规则修正2：判断句否定（T08）优先级高于判断句肯定（T07）=====
        # 如果句子里有 не，且 tags 里同时有 T07 和 T08，优先选 T08
        has_negation = " не " in (" " + sentence_ru.lower() + " ")
        if has_negation and "T08" in tags and "T07" in tags:
            tags = [t for t in tags if t != "T07"]  # 移除 T07，只留 T08

        # ===== 规则修正3：基础成分过滤 =====
        # 基础成分不应该当 primary_tag（除非整句只有基础成分）
        BASIC_TAGS = {
            "T01", "T02", "T03", "T04", "T06",
            "T12", "T13",
            "T24",
            "T28", "T29", "T30", "T31",
            "T33", "T34", "T35",
        }
        filtered_tags = [t for t in tags if t not in BASIC_TAGS]
        # 如果过滤后非空，用过滤后的 tags 选 primary
        if filtered_tags:
            tags_for_primary = filtered_tags
        else:
            tags_for_primary = tags  # 整句只有基础成分，才用全部 tags

        # 优先级权重：同难度下，越"难掌握"的语法点优先级越高
        priority = {
            # ===== 变格类内部细分（从低到高）=====
            "T05": 100,
            "T14": 110, "T17": 110, "T20": 110, "T21": 110, "T22": 110,
            "T11": 130, "T10": 125,
            "T25": 140,
            # ===== 句型类 =====
            "T07": 80, "T08": 90,  # 判断句否定比判断句肯定优先级高
            "T18": 80, "T19": 80, "T15": 80, "T16": 80, "T27": 80,
            # ===== 词类用法 =====
            "T09": 65, "T35": 65, "T33": 60, "T34": 60,
            "T06": 70,  # 否定优先级提高
            "T23": 60, "T24": 60,
            # ===== 基础代词/动词变位 =====
            "T01": 20, "T02": 20, "T03": 20, "T04": 20,
            "T12": 20, "T13": 20, "T28": 20, "T29": 20,
        }

        # 找 tags 里难度最高、优先级最高的
        best_score = -1
        correct_primary = ""
        for t in tags_for_primary:  # 用过滤后的 tags
            if t in points:
                lv = points[t]["level"]
                pri = priority.get(t, 50)
                score = lv * 100 + pri
                if score > best_score:
                    best_score = score
                    correct_primary = t

        # 如果大模型选的和规则算的不一样，以规则为准
        if correct_primary and primary != correct_primary:
            result["primary_tag"] = correct_primary
            result["reason"] += f" [规则修正：大模型选了{primary}，实际应为{correct_primary}]"

    # ===== 最终兜底：疑问句强制 T23（不管前面怎么算的）=====
    question_words = ["кто", "что", "где", "когда", "как", "почему", "какой", "какая", "какое", "какие"]
    first_word = sentence_ru.strip().lower().split()[0] if sentence_ru.strip() else ""
    if first_word in question_words or sentence_ru.strip().endswith("?"):
        result["primary_tag"] = "T23"
        if "T23" not in result["tags"]:
            result["tags"].append("T23")

    return result


def classify_sentences(sentences):
    """
    批量分类句子
    输入: [{"ru": "...", "zh": "..."}, ...]
    输出: [{"ru": "...", "zh": "...", "tags": [...], "primary_tag": "...", "level": N, "reason": "..."}, ...]
    """
    results = []
    points = TEACHING_POINTS["points"]

    for i, s in enumerate(sentences):
        ru = s["ru"]
        zh = s["zh"]
        print(f"分类中 {i+1}/{len(sentences)}: {ru[:30]}...")

        try:
            r = classify_one(ru, zh)
            primary = r.get("primary_tag", "")
            level = points.get(primary, {}).get("level", 1)
            results.append({
                "ru": ru,
                "zh": zh,
                "tags": r.get("tags", []),
                "primary_tag": primary,
                "level": level,
                "reason": r.get("reason", ""),
                "structure": r.get("structure", {}),  # 句子结构
            })
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            results.append({
                "ru": ru,
                "zh": zh,
                "tags": [],
                "primary_tag": "",
                "level": 1,
                "reason": f"分类失败: {e}"
            })

    return results


# ========== 测试 ==========
if __name__ == "__main__":
    # 测试样本：《走遍俄罗斯》第一课 20 句
    TEST_SENTENCES = [
        {"ru": "Я знаю Ивана.", "zh": "我认识伊万。"},
        {"ru": "Анна знает Антона.", "zh": "安娜认识安东。"},
        {"ru": "Он знает маму.", "zh": "他认识妈妈。"},
        {"ru": "Мы знаем дом.", "zh": "我们知道这个房子。"},
        {"ru": "Она знает лампу.", "zh": "她知道这个台灯。"},
        {"ru": "Я не знаю Ивана.", "zh": "我不认识伊万。"},
        {"ru": "Это мой друг.", "zh": "这是我的朋友。"},
        {"ru": "Это не мама.", "zh": "这不是妈妈。"},
        {"ru": "Сегодня это не мама.", "zh": "今天这不是妈妈。"},
        {"ru": "Я вижу красивую девушку.", "zh": "我看见一个漂亮的姑娘。"},
        {"ru": "Он читает интересную книгу.", "zh": "他在读一本有趣的书。"},
        {"ru": "Мы живём в Москве.", "zh": "我们住在莫斯科。"},
        {"ru": "Она была дома вчера.", "zh": "她昨天在家。"},
        {"ru": "Я хочу есть.", "zh": "我想吃。"},
        {"ru": "Мне нужно делать это.", "zh": "我需要做这个。"},
        {"ru": "Это студент.", "zh": "这是大学生。"},
        {"ru": "Она студентка.", "zh": "她是大学生。"},
        {"ru": "Мы друзья.", "zh": "我们是朋友。"},
        {"ru": "Моя книга здесь.", "zh": "我的书在这儿。"},
        {"ru": "Твой дом большой.", "zh": "你的房子很大。"},
    ]

    print("█" * 80)
    print("阶段2：句子分类器测试 — 20 句")
    print("█" * 80)

    results = classify_sentences(TEST_SENTENCES)

    # 打印结果
    print("\n\n" + "=" * 80)
    print("分类结果")
    print("=" * 80)
    points = TEACHING_POINTS["points"]
    for i, r in enumerate(results):
        primary_name = points.get(r["primary_tag"], {}).get("name", "?")
        print(f"\n{i+1}. {r['ru']}")
        print(f"   中文: {r['zh']}")
        print(f"   tags: {r['tags']}")
        print(f"   primary: {r['primary_tag']} ({primary_name}, 难度{r['level']})")
        print(f"   理由: {r['reason'][:80]}")

    # 保存到文件
    output_path = os.path.join(os.path.dirname(__file__), "classified_sentences.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n\n✅ 结果已保存到: {output_path}")

    # 统计
    print("\n" + "=" * 80)
    print("统计")
    print("=" * 80)
    from collections import Counter
    primary_counts = Counter(r["primary_tag"] for r in results)
    for tag, count in primary_counts.most_common():
        name = points.get(tag, {}).get("name", "?")
        lv = points.get(tag, {}).get("level", "?")
        print(f"  {tag} ({name}, 难度{lv}): {count} 句")
