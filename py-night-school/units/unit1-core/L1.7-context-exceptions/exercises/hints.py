"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "四个子句各就各位：try 放「可能出事的活」，except 放「收某个异常」，"
        "else 放「没出事才干的活」，finally 放「无论如何都要干的收尾」。",
        "形状：trace.append('try') 与 raise 放 try；trace.append('except') 放 except InvalidAmountError；"
        "trace.append('else') 放 else；trace.append('finally') 放 finally；"
        "返回值 'OK' 放 else 里、'FAILED' 放 except 里（return 在哪条路就回哪条路）。",
        "参考骨架：try: trace.append('try')；if amount <= 0: raise InvalidAmountError(...)；"
        "except InvalidAmountError: trace.append('except')；return 'FAILED'；"
        "else: trace.append('else')；return 'OK'；finally: trace.append('finally')——"
        "注意 return 不影响 finally 执行。",
    ],
    "ex2": [
        "基类 __init__ 三行：super().__init__(message) 让 str(e) 正常；self.context = context 存证据；"
        "parse_amount 里 try int(raw)，except ValueError as exc 后 raise ... from exc。",
        "ExpenseError.__init__ 的形状：super().__init__(message)；self.context = context。"
        'raise 的形状：raise AmountParseError(f"金额字段不是整数: {raw!r}", context="parse_amount") from exc。',
        "参考骨架：except ValueError as exc: raise AmountParseError("
        'f"金额字段不是整数: {raw!r}", context="parse_amount") from exc——'
        "别忘了 return int(raw) 在 try 里（成功路径直接返回）。",
    ],
    "ex3": [
        "函数体内要改模块级变量，先声明 global DAILY_MEAL_LIMIT_CENTS；"
        "四步顺序：保存旧值 -> 改新值 -> yield -> finally 恢复。",
        "形状：global DAILY_MEAL_LIMIT_CENTS；old = DAILY_MEAL_LIMIT_CENTS；"
        "DAILY_MEAL_LIMIT_CENTS = limit_cents；try: yield；finally: DAILY_MEAL_LIMIT_CENTS = old。",
        "参考骨架：global DAILY_MEAL_LIMIT_CENTS；old = DAILY_MEAL_LIMIT_CENTS；"
        "DAILY_MEAL_LIMIT_CENTS = limit_cents；try: yield；finally: DAILY_MEAL_LIMIT_CENTS = old——"
        "yield 裸写（不带值），with ... as 后面就不用接东西。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
