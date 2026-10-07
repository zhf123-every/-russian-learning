# -*- coding: utf-8 -*-
"""
新课程引擎统一入口：大模型规划 + pymorphy3 变形 + 规则组装
"""
import json
import urllib.request
import sys
import os

# 把项目根目录加到 path，方便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slot_engine import generate_table
from llm_plan_prompt import PLAN_SYSTEM_PROMPT

# 智谱 API 配置
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-4-plus"


def call_glm(system_prompt, user_prompt):
    """调用智谱 GLM-4-plus，返回 JSON dict"""
    if not ZHIPU_API_KEY:
        raise Exception("ZHIPU_API_KEY 未配置")

    payload = {
        "model": ZHIPU_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ZHIPU_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + ZHIPU_API_KEY,
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)


def check_completeness(original_ru, rows):
    """成分完整性检查：原句的词，生成的核心句里必须都有"""
    core_row = None
    for r in rows:
        if r.get("groupId") == "G_01" and r.get("cardType") == "完整句":
            core_row = r
            break
    if not core_row:
        return False, "没有找到核心完整句"

    generated = core_row["ru"].lower().replace(".", "")
    original_words = original_ru.lower().replace(".", "").split()

    missing = []
    for w in original_words:
        found = False
        for gen_word in generated.split():
            if w[:3] in gen_word or gen_word[:3] in w:
                found = True
                break
        if not found:
            missing.append(w)

    if not missing:
        return True, ""
    else:
        return False, f"丢了成分: {missing}"


def generate_course_steps(ru_sentence: str, zh_translation: str) -> dict:
    """
    新课程引擎入口：输入俄语句子+中文翻译，输出课程步骤

    返回:
        {
            "success": True/False,
            "steps": [...],
            "error": None 或 "错误信息",
            "engine": "new"
        }
    """
    try:
        # 1. 大模型构造 plan JSON
        user_prompt = f"请为这个俄语句子生成教学 plan：\n{ru_sentence}"
        plan = call_glm(PLAN_SYSTEM_PROMPT, user_prompt)

        # 2. 引擎执行，生成表格
        rows = generate_table(plan)

        # 3. 成分完整性检查
        ok, msg = check_completeness(ru_sentence, rows)
        if not ok:
            return {
                "success": False,
                "steps": [],
                "error": f"成分完整性检查失败: {msg}",
                "engine": "new"
            }

        # 4. 转换成 server.py 需要的格式
        steps = []
        for i, r in enumerate(rows):
            steps.append({
                "seq": i + 1,
                "type": r.get("cardType", "积木"),
                "ru": r.get("ru", ""),
                "zh": r.get("zh", zh_translation if r.get("cardType") == "完整句" else ""),
                "tag": r.get("tag", ""),
                "gid": r.get("groupId", "G_01"),
            })

        return {
            "success": True,
            "steps": steps,
            "error": None,
            "engine": "new"
        }

    except Exception as e:
        return {
            "success": False,
            "steps": [],
            "error": f"新引擎异常: {str(e)}",
            "engine": "new"
        }


def generate_chapter_course(sentences: list) -> dict:
    """
    章节级课程生成入口：输入一课的所有句子，输出完整课程数据

    输入:
        [
            {"ru": "Я знаю Ивана.", "zh": "我认识伊万。"},
            {"ru": "Это студент.", "zh": "这是大学生。"},
            ...
        ]

    返回:
        {
            "success": True,
            "steps": [
                {"seq": 1, "type": "积木", "ru": "Я", "zh": "我", "tag": "主语", "gid": "G_001"},
                ...
            ],
            "total_groups": 69,
            "total_steps": 293,
            "engine": "new"
        }
    """
    import time
    t0 = time.time()

    try:
        # 暂时用预先生成的测试数据（后面替换成自动流水线）
        # TODO: 接入 classifier + planner + orchestrator 自动生成
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_path = os.path.join(root_dir, "chapter_01_full_v3.json")
        t1 = time.time()

        if not os.path.exists(data_path):
            return {
                "success": False,
                "steps": [],
                "error": f"预生成数据文件不存在: {data_path}",
                "engine": "new"
            }
        t2 = time.time()

        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        t3 = time.time()

        steps = data.get("steps", [])

        # 按 seq 排序
        steps.sort(key=lambda x: x.get("seq", 0))
        t4 = time.time()

        print(f"[timing] read_file: {t1-t0:.2f}s, check_exists: {t2-t1:.2f}s, load_json: {t3-t2:.2f}s, sort: {t4-t3:.2f}s, total: {t4-t0:.2f}s")

        return {
            "success": True,
            "steps": steps,
            "total_groups": data.get("total_groups", 0),
            "total_steps": len(steps),
            "engine": "new"
        }

    except Exception as e:
        return {
            "success": False,
            "steps": [],
            "error": f"章节生成异常: {str(e)}",
            "engine": "new"
        }


