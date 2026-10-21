# -*- coding: utf-8 -*-
"""开发辅助：实测生产 /api/ai 对「带标题的课程简介」生成是否针对标题（不提交业务代码）"""
import json, urllib.request

URL = "https://russian-learning-jetq.onrender.com/api/ai"


def probe(title, textbook):
    messages = [
        {"role": "system", "content": "你是俄语课程运营编辑，擅长为俄语学习课程撰写专业、有吸引力、分三段的介绍文案，全部使用简体中文。"},
        {"role": "user", "content": f"请根据以下课程信息，撰写三段式课程简介：\n课程标题：{title}\n教材：{textbook}\n\n要求：1. 第一段以【课程介绍】开头；2. 第二段以【学习目标】开头；3. 第三段以【适合谁学】开头；直接输出三段文字，不要额外解释。"},
    ]
    req = urllib.request.Request(URL, data=json.dumps({"messages": messages}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("ok"), (data.get("content") or "")[:500]
    except Exception as e:
        return False, f"ERROR: {e}"


if __name__ == "__main__":
    print("=== 场景1：标题=俄罗斯旅游实用口语课，教材=走遍俄罗斯 ===")
    ok, c = probe("俄罗斯旅游实用口语课", "走遍俄罗斯")
    print("ok:", ok)
    print(c)

    print()
    print("=== 场景2：标题=考研俄语202语法强化课，教材=（空） ===")
    ok, c = probe("考研俄语202语法强化课", "")
    print("ok:", ok)
    print(c)
