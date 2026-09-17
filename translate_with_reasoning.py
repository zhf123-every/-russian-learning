"""
translate_with_reasoning() - 基于LLM Chain-of-Thought的上下文翻译函数
废弃逐词查词典逻辑，强制上下文推理
"""
import json
import os

# 加载口语化搭配示例库
EXAMPLES_PATH = os.path.join(os.path.dirname(__file__), 'colloquial_examples.json')
with open(EXAMPLES_PATH, 'r', encoding='utf-8') as f:
    COLLOQUIAL_EXAMPLES = json.load(f)['examples']


def build_cot_prompt(current_russian, full_sentence_russian, full_sentence_chinese,
                      previous_step_russian="", previous_step_chinese="", context_semantics=""):
    """
    构建Chain-of-Thought提示词
    """
    # 选取相关的Few-Shot示例（简单策略：取前5个通用示例）
    few_shot_examples = COLLOQUIAL_EXAMPLES[:5]

    examples_text = ""
    for i, ex in enumerate(few_shot_examples, 1):
        examples_text += f"""
示例{i}:
  当前步骤：{ex['russian']}
  完整句：{ex['full_sentence']} → {ex['full_chinese']}
  翻译：{ex['chinese']}
  说明：{ex['note']}
"""

    prompt = f"""你是俄语-中文翻译专家，专门处理语言学习中的"渐进构建"中间步骤翻译。

## 核心原则
1. 必须结合完整句上下文翻译，不能逐词直译
2. 语气词（бы、же、ли等）不是跳过，而是理解其语法功能（бы对应中文的"会/ would"）
3. 固定表达整体翻译（Не за что → 不客气，Как дела → 你好吗）
4. 存在句中есть不单独翻译（У меня есть → 我有）
5. 疑问句中疑问词放句末（Что вы любите → 您喜欢什么）
6. вы根据完整句上下文选择"您"或"你们"
7. 中文翻译必须自然流畅，符合中文表达习惯

## Few-Shot 示例
{examples_text}

## 翻译任务
请按以下步骤推理：

Step 1: 识别当前步骤的核心语义和口语化表达
  - 这是一个完整短语还是不完整片段？
  - 是否包含虚拟语气、疑问句、否定句等特殊结构？
  - 哪些词是固定搭配，需要整体理解？

Step 2: 结合完整句上下文，选择最贴切的中文表达
  - 完整句中文是什么？
  - 当前步骤对应完整句中的哪部分语义？
  - 语气词（如бы）在完整句中对应什么中文表达？
  - вы应该译为"您"还是"你们"？

Step 3: 生成自然流畅的翻译
  - 避免逐词直译
  - 符合中文表达习惯
  - 不添加语法标注（如"第三格"、"现在时"等）

## 输入信息
当前步骤：{current_russian}
完整句：{full_sentence_russian} → {full_sentence_chinese}
前一步骤：{previous_step_russian} → {previous_step_chinese}
语境语义：{context_semantics if context_semantics else "（暂无）"}

## 输出格式
请严格输出以下JSON格式（不要输出其他内容）：
{{
  "reasoning": "你的推理过程（Step 1-3的简要总结）",
  "chinese": "翻译结果"
}}
"""
    return prompt


def translate_with_reasoning(current_russian, full_sentence_russian, full_sentence_chinese,
                              previous_step_russian="", previous_step_chinese="",
                              context_semantics="", llm_client=None):
    """
    基于LLM Chain-of-Thought的上下文翻译函数

    Args:
        current_russian: 当前步骤俄语
        full_sentence_russian: 完整句俄语
        full_sentence_chinese: 完整句中文
        previous_step_russian: 前一步骤俄语（可选）
        previous_step_chinese: 前一步骤中文（可选）
        context_semantics: 语境语义（由RuModernBERT分析，可选）
        llm_client: LLM客户端（如果为None，则返回prompt供外部调用）

    Returns:
        dict: {"reasoning": "...", "chinese": "..."}
    """
    prompt = build_cot_prompt(
        current_russian, full_sentence_russian, full_sentence_chinese,
        previous_step_russian, previous_step_chinese, context_semantics
    )

    if llm_client is None:
        # 没有LLM客户端，返回prompt供外部调用
        return {"prompt": prompt, "chinese": None}

    # 调用LLM（具体实现取决于使用的API）
    # response = llm_client.chat(prompt)
    # result = parse_json(response)
    # return result

    raise NotImplementedError("请传入llm_client或在外部调用prompt")


if __name__ == '__main__':
    # 测试prompt生成
    prompt = build_cot_prompt(
        current_russian="Что бы вы",
        full_sentence_russian="Что бы вы посоветовали?",
        full_sentence_chinese="您会建议什么？",
        previous_step_russian="Что бы",
        previous_step_chinese="什么"
    )
    print(prompt)
