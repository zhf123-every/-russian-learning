# -*- coding: utf-8 -*-
"""
层内编排执行器 v2
保留 morph_engine，重写编排层和组装层
"""
from morph_engine import generate_form, generate_noun_phrase
import copy
import json
import os

# 加载词元中文表
WORD_DICT = {}
_dict_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "word_dict.json")
if os.path.exists(_dict_path):
    with open(_dict_path, "r", encoding="utf-8") as f:
        WORD_DICT = json.load(f)


def get_zh(lemma):
    """根据 lemma（原形）查中文，大小写不敏感"""
    if not lemma:
        return ""
    lemma_lower = lemma.lower()
    for category in ["pronouns", "verbs", "nouns", "adjectives", "adverbs", "prepositions", "negation"]:
        cat = WORD_DICT.get(category, {})
        # 遍历该类所有 key，都转小写比较
        for k, v in cat.items():
            if k.lower() == lemma_lower:
                return v
    return ""


# 主语 → 人称/数 映射（换主语后动词要跟着变位）
_SUBJ_TO_PERSON = {
    "я":   {"person": "1", "number": "sing"},
    "ты":  {"person": "2", "number": "sing"},
    "он":  {"person": "3", "number": "sing"},
    "она": {"person": "3", "number": "sing"},
    "оно": {"person": "3", "number": "sing"},
    "мы":  {"person": "1", "number": "plur"},
    "вы":  {"person": "2", "number": "plur"},
    "они": {"person": "3", "number": "plur"},
}


def validate_judgment_agreement(structure):
    """
    校验判断句的主语和表语的性别/数是否一致
    返回 True 表示一致（可以生成），False 表示不一致（跳过）
    """
    # 只有判断句才校验（没有实义动词）
    is_copula = (not structure.get("verb")) or (structure.get("verb", {}).get("lemma") == "быть")
    if not is_copula:
        return True  # 不是判断句，不校验
    
    subj = structure.get("subject", {})
    obj = structure.get("object", {})
    if not subj or not obj:
        return True  # 缺成分，不校验
    
    subj_grammar = subj.get("grammar", {})
    obj_grammar = obj.get("grammar", {})
    
    # 1. 数必须一致
    subj_number = subj_grammar.get("number")
    obj_number = obj_grammar.get("number")
    if subj_number and obj_number and subj_number != obj_number:
        return False
    
    # 2. 性别必须一致（都是单数的时候）
    if subj_number == "sing" and obj_number == "sing":
        subj_gender = subj_grammar.get("gender")
        obj_gender = obj_grammar.get("gender")
        if subj_gender and obj_gender and subj_gender != obj_gender:
            return False
    
    return True


def validate_g(gsteps, structure):
    """
    校验一个 G 是否合法。
    返回 (is_valid, reason)
    """
    # 1. 至少有一个完整句
    full = next((s for s in gsteps if s.get("type") == "完整句"), None)
    if not full:
        return False, "没有完整句"
    
    # 2. 完整句的 ru 不能为空
    if not full.get("ru", "").strip():
        return False, "完整句为空"
    
    # 3. 完整句不能是"单个词"（至少2个词）
    words = full["ru"].rstrip('.').rstrip('?').strip().split()
    if len(words) < 2:
        return False, f"完整句只有一个词: {full['ru']}"
    
    # 4. 不能出现原形动词（быть 是原形，不应该出现在完整句里）
    # 注意：есть 作为"有"的意思是可以的，但作为系动词的原形不行
    INVALID_WORDS = ["быть"]  # быть 是原形，绝对不能出现
    for w in words:
        if w.lower() in INVALID_WORDS:
            return False, f"出现原形动词: {w}"
    
    # 5. 不能出现"名词 + не" 这种崩坏语序（не必须在动词前或表语前）
    if len(words) >= 2:
        if words[-1].lower() == "не":
            return False, "не 在句尾"
    
    # 6. 完整性校验：至少要有主语或状语
    if structure:
        has_subject = bool(structure.get("subject"))
        has_adverbial = bool(structure.get("adverbial"))
        if not has_subject and not has_adverbial:
            return False, "没有主语也没有状语"
    
    return True, "OK"


