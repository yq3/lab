"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在 milestone/ 目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('t1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "t1": [
        "wrapper 是 async def，里面循环「调用 + 捕获 + 重试」：尝试最多 1 + max_retries 次，"
        "每次失败前想想还剩几次额度；耗尽后把最后一个异常原样抛出。",
        "形状：last_error 变量存异常；for _ in range(max_retries + 1): try: return await func(*args, **kwargs) "
        "except exceptions as exc: last_error = exc；循环走完 raise last_error。"
        "注意 except 点名的是 exceptions 元组——CancelledError 不在其中，自动放行。",
        "细节校准：return 只能出现在 try 里（拿到结果立刻返回）；raise last_error 前用断言说服类型检查它非空"
        "（assert last_error is not None）；functools.wraps(func) 已在骨架里给好。",
    ],
    "t2": [
        "try / except TimeoutError 包住一个 await asyncio.wait_for(...)，两个返回分支：正常 (结果, False)，"
        "超时 ([], True)。",
        "形状：try: receipts = await asyncio.wait_for(fetch_region_with_retry(region), timeout=FETCH_TIMEOUT) "
        "except TimeoutError: return [], True；最后 return receipts, False。",
        "预算套在重试链的外面（骨架已固定这个层次）：east 抖动 0.01 + 0.01 + 0.05 = 0.07s < 0.15s 预算，"
        "够它重试成功；north 0.3s > 0.15s，被掐断降级。",
    ],
    "t3": [
        "三件事：Semaphore 造闸机；async 帮手在 async with sem 里拿 guarded 结果并判状态；gather 并发 + 保序 + 汇总。",
        "帮手形状：async def collect_one(region): async with sem: receipts, degraded = "
        "await fetch_region_guarded(region)；然后按 degraded / call_count(region) > 1 判三态，"
        "返回 RegionReport(region, len(receipts), sum(receipts), status)。"
        "主函数：reports = await asyncio.gather(*(collect_one(r) for r in REGIONS))。",
        "组装：return Summary(list(reports), sum(r.total_cents for r in reports))。"
        "注意 call_count 要在帮手判状态时读取（那时该区域已拉完）；"
        'north 降级时 count=0、total=0，status="DEGRADED"。',
    ],
}


def hint(task: str, level: int = 1) -> str:
    """返回某任务第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[task]
    return levels[min(level, len(levels)) - 1]
