"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import time

import ex1_main_flow as ex1


def test_ex1_sequential_order_and_result() -> None:
    ex1.LOG.clear()
    results = ex1.run()
    assert [r["claim_id"] for r in results] == ["CLM-A", "CLM-B"]
    assert [r["total_cents"] for r in results] == [1200, 8800]
    assert ex1.LOG == ["start:CLM-A", "done:CLM-A", "start:CLM-B", "done:CLM-B"]


def test_ex1_sequential_cost_is_sum() -> None:
    ex1.LOG.clear()
    t0 = time.perf_counter()
    ex1.run()
    elapsed = time.perf_counter() - t0
    # 顺序 await：总耗时 = 两段 0.05s 相加（放宽到 0.08；并发版是 L1.9 的事）
    assert elapsed >= 0.08
