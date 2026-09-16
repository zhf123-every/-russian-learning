#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连词成句游戏（RuQuest）—— 判题引擎（重构版）

核心设计：基于 words 表的语法标注做结构化对比，而非靠编辑距离猜错误类型。

判题流程：
  1. 精确匹配标准词形 → 正确
  2. 匹配 acceptableAnswers.wordVariants 中允许的变体 → 正确
  3. 候选匹配：找编辑距离最小的标准词，确定用户输入属于哪个 lemma
  4. 错误诊断（基于语法标注，不靠距离猜）：
     - 差异在词干部分（非词尾）→ spelling_error（拼写错误）
     - 差异在词尾部分 + 名词/代词/形容词/数词 → case_error（变格错误）
     - 差异在词尾部分 + 动词 → conjugation_error（变位错误）
     - 与所有标准词差异都很大 → word_choice_error（用词错误）
"""

import re
import unicodedata
from difflib import SequenceMatcher


# ============================================================
# 工具函数
# ============================================================

def strip_accents(s):
    """去除俄语重音符号（combining acute accent U+0301）"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if c != '\u0301'
    )


def normalize_word(s):
    """标准化词：去重音、去首尾标点、转小写"""
    s = strip_accents(s).strip().lower()
    s = re.sub(r'^[^\w]+|[^\w]+$', '', s)
    return s


def levenshtein_distance(a, b):
    """计算两个字符串的编辑距离（Levenshtein）"""
    if len(a) < len(b):
        return levenshtein_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (ca != cb)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def first_diff_position(a, b):
    """
    找两个等长字符串第一个不同字符的位置（0-based）。
    如果完全相同返回 -1。
    """
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return -1


def _suffix_range(word_len):
    """
    根据词长动态计算词尾范围（最后N个字符视为词尾）。
    短词的词尾占比大，范围要缩小，避免把词干替换误判为变格。
      - 词长 <= 4 → 最后1个字符（如 стол 的词尾只有 л）
      - 词长 5~6 → 最后2个字符（如 книга 的词尾是 га）
      - 词长 >= 7 → 最后3个字符
    """
    if word_len <= 4:
        return 1
    elif word_len <= 6:
        return 2
    else:
        return 3


def is_suffix_change(a, b):
    """
    判断两个词的差异是否发生在词尾（词形变化），还是词干（拼写错误）。

    俄语词形变化（变格/变位）几乎都发生在词尾：
      - 名词变格：стол → столу（词尾加у）
      - 代词变格：ты → тебя（整体变化，长度差>=2视为词形变化）
      - 动词变位：люблю → любит（词尾替换）
    而拼写错误通常发生在词干部分。

    判断规则：
      - 长度相同 → 第一个不同位置是否在动态词尾范围内
      - 长度差 >= 2 → True（拼写错误通常只差1个字母）
      - 长度差 == 1：
          - 末尾添加且添加字母与前一字母相同（重复输入，стол→столл）→ False
          - 开头删除（стол→тол）→ False
          - 其他末尾添加/删除 → True
    """
    if len(a) == len(b):
        pos = first_diff_position(a, b)
        if pos == -1:
            return False  # 完全相同
        suffix_len = _suffix_range(len(a))
        if pos < len(a) - suffix_len:
            return False  # 差异在词干 → 拼写错误

        # 差异在词尾范围内，进一步精细判断：
        # 如果只有最后一个字符不同，且是辅音→辅音替换 → 拼写错误
        # （俄语变格通常是元音词尾变化，如 книга→книги；辅音词尾替换如 стол→стоп 是不同词）
        if pos == len(a) - 1:
            vowels = set('аеёиоуыэюя')
            last_a = a[-1].lower()
            last_b = b[-1].lower()
            if last_a not in vowels and last_b not in vowels:
                return False  # 辅音→辅音替换，不是变格

        return True

    # 长度不同
    short, long = (a, b) if len(a) < len(b) else (b, a)
    diff = len(long) - len(short)

    # 长度差 >= 2 → 词形变化（拼写错误不太可能差2个以上）
    if diff >= 2:
        return True

    # 长度差 == 1，精细判断
    # 情况1：长词以短词开头（字母添加在末尾）
    if long.startswith(short):
        added_char = long[len(short)]
        prev_char = short[-1] if short else ''
        # 末尾重复输入（стол → столл）→ 拼写错误
        if added_char == prev_char:
            return False
        return True

    # 情况2：短词是长词的后缀（字母删除在开头，如 стол → тол）→ 拼写错误
    if long.endswith(short):
        return False

    # 情况3：中间插入/删除 → 词干变化 → 拼写错误
    return False


# ============================================================
# 判题引擎
# ============================================================

