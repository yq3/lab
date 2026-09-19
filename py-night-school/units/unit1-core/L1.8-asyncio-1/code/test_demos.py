"""讲义示例测试：夜校的异步测试模板——同步 test 函数 + asyncio.run 包住真正的断言。

不引入 pytest-asyncio：模板就三行，自己就能写（这本身就是教学点）。
对照 Java：相当于在普通 @Test 里对 CompletableFuture 调 join() 再断言——
测试本身不需要「变成异步」，只在需要时进入异步世界取证。
"""

import asyncio

from blocking_disaster import run_disaster
from coroutine_object import review
from first_steps import CLAIM_DELAY, run_gather, run_sequential
from yield_point import interleave


def test_sequential_cost_is_sum() -> None:
    async def part() -> float:
        _, _, elapsed = await run_sequential()
        return elapsed

    elapsed = asyncio.run(part())
    assert elapsed >= 2 * CLAIM_DELAY - 0.005  # 顺序执行：总耗时 = 两段延迟相加


def test_gather_cost_is_max() -> None:
    async def part() -> tuple[float, float]:
        _, _, t_seq = await run_sequential()
        _, _, t_gather = await run_gather()
        return t_seq, t_gather

    t_seq, t_gather = asyncio.run(part())
    assert t_gather < t_seq  # 并发快于顺序
    assert t_gather < 2 * CLAIM_DELAY - 0.03  # ≈ 单段延迟，而不是两段相加


def test_disaster_freezes_everyone() -> None:
    async def part() -> tuple[list[str], float]:
        _, log, elapsed = await run_disaster()
        return log, elapsed

    log, elapsed = asyncio.run(part())
    # Y 和 Z 在 X 完全结束之后才开始——0.3s 的同步阻塞把全场冻住了
    assert log.index("start CLM-Y") > log.index("done  CLM-X")
    assert elapsed >= 0.38  # 0.3s 阻塞 + Y/Z 被放行后的 0.1s


def test_yield_point_interleaves() -> None:
    log = asyncio.run(interleave(3))
    assert log == ["窗口A:1", "窗口B:1", "窗口A:2", "窗口B:2", "窗口A:3", "窗口B:3"]


def test_coroutine_object_three_observations() -> None:
    coro = review("CLM-T")  # 只创建：函数体不执行（review 里的 print 不会出现）
    assert type(coro).__name__ == "coroutine"
    coro.close()
    assert asyncio.run(review("CLM-T")) == "PASS"  # run 驱动：拿到真实返回值
