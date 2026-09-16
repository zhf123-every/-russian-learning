#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
answer_engine.py 单元测试

测试场景：
  1. 输入完全正确（标准语序）→ 正确
  2. 输入正确但语序调整（Я тебя люблю）→ 正确
  3. 输入变格错误（Я люблю ты）→ 错误，errorType=case_error
  4. 输入拼写错误（Я люблю тибя）→ 错误，errorType=spelling_error
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from answer_engine import AnswerEngine


# ============================================================
# 测试数据：第一条种子句子 "Я люблю тебя."
# ============================================================
TEST_STATEMENT = {
    "id": "stmt_001",
    "order": 1,
    "chinese": "我爱你。",
    "russian": "Я люблю тебя.",
    "stressMarked": "Я люблю́ тебя́.",
    "grammaticalNote": "主谓宾句型；любить 为及物动词，接第四格；тебя 是 ты 的第二/第四格同形。",
    "wordOrderFlexible": True,
    "words": [
        {
            "order": 0, "lemma": "я", "form": "Я", "pos": "pronoun",
            "grammaticalCase": "nom", "number": "sing", "gender": None,
            "person": 1, "tense": None, "aspect": None, "stressPosition": None,
            "syntacticRole": "subject", "isFixedPosition": False, "chunkType": "single_word",
        },
        {
            "order": 1, "lemma": "любить", "form": "люблю́", "pos": "verb",
            "grammaticalCase": None, "number": "sing", "gender": None,
            "person": 1, "tense": "present", "aspect": "imperf", "stressPosition": 2,
            "syntacticRole": "predicate", "isFixedPosition": False, "chunkType": "single_word",
        },
        {
            "order": 2, "lemma": "ты", "form": "тебя́", "pos": "pronoun",
            "grammaticalCase": "acc", "number": "sing", "gender": None,
            "person": 2, "tense": None, "aspect": None, "stressPosition": 2,
            "syntacticRole": "object", "isFixedPosition": False, "chunkType": "single_word",
        },
    ],
    "acceptableAnswers": [
        {
            "wordOrder": [0, 1, 2],
            "wordVariants": {},
            "isDefault": True,
            "note": "标准语序（主谓宾）",
        },
        {
            "wordOrder": [0, 2, 1],
            "wordVariants": {},
            "isDefault": False,
            "note": "宾语前置（Я тебя люблю），俄语常见语序",
        },
    ],
}


def run_tests():
    engine = AnswerEngine(TEST_STATEMENT)
    passed = 0
    failed = 0

    # --------------------------------------------------------
    # 测试 1：标准语序，完全正确
    # --------------------------------------------------------
    print("=" * 60)
    print("测试 1：标准语序，完全正确")
    print("  输入: Я люблю тебя")
    result = engine.judge("Я люблю тебя")
    try:
        assert result['correct'] is True, "应判定为正确"
        assert len(result['errors']) == 0, "不应有错误"
        assert len(result['wordAnalysis']) == 3, "应有3个词的分析"
        assert all(w['correct'] for w in result['wordAnalysis']), "所有词都应正确"
        print("  ✅ 通过")
        passed += 1
    except AssertionError as e:
        print("  ❌ 失败:", e)
        print("     result:", result)
        failed += 1

    # --------------------------------------------------------
    # 测试 2：灵活语序（宾语前置），应判定为正确
    # --------------------------------------------------------
    print("=" * 60)
    print("测试 2：灵活语序（宾语前置），应正确")
    print("  输入: Я тебя люблю")
    result = engine.judge("Я тебя люблю")
    try:
        assert result['correct'] is True, "灵活语序应判定为正确"
        assert len(result['errors']) == 0, "不应有错误"
        assert len(result['wordAnalysis']) == 3, "应有3个词的分析"
        # 验证 acceptedVariants 中包含两种语序
        assert any('Я люблю' in v for v in result['acceptedVariants']), "应包含标准语序变体"
        print("  acceptedVariants:", result['acceptedVariants'])
        print("  ✅ 通过")
        passed += 1
    except AssertionError as e:
        print("  ❌ 失败:", e)
        print("     result:", result)
        failed += 1

    # --------------------------------------------------------
    # 测试 3：变格错误（ты 应该用 тебя 第四格）
    # --------------------------------------------------------
    print("=" * 60)
    print("测试 3：变格错误（ты 应为 тебя 第四格）")
    print("  输入: Я люблю ты")
    result = engine.judge("Я люблю ты")
    try:
        assert result['correct'] is False, "应判定为错误"
        assert len(result['errors']) >= 1, "至少有1个错误"
        # 找到 ты 对应的错误（wordIndex=2）
        thy_errors = [e for e in result['errors'] if e['wordIndex'] == 2]
        assert len(thy_errors) >= 1, "第3个词(ты)应有错误"
        err = thy_errors[0]
        assert err['errorType'] == 'case_error', \
            "errorType 应为 case_error，实际为: {}".format(err['errorType'])
        assert err['expected'] == 'тебя́', "expected 应为 тебя́，实际为: {}".format(err['expected'])
        print("  errorType:", err['errorType'])
        print("  expected:", err['expected'])
        print("  suggestion:", err['suggestion'])
        print("  ✅ 通过")
        passed += 1
    except AssertionError as e:
        print("  ❌ 失败:", e)
        print("     errors:", result['errors'])
        failed += 1

    # --------------------------------------------------------
    # 测试 4：拼写错误（тибя 应为 тебя）
    # --------------------------------------------------------
    print("=" * 60)
    print("测试 4：拼写错误（тибя 应为 тебя）")
    print("  输入: Я люблю тибя")
    result = engine.judge("Я люблю тибя")
    try:
        assert result['correct'] is False, "应判定为错误"
        assert len(result['errors']) >= 1, "至少有1个错误"
        # 找到 тибя 对应的错误（wordIndex=2）
        typo_errors = [e for e in result['errors'] if e['wordIndex'] == 2]
        assert len(typo_errors) >= 1, "第3个词(тибя)应有错误"
        err = typo_errors[0]
        assert err['errorType'] == 'spelling_error', \
            "errorType 应为 spelling_error，实际为: {}".format(err['errorType'])
        assert err['expected'] == 'тебя́', "expected 应为 тебя́"
        print("  errorType:", err['errorType'])
        print("  expected:", err['expected'])
        print("  suggestion:", err['suggestion'])
        print("  ✅ 通过")
        passed += 1
    except AssertionError as e:
        print("  ❌ 失败:", e)
        print("     errors:", result['errors'])
        failed += 1

    # --------------------------------------------------------
    # 汇总
    # --------------------------------------------------------
    print("=" * 60)
    print("测试结果：{} 通过，{} 失败".format(passed, failed))
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    run_tests()
