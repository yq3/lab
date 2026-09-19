"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "用一个推进中的下标 i：只要还没到末尾，就 yield items[i:i + size]，然后 i += size。"
        "size 非法的检查放在函数体开头（生成器函数体在第一次 next 才执行，测试用 list() 触发，语义正好）。",
        "形状：if size <= 0: raise ValueError(...)；然后 i = 0；while i < len(items): yield items[i:i + size]；"
        "i += size。",
        '参考实现骨架：if size <= 0: raise ValueError(f"size 必须为正数: {size}")；i = 0；'
        "while i < len(items): yield list(items[i : i + size])；i += size——切片天然处理最后一页不满；"
        "list() 是为了对齐声明的 Iterator[list[T]]（Sequence 切片不是 list）。",
    ],
    "ex2": [
        "三段各自是独立的生成器函数：for 循环里处理一条、yield 一条；组合时把上一段的返回值直接喂给下一段。",
        "parse 的形状：for line in lines: claim_id, category, amount = line.split(',')；"
        "yield claim_id, category, int(amount)。filter 的形状：for record in records: 命中才 yield。",
        "total_over_limit 一行组合：return sum(record[2] for record in over_limit_meals(parse_lines(lines)))——"
        "或先 for 再累加；关键是「不要在中途 list()」，否则测试里的短路计数会变成 5。",
    ],
    "ex3": [
        "坏味道在「模块级把生成器赋给常量」：第一次消费排空它，第二次拿到空序列。要复用就物化。",
        "把 AMOUNTS 从 Iterator[int] 变成 list[int]：AMOUNTS = list(read_amounts(LINES))——"
        "类型注解同步改成 list[int]（list 是可重复消费的）。",
        "参考修复一行：AMOUNTS: list[int] = list(read_amounts(LINES))（注解与赋值都在 TODO 区内）。"
        "「每次重建生成器」的另一种修法见讲义 code/oneshot.py。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
