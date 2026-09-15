"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "两条规则的形状照抄 check_invalid：any(...)/sum(...) 命中就 return 原因串，否则 return None；"
        "主函数就是「for 遍历 RULES，拿到第一个非 None 就返回它」。",
        "check_item_limit: any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents)；"
        "check_total_limit: sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS；"
        "preapprove: for rule in RULES: verdict = rule(items_cents)。",
        "preapprove 收尾三行：for 循环内 if verdict is not None: return verdict；"
        '循环走完 return "PASS"。别忘了「非 None」要用 is not 判断（verdict 可能是 "REJECT:..." 字符串，'
        "但「没命中」的标志是 None，is not None 是判 None 的标准姿势）。",
    ],
    "ex2": [
        "make_greeter：外层定义内层函数（读 greeting），外层 return 内层函数名——不带括号，"
        "返回的是函数本身不是调用结果；make_counter：state 放外层，内层推进它。",
        'make_greeter 骨架：def greet(name): return f"{greeting}，{name}！"；return greet；'
        "make_counter 骨架：state = start；def next_value(): ...；return next_value。",
        "make_counter 内层三行：nonlocal state；state += step；return state。"
        "注意 return next_value 也不带括号；两个工厂函数各自调用一次就各有一套 state，"
        "独立性测试（两个计数器不串台）过不了说明 state 放到全局去了。",
    ],
    "ex3": [
        "ex3a 按 docstring 拼 f-string，四条测试就是四种组合；ex3b 只需一行 return，把 ** 用在「调用侧」摊开 options。",
        'ex3a 形状：return f"[{submitter}] {total_cents} {unit}" if bracket else '
        'f"{submitter}: {total_cents} {unit}"；'
        "ex3b 形状：return format_claim_line(submitter, total_cents, **options)。",
        "ex3b 完整一行：return format_claim_line(submitter, total_cents, **options)。"
        "不需要手动校验 options 里的键——摊开到调用处，多余的键自然 TypeError（测试专查这个行为）。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
