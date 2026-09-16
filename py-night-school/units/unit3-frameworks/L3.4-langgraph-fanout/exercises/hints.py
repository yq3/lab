"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "两件事：状态字段怎么声明「合并语义」——本课的 reducer 不是标准库 operator.add，"
        "而是你自己写的 (旧 dict, 新 dict) -> 合并 dict 函数（Annotated 第二参放函数对象）；"
        "条件边函数的返回值从「节点名字符串」升级成「Send 对象的列表」。",
        "形状级：reducer 函数体怎么用两个 dict 造一个新 dict（dict 的双星拆包）？"
        "Annotated[dict[str, Advice], 你的函数] 里第二参是函数本身还是函数调用？"
        "Send 的两个参数分别填什么——目标节点名是哪个字符串？arg 里 worker 需要的最小状态是什么"
        "（review_worker 读的是哪个键）？",
        "完整装配：def merge_advice(old: dict, new: dict) -> dict: return {**old, **new}；"
        "状态里写 results: Annotated[dict[str, Advice], merge_advice]；"
        'fan_out 里 return [Send("review", {"claim_id": claim_id}) for claim_id in state["claim_ids"]]；'
        "装配补 builder.add_conditional_edges('dispatch', fan_out)、builder.add_edge('review', 'reduce')、"
        "builder.add_edge('reduce', END)——END 加进现有那行 langgraph.graph import，"
        "Annotated 加进 typing import。",
    ],
    "ex2": [
        "对照讲义 Step1：装配就一个函数调用，三个参数——model（骨架已给，注意不要自己再 bind_tools）、"
        "tools（两个裸函数的列表）、prompt（SYSTEM_PROMPT 字符串）。出口对照 L3.2 的 finalize："
        "ainvoke 的结果里取最后一条消息的 content，model_validate_json 解析。",
        "形状级：create_react_agent(?, tools=[?, ?], prompt=?) 的问号各填什么？"
        "ainvoke 返回的 dict 里消息史在哪个键？最后一条消息对象身上文本属性叫什么？"
        "Advice 的类方法里哪个负责从 JSON 文本解析（L2.4 学过）？",
        "完整做法：return create_react_agent(model, tools=[mock_tools.check_budget, mock_tools.verify_invoice], "
        "prompt=SYSTEM_PROMPT)；run_review 里 agent = build_agent(model_for_url(ep.url))，"
        'result = await agent.ainvoke({"messages": [{"role": "user", '
        '"content": user_brief(claim_id)}]}, config={"recursion_limit": RECURSION_LIMIT})，'
        '然后 return Advice.model_validate_json(result["messages"][-1].content.strip())。'
        "顶部补 from langgraph.prebuilt import create_react_agent。",
    ],
    "ex3": [
        "全部答案都在两个文件里（按 docstring 的行号路标翻）：chat_agent_executor.py 的装配段 861–1002 "
        "看 add_node 的第一个参数与 response_format 分支；should_continue（831–859）看 v2 默认返回什么；"
        "689 行附近找那句英文哨兵；tool_node.py 的 _validate_tool_call（1268 行起）看未注册工具名时返回什么。",
        "形状级逐条：①② 装配段开头的两个 add_node；③ should_continue 的 else 分支里 version 判断后 "
        "return 的东西的类型；④ 849 行起的列表推导每个元素对应什么（一轮 2 个 tool_call 就是 2 个）；"
        "⑤ 899–910 行 add_node 的名字；⑥ 689 行 content= 的完整字符串（一字不差地抄）；"
        "⑦ _validate_tool_call 返回 ToolMessage 还是抛异常。",
        "答案核对（背不住就翻源码，别背提示）：agent / tools / send_list / 2 / generate_structured_response / "
        "'Sorry, need more steps to process this request.' / feed_back。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
