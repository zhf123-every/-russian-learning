# -*- coding: utf-8 -*-
"""
阶段4：层内编排器（最小可用版 v2）
输入：一层的句子（每句自带 structure）→ 输出：orchestrator 能执行的 layer_plan
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from templates import match_template
import pymorphy3

morph = pymorphy3.MorphAnalyzer()

# 主语 lemma 到 person/number 的映射（唯一事实来源）
SUBJ_PERSON_NUMBER = {
    "я":     {"person": "1", "number": "sing"},
    "ты":    {"person": "2", "number": "sing"},
    "он":    {"person": "3", "number": "sing"},
    "она":   {"person": "3", "number": "sing"},
    "оно":   {"person": "3", "number": "sing"},
    "мы":    {"person": "1", "number": "plur"},
    "вы":    {"person": "2", "number": "plur"},
    "они":   {"person": "3", "number": "plur"},
    "вы":    {"person": "2", "number": "plur"},  # 敬称
}


def derive_subject_person_number(subject):
    """
    从主语结构里推导 person 和 number。
    优先级：
    1. 如果主语 lemma 在 SUBJ_PERSON_NUMBER 字典里，用字典（字典是唯一事实来源）
    2. 如果主语 grammar 里有 person/number，直接用
    3. 否则，用 pymorphy3 分析主语的数，推导为第三人称
    """
    if not subject:
        return {}

    # 优先级1：字典优先
    lemma = (subject.get("lemma") or "").lower()
    if lemma in SUBJ_PERSON_NUMBER:
        return SUBJ_PERSON_NUMBER[lemma]

    # 优先级2：grammar 里有就用
    subj_grammar = subject.get("grammar") or {}
    if subj_grammar.get("person") and subj_grammar.get("number"):
        return {"person": subj_grammar["person"], "number": subj_grammar["number"]}

    # 优先级3：名词主语，用 pymorphy3 分析数，默认第三人称
    try:
        parsed = morph.parse(subject.get("lemma", ""))[0]
        number = "plur" if "plur" in parsed.tag else "sing"
        return {"person": "3", "number": number}
    except:
        return {"person": "3", "number": "sing"}


def normalize_llm_structure(structure, primary_tag=None):
    """
    把大模型输出的 structure 规范化（统一处理，不要在多处打补丁）
    1. verb 的 lemma 用 pymorphy3 normal_form 还原为原形
    2. subject 的 person/number 用 SUBJ_PERSON_NUMBER 字典强制修正
    3. T23 疑问句清空 verb 字段（Кто это? 里根本没有动词）
    4. 其他字段的统一处理
    """
    if not structure:
        return {}

    # 1. verb lemma 规范化：变位形式 → 原形
    if structure.get("verb") and structure["verb"].get("lemma"):
        lemma = structure["verb"]["lemma"]
        try:
            parsed = morph.parse(lemma)[0]
            structure["verb"]["lemma"] = parsed.normal_form
        except:
            pass  # 解析失败就保留原 lemma
    
    # 1.2 判断句（T07/T08）清空verb字段（это是指示代词，不是动词）
    if primary_tag in ("T07", "T08"):
        structure.pop("verb", None)
    
    # 1.5 object lemma 规范化：变形后的形式 → 原形（друзья → друг）
    if structure.get("object") and isinstance(structure["object"], dict):
        obj = structure["object"]
        if obj.get("lemma"):
            try:
                parsed = morph.parse(obj["lemma"])[0]
                obj["lemma"] = parsed.normal_form
                # 如果是人名（Name），首字母大写
                if "Name" in parsed.tag:
                    obj["lemma"] = obj["lemma"].capitalize()
                # 自动加上animacy字段
                obj["grammar"] = obj.get("grammar", {})
                if "anim" in parsed.tag:
                    obj["grammar"]["animacy"] = "anim"
                elif "inan" in parsed.tag:
                    obj["grammar"]["animacy"] = "inan"
            except:
                pass
        # 如果是带head的名词短语，也规范化head的lemma
        if obj.get("head") and obj["head"].get("lemma"):
            try:
                parsed = morph.parse(obj["head"]["lemma"])[0]
                obj["head"]["lemma"] = parsed.normal_form
                # 如果是人名（Name），首字母大写
                if "Name" in parsed.tag:
                    obj["head"]["lemma"] = obj["head"]["lemma"].capitalize()
            except:
                pass

    # 2. subject 的 person/number 强制修正（字典优先）
    if structure.get("subject") and structure["subject"].get("lemma"):
        subj_lemma = structure["subject"]["lemma"].lower()
        if subj_lemma in SUBJ_PERSON_NUMBER:
            structure["subject"]["grammar"] = structure["subject"].get("grammar", {})
            structure["subject"]["grammar"]["person"] = SUBJ_PERSON_NUMBER[subj_lemma]["person"]
            structure["subject"]["grammar"]["number"] = SUBJ_PERSON_NUMBER[subj_lemma]["number"]

    # 3. T23 疑问句清空 verb 字段（Кто это? 里根本没有动词，это 是指示代词）
    if primary_tag == "T23":
        structure.pop("verb", None)

    return structure


# 动词-宾语匹配表：每个动词能接什么类型的宾语
VERB_OBJECT_MAP = {
    "читать": [
        {"lemma": "книга", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "inanim"}},
        {"lemma": "газета", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "inanim"}},
    ],
    "видеть": [
        {"lemma": "человек", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
        {"lemma": "дом", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "inanim"}},
    ],
    "знать": [
        {"lemma": "Иван", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}},
        {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}},
    ],
    "хотеть": [
        {"lemma": "читать", "grammar": {"type": "inf"}},
        {"lemma": "есть", "grammar": {"type": "inf"}},
    ],
}


def normalize_base_structure(structure, primary_tag):
    """
    把大模型的 structure 标准化成 orchestrator 需要的格式
    种子句和复用句都调这个函数，保证逻辑一致
    """
    base = {
        "subject": structure.get("subject"),
        "verb": structure.get("verb"),
        "object": structure.get("object") or structure.get("predicate"),  # 判断句用predicate
        "negation": structure.get("negation", False),
        "adverbial": structure.get("adverbial", []),
        "is_question": structure.get("type") == "question" or primary_tag == "T23",  # 疑问句标记
    }

    # 自动修正：根据主语的 person/number，自动设置动词的 person/number
    # 统一调用 derive_subject_person_number，不要自己查表
    if base.get("verb"):
        pn = derive_subject_person_number(base.get("subject"))
        if pn:
            base["verb"]["grammar"] = base["verb"].get("grammar", {})
            base["verb"]["grammar"]["person"] = pn["person"]
            base["verb"]["grammar"]["number"] = pn["number"]

    return base


def build_plan_for_sentence(sentence):
    """
    为单句生成编排计划
    输入: {"ru": "...", "zh": "...", "primary_tag": "...", "structure": {...}}
    输出: orchestrator 需要的 {base_structure, derivations, zh}
    """
    primary_tag = sentence["primary_tag"]
    structure = sentence.get("structure", {})

    # 统一规范化大模型输出的 structure
    structure = normalize_llm_structure(structure, primary_tag)

    # 匹配模板
    template_name, template = match_template(primary_tag)
    if not template:
        raise Exception(f"缺少 {primary_tag} 的模板（句子：{sentence['ru']}）")

    # 标准化 base_structure（公共函数）
    base_structure = normalize_base_structure(structure, primary_tag)

    # 特殊模板：不衍生（如疑问句）
    if template.get("no_derivation"):
        return {
            "base_structure": base_structure,
            "derivations": [],  # 没有衍生
            "zh": sentence["zh"],
            "no_derivation": True,  # 标记
        }

    # 生成衍生计划
    derivations = []
    verb_lemma = (structure.get("verb") or {}).get("lemma", "")

    for deriv_tpl in template["seed_derivations"]:
        deriv_type = deriv_tpl["type"]

        # 加否定：如果原句已经是否定，就不加
        if deriv_type == "加否定" and base_structure.get("negation"):
            continue

        # 其他衍生：按 max 取多个候选
        candidates = deriv_tpl.get("candidates", [])
        max_count = deriv_tpl.get("max", 1)  # 默认取1个

        # 换宾语：如果动词有专门的宾语候选列表，用它替换全局候选
        if deriv_type == "换宾语" and verb_lemma in VERB_OBJECT_MAP:
            candidates = VERB_OBJECT_MAP[verb_lemma]
        
        # 换表语：判断句用，candidates是按性别分池的字典，按主语性别选池
        if deriv_type == "换表语" and isinstance(candidates, dict):
            # 获取主语的性别
            subj = base_structure.get("subject", {})
            subj_gender = subj.get("grammar", {}).get("gender", "masc")
            # 从对应性别池里选
            candidates = candidates.get(subj_gender, candidates.get("masc", []))

        if deriv_type in ("换名词", "换主语", "换宾语", "换表语"):
            for i, cand in enumerate(candidates[:max_count]):
                deriv = {"type": deriv_type, "value": cand}
                derivations.append(deriv)
        elif deriv_type in ("加时间", "加地点"):
            for i, cand in enumerate(candidates[:max_count]):
                deriv = {"type": deriv_type, "value": cand}
                derivations.append(deriv)
        else:
            derivations.append({"type": deriv_type})

    return {
        "base_structure": base_structure,
        "derivations": derivations,
        "zh": sentence["zh"],
    }


def build_reuse_plan_for_sentence(sentence, template):
    """
    为复用句生成编排计划（短链）
    输入: 句子 + 模板
    输出: {base_structure, derivations, zh}
    """
    structure = sentence.get("structure") or {}
    primary_tag = sentence.get("primary_tag", "")

    # 统一规范化大模型输出的 structure（和种子句用同一个函数）
    structure = normalize_llm_structure(structure, primary_tag)

    # 标准化 base_structure（公共函数，和种子句用同一个）
    base_structure = normalize_base_structure(structure, primary_tag)

    # 特殊模板：不衍生（如疑问句）
    if template.get("no_derivation"):
        return {
            "base_structure": base_structure,
            "derivations": [],  # 没有衍生
            "zh": sentence["zh"],
            "no_derivation": True,
        }

    # 生成复用句的衍生计划
    derivations = []
    verb_lemma = (structure.get("verb") or {}).get("lemma", "")

    for deriv_tpl in template.get("reuse_derivations", []):
        deriv_type = deriv_tpl["type"]

        # 加否定：如果原句已经是否定，就不加
        if deriv_type == "加否定" and base_structure.get("negation"):
            continue

        # 其他衍生：按 max 取多个候选
        candidates = deriv_tpl.get("candidates", [])
        max_count = deriv_tpl.get("max", 1)

        # 换宾语：如果动词有专门的宾语候选列表，用它替换全局候选
        if deriv_type == "换宾语" and verb_lemma in VERB_OBJECT_MAP:
            candidates = VERB_OBJECT_MAP[verb_lemma]
        
        # 换表语：判断句用，candidates是按性别分池的字典，按主语性别选池
        if deriv_type == "换表语" and isinstance(candidates, dict):
            # 获取主语的性别
            subj = base_structure.get("subject", {})
            subj_gender = subj.get("grammar", {}).get("gender", "masc")
            # 从对应性别池里选
            candidates = candidates.get(subj_gender, candidates.get("masc", []))

        if deriv_type in ("换名词", "换主语", "换宾语", "换表语"):
            for cand in candidates[:max_count]:
                deriv = {"type": deriv_type, "value": cand}
                derivations.append(deriv)
        elif deriv_type in ("加时间", "加地点"):
            for cand in candidates[:max_count]:
                deriv = {"type": deriv_type, "value": cand}
                derivations.append(deriv)
        else:
            derivations.append({"type": deriv_type})

    return {
        "base_structure": base_structure,
        "derivations": derivations,
        "zh": sentence["zh"],
        "no_derivation": template.get("no_derivation", False),  # 传递 no_derivation 标记
    }


def plan_layer(layer):
    """
    层内编排器
    输入: 一层的句子（每句自带 structure）
    输出: orchestrator 能执行的 layer_plan
    """
    sentences = layer["sentences"]
    if not sentences:
        return {"seed1": None, "reuse": []}

    # 第一句当种子句
    seed_plan = build_plan_for_sentence(sentences[0])

    # 其他句子当复用句
    reuse_plans = []
    for s in sentences[1:]:
        try:
            # 匹配模板
            template_name, template = match_template(s["primary_tag"])
            if not template:
                print(f"  复用句跳过: {s['ru'][:30]}... - 无模板 {s['primary_tag']}")
                continue

            reuse_plan = build_reuse_plan_for_sentence(s, template)
            reuse_plans.append(reuse_plan)
        except Exception as e:
            print(f"  复用句跳过: {s['ru'][:30]}... - {e}")

    return {
        "seed1": seed_plan,
        "reuse": reuse_plans,
    }


# ========== 测试 ==========
if __name__ == "__main__":
    # 测试样本
    test_layer = {
        "sentences": [
            {
                "ru": "Это студент.",
                "zh": "这是大学生。",
                "primary_tag": "T07",
                "structure": {
                    "type": "judgment",
                    "subject": {"lemma": "это", "grammar": {}},
                    "predicate": {"lemma": "студент", "grammar": {"case": "nom", "gender": "masc", "number": "sing"}},
                    "negation": False,
                    "adverbial": []
                }
            },
            {
                "ru": "Это не мама.",
                "zh": "这不是妈妈。",
                "primary_tag": "T08",
                "structure": {
                    "type": "judgment",
                    "subject": {"lemma": "это", "grammar": {}},
                    "predicate": {"lemma": "мама", "grammar": {"case": "nom", "gender": "fem", "number": "sing"}},
                    "negation": True,
                    "adverbial": []
                }
            },
        ]
    }

    try:
        result = plan_layer(test_layer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
