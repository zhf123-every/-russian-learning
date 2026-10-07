# -*- coding: utf-8 -*-
"""
阶段3：分层规划器
输入：分类好的句子列表 → 输出：分层计划
"""
import json
import os

# 加载教学点字典
with open(os.path.join(os.path.dirname(__file__), "teaching_points.json"), "r", encoding="utf-8") as f:
    TEACHING_POINTS = json.load(f)


def _select_seed_sentence(layer_sentences):
    """选种子句：结构最完整的那句"""
    # 规则：tags数量最多的 > 句子最长的 > 第一句
    def score(s):
        tags_count = len(s.get("tags", []))
        ru_len = len(s.get("ru", ""))
        return (tags_count, ru_len)

    sorted_sents = sorted(layer_sentences, key=score, reverse=True)
    return sorted_sents[0]["ru"]


def plan_chapter(classified_sentences):
    """
    分层规划器
    输入: [{"ru": "...", "zh": "...", "tags": [...], "primary_tag": "...", "level": N}, ...]
    输出: {
        "chapter_id": "chapter_01",
        "total_layers": 8,
        "layers": [
            {
                "layer_id": 1,
                "theme": "名词第四格",
                "primary_tag": "T05",
                "sentences": [...],
                "seed_sentence": "Я знаю Ивана",
                "reuse_sentences": [...]
            },
            ...
        ]
    }
    """
    points = TEACHING_POINTS["points"]

    # 步骤1：按 primary_tag 分组
    groups = {}
    for s in classified_sentences:
        tag = s.get("primary_tag", "")
        if not tag:
            continue
        if tag not in groups:
            groups[tag] = []
        groups[tag].append(s)

    # 步骤2：按教学顺序排序（level低的在前，同level按教学顺序）
    # 教学顺序：判断句 → 主谓宾 → 物主代词 → 形容词 → 复合谓语 → 扩展成分
    TEACHING_ORDER = {
        "T07": 1,   # 判断句
        "T08": 2,   # 判断句否定
        "T05": 3,   # 名词第四格
        "T06": 4,   # 动词否定
        "T09": 5,   # 物主代词
        "T10": 6,   # 形容词一致
        "T11": 7,   # 形容词第四格
        "T19": 8,   # 动词+不定式
        "T18": 9,   # 无人称句
        "T14": 10,  # 地点状语
        "T15": 11,  # 过去时
        "T23": 12,  # 疑问句
        "T25": 13,  # 代词第四格
        "T27": 14,  # 未来时
    }

    def sort_key(tag):
        level = points.get(tag, {}).get("level", 99)
        order = TEACHING_ORDER.get(tag, 999)  # 没在表里的，排最后
        return (level, order, tag)

    sorted_tags = sorted(groups.keys(), key=sort_key)

    # 步骤3：合并单句层（和相邻层合并）
    layers = []
    i = 0
    while i < len(sorted_tags):
        tag = sorted_tags[i]
        sents = groups[tag]

        # 如果这层只有1句，尝试和下一层合并
        if len(sents) == 1 and i + 1 < len(sorted_tags):
            next_tag = sorted_tags[i + 1]
            next_sents = groups[next_tag]
            # 合并到下一层
            merged = sents + next_sents
            layers.append({
                "primary_tag": f"{tag}+{next_tag}",
                "sentences": merged,
            })
            i += 2
        else:
            layers.append({
                "primary_tag": tag,
                "sentences": sents,
            })
            i += 1

    # 步骤4：给每一层编号、选种子句、生成主题
    result_layers = []
    for idx, layer in enumerate(layers):
        primary_tag = layer["primary_tag"]
        sents = layer["sentences"]
        seed = _select_seed_sentence(sents)
        reuse = [s["ru"] for s in sents if s["ru"] != seed]

        # 生成主题名
        if "+" in primary_tag:
            t1, t2 = primary_tag.split("+")
            name1 = points.get(t1, {}).get("name", t1)
            name2 = points.get(t2, {}).get("name", t2)
            theme = f"{name1} + {name2}"
        else:
            theme = points.get(primary_tag, {}).get("name", primary_tag)

        result_layers.append({
            "layer_id": idx + 1,
            "theme": theme,
            "primary_tag": primary_tag,
            "sentences": sents,
            "seed_sentence": seed,
            "reuse_sentences": reuse,
        })

    return {
        "chapter_id": "chapter_01",
        "total_layers": len(result_layers),
        "layers": result_layers,
    }


# ========== 测试 ==========
if __name__ == "__main__":
    # 测试样本
    TEST = [
        {"ru": "Это студент.", "zh": "这是大学生。", "tags": ["T07"], "primary_tag": "T07", "level": 1},
        {"ru": "Она студентка.", "zh": "她是大学生。", "tags": ["T07"], "primary_tag": "T07", "level": 1},
        {"ru": "Мы друзья.", "zh": "我们是朋友。", "tags": ["T07"], "primary_tag": "T07", "level": 1},
        {"ru": "Это не мама.", "zh": "这不是妈妈。", "tags": ["T08"], "primary_tag": "T08", "level": 1},
        {"ru": "Я знаю Ивана.", "zh": "我认识伊万。", "tags": ["T01", "T05"], "primary_tag": "T05", "level": 1},
        {"ru": "Я вижу красивую девушку.", "zh": "我看见一个漂亮的姑娘。", "tags": ["T11"], "primary_tag": "T11", "level": 1},
    ]

    result = plan_chapter(TEST)
    print(json.dumps(result, ensure_ascii=False, indent=2))