def apply_derivation(structure, derivation):
    """
    应用一个衍生指令，返回新的句子结构

    structure = {
        "subject": {"lemma": "я", "grammar": {...}},
        "verb": {"lemma": "знать", "grammar": {...}},
        "object": {"lemma": "Иван", "grammar": {...}},  # 或 NP 结构
        "negation": False,
        "adverbial": []
    }

    derivation = {"type": "换主语", "value": {"lemma": "он", "grammar": {...}}}
    """
    s = copy.deepcopy(structure)
    dtype = derivation["type"]

    if dtype == "换主语":
        new_subj = derivation["value"]
        s["subject"] = new_subj
        # 换主语 → 动词联动变位（如果有动词的话）
        subj_lemma = new_subj.get("lemma", "").lower()
        if subj_lemma in _SUBJ_TO_PERSON and s.get("verb"):
            v = s["verb"]
            v["grammar"] = v.get("grammar", {})
            v["grammar"].update(_SUBJ_TO_PERSON[subj_lemma])

    elif dtype == "换宾语":
        s["object"] = derivation["value"]
    
    elif dtype == "换表语":
        # 判断句的表语就是object字段，只是候选用主格
        s["object"] = derivation["value"]

    elif dtype == "加否定":
        s["negation"] = True

    elif dtype == "加时间":
        s["adverbial"].append({"type": "time", "head": {"lemma": derivation["value"]}})

    elif dtype == "换时间":
        # 先清空原来的时间状语，再加新的
        s["adverbial"] = [a for a in s["adverbial"] if a.get("type") != "time"]
        s["adverbial"].append({"type": "time", "head": {"lemma": derivation["value"]}})

    elif dtype == "加地点":
        s["adverbial"].append({"type": "place", "head": {"lemma": derivation["value"]}})

    elif dtype == "换地点":
        # 先清空原来的地点状语，再加新的
        s["adverbial"] = [a for a in s["adverbial"] if a.get("type") != "place"]
        s["adverbial"].append({"type": "place", "head": {"lemma": derivation["value"]}})

    elif dtype == "换形容词":
        # 换宾语的形容词部分
        if "object" in s and isinstance(s["object"], dict):
            s["object"]["modifier"] = derivation["value"]

    return s


def _resolve_np(np_item):
    """解析名词短语（NP）"""
    if not isinstance(np_item, dict):
        return ""

    if "lemma" in np_item and "head" not in np_item:
        return generate_form(np_item["lemma"], np_item.get("grammar") or {})

    head = np_item.get("head") or {}
    modifier = np_item.get("modifier") or np_item.get("determiner")

    if modifier:
        return generate_noun_phrase(modifier, head)
    else:
        return generate_form(head.get("lemma", ""), head.get("grammar") or {})


def build_steps(structure, gid, zh_translation=""):
    """
    把句子结构变成积木+完整句的步骤列表
    中文翻译根据成分动态拼装
    """
    steps = []

    # 1. 变形 + 查中文
    # 主语
    subject_form = ""
    subject_zh = ""
    if structure.get("subject"):
        subj = structure["subject"]
        subject_form = _resolve_np(subj)
        subj_lemma = subj.get("lemma", "")
        if "head" in subj:
            subj_lemma = subj["head"].get("lemma", "")
        subject_zh = get_zh(subj_lemma)

    # 谓语
    verb_form = ""
    verb_zh = ""
    if structure.get("verb"):
        v = structure["verb"]
        verb_form = generate_form(v["lemma"], v.get("grammar", {}))
        verb_zh = get_zh(v["lemma"])

    # 宾语
    object_form = ""
    object_zh = ""
    if structure.get("object"):
        obj = structure["object"]
        object_form = _resolve_np(obj)
        obj_lemma = obj.get("lemma", "")
        if "head" in obj:
            obj_lemma = obj["head"].get("lemma", "")
        object_zh = get_zh(obj_lemma)

    # 状语：分成时间状语和地点状语
    time_adv_forms = []
    time_adv_zhs = []
    place_adv_forms = []
    place_adv_zhs = []
    for adv in structure.get("adverbial", []):
        head = adv.get("head", {})
        adv_type = adv.get("type", "")  # time / place
        if "lemma" in head:
            form = generate_form(head["lemma"], head.get("grammar", {}))
            zh = get_zh(head["lemma"])
            if adv_type == "time":
                time_adv_forms.append(form)
                time_adv_zhs.append(zh)
            else:
                place_adv_forms.append(form)
                place_adv_zhs.append(zh)
    
    # 合并成 adv_forms（保持原有顺序，用于积木）
    adv_forms = time_adv_forms + place_adv_forms
    adv_zhs = time_adv_zhs + place_adv_zhs

    has_neg = structure.get("negation", False)

    # 判断句检测：没有实义动词，或动词是 быть
    is_copula = (not structure.get("verb")) or (structure.get("verb", {}).get("lemma") == "быть")

    # 疑问句检测：如果原句以 ? 结尾，完整句也用 ?
    is_question = structure.get("is_question", False)

    # 2. 拆积木
    if subject_form:
        steps.append({"type": "积木", "ru": subject_form, "zh": subject_zh, "tag": "主语", "gid": gid})

    # не 单独成积木
    if has_neg:
        steps.append({"type": "积木", "ru": "не", "zh": "不/没有", "tag": "否定", "gid": gid})

    if verb_form:
        steps.append({"type": "积木", "ru": verb_form, "zh": verb_zh, "tag": "谓语", "gid": gid})

    if object_form:
        # 判断句里的名词是表语，不是宾语
        obj_tag = "表语" if is_copula else "宾语"
        steps.append({"type": "积木", "ru": object_form, "zh": object_zh, "tag": obj_tag, "gid": gid})

    for i, adv in enumerate(adv_forms):
        steps.append({"type": "积木", "ru": adv, "zh": adv_zhs[i] if i < len(adv_zhs) else "", "tag": f"状语{i+1}", "gid": gid})

    # 3. 组装完整句
    ru_parts = []
    zh_parts = []

    # 时间状语放句首
    for i, adv in enumerate(time_adv_forms):
        ru_parts.append(adv)
        if i < len(time_adv_zhs):
            zh_parts.append(time_adv_zhs[i])

    if subject_form:
        ru_parts.append(subject_form)
        zh_parts.append(subject_zh)

    # 判断句：加 не 到俄语里，中文加"不是"
    if is_copula:
        if has_neg:
            ru_parts.append("не")
            zh_parts.append("不是")
        else:
            zh_parts.append("是")

    if has_neg and not is_copula:
        ru_parts.append("не")
        # 中文否定：加在动词前
        if verb_zh:
            zh_parts.append("不" + verb_zh)
            verb_zh = ""  # 避免重复

    if verb_form:
        ru_parts.append(verb_form)
        if verb_zh and not is_copula:  # 判断句不加动词中文
            if verb_zh:  # 如果否定时已经加过了，这里就不加了
                zh_parts.append(verb_zh)

    if object_form:
        ru_parts.append(object_form)
        zh_parts.append(object_zh)

    # 地点状语放句尾
    for i, adv in enumerate(place_adv_forms):
        ru_parts.append(adv)
        if i < len(place_adv_zhs):
            zh_parts.append(place_adv_zhs[i])

    # 标点：疑问句用 ?，其他用 .
    punct = "?" if is_question else "."
    full_ru = " ".join(ru_parts) + punct
    full_zh = "".join(zh_parts)

    steps.append({
        "type": "完整句",
        "ru": full_ru,
        "zh": full_zh,
        "tag": "完整句",
        "gid": gid
    })

    return steps


