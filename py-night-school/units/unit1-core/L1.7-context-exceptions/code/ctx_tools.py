"""@contextmanager——用生成器写上下文管理器：yield 前是 __enter__，yield 后是 __exit__。

这是 L1.6 生成器知识的直接复用（课程设计线：上一课的 yield，这一课的 with）。
标准库已有 tempfile.TemporaryDirectory，这里手搓一遍看原理。

运行本文件：
    uv run python code/ctx_tools.py
"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter


@contextmanager
def timed_block(label: str, log: list[tuple[str, float]]) -> Iterator[None]:
    """计时上下文：with 进来启动计时，出去（无论是否异常）记一条耗时。

    yield 前的代码 = __enter__；yield 后的代码 = __exit__；finally 保证「清理必达」。
    """
    start = perf_counter()
    try:
        yield  # with 体在这里执行；体内抛的异常会从这个 yield 点「射入」
    finally:
        log.append((label, perf_counter() - start))


@contextmanager
def scratch_dir(prefix: str = "expense-") -> Iterator[Path]:
    """临时工作目录：进入时创建，退出（无论是否异常）时整目录删除。"""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        shutil.rmtree(path)  # 清理必达：正常退出与异常退出都走这里


if __name__ == "__main__":
    timings: list[tuple[str, float]] = []
    with timed_block("预审一批单据", timings):
        total = sum([1200, 3500, 2400])
    print(f"合计 {total} 分，计时记录: {[(label, f'{elapsed:.4f}s') for label, elapsed in timings]}")

    created: list[Path] = []
    try:
        with scratch_dir("expense-demo-") as workdir:
            created.append(workdir)
            outfile = workdir / "claims.txt"
            outfile.write_text("CLM-2026-0001,1200\n", encoding="utf-8")
            print(f"会话内: {outfile} 存在? {outfile.exists()}")
            raise RuntimeError("处理中途出事")  # 演示：异常退出也走清理
    except RuntimeError as exc:
        print(f"异常逃出: {exc}")
    print(f"会话外: {created[0]} 还在? {created[0].exists()}")  # False：rmtree 兜住了
