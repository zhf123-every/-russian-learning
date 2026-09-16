#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连词成句游戏（RuQuest）—— 种子数据脚本

注入 22 条 A1 级别俄语句子（含 6 条渐进式累加演示），覆盖：
  - 名词第一格到第六格（每格至少一例）
  - 动词现在时、过去时、将来时（不同人称和数）
  - 形容词与名词的性数格一致
  - 前置词（в, на, с, у, по）

每条句子带完整的 words 语法标注和 acceptableAnswers。

使用方法：
    python seed_quest.py

前置条件：
    - 已配置 DATABASE_URL 环境变量（或在 .env 中配置）
    - 已运行 python server.py 至少一次（表会自动创建）
"""

import json
import os
import sys
import time
import uuid

# 复用 server.py 中的数据库连接函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从环境变量或 .env 读取 DATABASE_URL
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("[ERROR] 未配置 DATABASE_URL 环境变量")
    print("请在 .env 文件中添加：DATABASE_URL=\"postgres://user:password@localhost:5432/dbname\"")
    sys.exit(1)

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("[ERROR] 未安装 psycopg2，请运行：pip install psycopg2-binary")
    sys.exit(1)


def _normalize_db_url(url):
    """修正 Render 注入的 DATABASE_URL 的 sslmode 问题"""
    if not url:
        return url
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=prefer"
    return url


def get_conn():
    from urllib.parse import urlparse
    clean_url = DATABASE_URL.split("?")[0] if "?" in DATABASE_URL else DATABASE_URL
    parsed = urlparse(clean_url)
    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 4000,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        ssl={"ssl_disabled": False},
        connect_timeout=30,
        charset="utf8mb4",
    )


def gen_id():
    return uuid.uuid4().hex[:16] + uuid.uuid4().hex[:8]


def w(order, lemma, form, pos, case=None, number=None, gender=None, person=None,
      tense=None, aspect=None, stress_pos=None, role=None, fixed=False, chunk="single_word"):
    """快捷构造单词标注"""
    return {
        "order": order, "lemma": lemma, "form": form, "pos": pos,
        "grammatical_case": case, "number": number, "gender": gender, "person": person,
        "tense": tense, "aspect": aspect, "stress_position": stress_pos,
        "syntactic_role": role, "is_fixed_position": fixed, "chunk_type": chunk,
    }


# ============================================================
# 16 条 A1 俄语句子（含完整语法标注）
# ============================================================
STATEMENTS = [
    # ── 1. 第一格（主格）：Это мой друг. ──
    {
        "order": 1,
        "chinese": "这是我的朋友。",
        "russian": "Это мой друг.",
        "stress_marked": "Это мой друг.",
        "grammatical_note": "第一格（主格）；Это 为中性指示代词作主語；мой 阳性物主代词与 друг 性数格一致；друг 阳性名词第一格作表语。",
        "word_order_flexible": False,
        "words": [
            w(0, "это", "Это", "pronoun", case="nom", number="sing", gender="neut", person=3, role="subject"),
            w(1, "мой", "мой", "adjective", case="nom", number="sing", gender="masc", role="attribute"),
            w(2, "друг", "друг", "noun", case="nom", number="sing", gender="masc", role="predicate_noun"),
        ],
    },
    # ── 2. 第二格（属格）：У меня есть книга. ──
    {
        "order": 2,
        "chinese": "我有一本书。",
        "russian": "У меня есть книга.",
        "stress_marked": "У меня́ есть кни́га.",
        "grammatical_note": "第二格（属格）；у + 第二格表示所属；меня 是 я 的第二格；есть 为存在动词第三人称单数；книга 阴性名词第一格作主语。",
        "word_order_flexible": True,
        "words": [
            w(0, "у", "У", "preposition", role="preposition"),
            w(1, "я", "меня́", "pronoun", case="gen", number="sing", person=1, stress_pos=2, role="adverbial"),
            w(2, "есть", "есть", "verb", number="sing", person=3, tense="present", aspect="imperf", role="predicate"),
            w(3, "книга", "кни́га", "noun", case="nom", number="sing", gender="fem", stress_pos=2, role="subject"),
        ],
    },
    # ── 3. 第三格（与格）：Я даю подарок другу. ──
    {
        "order": 3,
        "chinese": "我给朋友一个礼物。",
        "russian": "Я даю подарок другу.",
        "stress_marked": "Я даю́ пода́рок дру́гу.",
        "grammatical_note": "第三格（与格）；давать 为双宾语动词，подарок 第四格直接宾语，другу 第三格间接宾语；друг 阳性名词第三格 другу。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "давать", "даю́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "подарок", "пода́рок", "noun", case="acc", number="sing", gender="masc", stress_pos=2, role="direct_object"),
            w(3, "друг", "дру́гу", "noun", case="dat", number="sing", gender="masc", stress_pos=1, role="indirect_object"),
        ],
    },
    # ── 4. 第四格（宾格）：Я люблю тебя. ──
    {
        "order": 4,
        "chinese": "我爱你。",
        "russian": "Я люблю тебя.",
        "stress_marked": "Я люблю́ тебя́.",
        "grammatical_note": "第四格（宾格）；любить 为及物动词，接第四格；тебя 是 ты 的第二/第四格同形代词。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "любить", "люблю́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "ты", "тебя́", "pronoun", case="acc", number="sing", person=2, stress_pos=2, role="direct_object"),
        ],
    },
    # ── 5. 第五格（工具格）：Я пишу ручкой. ──
    {
        "order": 5,
        "chinese": "我用钢笔写字。",
        "russian": "Я пишу ручкой.",
        "stress_marked": "Я пишу́ ру́чкой.",
        "grammatical_note": "第五格（工具格）；писать 不及物用法；ручка 阴性名词第五格 ручкой，表示工具；无前置词的第五格。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "писать", "пишу́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "ручка", "ру́чкой", "noun", case="inst", number="sing", gender="fem", stress_pos=1, role="adverbial_instrument"),
        ],
    },
    # ── 6. 第六格（前置格）：Он работает в школе. ──
    {
        "order": 6,
        "chinese": "他在学校工作。",
        "russian": "Он работает в школе.",
        "stress_marked": "Он рабо́тает в шко́ле.",
        "grammatical_note": "第六格（前置格）；в + 第六格表示地点；школа 阴性名词第六格 школе；работать 第三人称单数现在时。",
        "word_order_flexible": True,
        "words": [
            w(0, "он", "Он", "pronoun", case="nom", number="sing", gender="masc", person=3, role="subject"),
            w(1, "работать", "рабо́тает", "verb", number="sing", person=3, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "в", "в", "preposition", role="preposition"),
            w(3, "школа", "шко́ле", "noun", case="prep", number="sing", gender="fem", stress_pos=2, role="adverbial_place"),
        ],
    },
    # ── 7. 动词现在时（第一人称复数）：Мы читаем книги. ──
    {
        "order": 7,
        "chinese": "我们读书。",
        "russian": "Мы читаем книги.",
        "stress_marked": "Мы чита́ем кни́ги.",
        "grammatical_note": "动词现在时第一人称复数；читать 变位 читаем；книга 阴性名词复数第四格 книги（与第一格同形）。",
        "word_order_flexible": True,
        "words": [
            w(0, "мы", "Мы", "pronoun", case="nom", number="plur", person=1, role="subject"),
            w(1, "читать", "чита́ем", "verb", number="plur", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "книга", "кни́ги", "noun", case="acc", number="plur", gender="fem", stress_pos=2, role="direct_object"),
        ],
    },
    # ── 8. 动词过去时（阳性）：Ты читал эту книгу? ──
    {
        "order": 8,
        "chinese": "你读过这本书吗？",
        "russian": "Ты читал эту книгу?",
        "stress_marked": "Ты чита́л э́ту кни́гу?",
        "grammatical_note": "动词过去时阳性；читать 过去时阳性 читал（主语男性）；этот 阴性第四格 эту；книга 第四格 книгу。",
        "word_order_flexible": True,
        "words": [
            w(0, "ты", "Ты", "pronoun", case="nom", number="sing", person=2, role="subject"),
            w(1, "читать", "чита́л", "verb", number="sing", gender="masc", tense="past", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "этот", "э́ту", "adjective", case="acc", number="sing", gender="fem", stress_pos=1, role="attribute"),
            w(3, "книга", "кни́гу", "noun", case="acc", number="sing", gender="fem", stress_pos=2, role="direct_object"),
        ],
    },
    # ── 9. 动词过去时（阴性）+ 形容词第四格阴性一致：Она купила новую машину. ──
    {
        "order": 9,
        "chinese": "她买了一辆新车。",
        "russian": "Она купила новую машину.",
        "stress_marked": "Она́ купи́ла но́вую маши́ну.",
        "grammatical_note": "动词过去时阴性；купить 完成体过去时阴性 купила；новый 阴性第四格 новую 与 машина 性数格一致；машина 第四格 машину。",
        "word_order_flexible": True,
        "words": [
            w(0, "она", "Она́", "pronoun", case="nom", number="sing", gender="fem", person=3, stress_pos=2, role="subject"),
            w(1, "купить", "купи́ла", "verb", number="sing", gender="fem", tense="past", aspect="perf", stress_pos=2, role="predicate"),
            w(2, "новый", "но́вую", "adjective", case="acc", number="sing", gender="fem", stress_pos=1, role="attribute"),
            w(3, "машина", "маши́ну", "noun", case="acc", number="sing", gender="fem", stress_pos=2, role="direct_object"),
        ],
    },
    # ── 10. 动词将来时（复合将来时）：Я буду читать завтра. ──
    {
        "order": 10,
        "chinese": "我明天将读书。",
        "russian": "Я буду читать завтра.",
        "stress_marked": "Я бу́ду чита́ть за́втра.",
        "grammatical_note": "复合将来时；быть 将来时第一人称单数 буду + 未完成体不定式 читать；завтра 时间副词。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "быть", "бу́ду", "verb", number="sing", person=1, tense="future", aspect="imperf", stress_pos=1, role="auxiliary"),
            w(2, "читать", "чита́ть", "verb", tense="infinitive", aspect="imperf", stress_pos=2, role="predicate"),
            w(3, "завтра", "за́втра", "adverb", stress_pos=1, role="adverbial_time"),
        ],
    },
    # ── 11. 形容词阴性第一格一致：Красивая девушка поёт. ──
    {
        "order": 11,
        "chinese": "漂亮的女孩在唱歌。",
        "russian": "Красивая девушка поёт.",
        "stress_marked": "Краси́вая де́вушка поёт.",
        "grammatical_note": "形容词阴性第一格一致；красивый 阴性第一格 красивая 与 девушка 性数格一致；петь 第三人称单数现在时 поёт。",
        "word_order_flexible": True,
        "words": [
            w(0, "красивый", "Краси́вая", "adjective", case="nom", number="sing", gender="fem", stress_pos=2, role="attribute"),
            w(1, "девушка", "де́вушка", "noun", case="nom", number="sing", gender="fem", stress_pos=1, role="subject"),
            w(2, "петь", "поёт", "verb", number="sing", person=3, tense="present", aspect="imperf", role="predicate"),
        ],
    },
    # ── 12. 形容词阳性第六格一致：Я живу в большом городе. ──
    {
        "order": 12,
        "chinese": "我住在大城市里。",
        "russian": "Я живу в большом городе.",
        "stress_marked": "Я живу́ в большо́м го́роде.",
        "grammatical_note": "形容词阳性第六格一致；большой 阳性第六格 большом 与 город 性数格一致；в + 第六格表示地点；жить 第一人称单数现在时。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "жить", "живу́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "в", "в", "preposition", role="preposition"),
            w(3, "большой", "большо́м", "adjective", case="prep", number="sing", gender="masc", stress_pos=2, role="attribute"),
            w(4, "город", "го́роде", "noun", case="prep", number="sing", gender="masc", stress_pos=1, role="adverbial_place"),
        ],
    },
    # ── 13. 前置词 с + 第五格：Он пришёл с другом. ──
    {
        "order": 13,
        "chinese": "他和朋友一起来的。",
        "russian": "Он пришёл с другом.",
        "stress_marked": "Он пришёл́ с дру́гом.",
        "grammatical_note": "前置词 с + 第五格表示伴随；прийти 完成体过去时阳性 пришёл；друг 阳性名词第五格 другом。",
        "word_order_flexible": True,
        "words": [
            w(0, "он", "Он", "pronoun", case="nom", number="sing", gender="masc", person=3, role="subject"),
            w(1, "прийти", "пришёл́", "verb", number="sing", gender="masc", tense="past", aspect="perf", stress_pos=2, role="predicate"),
            w(2, "с", "с", "preposition", role="preposition"),
            w(3, "друг", "дру́гом", "noun", case="inst", number="sing", gender="masc", stress_pos=1, role="adverbial_accompaniment"),
        ],
    },
    # ── 14. 前置词 на + 第六格：На столе лежит книга. ──
    {
        "order": 14,
        "chinese": "桌子上放着一本书。",
        "russian": "На столе лежит книга.",
        "stress_marked": "На столе́ лежи́т кни́га.",
        "grammatical_note": "前置词 на + 第六格表示地点；стол 阳性名词第六格 столе；лежать 第三人称单数现在时；книга 阴性名词第一格作主语（倒装语序）。",
        "word_order_flexible": True,
        "words": [
            w(0, "на", "На", "preposition", role="preposition"),
            w(1, "стол", "столе́", "noun", case="prep", number="sing", gender="masc", stress_pos=2, role="adverbial_place"),
            w(2, "лежать", "лежи́т", "verb", number="sing", person=3, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(3, "книга", "кни́га", "noun", case="nom", number="sing", gender="fem", stress_pos=2, role="subject"),
        ],
    },
    # ── 15. 前置词 у + 第二格（形容词第二格一致）：Я учусь у хорошего учителя. ──
    {
        "order": 15,
        "chinese": "我跟一位好老师学习。",
        "russian": "Я учусь у хорошего учителя.",
        "stress_marked": "Я учу́сь у хоро́шего учи́теля.",
        "grammatical_note": "前置词 у + 第二格表示动作主体；учиться 反身动词第一人称单数现在时；хороший 阳性第二格 хорошего 与 учитель 性数格一致；учитель 阳性名词第二格 учителя。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "учиться", "учу́сь", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "у", "у", "preposition", role="preposition"),
            w(3, "хороший", "хоро́шего", "adjective", case="gen", number="sing", gender="masc", stress_pos=2, role="attribute"),
            w(4, "учитель", "учи́теля", "noun", case="gen", number="sing", gender="masc", stress_pos=2, role="adverbial_agent"),
        ],
    },
    # ── 16. 动词现在时（第三人称单数）+ 方式副词：Она говорит по-русски. ──
    {
        "order": 16,
        "chinese": "她说俄语。",
        "russian": "Она говорит по-русски.",
        "stress_marked": "Она́ говори́т по-ру́сски.",
        "grammatical_note": "动词现在时第三人称单数；говорить 变位 говорит；по-русски 为带连字符的方式副词（不变格）。",
        "word_order_flexible": True,
        "words": [
            w(0, "она", "Она́", "pronoun", case="nom", number="sing", gender="fem", person=3, stress_pos=2, role="subject"),
            w(1, "говорить", "говори́т", "verb", number="sing", person=3, tense="present", aspect="imperf", stress_pos=3, role="predicate"),
            w(2, "по-русски", "по-ру́сски", "adverb", stress_pos=2, role="adverbial_manner"),
        ],
    },
    # ════════════════════════════════════════════════════════════
    # 渐进式累加序列：Я люблю смотреть фильмы（我喜欢看电影）
    # 6 道题，共享 sequence_id="seq_love_movies"
    # ════════════════════════════════════════════════════════════
    # ── 17. 我 → Я ──
    {
        "order": 17,
        "sequence_id": "seq_love_movies",
        "sequence_order": 1,
        "chinese": "我",
        "russian": "Я",
        "stress_marked": "Я",
        "grammatical_note": "人称代词 я 第一格单数，作主语。",
        "word_order_flexible": False,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
        ],
    },
    # ── 18. 喜欢 → люблю ──
    {
        "order": 18,
        "sequence_id": "seq_love_movies",
        "sequence_order": 2,
        "chinese": "喜欢",
        "russian": "люблю",
        "stress_marked": "люблю́",
        "grammatical_note": "动词 любить 第一人称单数现在时，作谓语。",
        "word_order_flexible": False,
        "words": [
            w(0, "любить", "люблю́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
        ],
    },
    # ── 19. 我喜欢 → Я люблю ──
    {
        "order": 19,
        "sequence_id": "seq_love_movies",
        "sequence_order": 3,
        "chinese": "我喜欢",
        "russian": "Я люблю",
        "stress_marked": "Я люблю́",
        "grammatical_note": "主语 + 谓语结构；я 第一格，люблю 第一人称单数现在时。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "любить", "люблю́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
        ],
    },
    # ── 20. 看 → смотреть ──
    {
        "order": 20,
        "sequence_id": "seq_love_movies",
        "sequence_order": 4,
        "chinese": "看",
        "russian": "смотреть",
        "stress_marked": "смотре́ть",
        "grammatical_note": "动词 смотреть 不定式，作宾语（любить + 不定式）。",
        "word_order_flexible": False,
        "words": [
            w(0, "смотреть", "смотре́ть", "verb", tense="infinitive", aspect="imperf", stress_pos=3, role="direct_object"),
        ],
    },
    # ── 21. 看电影 → смотреть фильмы ──
    {
        "order": 21,
        "sequence_id": "seq_love_movies",
        "sequence_order": 5,
        "chinese": "看电影",
        "russian": "смотреть фильмы",
        "stress_marked": "смотре́ть фи́льмы",
        "grammatical_note": "不定式 + 第四格宾语；фильм 阳性名词复数第四格 фильмы。",
        "word_order_flexible": True,
        "words": [
            w(0, "смотреть", "смотре́ть", "verb", tense="infinitive", aspect="imperf", stress_pos=3, role="predicate"),
            w(1, "фильм", "фи́льмы", "noun", case="acc", number="plur", gender="masc", stress_pos=1, role="direct_object"),
        ],
    },
    # ── 22. 我喜欢看电影 → Я люблю смотреть фильмы（完整句）──
    {
        "order": 22,
        "sequence_id": "seq_love_movies",
        "sequence_order": 6,
        "chinese": "我喜欢看电影。",
        "russian": "Я люблю смотреть фильмы.",
        "stress_marked": "Я люблю́ смотре́ть фи́льмы.",
        "grammatical_note": "любить + 不定式结构；я 第一格主语，люблю 第一人称单数现在时谓语，смотреть 不定式作宾语，фильмы 复数第四格作 смотреть 的宾语。",
        "word_order_flexible": True,
        "words": [
            w(0, "я", "Я", "pronoun", case="nom", number="sing", person=1, role="subject"),
            w(1, "любить", "люблю́", "verb", number="sing", person=1, tense="present", aspect="imperf", stress_pos=2, role="predicate"),
            w(2, "смотреть", "смотре́ть", "verb", tense="infinitive", aspect="imperf", stress_pos=3, role="direct_object"),
            w(3, "фильм", "фи́льмы", "noun", case="acc", number="plur", gender="masc", stress_pos=1, role="direct_object"),
        ],
    },
]


def seed():
    print("=" * 60)
    print("  连词成句游戏（RuQuest）—— 种子数据注入（22题，含渐进式序列）")
    print("=" * 60)

    conn = get_conn()
    now = int(time.time() * 1000)

    try:
        with conn.cursor() as cur:
            # ── 0. 删除旧表（按外键依赖顺序）──
            cur.execute("DROP TABLE IF EXISTS quest_learning_records")
            cur.execute("DROP TABLE IF EXISTS quest_acceptable_answers")
            cur.execute("DROP TABLE IF EXISTS quest_words")
            cur.execute("DROP TABLE IF EXISTS quest_statements")
            cur.execute("DROP TABLE IF EXISTS quest_courses")
            cur.execute("DROP TABLE IF EXISTS quest_course_packs")
            print("已删除旧表")

            # ── 0. 建表 ──
            cur.execute("CREATE TABLE IF NOT EXISTS quest_course_packs (id VARCHAR(64) PRIMARY KEY, title VARCHAR(255) NOT NULL, description TEXT, level VARCHAR(32), `order` INTEGER NOT NULL DEFAULT 0, is_free BOOLEAN DEFAULT TRUE, created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE TABLE IF NOT EXISTS quest_courses (id VARCHAR(64) PRIMARY KEY, course_pack_id VARCHAR(64) NOT NULL, title VARCHAR(255) NOT NULL, description TEXT, `order` INTEGER NOT NULL DEFAULT 0, created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE TABLE IF NOT EXISTS quest_statements (id VARCHAR(64) PRIMARY KEY, course_id VARCHAR(64) NOT NULL, `order` INTEGER NOT NULL, chinese TEXT NOT NULL, russian TEXT NOT NULL, stress_marked TEXT, grammatical_note TEXT, word_order_flexible BOOLEAN NOT NULL DEFAULT TRUE, sequence_id VARCHAR(64), sequence_order INTEGER, created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE TABLE IF NOT EXISTS quest_words (id VARCHAR(64) PRIMARY KEY, statement_id VARCHAR(64) NOT NULL, `order` INTEGER NOT NULL, lemma VARCHAR(128) NOT NULL, form VARCHAR(128) NOT NULL, pos VARCHAR(32) NOT NULL, grammatical_case VARCHAR(32), number VARCHAR(16), gender VARCHAR(16), person INTEGER, tense VARCHAR(32), aspect VARCHAR(32), stress_position INTEGER, syntactic_role VARCHAR(64), is_fixed_position BOOLEAN NOT NULL DEFAULT FALSE, chunk_type VARCHAR(32) NOT NULL DEFAULT 'single_word', created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE TABLE IF NOT EXISTS quest_acceptable_answers (id VARCHAR(64) PRIMARY KEY, statement_id VARCHAR(64) NOT NULL, word_order JSON NOT NULL, word_variants JSON NOT NULL, is_default BOOLEAN NOT NULL DEFAULT FALSE, note TEXT, created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE TABLE IF NOT EXISTS quest_learning_records (id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64), course_id VARCHAR(64) NOT NULL, completion_time INTEGER NOT NULL DEFAULT 0, correct_count INTEGER NOT NULL DEFAULT 0, total_count INTEGER NOT NULL DEFAULT 0, max_combo INTEGER NOT NULL DEFAULT 0, rating VARCHAR(8) NOT NULL DEFAULT 'C', created_at BIGINT DEFAULT 0)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_statement_id ON quest_words(statement_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_words_lemma ON quest_words(lemma)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_aa_statement_id ON quest_acceptable_answers(statement_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_quest_learning_records_course_id ON quest_learning_records(course_id)")
            print("\n[0/5] 数据表已确保存在")

            # ── 0.5. 清空旧数据 ──
            cur.execute("DELETE FROM quest_learning_records")
            cur.execute("DELETE FROM quest_acceptable_answers")
            cur.execute("DELETE FROM quest_words")
            cur.execute("DELETE FROM quest_statements")
            cur.execute("DELETE FROM quest_courses")
            cur.execute("DELETE FROM quest_course_packs")
            print("[0.5/5] 已清空旧数据")

            # ── 1. 创建课程包 ──
            pack_id = gen_id()
            cur.execute(
                "INSERT INTO quest_course_packs (id, title, description, level, `order`, is_free, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (pack_id, "俄语 A1 入门", "俄语零基础入门课程，覆盖六格变化、动词三时态、形容词一致与常用前置词", "A1", 1, True, now)
            )
            print(f"[1/5] 课程包已创建: {pack_id}")

            # ── 2. 创建课程 ──
            course_id = gen_id()
            cur.execute(
                "INSERT INTO quest_courses (id, course_pack_id, title, description, `order`, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (course_id, pack_id, "A1 基础语法全览", "16道核心句型，覆盖名词六格、动词三时态、形容词一致与前置词搭配", 1, now)
            )
            print(f"[2/5] 课程已创建: {course_id}")

            # ── 3. 插入句子 + words + acceptable_answers ──
            total_words = 0
            for s in STATEMENTS:
                stmt_id = gen_id()
                cur.execute(
                    "INSERT INTO quest_statements (id, course_id, `order`, chinese, russian, stress_marked, grammatical_note, word_order_flexible, sequence_id, sequence_order, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (stmt_id, course_id, s["order"], s["chinese"], s["russian"],
                     s["stress_marked"], s["grammatical_note"], s["word_order_flexible"],
                     s.get("sequence_id"), s.get("sequence_order"), now)
                )

                for wd in s["words"]:
                    word_id = gen_id()
                    cur.execute(
                        "INSERT INTO quest_words (id, statement_id, `order`, lemma, form, pos, grammatical_case, number, gender, person, tense, aspect, stress_position, syntactic_role, is_fixed_position, chunk_type, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (word_id, stmt_id, wd["order"], wd["lemma"], wd["form"], wd["pos"],
                         wd["grammatical_case"], wd["number"], wd["gender"], wd["person"],
                         wd["tense"], wd["aspect"], wd["stress_position"], wd["syntactic_role"],
                         wd["is_fixed_position"], wd["chunk_type"], now)
                    )
                    total_words += 1

                # 插入默认可接受答案（标准语序）
                aa_id = gen_id()
                word_order = list(range(len(s["words"])))
                cur.execute(
                    "INSERT INTO quest_acceptable_answers (id, statement_id, word_order, word_variants, is_default, note, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (aa_id, stmt_id, json.dumps(word_order), json.dumps({}), True, "标准语序", now)
                )

            print(f"[3/5] 已插入 {len(STATEMENTS)} 条句子，{total_words} 个单词标注")
            print(f"[4/5] 已插入 {len(STATEMENTS)} 条默认可接受答案")

        conn.commit()
        print("[5/5] 事务已提交")

        print("\n" + "=" * 60)
        print("  种子数据注入完成！")
        print("=" * 60)
        print(f"  课程包 ID:  {pack_id}")
        print(f"  课程 ID:    {course_id}")
        print(f"  句子数量:   {len(STATEMENTS)}（含 6 条渐进式累加）")
        print(f"  单词标注:   {total_words}")
        print("")
        print("  语法覆盖:")
        print("    名词六格:  1格(Это мой друг) / 2格(У меня есть) / 3格(Я даю другу)")
        print("               4格(Я люблю тебя) / 5格(Я пишу ручкой) / 6格(в школе)")
        print("    动词时态:  现在时(читаю/говорит) / 过去时(читал/купила/пришёл) / 将来时(буду читать)")
        print("    形容词一致: 阴性(красивая девушка) / 阳性六格(большом городе) / 阴性四格(новую машину)")
        print("    前置词:    в(六格) / на(六格) / с(五格) / у(二格) / по-русски(副词)")
        print("")
        print("  测试 API:")
        print(f"  curl http://localhost:8000/api/courses/{course_id}/statements")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 注入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
