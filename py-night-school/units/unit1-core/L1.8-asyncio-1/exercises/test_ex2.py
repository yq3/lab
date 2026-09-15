"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio
import time

import ex2_fix_blocking as ex2


def test_ex2_no_longer_blocks() -> None:
    ex2.LOG.clear()
    t0 = time.perf_counter()
    results = asyncio.run(ex2.verify_three())
    elapsed = time.perf_counter() - t0

    assert results == ["PASS:CLM-A", "PASS:CLM-B", "PASS:CLM-C"]

    # 并发证据：三个 start 全部出现在任何 rechecked/done 之前（阻塞版做不到）
    starts = [e for e in ex2.LOG if e.startswith("start:")]
    assert starts == ["start:CLM-A", "start:CLM-B", "start:CLM-C"]
    assert ex2.LOG[:3] == starts

    # 时间证据：修好后 ≈ 0.12s（阻塞版是 3 x 0.12 = 0.36s）；阈值放宽到 0.25
    assert elapsed < 0.25
