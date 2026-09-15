"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "工具函数体就是普通函数体：读文件（json.loads + Path.read_text）、循环找单号、"
        "两种返回（找到 / error JSON）。装饰器和 server.run 都已备好，别动。",
        '形状：claims = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))["expense_claims"]；'
        'for claim in claims: if claim["id"] == claim_id: return json.dumps({"id": claim["id"], '
        '"submitter": ..., "purpose": ..., "items_cents": ...}, ensure_ascii=False)。',
        '收尾（循环外）：return json.dumps({"error": f"claim_not_found: {claim_id}"}, '
        "ensure_ascii=False)。返回值必须是 str——content 是回喂给模型的文本。",
    ],
    "ex2": [
        "列表推导一行一个工具；三层 dict 套娃与 L2.2 的 openai_function 完全同构，"
        "只是 parameters 的来源换成 tool.input_schema。",
        '形状：{"type": "function", "function": {"name": tool.name, "description": '
        'tool.description or "", "parameters": tool.input_schema}}。',
        "完整版：return [ ... for tool in tools ]，三个键原样透传——description 的 "
        'or "" 是唯一的小心思（None 会炸下游的 str 操作）。',
    ],
    "ex3": [
        "三步：拆封（json.loads，坏 JSON 抛 McpToolError）→ 调用（await session.call_tool"
        "(name, arguments=arguments)）→ 取文本（遍历 result.content，取有 .text 的 part）。",
        "形状：try: arguments = json.loads(arguments_json)；except json.JSONDecodeError as exc: "
        'raise McpToolError(f"invalid_arguments: {exc.msg}") from exc；'
        'texts = [text for part in result.content if (text := getattr(part, "text", None))]——'
        "content 是联合类型列表，直接 part.text 会被 pyright 拦（ImageContent 没有 text）。",
        "收尾：if result.is_error: raise McpToolError(f\"{name}: {'; '.join(texts)}\")；"
        'return "\\n".join(texts)。content 是列表（可能多段文本），拼接成单字符串对齐 run_tool 的口径。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