class AnswerEngine:
    """俄语连词成句判题引擎（基于语法标注的结构化诊断）"""

    # 候选匹配阈值：编辑距离 <= 3 认为属于同一个 lemma（可能是词形变化或拼写错误）
    LEMMA_MATCH_MAX_DIST = 3

    # 变格词性（名词/代词/形容词/数词/限定词）
    CASED_POS = {'noun', 'pronoun', 'adjective', 'numeral', 'det'}

    def __init__(self, statement):
        """
        Args:
            statement: 从数据库查出的完整句子对象，必须包含 words 和 acceptableAnswers
        """
        self.statement = statement
        self.words = statement.get('words', []) or []
        self.acceptable_answers = statement.get('acceptableAnswers', []) or []

        # 构建允许的词形变体表：{lemma_lower: {variant_normalized: True}}
        self.allowed_variants = {}
        for aa in self.acceptable_answers:
            variants = aa.get('wordVariants', {}) or {}
            for lemma, forms in variants.items():
                key = lemma.lower()
                if key not in self.allowed_variants:
                    self.allowed_variants[key] = set()
                if isinstance(forms, list):
                    for f in forms:
                        self.allowed_variants[key].add(normalize_word(f))
                elif isinstance(forms, str):
                    self.allowed_variants[key].add(normalize_word(forms))

    # --------------------------------------------------------
    # 主入口
    # --------------------------------------------------------

    def judge(self, user_input):
        """
        判题主入口

        Returns:
            {
                "correct": bool,
                "errors": [...],
                "acceptedVariants": [...],
                "wordAnalysis": [...],
            }
        """
        # 1. 用户输入分词
        user_words = [normalize_word(w) for w in user_input.split() if w.strip()]

        # 2. 逐词匹配（不按位置，灵活语序）
        word_analysis = []
        errors = []
        used_indices = set()

        for user_idx, uw in enumerate(user_words):
            result = self._match_word(uw, used_indices)
            word_analysis.append(result['analysis'])

            if not result['analysis']['correct']:
                errors.append({
                    'wordIndex': user_idx,
                    'errorType': result['error_type'],
                    'expected': result.get('expected'),
                    'expectedCase': result.get('expectedCase'),
                    'userCase': result.get('userCase'),
                    'suggestion': result.get('suggestion'),
                })

            if result.get('word_idx') is not None:
                used_indices.add(result['word_idx'])

        # 3. 检查缺失的词
        for i, w in enumerate(self.words):
            if i not in used_indices:
                errors.append({
                    'wordIndex': -1,
                    'errorType': 'missing_word',
                    'expected': w['form'],
                    'expectedCase': w.get('grammaticalCase'),
                    'userCase': None,
                    'suggestion': '缺少单词：{}（{}）'.format(w['form'], w['lemma']),
                })

        # 4. 生成可接受的句子变体
        accepted_variants = self._generate_accepted_variants()

        # 5. 综合判定
        correct = (len(errors) == 0) and (len(user_words) == len(self.words))

        return {
            'correct': correct,
            'errors': errors,
            'acceptedVariants': accepted_variants,
            'wordAnalysis': word_analysis,
        }

    # --------------------------------------------------------
    # 核心匹配 + 结构化诊断
    # --------------------------------------------------------

    def _match_word(self, user_word, used_indices):
        """
        为用户输入词找最佳匹配的标准词，并做结构化错误诊断。

        诊断逻辑（基于语法标注，不靠编辑距离猜）：
          1. 精确匹配 form → 正确
          2. 匹配 wordVariants → 正确
          3. 候选匹配：找编辑距离最小的标准词
          4. 最小距离 > LEMMA_MATCH_MAX_DIST → word_choice_error（lemma 完全不同）
          5. 最小距离 <= 阈值 → lemma 相同，词形不符：
             a. 差异在词干（非词尾）→ spelling_error
             b. 差异在词尾 + 变格词性 → case_error（返回 expected_case）
             c. 差异在词尾 + 动词 → conjugation_error（返回 expected_person/number）
        """
        best_idx = None
        best_dist = float('inf')
        best_word = None

        for i, w in enumerate(self.words):
            if i in used_indices:
                continue

            std_form = normalize_word(w['form'])
            lemma = w['lemma'].lower()

            # === a. 精确匹配标准词形 → 正确 ===
            if user_word == std_form:
                return {
                    'analysis': self._build_analysis(user_word, w, correct=True),
                    'error_type': None,
                    'word_idx': i,
                }

            # === b. 匹配允许的词形变体 → 正确 ===
            allowed = self.allowed_variants.get(lemma, set())
            if user_word in allowed:
                return {
                    'analysis': self._build_analysis(user_word, w, correct=True, variant_accepted=True),
                    'error_type': None,
                    'word_idx': i,
                }

            # === c. 记录编辑距离，找最相似的标准词（确定 lemma 归属） ===
            dist = levenshtein_distance(user_word, std_form)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
                best_word = w

        # 没有可用的标准词 → 多余的词
        if best_word is None:
            return {
                'analysis': {
                    'word': user_word, 'lemma': None, 'pos': None,
                    'case': None, 'correct': False,
                },
                'error_type': 'extra_word',
                'word_idx': None,
                'expected': None,
                'suggestion': '多余的单词',
            }

        std_form = normalize_word(best_word['form'])
        pos = best_word.get('pos', '')

        # === d. 差异太大 → lemma 完全不同 → 用词错误 ===
        if best_dist > self.LEMMA_MATCH_MAX_DIST:
            return {
                'analysis': self._build_analysis(user_word, best_word, correct=False),
                'error_type': 'word_choice_error',
                'word_idx': best_idx,
                'expected': best_word['form'],
                'suggestion': '用词错误，应为：{}（{}）'.format(best_word['form'], best_word['lemma']),
            }

        # === e. lemma 相同，词形不符 → 结构化诊断 ===
        suffix_change = is_suffix_change(user_word, std_form)

        # e1. 差异在词干 → 拼写错误（lemma 正确但拼错了字母）
        if not suffix_change:
            return {
                'analysis': self._build_analysis(user_word, best_word, correct=False),
                'error_type': 'spelling_error',
                'word_idx': best_idx,
                'expected': best_word['form'],
                'expectedCase': best_word.get('grammaticalCase'),
                'userCase': None,
                'suggestion': '拼写错误，正确写法：{}'.format(best_word['form']),
            }

        # e2. 差异在词尾 + 变格词性 → 变格错误（case_error）
        if pos in self.CASED_POS:
            expected_case = best_word.get('grammaticalCase')
            case_name = self._case_name(expected_case)
            return {
                'analysis': self._build_analysis(user_word, best_word, correct=False),
                'error_type': 'case_error',
                'word_idx': best_idx,
                'expected': best_word['form'],
                'expectedCase': expected_case,
                'userCase': None,  # 无法从词形精确推断用户用了哪一格，需形态分析器
                'suggestion': '变格错误，应使用{}，正确形式：{}'.format(case_name, best_word['form']),
            }

        # e3. 差异在词尾 + 动词 → 变位错误（conjugation_error）
        if pos == 'verb':
            person = best_word.get('person')
            number = best_word.get('number')
            person_name = self._person_name(person)
            number_name = self._number_name(number)
            return {
                'analysis': self._build_analysis(user_word, best_word, correct=False),
                'error_type': 'conjugation_error',
                'word_idx': best_idx,
                'expected': best_word['form'],
                'expectedCase': None,
                'userCase': None,
                'suggestion': '变位错误，应使用{}{}，正确形式：{}'.format(
                    person_name, number_name, best_word['form']),
            }

        # e4. 其他词性（副词、介词、连词等）词尾变化 → 视为拼写错误
        return {
            'analysis': self._build_analysis(user_word, best_word, correct=False),
            'error_type': 'spelling_error',
            'word_idx': best_idx,
            'expected': best_word['form'],
            'expectedCase': None,
            'userCase': None,
            'suggestion': '拼写错误，正确写法：{}'.format(best_word['form']),
        }

    # --------------------------------------------------------
    # 辅助方法
    # --------------------------------------------------------

    def _build_analysis(self, user_word, word_data, correct, variant_accepted=False):
        """构建 wordAnalysis 条目"""
        return {
            'word': user_word,
            'lemma': word_data.get('lemma'),
            'pos': word_data.get('pos'),
            'case': word_data.get('grammaticalCase'),
            'correct': correct,
            'variantAccepted': variant_accepted,
        }

    def _generate_accepted_variants(self):
        """生成所有可接受的完整句子变体"""
        variants = []
        standard = ' '.join(w['form'] for w in self.words)
        variants.append(standard)

        for aa in self.acceptable_answers:
            word_order = aa.get('wordOrder', [])
            if not word_order or word_order == list(range(len(self.words))):
                continue
            try:
                sentence = ' '.join(self.words[i]['form'] for i in word_order)
                if sentence not in variants:
                    variants.append(sentence)
            except (IndexError, TypeError):
                pass

        return variants

    @staticmethod
    def _case_name(case_code):
        mapping = {
            'nom': '第一格（主格）', 'gen': '第二格（属格）',
            'dat': '第三格（与格）', 'acc': '第四格（宾格）',
            'ins': '第五格（工具格）', 'prep': '第六格（前置格）',
        }
        return mapping.get(case_code, str(case_code) + '格')

    @staticmethod
    def _person_name(person):
        mapping = {1: '第一人称', 2: '第二人称', 3: '第三人称'}
        return mapping.get(person, '')

    @staticmethod
    def _number_name(number):
        mapping = {'sing': '单数', 'plur': '复数', 'plural': '复数'}
        return mapping.get(number, '')
