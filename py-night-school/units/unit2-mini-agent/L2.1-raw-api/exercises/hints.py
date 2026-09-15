"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "build_messages 就是两个字面量 dict 的列表；extract_reply 沿着 choices → [0] → "
        "message/finish_reason 一层层下钻。",
        'extract_reply 的形状：choice = response["choices"][0]；content = '
        'choice["message"]["content"]；None 要归一成空串：content if content is not None else ""。',
        "extract_reply 一行版："
        'return (c["message"]["content"] or "", c["finish_reason"])，其中 c = '
        'response["choices"][0]——注意 or 只在这里安全，因为 content 要么 None 要么非空串。',
    ],
    "ex2": [
        'iter_sse_data 的全部秘密是「缓冲 + 切割」：buffer += chunk 后反复找 b"\\n\\n"，'
        "找到就切出一个完整块，找不到就留着等下一块。UTF-8 解码必须在整个 data 行凑齐之后做。",
        "iter_sse_data 的形状：循环内 block, buffer = buffer[:i], buffer[i+2:]；"
        '对 block.split(b"\\n") 里 startswith(b"data:") 的行切掉前缀（再剥一个可选空格）'
        '后 yield。collect_content 里先判 data == "[DONE]" 再 json.loads，'
        'content 用 event["choices"][0]["delta"].get("content") 取（可能是 None 或缺失）。',
        'iter_sse_data 骨架：def gen(): buffer = b""; for chunk in chunks: buffer += chunk; '
        'while True: i = buffer.find(b"\\n\\n"); if i == -1: break; block, buffer = buffer[:i], '
        'buffer[i+2:]; lines = [l[5:] for l in block.split(b"\\n") if l.startswith(b"data:")]; '
        'lines = [l[1:] if l.startswith(b" ") else l for l in lines]; if lines: yield '
        'b"\\n".join(lines).decode("utf-8")——注意把函数写成生成器（内部用 yield）或返回生成器均可，'
        "测试只要求可迭代。",
    ],
    "ex3": [
        "preapprove 照 L0.1 的优先级三条 if 加一条兜底；handle_tool_calls 就是「遍历 → json.loads → "
        "调用 → 组 dict」四步。",
        'handle_tool_calls 的形状：for tool_call in assistant_message["tool_calls"]: '
        'name = tool_call["function"]["name"]; arguments = json.loads(tool_call["function"]["arguments"])；'
        'if name != "preapprove": continue；content = preapprove(**arguments)；'
        'results.append({"role": "tool", "tool_call_id": tool_call["id"], "content": content})。',
        "完整版就是把第 2 级串起来：results: list[dict] = [] 收集，最后 return results。"
        '忘记 json.loads 的话 preapprove(**"{...}") 会直接 TypeError——那正是 §5 坑位在提醒你。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
