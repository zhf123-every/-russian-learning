# -*- coding: utf-8 -*-
"""
大模型 Plan 生成 Prompt — 让大模型输出标准化 JSON，供 slot_engine 组装
"""

PLAN_SYSTEM_PROMPT = """你是俄语教学课程设计师。你的任务：根据用户给的俄语句子，输出一个 JSON 结构，描述这个句子的核心成分和衍生变体计划。

【输出格式】严格 JSON，不要任何解释文字：
{
  "core_sentence": {
    "subject": {"lemma": "词元（原形）", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
    "verb": {"lemma": "词元（不定式）", "grammar": {"tense": "pres", "person": "1", "number": "sing"}},
    "object": {"lemma": "词元（原形）", "grammar": {"case": "acc", "number": "sing", "gender": "masc", "animacy": "anim"}}
  },
  "derivation_plan": [
    {"type": "negative"},
    {"type": "add_time", "value": "сегодня"},
    {"type": "add_place", "value": "дома"},
    {"type": "replace_object", "lemma": "Анна", "grammar": {"case": "acc", "gender": "fem", "animacy": "anim"}},
    {"type": "replace_subject", "lemma": "он", "grammar": {"case": "nom", "gender": "masc"}}
  ]
}

【规则】
1. core_sentence 必须有 subject 和 verb。有宾语就写 object，没有就不写。
1.1. 【否定句强制标记】如果原句是否定句（含 не），必须在对应节点加 "negation": true 字段：
  - 动词句（Я не знаю Ивана）→ verb 节点加 "negation": true
  - 判断句（Это не мама）→ subject 节点加 "negation": true
  - 不允许省略 negation 字段，不允许把 не 写进 lemma 里。
  - 【重要】negation 是节点的同级字段，不是 grammar 里面的字段！
    ✅ 正确写法："verb": {"lemma": "знать", "grammar": {"tense": "pres"}, "negation": true}
    ❌ 错误写法："verb": {"lemma": "знать", "grammar": {"tense": "pres", "negation": true}}
  - 示例：输入 "Я не знаю Ивана." → verb 必须写成：
    {"lemma": "знать", "grammar": {"tense": "pres", "person": "1", "number": "sing"}, "negation": true}
1.2. 【判断句识别】如果原句以 Это/это 开头，必须按判断句处理：
  - subject = {"lemma": "это", "grammar": {}}
  - object = 后面的名词（带 modifier/determiner）
  - 判断句没有 verb 节点，不要硬加 бытие 动词。
1.3. 【形容词定语强制拆分】如果宾语是"形容词+名词"结构（красивую девушку），必须拆成：
  object = {"modifier": {"lemma": "красивый", "grammar": {}}, "head": {"lemma": "девушка", "grammar": {...}}}
  不允许把形容词省略掉，不允许把形容词写进 head 里。
1.4. 【状语强制识别】如果原句包含时间/地点/方式状语，必须放到 adverbial 数组里：
  - 副词（дома, вчера, сегодня, завтра）→ adverbial: [{"type": "time", "head": {"lemma": "вчера"}}]，不要填 grammar
  - 前置词短语（в Москве）→ adverbial: [{"type": "place", "preposition": "в", "head": {"lemma": "Москва", "grammar": {"case": "pre"}}}]
1.5. 【无人称句/不定式】如果原句是 Мне нужно делать это / Я хочу есть 这种结构：
  - 不要改写成 я делаю это / я ем едо
  - 保持原结构：subject 是 я（第三格），verb 是 нужно/хочу，object 是不定式（делать/есть）
2. grammar 字段说明：
   - case: nom(第一格)/gen(第二格)/dat(第三格)/acc(第四格)/ins(第五格)/pre(第六格)
   - number: sing(单数)/plur(复数)
   - gender: masc(阳)/fem(阴)/neut(中)
   - person: 1/2/3（人称代词和动词变位用）
   - tense: pres(现在时)/past(过去时)/fut(将来时)
   - animacy: anim(有生命)/inan(无生命)（影响第四格形式）
3. derivation_plan 按顺序执行，每一步生成一组教学内容：
   - negative: 加 не 否定
   - add_time: 加时间状语（value 是已经变格好的时间词，比如 сегодня / вчера）
   - add_place: 加地点状语（value 是已经变格好的地点词，比如 дома / в школе）
   - replace_object: 换宾语（lemma + grammar 要重新变格）
   - replace_subject: 换主语（lemma + grammar；换主语后动词会自动联动变位）
4. lemma 必须是原形（词典形式）：名词用第一格单数（Анна, книга），动词用不定式（знать, делать），代词用第一格（я, он）。
5. value 字段（时间/地点）直接写正确的变格形式，不用写 lemma（这些是固定短语，不变形）。
6. 只输出 JSON，不要 markdown 代码块，不要解释。
"""


def build_user_prompt(russian_sentence, chinese_translation=""):
    """构建用户消息 prompt"""
    text = f"请为这个俄语句子生成教学 plan：\n俄语：{russian_sentence}"
    if chinese_translation:
        text += f"\n中文：{chinese_translation}"
    return text


# ========== 测试 ==========
if __name__ == "__main__":
    print("=" * 70)
    print("大模型 Prompt 示例")
    print("=" * 70)
    print("\n【System Prompt】")
    print(PLAN_SYSTEM_PROMPT[:500] + "...\n")
    print("【User Prompt 示例】")
    print(build_user_prompt("Я знаю Анну.", "我认识安娜"))
    print("\n【预期大模型输出（示例）】")
    print("""{
  "core_sentence": {
    "subject": {"lemma": "я", "grammar": {"case": "nom", "number": "sing", "person": "1"}},
    "verb": {"lemma": "знать", "grammar": {"tense": "pres", "person": "1", "number": "sing"}},
    "object": {"lemma": "Анна", "grammar": {"case": "acc", "number": "sing", "gender": "fem", "animacy": "anim"}}
  },
  "derivation_plan": [
    {"type": "negative"},
    {"type": "add_time", "value": "сегодня"},
    {"type": "add_place", "value": "дома"},
    {"type": "replace_object", "lemma": "Иван", "grammar": {"case": "acc", "gender": "masc", "animacy": "anim"}},
    {"type": "replace_subject", "lemma": "мы", "grammar": {"case": "nom", "number": "plur"}}
  ]
}""")
