"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "对照讲义 Step1 的输出找规律：rounds=1 时辩论段 2 次调用、rounds=2 时 4 次——"
        "路由器的终止计数是 2*self.max_debate_rounds，这个 self.max_debate_rounds 从哪来？"
        "现在它在构造器里写死成 1，而 build(config, model) 手里明明有一个 config。",
        "形状级：DebateRouter 的构造器要收什么（config 对象？还是轮次整数？两种形状验收都认）？"
        "build 里构造 DebateRouter 那一行，实参怎么从 config 里取？"
        "注意 should_continue_debate 的函数体一行都不用动。",
        "完整做法：__init__ 加参数——self.max_debate_rounds = max_debate_rounds（或直接收 "
        "RoundsConfig 取 .max_debate_rounds）；build 里改 router = "
        "DebateRouter(config.max_debate_rounds)（或 DebateRouter(config)）。逻辑不变，"
        "轮次的来源从「写死」换成「配置流入」。",
    ],
    "ex2": [
        "想想「检查-放行-计数-委托」四件事的顺序：如果先计数再检查会怎样（被拒的调用算不算数）？"
        "如果先委托再检查会怎样（超限的那次已经打到模型了）？limit 是 None 时检查分支怎么走？",
        "形状级：一次调用进来——先判「预算还有没有」（limit 为 None 意味着永远有）；不够就抛 "
        "BudgetExceeded（异常信息里带上限与已用次数，运维才看得懂）；够就把消息交给"
        "被包装的模型、已用次数加一、结果原样返回。",
        "完整做法：函数体四行——`if self._limit is not None and self._used >= self._limit: "
        "raise BudgetExceeded(...)`；`result = await self._model.ainvoke(messages)`；"
        "`self._used += 1`；`return result`。对照讲义 code/budget.py#BudgetedModel.ainvoke——"
        "同一个模式，那里拆成了 _try_acquire/_record 两个方法。",
    ],
    "ex3": [
        "对版产品的取向先想清楚：百分比为什么必须丢（把 '85%' 读成 85 分会怎样）？"
        "带小数的 '¥1,234.50' 对一个「整数分」字段意味着什么（1234.50 元还是 1234.50 分）？"
        "把这两类与占位串同等对待；整数形态的串（去逗号、去币符、去空白后）可以放心 int()。",
        "形状级：ex3-a——非字符串直接放行；字符串先 strip：命中占位串集合或以 % 结尾 → None；"
        "再去掉逗号与前导币符：空了 → None；剩下的能安全转成整数吗（包一层 try/except）？"
        "转不成 → None。ex3-b——strip 后走 pydantic 的 JSON 入口；except 住校验异常，返回"
        "verdict 为哨兵档的 AppealRuling，rationale 写明「不可解析」与原因。",
        "完整做法：ex3-a 返回 `None if (text.lower() in _NULLISH_CENTS or text.endswith('%')) "
        "else int(cleaned) 若可解析 else None`（int 包 try/except ValueError）；"
        "ex3-b `try: return AppealRuling.model_validate_json(text.strip()) except "
        "ValidationError as exc: return AppealRuling(verdict='REVIEW', "
        "rationale=f'裁决输出不可解析，转人工复核：{str(exc)[:120]}')`。对照讲义 "
        "code/schemas.py#parse_ruling——一字不差的同构。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
