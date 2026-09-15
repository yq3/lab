# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""async 主流程补全：两个 async def + 顺序 await + asyncio.run 入口。

考察点：async def 定义协程函数、await 驱动协程、asyncio.run 作为同步世界的入口。
完成判据：uv run pytest exercises/test_ex1.py 全绿——
  执行顺序断言（LOG 顺序）+ 顺序执行总耗时 >= 两段延迟相加。
提示：函数体里要用到 asyncio（sleep / run），记得在顶部补 import asyncio。
"""

LOG: list[str] = []


async def fetch_receipt(claim_id: str, delay: float, total_cents: int) -> dict[str, int | str]:
    """模拟从台账端点拉取一张报销单（asyncio.sleep 模拟网络延迟）。"""
    # TODO(ex1): ① 向 LOG 记录 "start:<claim_id>"；
    # ② await asyncio.sleep(delay) 模拟网络等待；
    # ③ 等待结束后向 LOG 记录 "done:<claim_id>"；
    # ④ 返回 {"claim_id": claim_id, "total_cents": total_cents}
    raise NotImplementedError("TODO(ex1): 按 docstring 的 ①②③④ 补全 fetch_receipt")


async def main() -> list[dict[str, int | str]]:
    """顺序拉取两张单据：先 CLM-A（延迟 0.05s，1200 分），完成后再 CLM-B（延迟 0.05s，8800 分）。"""
    # TODO(ex1): 按顺序 await fetch_receipt 两次（参数见 docstring），把结果收进列表返回
    raise NotImplementedError("TODO(ex1): 补全 main 的顺序 await")


def run() -> list[dict[str, int | str]]:
    """同步入口：用 asyncio.run 驱动 main——这就是同步世界与异步世界的边界。"""
    # TODO(ex1): 用 asyncio.run 驱动 main 并返回其结果
    raise NotImplementedError("TODO(ex1): 补全 run 的 asyncio.run 入口")
