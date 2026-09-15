"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在 exercises/ 目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "每个函数问两个问题：参数进来是什么形状（str？list[int]？list[元组]？）、"
        "返回出去是什么形状（注意 first_rejected 有一条 return None 的路）。",
        "形状：raw: str -> list[int]；results: list[tuple[str, str]] 出现在两个函数里；"
        "first_rejected 的返回是联合类型（str 加上 None），写法是竖线。",
        "def parse_amounts(raw: str) -> list[int]:；def first_rejected(results: list[tuple[str, str]])"
        " -> str | None:；def reject_tally(results: list[tuple[str, str]]) -> dict[str, int]:；"
        "def is_clean(verdicts: list[str]) -> bool:。",
    ],
    "ex2": [
        "「长得像」= 方法名一样、参数个数对得上；不用写继承，不用 @Override。",
        "两个类的形状：def record(self, claim_id: str, verdict: str) -> str:，"
        "方法体一行 f-string 返回；注意前缀分别是 [console] 与 [team]。",
        'ConsoleSink 的方法体：return f"[console] {claim_id} {verdict}"；'
        'TeamSink 换成 return f"[team] {claim_id} {verdict}"——精确到空格，验收按全字符串比对。',
    ],
    "ex3": [
        "Any 换成精确类型的依据在函数体里：min(a, 5000) 说明元素是 int；"
        ".startswith / .split 说明是 str；counts 的键值形状看 dict.get 那行。",
        "形状：clip_to_limit 是 list[int] 进 list[int] 出；rejection_code 是 str 进 str 出；"
        "verdict_counts 是 list[tuple[str, str]] 进 dict[str, int] 出。",
        "三个签名分别是：def clip_to_limit(amounts: list[int]) -> list[int]:、"
        "def rejection_code(verdict: str) -> str:、def verdict_counts(results: list[tuple[str, str]])"
        " -> dict[str, int]:；改完删掉 from typing import Any（F401）。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
