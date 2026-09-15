"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "循环骨架：messages 列表从 system+user 起步；每轮 message = (await model.complete(messages))"
        '["choices"][0]["message"]；先 append(message) 再分支。',
        '分支形状：tool_calls = message.get("tool_calls")；空则 return (message.get("content") or "", messages)；'
        "非空则 for tool_call in tool_calls：name 查 REGISTRY（.get，None 则 _error_json），"
        "否则 json.loads(arguments) 后 func(**args) 得结果，回喂三件套 dict。",
        '回喂一行：messages.append({"role": "tool", "tool_call_id": tool_call["id"], '
        '"content": result})，其中未知工具 result = _error_json(f"unknown_tool: {name}")，'
        "已知工具 result = str(REGISTRY[name](**json.loads(arguments)))。循环无需显式上限（ex2 补上）。",
    ],
    "ex2": [
        "骨架与 ex1 同构，只多两件事：for turn in range(1, max_turns + 1) 圈住循环；"
        "循环自然走完（模型一直要工具）就落到循环外的 raise。",
        "形状：for turn in range(1, max_turns + 1): ...message 有 tool_calls 就执行回喂、"
        'continue 下一轮；没有就 return messages。循环外：raise BudgetExceeded(f"{max_turns} 轮预算耗尽...")。',
        "执念模型永不回答，所以循环内的 return 分支实际走不到——这正是本题的考点："
        "软终止（模型的概率性选择）靠不住，硬终止（你的 for 上限）才是护栏。"
        "回喂处 func 调用：REGISTRY 固定 preapprove：_preapprove(**json.loads(arguments))。",
    ],
    "ex3": [
        "先 trimmed = list(messages)（别原地改）；循环条件：estimate_chars(trimmed) > max_chars "
        "且 len(trimmed) > 2（system + 至少一条，全裁光没意义）。",
        "形状：while estimate_chars(trimmed) > max_chars and len(trimmed) > 2: trimmed.pop(1)；"
        '随后 while len(trimmed) > 1 and trimmed[1]["role"] == "tool": trimmed.pop(1)；return trimmed。'
        "第二个 while 要包在第一个循环体内——每裁一条都要重新检查排头。",
        "完整版就是把第 2 级的两段 while 嵌套：外层收敛预算、内层处理孤儿。"
        "「排头不是 tool」检查放在每次 pop(1) 之后立即做，不是循环结束后补做。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
