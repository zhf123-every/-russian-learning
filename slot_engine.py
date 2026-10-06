# -*- coding: utf-8 -*-
"""
俄语 slot 表格规则组装引擎 v2
支持：定语+中心名词整组一致变形、多状语、前置词短语
"""
from morph_engine import generate_form, generate_noun_phrase

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


def _resolve_np(np_item):
    """
    解析名词短语（NP）：{determiner?, modifier?, head} → 变形成正确词形
    如果只是简单的 {lemma, grammar}，也兼容旧格式
    """
    if not isinstance(np_item, dict):
        return ""

    # 旧格式：直接 {lemma, grammar}
    if "lemma" in np_item and "head" not in np_item:
        return generate_form(np_item["lemma"], np_item.get("grammar") or {})

    # 新格式：{determiner?, modifier?, head}
    head = np_item.get("head") or {}
    modifier = np_item.get("modifier") or np_item.get("determiner")

    if modifier:
        return generate_noun_phrase(modifier, head)
    else:
        return generate_form(head.get("lemma", ""), head.get("grammar") or {})


def _resolve_adverbial(adv):
    """解析状语：{type, preposition?, head} → 变形成正确词形"""
    if not isinstance(adv, dict):
        return str(adv)

    head = adv.get("head") or {}
    preposition = adv.get("preposition", "")

    if head and "lemma" in head:
        head_form = generate_form(head["lemma"], head.get("grammar") or {})
    else:
        head_form = ""

    if preposition:
        return f"{preposition} {head_form}".strip()
    return head_form


def build_core_sentence(core):
    """
    根据 core_sentence JSON，生成基础肯定句的词形。
    支持新 schema：主语/宾语是 NP 结构，adverbial 是数组
    """
    out = {}

    for role, item in core.items():
        if role == "adverbial":
            # 状语数组
            if isinstance(item, list):
                out["adverbial"] = [_resolve_adverbial(a) for a in item]
            continue

        if not isinstance(item, dict):
            continue

        if "head" in item or "modifier" in item or "determiner" in item:
            # 名词短语结构
            out[role] = _resolve_np(item)
        elif "lemma" in item:
            # 简单词（动词、代词等）
            out[role] = generate_form(item["lemma"], item.get("grammar") or {})

    return out


def compose_full_sentence(parts):
    """按顺序拼完整句：主语 → 谓语 → 宾语 → 状语"""
    return " ".join(p for p in parts if p).strip()


