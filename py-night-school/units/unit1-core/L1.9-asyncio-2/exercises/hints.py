"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "fetch_all 里只缺一行：把 5 个 fetch_region(...) 交给 gather 并 await 它。"
        "注意返回值直接就是按传入顺序排好的列表。",
        "形状：results = await asyncio.gather(*(fetch_region(r) for r in REGION_ENDPOINTS))；"
        "生成器表达式里的 r 就是区域名（dict 的迭代序 = 你要的顺序）。",
        "整函数体就一句：return list(await asyncio.gather(*(fetch_region(r) for r in REGION_ENDPOINTS)))。",
    ],
    "ex2": [
        "两个函数各司其职：fetch_with_fallback 管「预算与降级」，fetch_two 管「并发」。"
        "超时抛的是内建 TimeoutError（3.11 起 asyncio.TimeoutError 是它的别名）。",
        "fetch_with_fallback 的形状：try: return await asyncio.wait_for(fetch_ledger(region), "
        "timeout=TIMEOUT_SECONDS)；except TimeoutError: return 0。"
        "fetch_two 用 gather 并发驱动 west 与 north。",
        "fetch_two 就一句："
        'return list(await asyncio.gather(fetch_with_fallback("west"), fetch_with_fallback("north")))。',
    ],
    "ex3": [
        "把 L1.6 的同步生成器「翻译」成异步版：yield 不变，在它前面加 await asyncio.sleep(CHUNK_DELAY)；"
        "消费端把 for 换成 async for。",
        "stream_review 的形状：for chunk in CHUNKS: 先 await asyncio.sleep(CHUNK_DELAY)，再 yield chunk；"
        'collect 里用 parts 列表收集 async for 的每段，最后 "".join(parts) 与 len 计数。',
        "collect 的形状：parts: list[str] = []，async for chunk in stream_review(): parts.append(chunk)；"
        'return "".join(parts), len(parts)。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
