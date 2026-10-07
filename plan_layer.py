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

    # 自动修正：根据主语的人称和数，自动设置动词的人称和数
    subj = base.get("subject") or {}
    subj_grammar = subj.get("grammar") or {}
    if base.get("verb") and subj_grammar.get("person") and subj_grammar.get("number"):
        base["verb"]["grammar"] = base["verb"].get("grammar", {})
        base["verb"]["grammar"]["person"] = subj_grammar["person"]
        base["verb"]["grammar"]["number"] = subj_grammar["number"]

    return base


def build_plan_for_sentence(sentence):
    """
    为单句生成编排计划
    输入: {"ru": "...", "zh": "...", "primary_tag": "...", "structure": {...}}
    输出: orchestrator 需要的 {base_structure, derivations, zh}
    """
    primary_tag = sentence["primary_tag"]
    structure = sentence.get("structure", {})

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

        if deriv_type in ("换名词", "换主语", "换宾语"):
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

        if deriv_type in ("换名词", "换主语", "换宾语"):
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
