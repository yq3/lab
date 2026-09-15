"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

用法（在本目录下）：
    python3 -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "脏数据最先判：any(c <= 0 for c in items_cents) 命中就立刻返回——三条规则的顺序就是返回优先级。",
        "单笔超限用 any(c > DAILY_MEAL_LIMIT_CENTS ...)，合计超限用 sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS；"
        "都未命中才返回 PASS。",
    ],
    "ex2": [
        '参数化表每一行是一个 (items, expected) 二元组，items 是 list[int]，例如 ([1200, 3500], "PASS")。',
        "边界用例最值得写：恰好等于上限（[5000]、合计恰好 500000）应当 PASS；"
        "合计超限可以用 [4000] * 126 这类乘法构造。",
    ],
    "ex3": [
        "F401 / F841 的修法是「删掉没用的东西」；E501 的修法是拆行——相邻字符串字面量在括号内会自动拼接。",
        "修完跑 uv run ruff check exercises/ex3_ruff_fix.py，直到 0 error；再跑 uv run ruff format exercises/ 收尾。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
