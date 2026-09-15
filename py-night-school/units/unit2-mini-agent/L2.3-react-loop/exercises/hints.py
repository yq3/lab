"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "循环每轮只做三件事：请求模型、消息入史、按「有无 tool_calls」分支。入史永远在分支之前——"
        "想想为什么（审计不留缺口）。",
        "形状级三问：分支条件读消息的哪个键？回喂消息的三个键是什么、id 从 tool_call 的哪里来？"
        "未知工具与已知工具的 content 分别放什么（哪种情况要 error JSON）？"
        "字符串套娃在第几步拆？",
        '回喂一行：messages.append({"role": "tool", "tool_call_id": tool_call["id"], '
        '"content": result})，其中未知工具 result = _error_json(f"unknown_tool: {name}")，'
        "已知工具 result = str(REGISTRY[name](**json.loads(arguments)))。循环无需显式上限（ex2 补上）。",
    ],
    "ex2": [
        "骨架与 ex1 同构，只多两件事：for-range 把预算圈进循环结构；循环自然走完（模型一直要工具）"
        "就落到循环外的 raise。",
        "形状级：软终止与硬终止分别写在循环的哪个位置？异常信息里必须带哪个数字（运维第一眼要知道"
        "什么）？执念模型哪个出口永远走不到——这说明了什么？",
        "执念模型永不回答，循环内的 return 分支实际走不到——这正是考点：软终止（模型的概率性选择）"
        "靠不住，硬终止（你的 for 上限）才是护栏。回喂处调用：_preapprove(**json.loads(arguments))；"
        '循环外：raise BudgetExceeded(f"{max_turns} 轮预算耗尽...")。',
    ],
    "ex3": [
        "先复制列表（别原地改）；外层 while 管预算收敛，内层 while 管排头孤儿；裁剪位置永远是 "
        "index 1——index 0 是谁，不能动。",
        "形状级：外层的两个收敛条件是什么（预算、剩余条数下限）？内层的判断条件读排头消息的哪个键？"
        "内层为什么必须在每次外层裁剪之后立刻跑一遍？",
        "完整版：trimmed = list(messages)；while estimate_chars(trimmed) > max_chars and "
        'len(trimmed) > 2: trimmed.pop(1)；while len(trimmed) > 1 and trimmed[1]["role"] == '
        '"tool": trimmed.pop(1)；return trimmed——第二段 while 包在第一段循环体内。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
