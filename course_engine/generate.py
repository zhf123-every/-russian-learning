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
