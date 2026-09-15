"""里程碑三级渐进提示：先自己想 10 分钟再看，每次只看一级。

用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('t1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "t1": [
        "L2.3 的 run() 你写过一遍——这里是复刻加一个接缝：执行工具时若 execute 参数给了，"
        "用它（await executor(name, arguments_json)），否则用 self._default_execute。",
        "形状：tools = to_openai_tools(self._registry)；for turn in range(1, self._max_turns + 1)："
        'message = (await self._client.complete(messages, tools))["choices"][0]["message"]；'
        'messages.append(message)；if not message.get("tool_calls"): return AgentResult(...)。',
        '回喂一行：messages.append({"role": "tool", "tool_call_id": tool_call["id"], '
        '"content": await executor(tool_call["function"]["name"], tool_call["function"]["arguments"])})。'
        '循环外 raise AgentBudgetExceeded(f"{self._max_turns} 轮预算耗尽（历史 {len(messages)} 条消息仍未收敛）")。',
    ],
    "t2": [
        "L2.4 的 ask_structured 你也写过——三个纪律回顾：先入史再校验；一个 except 接两种伤；"
        "耗尽抛 StructuredOutputError 带次数。",
        '形状：text = response["choices"][0]["message"]["content"] or ""；'
        'messages.append({"role": "assistant", "content": text})；'
        "try: return PreapprovalDecision.model_validate(extract_json(text)), messages；"
        "except (ValueError, ValidationError) as exc: messages.append(feedback_message(exc))。",
        '循环外：raise StructuredOutputError(f"{attempts} 次尝试仍未得到合法决策 JSON'
        '（历史 {len(messages)} 条消息）")。给定函数（extract_json / feedback_message）直接用，别重写。',
    ],
    "t3": [
        "L2.5 的两个函数原样搬：payload 是三层 dict 透传；执行是「拆封 → call_tool → 取文本 → "
        "is_error 分流」。content 是联合类型列表，取文本要收窄（getattr 或 isinstance）。",
        'payload 形状：{"type": "function", "function": {"name": tool.name, '
        '"description": tool.description or "", "parameters": tool.input_schema}}。'
        "执行形状：arguments = json.loads(arguments_json)；result = await session.call_tool(name, "
        'arguments=arguments)；texts = [text for part in result.content if (text := getattr(part, "text", None))]。',
        "收尾：if result.is_error: raise McpToolError(f\"{name}: {'; '.join(texts)}\")；"
        'return "\\n".join(texts)；坏 JSON：except json.JSONDecodeError as exc: '
        'raise McpToolError(f"invalid_arguments: {exc.msg}") from exc。',
    ],
}


def hint(task: str, level: int = 1) -> str:
    """返回某任务第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[task]
    return levels[min(level, len(levels)) - 1]
