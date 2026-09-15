"""里程碑三级渐进提示：先自己想 10 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('t1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "t1": [
        "L2.3 的 run() 你写过一遍——这里是复刻加一个接缝：执行工具时若 execute 参数给了就用它，"
        "否则用 self._default_execute。双终止纪律原样：软终止在循环内 return，硬终止在循环外 raise。",
        "形状级：契约列表从注册表经哪个函数生成？分支读消息的哪个键？执行器拿到的是名字和什么"
        "原始形态的参数（想想字符串套娃）？回喂消息的三个键是什么？预算耗尽的异常信息必须带哪两个数字？",
        '回喂核心：messages.append({"role": "tool", "tool_call_id": tool_call["id"], '
        '"content": await executor(tool_call["function"]["name"], '
        'tool_call["function"]["arguments"])})；循环外 raise AgentBudgetExceeded('
        'f"{self._max_turns} 轮预算耗尽（历史 {len(messages)} 条消息仍未收敛）")。',
    ],
    "t2": [
        "L2.4 的 ask_structured 你也写过——三个纪律回顾：先入史再校验；一个 except 接两种伤；"
        "耗尽抛 StructuredOutputError 带次数。给定函数（extract_json / feedback_message）直接用。",
        "形状级：content 从响应的哪条路径取（可能为 None，用什么兜底）？决策校验用哪个类方法？"
        "失败后追加的两条消息各是什么角色、内容来源是什么？",
        '循环外：raise StructuredOutputError(f"{attempts} 次尝试仍未得到合法决策 JSON'
        '（历史 {len(messages)} 条消息）")。',
    ],
    "t3": [
        "L2.5 的两个函数原样搬：payload 是三层 dict 透传；执行是「拆封 → call_tool → 取文本 → "
        "is_error 分流」。content 是联合类型列表，取文本要收窄（getattr 或 isinstance）。",
        "形状级：payload 的 parameters 从 Tool 的哪个属性来？执行时 arguments 要什么类型、"
        "从 JSON 字符串怎么变过来？坏 JSON 走哪个出口？多段文本怎么合成？",
        "收尾：if result.is_error: raise McpToolError(f\"{name}: {'; '.join(texts)}\")；"
        'return "\\n".join(texts)；坏 JSON：except json.JSONDecodeError as exc: '
        'raise McpToolError(f"invalid_arguments: {exc.msg}") from exc。',
    ],
}


def hint(task: str, level: int = 1) -> str:
    """返回某任务第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[task]
    return levels[min(level, len(levels)) - 1]
