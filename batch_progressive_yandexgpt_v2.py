"""
批量渐进构建 + YandexGPT上下文翻译 (v2 - 改进版)
改进：每批3条，强化prompt减少上下文混淆
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, r'C:\Users\张宏飞\russian-learning')

# YandexGPT API配置（从环境变量读取）
API_KEY = os.environ.get("YANDEX_API_KEY", "")
FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "b1gkl13f5cb9ucr0fopf")
MODEL = "yandexgpt-lite"
API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# 加载口语化示例库
with open(r'C:\Users\张宏飞\russian-learning\colloquial_examples.json', 'r', encoding='utf-8') as f:
    COLLOQUIAL_EXAMPLES = json.load(f)['examples']


def build_cot_prompt(batch_items):
    """构建批量翻译的CoT prompt - 改进版，强调独立翻译"""
    few_shot_text = ""
    for i, ex in enumerate(COLLOQUIAL_EXAMPLES[:3], 1):
        few_shot_text += f"""
示例{i}:
  当前步骤：{ex['russian']}
  完整句：{ex['full_sentence']} → {ex['full_chinese']}
  翻译：{ex['chinese']}
"""

    items_text = ""
    for idx, item in enumerate(batch_items, 1):
        items_text += f"""
========== 任务{idx} ==========
【当前步骤】{item['russian']}
【完整句上下文】{item['full_russian']} → {item['full_chinese']}
【要求】只翻译"当前步骤"这几个词，不要翻译完整句！
"""

    prompt = f"""你是俄语-中文翻译专家。

## 最重要规则（必须严格遵守）
1. 只翻译"当前步骤"的俄语，绝对不要翻译完整句！
2. 每个任务完全独立，不要参考其他任务的内容！
3. 单词级步骤（1个词）只翻译这个词，不要扩展成短语或句子！
4. 结合完整句上下文选择正确的词义，但翻译长度要与当前步骤匹配！

## 翻译原则
- 语气词бы对应中文的"会/ would"
- 固定表达整体翻译（Не за что → 不客气）
- 存在句中есть不单独翻译（У меня есть → 我有）
- вы根据上下文选择"您"或"你们"
- 中文翻译必须自然，不添加语法标注

## 示例
{few_shot_text}

## 翻译任务（共{len(batch_items)}个，每个独立翻译）
{items_text}

