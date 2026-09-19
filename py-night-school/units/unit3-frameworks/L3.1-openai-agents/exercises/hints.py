"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "两件事：复核专员就是一个普通的 Agent（少工具、多 output_type 与 handoff_description）；"
        "handoff() 把它包装成审查员的一个工具。台词侧想想：剧本怎么「替模型说出」转交——"
        "第 2 轮的 tool_calls 列表里放什么名字？",
        "形状级五问：specialist 的构造参数比单 agent 版多了哪两个、少了哪个？handoffs 里放 "
        "handoff(specialist) 还是 specialist 本身？script_for 返回的三元组里哪个字段告诉你这单要不要"
        "转交（decision 等于哪个字符串）？转交轮 script_tool_calls 的 name 用哪个常量、arguments 是"
        "什么？run_review 三元组的三项分别读 result 的哪个属性？",
        "build_agents：specialist = Agent(name='HumanSpecialist', handoff_description=…, "
        "instructions=…, model=model, output_type=Advice)；reviewer = 单 agent 版构造 + "
        "handoffs=[handoff(specialist)]。script_rounds：first_turn, final_text, expected = "
        "review_rules.script_for(claim_id)；ep.script_tool_calls(first_turn)；if expected.decision "
        "== 'ESCALATE': ep.script_tool_calls([{'id': 'call_handoff', 'name': HANDOFF_TOOL_NAME, "
        "'arguments': {}}])；最后 ep.script_text(final_text)。run_review：清 CALL_LOG、起端点、"
        "_build_model 同构的模型、build_agents、script_rounds、result = await Runner.run(reviewer, "
        "_user_message(claim_id))，return (result.final_output, result.last_agent.name, len(ep.requests))。",
    ],
    "ex2": [
        "护栏函数就是普通函数：抽单号 → 查表 → 包一个 GuardrailFunctionOutput。装饰器 "
        "@input_guardrail 负责把它变成框架认识的 InputGuardrail；tripwire_triggered 决定拦不拦。",
        "形状级四问：装饰器加在函数定义的哪一行、name 参数给了什么？input 形参可能是 list，"
        "怎么先归一成 str？known 的集合表达式怎么写（claims_table 的哪个字段）？"
        "output_info 的两个键各放什么、tripwire_triggered 等于 known 的什么运算？",
        "护栏体：text = input if isinstance(input, str) else str(input)；claim_id = "
        "_extract_claim_id(text)；known = claim_id is not None and claim_id in {c['id'] for c in "
        "mock_tools.claims_table()}；return GuardrailFunctionOutput(output_info={'claim_id': "
        "claim_id, 'known': known}, tripwire_triggered=not known)。run_guarded：把 run_unguarded "
        "整段复制，Agent 构造里加一行 input_guardrails=[claim_id_guardrail]，其余不动。",
    ],
    "ex3": [
        "与讲义 Step 1 唯一的结构差异是 Runner.run 的 max_turns 参数；记账用 try/finally——"
        "finally 不吞异常，只是路过时留一笔。",
        "形状级三问：ep.requests 的长度在哪个时机读才准确（return 之前？异常之后？为什么 "
        "finally 里读两边都覆盖）？Runner.run 的哪个关键字参数传预算？MaxTurnsExceeded 需要 "
        "import 吗——你不捕获它的话还需要吗？",
        "流程骨架：mock_tools.CALL_LOG.clear() → with MockLLMEndpoint() as ep: script_obsession(ep)"
        " → model = OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url="
        "ep.url, api_key=ep.api_key)) → agent = Agent(name='Reviewer', instructions='查预算。', "
        "model=model, tools=[function_tool(mock_tools.check_budget)]) → try: await Runner.run("
        "agent, USER_MESSAGE, max_turns=max_turns); return len(ep.requests) → finally: "
        "REQUESTS.append(len(ep.requests))。不需要 import MaxTurnsExceeded（不捕获就不必点名）。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
