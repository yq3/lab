"""Step 6：取消是「下一个让出点抛出的协作式异常」——task.cancel() 实录。

两相对照：
  A. 有 await 的任务：cancel() 在它的下一个 await 点抛 CancelledError，
     任务接住、清理、re-raise——干净的协作式取消；
  B. 纯 CPU 循环的任务：一个 await 都没有，取消信号没有落点——
     谁也打不断它（包括想取消它的你，因为你也在同一条线程上排队）。

运行：uv run python code/cancel_demo.py
"""

import asyncio
import time


async def slow_audit(audit_id: str, log: list[str]) -> str:
    """模拟一轮 0.3s 的审计（有 await，可被取消）。"""
    try:
        await asyncio.sleep(0.3)
        log.append(f"{audit_id}:AUDIT_OK")
        return "AUDIT_OK"
    except asyncio.CancelledError:
        log.append(f"{audit_id}:CANCELLED_CLEANUP")  # 该做的清理要做
        raise  # 然后必须 re-raise：吞掉它 = 对「取消」说「不」


async def cpu_hog(hog_id: str, seconds: float, log: list[str]) -> str:
    """纯 CPU 循环（无 await，不可打断）。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pass  # 没有一个 await——取消信号没有落脚点
    log.append(f"{hog_id}:RAN_TO_COMPLETION")
    return hog_id


async def run_cancel() -> list[str]:
    """A：在 await 点取消 slow_audit，观察清理与取消落地。"""
    log: list[str] = []
    task = asyncio.create_task(slow_audit("AUD-1", log))
    await asyncio.sleep(0.05)  # 让任务先跑起来（进入它的 await）
    task.cancel()  # 请求取消：CancelledError 将在任务的下一次挂起点抛出
    try:
        await task  # 等取消落地
    except asyncio.CancelledError:
        log.append("main:观察到任务已取消")
    return log


async def run_cpu_hog_unkillable() -> list[str]:
    """B：想取消纯 CPU 循环，却发现连「想」的机会都排不到它后面。"""
    log: list[str] = []
    task = asyncio.create_task(cpu_hog("HOG-1", 0.2, log))
    await asyncio.sleep(0.05)  # 我一让出，HOG-1 立刻霸占唯一的线程 0.2s
    log.append("main:终于醒了（睡了 0.05s 却被拖到 0.2s 后），此刻才想取消 HOG-1")
    cancelled = task.cancel()  # 但它已经跑完了
    log.append(f"main:cancel() 返回 {cancelled}（任务已完成，无从取消）")
    result = await task
    log.append(f"main:await 拿到 HOG-1 的正常结果 {result!r}——取消来晚了")
    return log


def main() -> None:
    log = asyncio.run(run_cancel())
    print("== A：有 await 的任务，取消干净落地 ==")
    for entry in log:
        print(f"  {entry}")
    print("  ——CancelledError 在 await 点抛入，清理后 re-raise，主流程 await 观察到取消。\n")

    log = asyncio.run(run_cpu_hog_unkillable())
    print("== B：纯 CPU 循环，取消来晚了 ==")
    for entry in log:
        print(f"  {entry}")
    print("  ——协作式的字面意思：循环里没有 await，就没人能打断它。")


if __name__ == "__main__":
    main()