def execute_layer_plan(layer_plan, start_gid=1):
    """
    执行一层的计划，输出完整步骤

    layer_plan = {
        "seed1": {
            "base_structure": {...},
            "derivations": [
                {"type": "加否定"},
                {"type": "换主语", "value": {"lemma": "он", "grammar": {...}}},
                ...
            ],
            "zh": "我认识伊万"
        },
        "seed2": {...},  # 可选
        "reuse": [
            {
                "base_structure": {...},
                "derivations": [...],
                "zh": "他认识妈妈"
            },
            ...
        ]
    }
    start_gid: 全局gid起始编号（不是每层从1开始）
    """
    all_steps = []
    seq = 1
    gid = start_gid  # 从传入的起始gid开始，不是每层从1开始

    def _add_steps(new_steps):
        nonlocal seq
        for s in new_steps:
            s["seq"] = seq
            seq += 1

    # 1. 种子句1的长链
    seed1 = layer_plan.get("seed1", {})
    if seed1:
        base = seed1["base_structure"]
        zh = seed1.get("zh", "")
        is_no_derivation = seed1.get("no_derivation", False)

        # G_01：原句
        steps = build_steps(base, f"G_{gid:02d}", zh)
        # 完整性校验：不通过就跳过这个G
        valid, reason = validate_g(steps, base)
        if not valid:
            print(f"[validate] G_{gid:02d} 被拦截: {reason}", flush=True)
        else:
            _add_steps(steps)
            all_steps.extend(steps)
            gid += 1

        # 如果是 no_derivation 类型，不执行衍生
        if is_no_derivation:
            pass  # 跳过衍生
        else:
            # 衍生
            for deriv in seed1.get("derivations", []):
                new_struct = apply_derivation(base, deriv)
                # 校验判断句的性别/数一致性，不一致就跳过这个衍生
                if not validate_judgment_agreement(new_struct):
                    continue
                steps = build_steps(new_struct, f"G_{gid:02d}", zh)
                # 完整性校验：不通过就跳过这个G
                valid, reason = validate_g(steps, new_struct)
                if not valid:
                    print(f"[validate] G_{gid:02d} 被拦截: {reason}", flush=True)
                    continue
                _add_steps(steps)
                all_steps.extend(steps)
                gid += 1

    # 2. 种子句2（如果有）
    seed2 = layer_plan.get("seed2", {})
    if seed2:
        base = seed2["base_structure"]
        zh = seed2.get("zh", "")

        steps = build_steps(base, f"G_{gid:02d}", zh)
        _add_steps(steps)
        all_steps.extend(steps)
        gid += 1

        for deriv in seed2.get("derivations", []):
            new_struct = apply_derivation(base, deriv)
            steps = build_steps(new_struct, f"G_{gid:02d}", zh)
            _add_steps(steps)
            all_steps.extend(steps)
            gid += 1

    # 3. 复用句的短链
    for reuse in layer_plan.get("reuse", []):
        base = reuse["base_structure"]
        zh = reuse.get("zh", "")
        is_no_derivation = reuse.get("no_derivation", False)

        steps = build_steps(base, f"G_{gid:02d}", zh)
        _add_steps(steps)
        all_steps.extend(steps)
        gid += 1

        # 如果是 no_derivation 类型，不执行衍生
        if not is_no_derivation:
            for deriv in reuse.get("derivations", []):
                new_struct = apply_derivation(base, deriv)
                steps = build_steps(new_struct, f"G_{gid:02d}", zh)
                _add_steps(steps)
                all_steps.extend(steps)
                gid += 1

    return all_steps, gid - 1, seq - 1


