"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/提问式，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "这题没有框架代码要写——就是写一个普通的 Python 工具函数，只是 docstring 的读者是模型。"
        "对照 mock_tools.check_budget：一句话用途写什么？Args 段怎么排？查无数据的返回为什么是提示串"
        "而不是异常？",
        "形状级三问：docstring 首句让模型在什么场景想起这个工具（「查……」开头）？Args 段里 "
        "policy_key 的说明要包含哪些可用键（模型没有别的地方能看到键名）？查无键的返回串里要带上"
        "哪两个信息（错误码 + 出错的键）？",
        "docstring：查报销政策：按政策键返回一段政策文案。\\n\\n    Args:\\n        policy_key: "
        "政策键，如 item_limit / invoice_rule / budget_rule\\n    ；函数体：return POLICIES.get("
        'policy_key) or f"policy_not_found: {policy_key}"——.get + or 一行搞定命中/查无两分支。',
    ],
    "ex2": [
        "对照讲义 Step 1 的 demo.py 与 Step 3 的 demo_state.py：demo.py 的四步（剧本、装配、跑、parse）"
        "这里一步不少，唯一的改造在第②步——create_session 多传了什么参数？",
        "形状级三问：ep 的两条 script_* 分别吃什么（given 的 first_turn_for / expected_advice 各产出"
        "什么）？create_session 的哪个参数收初始状态？最终文本怎么变成 Advice（哪个类方法）？"
        "别忘了入口清 CALL_LOG——验收断言读它。",
        "核心三行：session = await runner.session_service.create_session(app_name=APP_NAME, "
        'user_id=USER_ID, state={"item_limit_cents": item_limit_cents})；events = [e async for e in '
        'ask(runner, session.id, f"请审查报销单 {claim_id}")]；return Advice.model_validate_json('
        "final_text(events))——runner 由 build_runner(build_agent(ep)) 装配，剧本喂法同 demo.py。",
    ],
    "ex3": [
        "对照讲义 Step 4 的 claim_id_guard：本题策略更严——讲义版只拦「格式像单号但不合规」，"
        "本题要求任何 CLM- 记号必须合规。回调的返回值语义是关键：None 与 truthy 各代表什么？",
        "形状级三问：user 文本从 llm_request 的哪里取（contents 的哪个元素、哪个 part 的哪个字段）？"
        "用 re.search 找什么模式的记号、找到后用什么 fullmatch 校验？短路时返回的 LlmResponse 里，"
        "Content 的 role 和 Part 的 text 各放什么？",
        '骨架注释已列出策略三分支，接线方式：match = re.search(r"CLM[-\\w]*", user_text) 取记号；'
        "if claim and not CLAIM_ID_RE.fullmatch(claim): return LlmResponse(content=types.Content("
        'role="model", parts=[types.Part(text=BLOCKED_REPLY)]))；末尾 return None——'
        "构造形状可再对照 demo_callback.py 的闸。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
