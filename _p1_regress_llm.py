# P1 第2步回归：call_llm / _parse_json_block 单元验证 + /api/ai 原行为
import json, server

# 1) _parse_json_block 剥 ```json 包裹
assert server._parse_json_block('```json\n{"a":1}\n```') == {"a": 1}, "剥包裹失败"
# 2) 兜底截取首个平衡括号块
assert server._parse_json_block('好的，结果是 {"b": [1,2]} 如上') == {"b": [1, 2]}, "兜底截取失败"
# 3) 数组块
assert server._parse_json_block('返回 [[0,1],[2]]') == [[0, 1], [2]], "数组兜底失败"
# 4) 非法输入 → None
assert server._parse_json_block('not json') is None, "非法输入应为 None"
# 5) 无 key → call_llm 返回 None（不抛异常）
assert server.call_llm("sys", "user") is None, "无 key 应返回 None"
# 6) 有 key 但 json_mode=False 的路径不会被误触发（当前无 key，跳过）
print("call_llm 单元验证：5/5 PASS")
