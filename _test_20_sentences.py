import sys, os
os.environ["ZHIPU_API_KEY"] = "88ce5361a34f45d497cc578e5aa7c47f.DUJXejjfdhj4tjEg"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 把course_engine目录也加到sys.path里，方便导入cache等模块
_course_engine_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "course_engine")
if _course_engine_dir not in sys.path:
    sys.path.insert(0, _course_engine_dir)

from course_engine.generate import generate_chapter_course_async

# 《走遍俄罗斯》第一课 20 句
test_sentences = [
    {"ru": "Это студент.", "zh": "这是大学生。"},
    {"ru": "Это не мама.", "zh": "这不是妈妈。"},
    {"ru": "Кто это?", "zh": "这是谁？"},
    {"ru": "Я знаю Ивана.", "zh": "我认识伊万。"},
    {"ru": "Он знает маму.", "zh": "他认识妈妈。"},
    {"ru": "Анна знает Антона.", "zh": "安娜认识安东。"},
    {"ru": "Я не знаю Ивана.", "zh": "我不认识伊万。"},
    {"ru": "Это мой дом.", "zh": "这是我的房子。"},
    {"ru": "Твой друг здесь.", "zh": "你的朋友在这里。"},
    {"ru": "Я вижу красивую девушку.", "zh": "我看见一个漂亮的姑娘。"},
    {"ru": "Он читает интересную книгу.", "zh": "他在读一本有趣的书。"},
    {"ru": "Я читаю книгу.", "zh": "我读书。"},
    {"ru": "Мы живём в Москве.", "zh": "我们住在莫斯科。"},
    {"ru": "Она была дома вчера.", "zh": "她昨天在家。"},
    {"ru": "Я хочу есть.", "zh": "我想吃。"},
    {"ru": "Мне нужно делать это.", "zh": "我需要做这个。"},
    {"ru": "Сегодня это не мама.", "zh": "今天这不是妈妈。"},
    {"ru": "Это не папа.", "zh": "这不是爸爸。"},
    {"ru": "Она знает лампу.", "zh": "她知道这个台灯。"},
    {"ru": "Мы знаем дом.", "zh": "我们知道这个房子。"},
]

print("开始 20 句完整测试...", flush=True)
result = generate_chapter_course_async(test_sentences)
print(f"Success: {result['success']}", flush=True)
print(f"Error: {result.get('error')}", flush=True)
print(f"Total layers: {result.get('total_layers')}", flush=True)
print(f"Total groups: {result.get('total_groups')}", flush=True)
print(f"Total steps: {result.get('total_steps')}", flush=True)

if result['success']:
    steps = result['steps']
    all_full = [s for s in steps if s.get('type') == '完整句']
    print(f"\n所有完整句（共 {len(all_full)} 组）：", flush=True)
    for s in all_full:
        print(f"  {s.get('gid')}: {s['ru']}", flush=True)
