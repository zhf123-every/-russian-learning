# -*- coding: utf-8 -*-
"""
衍生模板库 — 5个专用模板，对应常见句型
遇到不匹配的句型直接报错，列出缺少哪个模板
"""

# ========== 模板定义 ==========

TEMPLATES = {
    # 模板1：判断句（T07判断句 + T08判断句否定）
    "T07_T08_判断句": {
        "match_tags": ["T07", "T08"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换名词", "candidates": [
                {"lemma": "папа", "grammar": {"case": "nom", "number": "sing", "gender": "masc", "animacy": "anim"}},
                {"lemma": "книга", "grammar": {"case": "nom", "number": "sing", "gender": "fem", "animacy": "inan"}},
                {"lemma": "окно", "grammar": {"case": "nom", "number": "sing", "gender": "neut", "animacy": "inan"}},
            ], "max": 3},
            {"type": "加时间", "candidates": ["сегодня"], "max": 1},
        ],
        "reuse_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "fem"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            # 判断句的表语换词：必须用主格，不是第四格
            {"type": "换表语", "candidates": {
                "masc": [
                    {"lemma": "Иван", "grammar": {"case": "nom", "number": "sing", "gender": "masc"}},
                    {"lemma": "папа", "grammar": {"case": "nom", "number": "sing", "gender": "masc"}},
                    {"lemma": "друг", "grammar": {"case": "nom", "number": "sing", "gender": "masc"}},
                ],
                "fem": [
                    {"lemma": "Анна", "grammar": {"case": "nom", "number": "sing", "gender": "fem"}},
                    {"lemma": "мама", "grammar": {"case": "nom", "number": "sing", "gender": "fem"}},
                    {"lemma": "книга", "grammar": {"case": "nom", "number": "sing", "gender": "fem"}},
                ],
            }, "max": 2},
        ],
    },

    # 模板2：主谓宾（T05名词第四格 + T06动词否定）
    "T05_T06_主谓宾": {
        "match_tags": ["T05", "T06"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "加时间", "candidates": ["сейчас", "сегодня"], "max": 2},
            {"type": "加地点", "candidates": ["здесь"], "max": 1},
            {"type": "换主语", "candidates": [
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "fem"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 3},
            {"type": "换宾语", "candidates": [
                {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
                {"lemma": "мама", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
            ], "max": 2},
        ],
        "reuse_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "fem"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            {"type": "换宾语", "candidates": [
                {"lemma": "Иван", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
                {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
                {"lemma": "мама", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
            ], "max": 2},
        ],
    },

    # 模板3：物主代词（T09物主代词 + T10形容词一致）
    "T09_T10_物主代词": {
        "match_tags": ["T09", "T10"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换物主代词", "candidates": ["твой", "его"], "max": 2},
            {"type": "换名词", "candidates": [
                {"lemma": "друг", "grammar": {"case": "nom", "number": "sing", "gender": "masc"}},
                {"lemma": "окно", "grammar": {"case": "nom", "number": "sing", "gender": "neut"}},
            ], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}],
    },

    # 模板4：形容词第四格（T11形容词第四格）
    "T11_形容词第四格": {
        "match_tags": ["T11"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "加时间", "candidates": ["сегодня"], "max": 1},
            {"type": "换主语", "candidates": [
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            {"type": "换形容词+名词", "candidates": [
                {"adj_lemma": "интересный", "noun_lemma": "книга", "grammar": {"case": "acc", "number": "sing", "gender": "fem"}},
                {"adj_lemma": "новый", "noun_lemma": "дом", "grammar": {"case": "acc", "number": "sing", "gender": "masc"}},
            ], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}],
    },

    # 模板5：扩展成分（T14前置词第六格 + T15过去时 + T18无人称句 + T19动词+不定式 + T17第三格）
    "T14_T15_T17_T18_T19_扩展成分": {
        "match_tags": ["T14", "T15", "T17", "T18", "T19"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
            ], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}],
    },

    # 模板6：疑问句（T23）
    "T23_疑问句": {
        "match_tags": ["T23"],
        "no_derivation": True,  # 特殊标记：不衍生，只输出原句
        "seed_derivations": [],
        "reuse_derivations": []
    },

    # 模板7：代词第四格（T25）
    "T25_代词第四格": {
        "match_tags": ["T25"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换宾语", "candidates": [
                {"lemma": "ты", "grammar": {"case": "acc", "number": "sing", "person": "2"}},
                {"lemma": "он", "grammar": {"case": "acc", "number": "sing", "gender": "masc"}},
            ], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}]
    },

    # 模板8：未来时（T27）
    "T27_未来时": {
        "match_tags": ["T27"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            {"type": "换不定式", "candidates": ["читать", "работать"], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}]
    },

    # 模板9：运动动词定向（T36a идти / T36b ехать）
    "T36a_运动动词定向_идти": {
        "match_tags": ["T36a"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "fem"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            {"type": "换目的地", "candidates": ["в школу", "в кино", "домой"], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}]
    },

    "T36b_运动动词定向_ехать": {
        "match_tags": ["T36b"],
        "seed_derivations": [
            {"type": "加否定"},
            {"type": "换主语", "candidates": [
                {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3", "gender": "masc"}},
                {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
            ], "max": 2},
            {"type": "换目的地", "candidates": ["в школу", "в Москву", "домой"], "max": 2},
        ],
        "reuse_derivations": [{"type": "加否定"}]
    },
}


def match_template(primary_tag):
    """
    根据 primary_tag 匹配模板
    输入: "T05"
    输出: 模板 dict 或 None（没匹配到就报错）
    """
    for template_name, template in TEMPLATES.items():
        if primary_tag in template["match_tags"]:
            return template_name, template
    return None, None


# ========== 测试 ==========
if __name__ == "__main__":
    test_tags = ["T07", "T08", "T05", "T06", "T09", "T10", "T11", "T14", "T15", "T18", "T19", "T99"]

    for tag in test_tags:
        name, tpl = match_template(tag)
        if tpl:
            print(f"{tag} → {name}")
        else:
            print(f"{tag} → ❌ 无匹配模板")
