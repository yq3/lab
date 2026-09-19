"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "工具函数体就是普通函数体：读数据文件、循环找单号、两种返回（找到 / error JSON）。"
        "装饰器与 server.run 都已备好，别动。",
        "形状级三问：JSON 顶层取哪个键拿到单据列表？找到时返回的 JSON 有哪四个业务键？"
        "找不到时 error JSON 的键名与值格式是什么（对照 L2.2 的 error_result 惯例）？",
        '收尾（循环外）：return json.dumps({"error": f"claim_not_found: {claim_id}"}, '
        "ensure_ascii=False)。返回值必须是 str——content 是回喂给模型的文本。",
    ],
    "ex2": [
        "payload 的三层嵌套与 L2.2 的 openai_function 完全同构，只是 parameters 的来源换了——"
        "从 MCP 的 Tool 对象身上取。",
        "形状级：Tool 的哪个属性装着 JSON Schema（注意是 snake_case 的哪个词）？"
        "description 可能为 None，归一成什么才不炸下游的字符串操作？最外层的 type 固定是什么？",
        '完整版：return [{"type": "function", "function": {"name": tool.name, '
        '"description": tool.description or "", "parameters": tool.input_schema}} '
        "for tool in tools]。",
    ],
    "ex3": [
        "三步：拆封（arguments 是 JSON 字符串，坏 JSON 也要变成 McpToolError）→ 协议调用"
        "（call_tool 要 dict）→ 取文本（content 是联合类型列表，直接 .text 过不了 pyright）。",
        "形状级：取文本的两种收窄写法是什么（讲义 §2.3 提过）？is_error 为真时走哪个出口、"
        "错误信息从哪里拼？多段文本怎么合成单字符串？",
        "收尾：if result.is_error: raise McpToolError(f\"{name}: {'; '.join(texts)}\")；"
        'return "\\n".join(texts)；坏 JSON：except json.JSONDecodeError as exc: '
        'raise McpToolError(f"invalid_arguments: {exc.msg}") from exc。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
