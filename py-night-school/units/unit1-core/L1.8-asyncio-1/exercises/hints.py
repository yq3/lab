"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "fetch_receipt 里按时间顺序做四件事：记日志、异步等待、记日志、返回；"
        "run 里只有一件事：用 asyncio.run 把 main 交给事件循环。",
        "await asyncio.sleep(delay) 就是那声「异步等待」；"
        "main 里两次 await 一先一后（先把 CLM-A 的结果接住，再发 CLM-B）；"
        "run 的形状：return asyncio.run(main())。",
        'fetch_receipt 的核心两行：LOG.append(f"start:{claim_id}") 后接 '
        'await asyncio.sleep(delay)，再 LOG.append(f"done:{claim_id}")，'
        '最后 return {"claim_id": claim_id, "total_cents": total_cents}；'
        'main 里 a = await fetch_receipt("CLM-A", 0.05, 1200)、b = await fetch_receipt("CLM-B", 0.05, 8800)；'
        "run 就一行 return asyncio.run(main())。",
    ],
    "ex2": [
        "先跑 uv run pytest exercises/test_ex2.py 看两条证据怎么红："
        "时间阈值（0.36s > 0.25s）和 start 交错（start-A 后面跟的不是 start-B）。",
        "毒药只有一行：time.sleep(VERIFY_DELAY)。把它换成 await asyncio.sleep(VERIFY_DELAY)——"
        "等待同样的时长，但等待期间让出事件循环。",
        "改完这行，import time 就没人用了：删掉顶部那行 import time（ruff F401 会替你确认）；verify_three 不需要动。",
    ],
    "ex3": [
        "三个归宿各用一个「新的」协程对象——协程对象是一次性的：close 过 / run 过就不能再用。",
        "② 的形状：async def helper() -> str: coro = review_note(claim_id); return await coro，"
        '再 observed["await"] = asyncio.run(helper())；'
        '③ 直接 observed["run"] = asyncio.run(review_note(claim_id))。',
        '① 的形状：coro = review_note(claim_id); observed["type"] = type(coro).__name__; coro.close()；'
        '②③ 见上一级；返回的 dict 恰好三个键："type" / "await" / "run"。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
