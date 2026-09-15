"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "build_messages 就是把两句话各装进一个 role 固定的 dict；extract_reply 沿着 "
        "choices → 下标 0 → message / finish_reason 一层层下钻。注意 content 可能是 None——"
        "模型选工具时不写正文，这不是异常。",
        "extract_reply 的形状：先从 response 里取出第一个 choice；content 在 choice 的 message "
        "键下、finish_reason 在 choice 自己身上。None 归一化用一个条件表达式即可——"
        "想想「content 不是 None 才用它，否则给空串」怎么说。",
        'extract_reply 核心：c = response["choices"][0]；content = c["message"]["content"]；'
        'return (content if content is not None else "", c["finish_reason"])。',
    ],
    "ex2": [
        "iter_sse_data 的全部秘密是「缓冲 + 切割」：字节先追加进缓冲区，凑齐一个以空行结尾的完整事件"
        "才切出来处理；UTF-8 解码必须在整个 data 行凑齐之后做（半截中文字符会炸）。"
        "collect_content 里 [DONE] 不是 JSON，先判等再解析。",
        "伪代码形状：循环{找空行分隔符——找不到就等下一块；找到就切出完整块；从块里挑出 data: 开头的行，"
        "剥掉前缀和一个可选空格；多行 data 按规范拼接；整体解码后产出}。"
        "collect_content 逐个解析事件：delta 文本的键路径是什么？取值为什么要 .get？",
        'iter_sse_data 骨架：def gen(): buffer = b""; for chunk in chunks: buffer += chunk; '
        'while True: i = buffer.find(b"\\n\\n"); if i == -1: break; block, buffer = buffer[:i], '
        'buffer[i+2:]; lines = [l[5:] for l in block.split(b"\\n") if l.startswith(b"data:")]; '
        'lines = [l[1:] if l.startswith(b" ") else l for l in lines]; if lines: yield '
        'b"\\n".join(lines).decode("utf-8")——生成器或返回列表均可，测试只要求可迭代。',
    ],
    "ex3": [
        "preapprove 按 L0.1 的优先级三条判断加一条兜底；handle_tool_calls 是「遍历 → 拆封 → 调用 → "
        "组 dict」四步。本函数只认 preapprove——别的名字直接跳过（错误回喂是 L2.2 注册表的纪律）。",
        "shape 级三问：拆封用标准库哪个函数把 JSON 字符串变 dict？调用时怎么把 dict 摊开成关键字实参"
        "（L1.4 的星号语法）？回喂消息的三个键分别是什么、id 从哪来？",
        '完整版：for tool_call in assistant_message["tool_calls"]: name = '
        'tool_call["function"]["name"]；if name != "preapprove": continue（不认识的跳过）；'
        'result = preapprove(**json.loads(tool_call["function"]["arguments"]))；'
        'results.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
