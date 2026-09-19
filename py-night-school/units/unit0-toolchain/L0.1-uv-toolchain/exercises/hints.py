"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "先想「谁必须最先被挡住」：脏数据、单笔超限、合计超限——三条规则的判定顺序就是返回优先级。",
        "三个分支的形状分别是 any(...) 命中即返回、any(...) 命中即返回、sum(...) 与常量比较；都未命中才走最后一条路。",
        "any(c <= 0 for c in items_cents)；"
        "any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents)；"
        "sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS。",
    ],
    "ex2": [
        "最少的合格用例集：四种返回结果各至少一组，再加一个「恰好等于上限」的边界用例，共 5 组起步。",
        "边界用例考察「等于不等于超过」：[5000] 单笔恰好到限、合计恰好 500000，都应 PASS；"
        "合计超限可用 [4000] * 126 构造。",
        '示例骨架：([5000], "PASS")、([5001], "REJECT:ITEM_OVER_LIMIT")、'
        '([-1], "REJECT:INVALID_AMOUNT")、([4000] * 126, "REJECT:TOTAL_OVER_LIMIT")。',
    ],
    "ex3": [
        "先跑 uv run ruff check exercises/ex3_ruff_fix.py，看三处报错各在哪一行，再逐个处理。",
        "F401 / F841 的修法是删掉没用的东西；"
        "E501 那行是单字符串字面量，ruff format 拆不了——用括号内相邻字面量隐式拼接手工拆。",
        '把 detail_suffix 改成 ("…前半…", "…后半…") 的形式（相邻字符串字面量自动拼接）；'
        "import json 与 backup 直接删除。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
