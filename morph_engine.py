# -*- coding: utf-8 -*-
"""
俄语词形变化引擎 — 用 pymorphy2 实现 100% 正确的变格变位
"""
import pymorphy3

# 初始化解析器（全局只初始化一次）
_morph = pymorphy3.MorphAnalyzer()

# ========== 语法特征映射 ==========
_CASE_MAP = {
    "nom": "nomn",  # 第一格（主格）
    "gen": "gent",  # 第二格（属格）
    "dat": "datv",  # 第三格（与格）
    "acc": "accs",  # 第四格（宾格）
    "ins": "ablt",  # 第五格（工具格）
    "pre": "loct",  # 第六格（前置格）
}

_GENDER_MAP = {
    "masc": "masc",
    "m": "masc",
    "fem": "femn",
    "f": "femn",
    "neut": "neut",
    "n": "neut",
}

_NUMBER_MAP = {
    "sing": "sing",
    "sg": "sing",
    "plur": "plur",
    "pl": "plur",
}

_ANIMACY_MAP = {
    "anim": "anim",
    "inan": "inan",
    "inanim": "inan",
}

_PERSON_MAP = {
    "1": "1per",
    "2": "2per",
    "3": "3per",
}

_TENSE_MAP = {
    "pres": "pres",
    "past": "past",
    "fut": "futr",
}


def generate_form(lemma, grammar):
    """
    输入词元 + 语法特征，输出正确的俄语词形。

    参数:
        lemma: 词元（原形），比如 "знать", "Анна", "красивый"
        grammar: 语法特征字典
            - case: nom/gen/dat/acc/ins/pre
            - number: sing/plur
            - gender: masc/fem/neut
            - person: 1/2/3
            - tense: pres/past/fut
            - animacy: anim/inan
            - verb_form: inf/finite

    返回:
        str — 变格/变位后的正确词形
    """
    if not lemma:
        return ""
    lemma = str(lemma).strip()
    if not lemma:
        return ""

    parsed = _morph.parse(lemma)
    if not parsed:
        return lemma

    word = parsed[0]

    # 不变词识别：副词/助词/连词/感叹词 — 直接原样输出，不做变格变位
    INDECLINABLE_POS = {"ADVB", "PRCL", "CONJ", "INTJ", "PRED"}
    # 常见歧义副词硬编码（pymorphy3 可能误判为名词变格形式）
    INDECLINABLE_HARDCODE = {"дома", "вчера", "сегодня", "завтра", "утром", "вечером",
                              "ночью", "днем", "летом", "зимой", "хорошо", "плохо",
                              "быстро", "медленно", "тут", "там", "здесь", "сейчас"}
    if lemma.lower() in INDECLINABLE_HARDCODE:
        return lemma
    if word.tag.POS in INDECLINABLE_POS:
        return lemma  # 原样返回，保留原始大小写

    # 要求不定式就返回原形
    if grammar and grammar.get("verb_form") == "inf":
        return word.normal_form

    # 构建 pymorphy2 tag 集合
    tags = set()

    if grammar:
        if "case" in grammar and grammar["case"] in _CASE_MAP:
            tags.add(_CASE_MAP[grammar["case"]])
        if "number" in grammar and grammar["number"] in _NUMBER_MAP:
            tags.add(_NUMBER_MAP[grammar["number"]])
        if "gender" in grammar and grammar["gender"] in _GENDER_MAP:
            tags.add(_GENDER_MAP[grammar["gender"]])
        if "person" in grammar and grammar["person"] in _PERSON_MAP:
            tags.add(_PERSON_MAP[grammar["person"]])
        if "tense" in grammar and grammar["tense"] in _TENSE_MAP:
            tags.add(_TENSE_MAP[grammar["tense"]])
        if "animacy" in grammar and grammar["animacy"] in _ANIMACY_MAP:
            tags.add(_ANIMACY_MAP[grammar["animacy"]])

    if tags:
        result = word.inflect(tags)
        if result:
            out = result.word
            # 保留原词的大写状态（专有名词首字母大写）
            if lemma[0].isupper():
                out = out[0].upper() + out[1:]
            return out
        # fallback：去掉 animacy 重试（形容词第四格不需要 anim tag）
        if "anim" in tags or "inan" in tags:
            tags2 = tags - {"anim", "inan"}
            result = word.inflect(tags2)
            if result:
                out = result.word
                if lemma[0].isupper():
                    out = out[0].upper() + out[1:]
                return out

    out = word.normal_form
    if lemma[0].isupper():
        out = out[0].upper() + out[1:]
    return out


def generate_noun_phrase(modifier, head):
    """
    生成名词短语：形容词/物主代词 + 名词，整组性数格一致。

    参数:
        modifier: 定语（形容词/物主代词），{"lemma": "красивый", "grammar": {...}}
                  如果没有定语，传 None
        head: 中心名词，{"lemma": "девушка", "grammar": {"case": "acc", "gender": "fem"}}

    返回:
        str — 一致变形后的短语，比如 "красивую девушку"
    """
    head_form = generate_form(head["lemma"], head.get("grammar") or {})

    if not modifier:
        return head_form

    # 定语的语法特征 = 中心名词的格 + 性 + 数
    # 形容词必须和名词性数格一致
    head_grammar = head.get("grammar") or {}
    mod_grammar = dict(modifier.get("grammar") or {})

    # 强制一致：定语的性数格 = 名词的性数格
    if "case" in head_grammar:
        mod_grammar["case"] = head_grammar["case"]
    if "gender" in head_grammar:
        mod_grammar["gender"] = head_grammar["gender"]
    if "number" in head_grammar:
        mod_grammar["number"] = head_grammar["number"]

    mod_form = generate_form(modifier["lemma"], mod_grammar)
    return f"{mod_form} {head_form}"


# ========== 测试 ==========
if __name__ == "__main__":
    print("=" * 70)
    print("俄语词形变化引擎 — 测试")
    print("=" * 70)

    tests = [
        # 名词变格
        ("Иван", {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}, "Ивана"),
        ("Анна", {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}, "Анну"),
        ("каша", {"case": "acc", "number": "sing", "gender": "fem", "animacy": "inan"}, "кашу"),
        ("книга", {"case": "gen", "number": "sing"}, "книги"),
        ("мама", {"case": "gen", "number": "sing"}, "мамы"),

        # 形容词变格
        ("красивый", {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}, "красивую"),
        ("новый", {"case": "ins", "number": "plur"}, "новыми"),

        # 动词变位
        ("знать", {"tense": "pres", "person": "1", "number": "sing"}, "знаю"),
        ("делать", {"tense": "pres", "person": "1", "number": "sing"}, "делаю"),
        ("говорить", {"tense": "past", "number": "plur"}, "говорили"),
        ("хотеть", {"tense": "pres", "person": "3", "number": "sing"}, "хочет"),

        # 代词变格
        ("я", {"case": "gen", "number": "sing"}, "меня"),
        ("он", {"case": "gen", "number": "sing"}, "его"),
        ("мы", {"case": "dat", "number": "plur"}, "нам"),
        ("ты", {"case": "acc", "number": "sing"}, "тебя"),
    ]

    passed = 0
    failed = 0
    for lemma, grammar, expected in tests:
        result = generate_form(lemma, grammar)
        ok = result.lower() == expected.lower()
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"{status} {lemma:12s} → {result:15s} (预期: {expected})")

    print("=" * 70)
    print(f"结果: {passed} 通过 / {failed} 失败 / 共 {len(tests)} 个")