# ========== 测试：层3 ==========
if __name__ == "__main__":
    layer3_plan = {
        "seed1": {
            "base_structure": {
                "subject": {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
                "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "1", "number": "sing"}},
                "object": {"lemma": "Иван", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
                "negation": False,
                "adverbial": []
            },
            "derivations": [
                {"type": "加否定"},
                {"type": "加时间", "value": "сегодня"},
                {"type": "换主语", "value": {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3"}}},
                {"type": "换主语", "value": {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3"}}},
                {"type": "换主语", "value": {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}}},
                {"type": "换宾语", "value": {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}}},
                {"type": "换宾语", "value": {"lemma": "мама", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}}},
            ],
            "zh": "我认识伊万"
        },
        "seed2": {
            "base_structure": {
                "subject": {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
                "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "1", "number": "sing"}},
                "object": {"lemma": "Иван", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
                "negation": True,
                "adverbial": []
            },
            "derivations": [
                {"type": "换主语", "value": {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3"}}},
                {"type": "换主语", "value": {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}}},
                {"type": "换宾语", "value": {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}}},
            ],
            "zh": "我不认识伊万"
        },
        "reuse": [
            {
                "base_structure": {
                    "subject": {"lemma": "он", "grammar": {"case": "nom", "number": "sing", "person": "3"}},
                    "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "3", "number": "sing"}},
                    "object": {"lemma": "мама", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
                    "negation": False,
                    "adverbial": []
                },
                "derivations": [{"type": "加否定"}],
                "zh": "他认识妈妈"
            },
            {
                "base_structure": {
                    "subject": {"lemma": "Анна", "grammar": {"case": "nom", "number": "sing", "gender": "fem"}},
                    "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "3", "number": "sing"}},
                    "object": {"lemma": "Антон", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
                    "negation": False,
                    "adverbial": []
                },
                "derivations": [{"type": "加否定"}],
                "zh": "安娜认识安东"
            },
            {
                "base_structure": {
                    "subject": {"lemma": "она", "grammar": {"case": "nom", "number": "sing", "person": "3"}},
                    "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "3", "number": "sing"}},
                    "object": {"lemma": "лампа", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "inan"}},
                    "negation": False,
                    "adverbial": []
                },
                "derivations": [{"type": "加否定"}],
                "zh": "她知道这个台灯"
            },
            {
                "base_structure": {
                    "subject": {"lemma": "мы", "grammar": {"case": "nom", "number": "plur", "person": "1"}},
                    "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "1", "number": "plur"}},
                    "object": {"lemma": "дом", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "inan"}},
                    "negation": False,
                    "adverbial": []
                },
                "derivations": [{"type": "加否定"}],
                "zh": "我们知道这个房子"
            },
        ]
    }

    steps, total_groups, total_steps = execute_layer_plan(layer3_plan)

    print("=" * 90)
    print(f"层3：名词第四格 — 新编排器输出（共 {total_groups} 组，{total_steps} 步）")
    print("=" * 90)
    print(f"{'序号':<4} {'组ID':<6} {'类型':<6} {'俄语':<35} {'中文':<15} {'标签':<10}")
    print("-" * 90)

    for s in steps:
        print(f"{s['seq']:<4} {s['gid']:<6} {s['type']:<6} {s['ru']:<35} {s['zh']:<15} {s['tag']:<10}")
