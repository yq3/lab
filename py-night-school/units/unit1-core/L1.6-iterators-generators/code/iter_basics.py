"""迭代协议手工拆解 + 生成器暂停语义——本课最重要的两个演示在一个文件里。

运行本文件（逐段对照讲义 §2.1 / §2.3）：
    uv run python code/iter_basics.py
"""

from collections.abc import Generator, Iterable

CLAIMS = [1200, 3500, 2400]  # 一张报销单的三笔金额（整数分）


# ---- 演示一：手工 for——把 for 循环的糖衣全部剥掉 ----
def manual_total(items: Iterable[int]) -> int:
    """不用 for，用 while + next + StopIteration 手工迭代。

    这就是 `for x in items: total += x` 的真实面目（讲义 §2.1 的三步协议）。
    """
    it = iter(items)  # 第 1 步：iter() 拿迭代器
    total = 0
    while True:
        try:
            item = next(it)  # 第 2 步：next() 推进一步
        except StopIteration:  # 第 3 步：耗尽信号是个异常
            break
        total += item
    return total


# ---- 演示二：三 yield 生成器——「函数可以暂停」的完整证据 ----
def audit_steps(claim_id: str) -> Generator[str, None, None]:
    """审批三步走：执行到 yield 就暂停并吐值，局部变量与指令位置完整保留。"""
    print(f"  [进入] {claim_id} 开始审批（此刻函数体刚启动）")
    print("  [执行] 第一段：校验金额")
    yield "OK:金额"  # 吐出这个值，然后函数在这里「冻结」
    print("  [执行] 第二段：查预算")  # 下次 next() 从这里继续——前面的变量都还在
    yield "OK:预算"
    print("  [执行] 第三段：出结论")
    yield "PASS"  # 最后一个 yield 之后，再 next() 触发函数自然结束 -> StopIteration


if __name__ == "__main__":
    # 演示一：for 的糖衣手工展开
    print("演示一：手工 for")
    print(manual_total(CLAIMS), sum(CLAIMS))  # 两个数应相等：7100 7100

    # 演示二：逐次 next，看暂停与恢复
    print("演示二：三 yield 逐次 next")
    gen = audit_steps("CLM-2026-0001")
    print(f"[main] 拿到生成器对象，函数体一行都没执行: {gen}")
    print(f"[next ] 第 1 次吐出: {next(gen)}")
    print("[main] 函数此刻冻结在第一个 yield 处，我在干别的事……")
    print(f"[next ] 第 2 次吐出: {next(gen)}")
    print(f"[next ] 第 3 次吐出: {next(gen)}")
    try:
        next(gen)  # 函数早已自然结束——再要就是 StopIteration
    except StopIteration:
        print("[next ] 第 4 次: StopIteration（生成器耗尽）")

    # 生成器就是迭代器：iter(gen) 就是 gen 自己
    print("iter(gen) is gen:", iter(gen) is gen)