def generate_chapter_course_async(sentences: list, on_progress=None) -> dict:
    """
    异步章节级课程生成入口：带进度回调，真实流水线

    输入:
        sentences: [{"ru": "...", "zh": "..."}, ...]
        on_progress: 回调函数，参数是 classified_count（已分类句数）

    返回:
        {
            "success": True,
            "steps": [...],
            "total_layers": 7,
            "total_groups": 48,
            "total_steps": 302,
            "engine": "new"
        }
    """
    import time
    t0 = time.time()

    try:
        # 导入真实流水线模块
        from classifier import classify_sentences
        from plan_chapter import plan_chapter
        from plan_layer import plan_layer
        from orchestrator import execute_layer_plan

        total = len(sentences)

        # 步骤1：分类（带缓存）
        print(f"[pipeline] 开始分类 {total} 句...", flush=True)

        from .cache import get_cached_classification, save_classification_to_cache

        classified = []
        cache_hit = 0
        cache_miss = 0

        for i, s in enumerate(sentences):
            ru = s["ru"]
            zh = s["zh"]
            print(f"分类中 {i+1}/{total}: {ru[:30]}...", flush=True)

            # 先查缓存
            cached = get_cached_classification(ru)
            if cached:
                classified.append(cached)
                cache_hit += 1
                print(f"  ✅ 缓存命中", flush=True)
                continue

            # 缓存未命中，调大模型
            cache_miss += 1
            try:
                from classifier import classify_one
                from teaching_points_loader import TEACHING_POINTS
                points = TEACHING_POINTS["points"]

                r = classify_one(ru, zh)
                primary = r.get("primary_tag", "")
                level = points.get(primary, {}).get("level", 1)
                result = {
                    "ru": ru,
                    "zh": zh,
                    "tags": r.get("tags", []),
                    "primary_tag": primary,
                    "level": level,
                    "reason": r.get("reason", ""),
                    "structure": r.get("structure", {}),
                }
                classified.append(result)
                # 写入缓存
                save_classification_to_cache(ru, result)
            except Exception as e:
                print(f"  ❌ 失败: {e}", flush=True)
                classified.append({
                    "ru": ru,
                    "zh": zh,
                    "classification_failed": True,
                    "error": str(e),
                })

        t1 = time.time()
        print(f"[pipeline] 分类完成: {t1-t0:.1f}s，命中缓存 {cache_hit} 句，调大模型 {cache_miss} 句", flush=True)

        # 检查分类失败
        failed = [c for c in classified if c.get("classification_failed")]
        if failed:
            return {
                "success": False,
                "steps": [],
                "error": f"{len(failed)} 句无法分类",
                "engine": "new"
            }

        # 步骤2：分层
        chapter_plan = plan_chapter(classified)
        t2 = time.time()
        print(f"[pipeline] 分层完成: {t2-t1:.1f}s, {len(chapter_plan['layers'])} 层", flush=True)

        # 步骤3：层内编排
        for layer in chapter_plan["layers"]:
            layer["plan"] = plan_layer(layer)
        t3 = time.time()
        print(f"[pipeline] 层内编排完成: {t3-t2:.1f}s", flush=True)

        # 步骤4：执行所有层
        all_steps = []
        global_gid = 1
        for layer in chapter_plan["layers"]:
            layer_steps, layer_groups, layer_step_count = execute_layer_plan(layer["plan"])
            for step in layer_steps:
                step["layer_id"] = layer.get("layer_id", 0)
                all_steps.append(step)
        t4 = time.time()
        print(f"[pipeline] 执行完成: {t4-t3:.1f}s, {len(all_steps)} 步", flush=True)

        # ===== 全局去重：跳过完整句重复的 G =====
        # 按 gid 分组
        from collections import defaultdict
        groups = defaultdict(list)
        for step in all_steps:
            groups[step["gid"]].append(step)

        seen_sentences = set()
        deduped_steps = []
        skipped_groups = 0

        for gid, gsteps in groups.items():
            # 找完整句
            full = next((s for s in gsteps if s.get("type") == "完整句"), None)
            if not full:
                deduped_steps.extend(gsteps)
                continue

            # 标准化完整句
            normalized = full["ru"].strip().lower().rstrip('.').rstrip('?').strip()
            if normalized in seen_sentences:
                skipped_groups += 1
                continue  # 跳过整个 G

            seen_sentences.add(normalized)
            deduped_steps.extend(gsteps)

        all_steps = deduped_steps
        print(f"[pipeline] 全局去重: 跳过 {skipped_groups} 个重复 G，剩余 {len(all_steps)} 步", flush=True)

        # 重新编号 seq 和 gid
        current_gid = 1
        current_seq = 1
        last_full_sentence = None
        for step in all_steps:
            step["seq"] = current_seq
            current_seq += 1
            if step.get("type") == "完整句":
                step["gid"] = f"G_{current_gid:03d}"
                current_gid += 1
            else:
                # 积木属于上一个完整句的 gid
                step["gid"] = f"G_{current_gid:03d}"

        total_groups = len(set(s["gid"] for s in all_steps))

        t5 = time.time()
        print(f"[pipeline] 总耗时: {t5-t0:.1f}s", flush=True)

        return {
            "success": True,
            "steps": all_steps,
            "total_layers": len(chapter_plan["layers"]),
            "total_groups": total_groups,
            "total_steps": len(all_steps),
            "engine": "new"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "steps": [],
            "error": f"异步章节生成异常: {str(e)}",
            "engine": "new"
        }
