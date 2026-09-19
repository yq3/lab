"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/提问级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "工具本体是纯函数——工具箱里最像 mock_tools.check_budget 的一题：输入关键词、查表、"
        "返回 dict。错误（未命中）也是返回值不是异常，对照 check_budget 的 unknown_dept 分支"
        "它连日志都不记。注册处回看讲义 Step 1：tools 列表里放的是函数本身。",
        "形状级三问：两边都 lower 之后用哪个运算符判断「键是关键词的子串」还是「关键词含键」"
        "——题目说「按关键词子串匹配表的键」，谁包含谁？命中时 POLICY_LOG 记什么字符串？"
        "build_agent 里 create_deep_agent 需要哪四个参数（model / tools / system_prompt / "
        "response_format），tools 列表里有几个元素、都是什么？",
        "lookup_policy：for key, row in POLICY_TABLE.items(): 若 purpose_keyword.lower() 里含 "
        "key（key 本身全中文时 lower 不改变它），命中分支 append 后 return dict(row)；循环走完"
        "未命中 return {'keyword': purpose_keyword, 'error': 'policy_not_found'}。"
        "build_agent：create_deep_agent(model=model, tools=[mock_tools.check_budget, lookup_policy],"
        " system_prompt=SYSTEM, response_format=Advice)。",
    ],
    "ex2": [
        "SubAgent 是声明式 spec：四个键各司其职——name 是 task 工具找人用的 id，description "
        "是主代理决定何时转交的唯一依据（它被拼进 task 工具描述），system_prompt 是子代理自己的"
        "人设，tools 圈定它的能力边界。讲义 Step 3 的 INVOICE_SPECIALIST 是同构样板。",
        "形状级三问：name 必须严格等于哪个字符串（given 剧本按它转交）？description 写成什么"
        "主代理才会把「查预算」这件事转过来——它读得到 description 里的哪些词？tools 列表给几个"
        "元素、是 mock_tools 里的哪个函数（想想子代理该不该拿到 verify_invoice）？",
        "BUDGET_SPECIALIST 四键：name 用给定名字；description 写「预算查询专员：查询部门预算"
        "余额与剩余，需要 check_budget 结果时转交」；system_prompt 写「你是预算查询专员，只负责"
        "调用 check_budget 工具查部门预算，并简短报告余额」；tools=[mock_tools.check_budget]。",
    ],
    "ex3": [
        "两处 TODO 是一条数据的两端：_write_arguments 是「发」（write_file 轮的参数——file_path "
        "加 content），extract_dossier 是「收」（state → files → 路径 → content）。content 的"
        "三个事实全部来自纯读取函数——再想一遍为什么不能用 check_budget（提示：CALL_LOG 取证）。",
        "形状级三问：返回的 dict 有哪两个键（回看讲义 WriteFileSchema 的入参名）？content 的"
        "三要素分别来自 claim_view 的哪个字段、review_rules.decide 的哪个返回字段、budget_row "
        "两数之差？extract_dossier 沿 result 的哪个键找到 dict、用哪个路径索引、再取 FileData "
        "的哪个字段？",
        "_write_arguments：用 claim_view / budget_row / invoice_row 纯读取 + review_rules.decide "
        "拿决策；返回 {'file_path': f'/review/{claim_id}.md', 'content': '# 审查底稿 ' + claim_id "
        "+ '\\n- 结论：' + expected.reason + '\\n- 剩余预算：' + str(budget['budget_cents'] - "
        "budget['spent_cents']) + ' 分\\n'}。extract_dossier：extract_dossier 只收到 result，"
        "拿不到单号——但本轮只落一个文件：path = next(p for p in result['files'] if "
        "p.startswith('/review/'))，return result['files'][path]['content']。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
