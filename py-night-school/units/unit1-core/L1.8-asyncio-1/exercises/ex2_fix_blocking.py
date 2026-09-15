# 练习 2（单变量编辑约束：只改 TODO 标注的那一行与文件顶部的 import，其余不要动）
"""修复阻塞毒药：async 函数里混入了 time.sleep，三个任务并发时它冻住整个事件循环。

考察点：识别「同步阻塞混进 async 函数」的事故（本课坑位二的迷你版），改成异步等待。
完成判据：uv run pytest exercises/test_ex2.py 全绿——
  总时长阈值 + 三个任务的 start 全部排在任何 rechecked/done 之前（并发证据）。
修完别忘了：顶部的 import time 若不再被使用，删掉它（ruff 的 F401 会提醒你）。
"""

import asyncio
import time

LOG: list[str] = []

VERIFY_DELAY = 0.08  # 查重接口的模拟网络延迟
RULE_DELAY = 0.04  # 规则引擎的模拟计算延迟


async def verify_claim(claim_id: str) -> str:
    """并发校验一张单据：先查重复提交（网络 IO），再跑规则（也模拟成 IO）。"""
    LOG.append(f"start:{claim_id}")
    # TODO(ex2): 下面这行 time.sleep 是阻塞毒药——三个任务并发时它独自冻住全场 0.08s。
    # 把它改成正确的异步等待（保持 VERIFY_DELAY 不变），并删掉顶部不再使用的 import time。
    time.sleep(VERIFY_DELAY)
    LOG.append(f"rechecked:{claim_id}")
    await asyncio.sleep(RULE_DELAY)
    LOG.append(f"done:{claim_id}")
    return f"PASS:{claim_id}"


async def verify_three() -> list[str]:
    """并发校验三张单据（gather 的完整规格是 L1.9 的事，这里当对照组用）。"""
    results = await asyncio.gather(
        verify_claim("CLM-A"),
        verify_claim("CLM-B"),
        verify_claim("CLM-C"),
    )
    return list(results)
