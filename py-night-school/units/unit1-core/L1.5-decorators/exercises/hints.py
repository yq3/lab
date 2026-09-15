"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "两层函数：timing 收 func、返回 wrapper；wrapper 里做「计时起点 -> 调 func -> 计时终点 -> 记录 -> 返回结果」。",
        "形状：TIMINGS.append(perf_counter() - start)；@wraps(func) 贴在 def wrapper 上一行；最后 return wrapper。",
        "参考实现骨架：start = perf_counter()；result = func()；TIMINGS.append(perf_counter() - start)；"
        "return result——外面包上 @wraps(func) 的 def wrapper，timing 最后 return wrapper。",
    ],
    "ex2": [
        "三层函数从外到内：retry(max_attempts, retry_on) 返回 decorator；decorator(func) 返回 wrapper；wrapper 里试。",
        "wrapper 的形状：循环或 while 计数尝试；try 里 return func()；except retry_on 里判断「这是不是最后一次」——"
        "是就裸 raise，不是就继续循环。@wraps(func) 贴在 wrapper 上。",
        "骨架：attempt 计数；try: return func()；except retry_on: attempt 达到 max_attempts 时裸 raise，"
        "否则继续；注意成功路径直接 return，不进重试逻辑。",
    ],
    "ex3": [
        "register 是「注册型」装饰器：不包装、不改行为——往 TOOLS 里放一条，然后 return func 本身。",
        "两个工具的形状：@register 下一行 def check_item_limit(items_cents: list[int]) -> str，"
        "体内 any(c > 5000 ...) 命中返回 REJECT，否则 PASS（total 版用 sum 比较 500000）。",
        "run_tool 的形状：if name not in TOOLS: raise KeyError(name)；return TOOLS[name](items_cents)。"
        "register 本体两行：TOOLS[func.__name__] = func；return func。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