## 输出格式
严格输出JSON，不要输出其他内容：
{{"translations":[{{"id":1,"chinese":"翻译1"}},{{"id":2,"chinese":"翻译2"}}]}}
"""
    return prompt


def call_yandexgpt(prompt, max_retries=3):
    """调用YandexGPT API"""
    data = json.dumps({
        'modelUri': f'gpt://{FOLDER_ID}/{MODEL}',
        'completionOptions': {
            'stream': False,
            'temperature': 0.2,
            'maxTokens': 1500
        },
        'messages': [
            {'role': 'user', 'text': prompt}
        ]
    }).encode('utf-8')

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(API_URL, data=data, headers={
                'Authorization': f'Api-Key {API_KEY}',
                'Content-Type': 'application/json'
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                text = result['result']['alternatives'][0]['message']['text']
                return text
        except urllib.error.HTTPError as e:
            print(f"  ⚠️ HTTP错误 {e.code} (尝试{attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ 调用失败 (尝试{attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
    
    return None


def translate_batch(batch_items, max_retries=3):
    """批量翻译一批中间步骤"""
    prompt = build_cot_prompt(batch_items)
    
    for attempt in range(max_retries):
        content = call_yandexgpt(prompt)
        
        if content is None:
            continue
        
        # 清理
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        try:
            result = json.loads(content)
            translations = result.get('translations', [])
            
            if len(translations) != len(batch_items):
                print(f"  ⚠️ 数量不匹配: 期望{len(batch_items)}, 实际{len(translations)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
            
            return translations
            
        except json.JSONDecodeError as e:
            print(f"  ⚠️ JSON解析失败 (尝试{attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return [{"id": i+1, "chinese": item['russian']} for i, item in enumerate(batch_items)]


def generate_progressive_steps(full_russian, full_chinese):
    """生成渐进构建步骤结构"""
    clean_russian = full_russian.strip().rstrip('.,!?')
    words_list = clean_russian.split()
    n = len(words_list)
    
    has_punct = full_russian.strip()[-1] in '.,!?'
    punct = full_russian.strip()[-1] if has_punct else ''
    
    steps = []
    step_order = 1
    
    if n <= 3:
        steps.append({
            "step": 1,
            "russian": full_russian,
            "chinese": full_chinese,
            "is_complete": True
        })
        return steps
    
    # 步骤1-2：引入前两个词
    for i in range(min(2, n)):
        steps.append({
            "step": step_order,
            "russian": words_list[i],
            "chinese": None,
            "is_complete": False,
            "is_word": True
        })
        step_order += 1
    
    # 步骤3：组合前两个词
    if n >= 2:
        steps.append({
            "step": step_order,
            "russian": " ".join(words_list[:2]),
            "chinese": None,
            "is_complete": False,
            "is_combine": True
        })
        step_order += 1
    
    # 步骤4+：逐个引入剩余单词，并组合
    for i in range(2, n):
        steps.append({
            "step": step_order,
            "russian": words_list[i],
            "chinese": None,
            "is_complete": False,
            "is_word": True
        })
        step_order += 1
        
        current = " ".join(words_list[:i+1])
        is_last = (i == n - 1)
        
        if is_last and punct:
            current = current + punct
        
        steps.append({
            "step": step_order,
            "russian": current,
            "chinese": full_chinese if is_last else None,
            "is_complete": is_last,
            "is_combine": True
        })
        step_order += 1
    
    return steps


def main():
    print("=" * 70)
    print("渐进构建批量翻译 v2 - YandexGPT Lite (每批3条)")
    print("=" * 70)
    
    # 加载数据
    print("\n[1/5] 加载数据...")
    with open(r'C:\Users\张宏飞\russian-learning\pipeline_split_results.json', 'r', encoding='utf-8') as f:
        pipeline_data = json.load(f)
    
    all_sentences = pipeline_data['results']
    print(f"  共 {len(all_sentences)} 句")
    
    # 生成渐进构建步骤
    print("\n[2/5] 生成渐进构建步骤结构...")
    all_sequences = []
    for seq in all_sentences:
        steps = generate_progressive_steps(seq['full_russian'], seq['full_chinese'])
        all_sequences.append({
            "id": seq['id'],
            "full_russian": seq['full_russian'],
            "full_chinese": seq['full_chinese'],
            "steps": steps
        })
    
    total_steps = sum(len(s['steps']) for s in all_sequences)
    print(f"  共生成 {total_steps} 个步骤")
    
    # 提取需要LLM翻译的中间步骤
    print("\n[3/5] 提取需要LLM翻译的中间步骤...")
    items_to_translate = []
    for seq in all_sequences:
        prev_russian = ""
        prev_chinese = ""
        for step in seq['steps']:
            if step['chinese'] is None and not step.get('is_complete', False):
                items_to_translate.append({
                    'seq_id': seq['id'],
                    'step_num': step['step'],
                    'russian': step['russian'],
                    'full_russian': seq['full_russian'],
                    'full_chinese': seq['full_chinese'],
                    'prev_russian': prev_russian,
                    'prev_chinese': prev_chinese
                })
            prev_russian = step['russian']
            prev_chinese = step['chinese'] or ""
    
    print(f"  共 {len(items_to_translate)} 个中间步骤需要翻译")
    
    # 分批调用LLM翻译
    BATCH_SIZE = 3  # 改进：每批3条
    total_batches = (len(items_to_translate) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n[4/5] 分批调用YandexGPT翻译 (每批{BATCH_SIZE}条，共{total_batches}批)...")
    
    translation_map = {}
    success_count = 0
    fail_count = 0
    start_time = time.time()
    
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(items_to_translate))
        batch = items_to_translate[start:end]
        
        elapsed = time.time() - start_time
        avg_time = elapsed / (batch_idx + 1) if batch_idx > 0 else 0
        remaining = avg_time * (total_batches - batch_idx - 1)
        
        print(f"  批次 {batch_idx+1}/{total_batches} ({start+1}-{end})...", end=" ")
        
        translations = translate_batch(batch)
        
        for i, item in enumerate(batch):
            if i < len(translations):
                chinese = translations[i].get('chinese', item['russian'])
                translation_map[(item['seq_id'], item['step_num'])] = chinese
                success_count += 1
            else:
                translation_map[(item['seq_id'], item['step_num'])] = item['russian']
                fail_count += 1
        
        print(f"✅ (成功:{success_count}, 剩余约{remaining/60:.0f}分钟)")
        
        # 每50批保存一次中间结果
        if (batch_idx + 1) % 50 == 0:
            intermediate_file = r'C:\Users\张宏飞\russian-learning\progressive_999_intermediate_v2.json'
            with open(intermediate_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'translation_map': {f"{k[0]}|{k[1]}": v for k, v in translation_map.items()},
                    'success_count': success_count,
                    'fail_count': fail_count
                }, f, ensure_ascii=False, indent=2)
            print(f"    💾 已保存中间结果")
        
        time.sleep(0.2)
    
    # 将翻译结果写回步骤
    print("\n[5/5] 将翻译结果写回步骤...")
    for seq in all_sequences:
        for step in seq['steps']:
            key = (seq['id'], step['step'])
            if key in translation_map:
                step['chinese'] = translation_map[key]
    
    # 输出最终结果
    output_file = r'C:\Users\张宏飞\russian-learning\progressive_999sentences_result_v2.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_sequences': len(all_sequences),
            'total_steps': total_steps,
            'translated_steps': success_count,
            'failed_steps': fail_count,
            'model': 'yandexgpt-lite',
            'version': 'v2 (batch_size=3)',
            'sequences': all_sequences
        }, f, ensure_ascii=False, indent=2)
    
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print("✅ 批量翻译完成 v2！")
    print(f"{'='*70}")
    print(f"  总句子数: {len(all_sequences)}")
    print(f"  总步骤数: {total_steps}")
    print(f"  翻译成功: {success_count}")
    print(f"  翻译失败: {fail_count}")
    print(f"  总耗时: {total_time/60:.1f} 分钟")
    print(f"  输出文件: {output_file}")
    
    # 展示前5句
    print(f"\n{'='*70}")
    print("前5句结果预览:")
    print(f"{'='*70}")
    for seq in all_sequences[:5]:
        print(f"\n【{seq['full_russian']}】→ {seq['full_chinese']}")
        for step in seq['steps']:
            print(f"  step{step['step']:2d}: {step['russian']:35s} → {step['chinese']}")


if __name__ == '__main__':
    main()