def generate_table(plan_json):
    """
    主入口：输入大模型的 plan JSON，输出完整表格行。
    支持新 schema：NP 结构 + adverbial 数组
    """
    rows = []
    seq = 0

    # ========== G_01 骨架组 ==========
    core = plan_json.get("core_sentence", {})
    core_forms = build_core_sentence(core)

    # 积木行：逐个成分单出
    for role, form in core_forms.items():
        if role == "adverbial":
            # 状语积木：每个状语单独出
            for adv in form:
                seq += 1
                rows.append({
                    "seq": seq,
                    "cardType": "积木",
                    "ru": adv,
                    "zh": "",
                    "tag": "状语",
                    "groupId": "G_01",
                })
            continue

        if not form:
            continue
        seq += 1
        rows.append({
            "seq": seq,
            "cardType": "积木",
            "ru": form,
            "zh": "",
            "tag": role,
            "groupId": "G_01",
        })

    # 完整句：主语 + 谓语 + 宾语 + 状语
    # 支持 negation 标记：原句是否定句时自动加 не
    sentence_parts = []
    subject_neg = core.get("subject", {}).get("negation", False)
    verb_neg = core.get("verb", {}).get("negation", False)

    if "subject" in core_forms:
        sentence_parts.append(core_forms["subject"])
        if subject_neg:
            sentence_parts.append("не")
    if "verb" in core_forms:
        if verb_neg:
            sentence_parts.append("не")
        sentence_parts.append(core_forms["verb"])
    if "object" in core_forms:
        sentence_parts.append(core_forms["object"])
    if "adverbial" in core_forms:
        sentence_parts.extend(core_forms["adverbial"])

    seq += 1
    core_full = compose_full_sentence(sentence_parts)
    rows.append({
        "seq": seq,
        "cardType": "完整句",
        "ru": core_full + ".",
        "zh": "",
        "tag": "完整句",
        "groupId": "G_01",
    })

    # ========== 衍生组 ==========
    current = dict(core_forms)
    current_full = core_full

    plan = plan_json.get("derivation_plan", [])
    group_idx = 1

    for step in plan:
        step_type = step.get("type")

        if step_type == "negative":
            gid = f"G_{group_idx:02d}"
            group_idx += 1

            seq += 1
            rows.append({"seq": seq, "cardType": "积木", "ru": "не", "zh": "", "tag": "否定", "groupId": gid})

            # 否定句：не 插在动词前；判断句插在主语后
            neg_parts = []
            has_verb = "verb" in current
            items = list(current.items())
            for i, (role, form) in enumerate(items):
                if has_verb and role == "verb":
                    neg_parts.append("не")
                elif not has_verb and i == 1:
                    neg_parts.append("не")
                if role == "adverbial":
                    neg_parts.extend(form)
                else:
                    neg_parts.append(form)
            neg_full = compose_full_sentence(neg_parts)

            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": neg_full + ".", "zh": "", "tag": "否定句", "groupId": gid})

        elif step_type == "add_time":
            gid = f"G_{group_idx:02d}"
            group_idx += 1

            time_val = step.get("value", "")

            seq += 1
            rows.append({"seq": seq, "cardType": "积木", "ru": time_val, "zh": "", "tag": "时间词", "groupId": gid})

            # 肯定句 + 时间
            time_full = compose_full_sentence([time_val, current_full])
            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": time_full + ".", "zh": "", "tag": "时间状语句", "groupId": gid})

            # 否定句 + 时间
            neg_parts = []
            has_verb = "verb" in current
            items = list(current.items())
            for i, (role, form) in enumerate(items):
                if has_verb and role == "verb":
                    neg_parts.append("не")
                elif not has_verb and i == 1:
                    neg_parts.append("не")
                if role == "adverbial":
                    neg_parts.extend(form)
                else:
                    neg_parts.append(form)
            neg_full = compose_full_sentence(neg_parts)
            time_neg_full = compose_full_sentence([time_val, neg_full])
            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": time_neg_full + ".", "zh": "", "tag": "否定+时间", "groupId": gid})

        elif step_type == "add_place":
            gid = f"G_{group_idx:02d}"
            group_idx += 1

            place_val = step.get("value", "")

            seq += 1
            rows.append({"seq": seq, "cardType": "积木", "ru": place_val, "zh": "", "tag": "地点词", "groupId": gid})

            place_full = compose_full_sentence([place_val, current_full])
            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": place_full + ".", "zh": "", "tag": "地点状语句", "groupId": gid})

        elif step_type == "replace_object":
            gid = f"G_{group_idx:02d}"
            group_idx += 1

            new_obj_np = step.get("np") or {}
            new_obj = _resolve_np(new_obj_np)

            seq += 1
            rows.append({"seq": seq, "cardType": "积木", "ru": new_obj, "zh": "", "tag": "新宾语", "groupId": gid})

            new_parts = []
            for role, form in current.items():
                if role == "object":
                    new_parts.append(new_obj)
                elif role == "adverbial":
                    new_parts.extend(form)
                else:
                    new_parts.append(form)
            new_full = compose_full_sentence(new_parts)

            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": new_full + ".", "zh": "", "tag": "换宾语句", "groupId": gid})

            current["object"] = new_obj
            current_full = new_full

        elif step_type == "replace_subject":
            gid = f"G_{group_idx:02d}"
            group_idx += 1

            new_subj_np = step.get("np") or {}
            new_subj_lemma = step.get("lemma", "").lower()
            new_subj = _resolve_np(new_subj_np)

            seq += 1
            rows.append({"seq": seq, "cardType": "积木", "ru": new_subj, "zh": "", "tag": "新主语", "groupId": gid})

            # 换主语 → 动词联动变位
            new_verb = current.get("verb", "")
            if "verb" in core and new_subj_lemma in _SUBJ_TO_PERSON:
                v_lemma = core["verb"]["lemma"]
                v_grammar = dict(core["verb"].get("grammar") or {})
                v_grammar.update(_SUBJ_TO_PERSON[new_subj_lemma])
                new_verb = generate_form(v_lemma, v_grammar)

            new_parts = []
            for role, form in current.items():
                if role == "subject":
                    new_parts.append(new_subj)
                elif role == "verb":
                    new_parts.append(new_verb)
                elif role == "adverbial":
                    new_parts.extend(form)
                else:
                    new_parts.append(form)
            new_full = compose_full_sentence(new_parts)

            seq += 1
            rows.append({"seq": seq, "cardType": "完整句", "ru": new_full + ".", "zh": "", "tag": "换主语句", "groupId": gid})

            current["subject"] = new_subj
            current["verb"] = new_verb
            current_full = new_full

    return rows


# ========== 测试 ==========
if __name__ == "__main__":
    # 测试新 schema：形容词+名词
    test_plan = {
        "core_sentence": {
            "subject": {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
            "verb": {"lemma": "видеть", "grammar": {"tense": "pres", "person": "1", "number": "sing"}},
            "object": {
                "modifier": {"lemma": "красивый", "grammar": {}},
                "head": {"lemma": "девушка", "grammar": {"case": "acc", "gender": "fem", "animacy": "anim"}}
            },
            "adverbial": [
                {"type": "place", "preposition": "в", "head": {"lemma": "школа", "grammar": {"case": "pre"}}}
            ]
        },
        "derivation_plan": [
            {"type": "negative"},
        ]
    }

    rows = generate_table(test_plan)
    print("新 schema 测试：я вижу красивую девушку в школе\n")
    for r in rows:
        print(f"  {r['seq']:2d}. [{r['groupId']}] {r['cardType']:4s} | {r['ru']}")
