"""异常链实验——raise X from e / 裸 raise / from None 的三种姿势与 traceback 链。

运行本文件（看 chained traceback 的真面目）：
    uv run python code/chains.py
"""

import traceback


class DomainError(Exception):
    """领域异常：底层脏数据被翻译成业务语言后的出口。"""


def parse_amount(raw: str) -> int:
    """把文本金额解析成整数分；失败时 raise DomainError from 原始异常。

    `from exc` 把 exc 记为 __cause__（直接原因），traceback 会打印
    "The above exception was the direct cause of the following exception"。
    对照 Java：new DomainError("...", exc) 里传的 cause。
    """
    try:
        return int(raw)
    except ValueError as exc:
        raise DomainError(f"金额字段不是整数: {raw!r}") from exc


def parse_and_report(raw: str) -> int:
    """捕获 -> 记日志 -> 裸 raise 原样上抛：不换对象、不丢栈。"""
    try:
        return parse_amount(raw)
    except DomainError:
        print(f"[日志] 解析失败，已记录，原样上抛: {raw!r}")
        raise  # 裸 raise：抛的就是 except 抓到的那个对象，原始 traceback 完整保留


if __name__ == "__main__":
    # 1) 正常路径
    print(parse_amount("1200"))

    # 2) 异常链：cause 链在 traceback 里连成一条（"direct cause" 桥接两段栈）
    try:
        parse_and_report("12abc")
    except DomainError as exc:
        print("--- chained traceback ---")
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        print(f"__cause__ 是: {type(exc.__cause__).__name__}")  # ValueError

    # 3) from None：主动切断因果链（只在「底层异常是噪音」时用，如重试后换新异常）
    try:
        int("xyz")
    except ValueError:
        try:
            raise DomainError("换个干净的新异常，不带旧栈") from None
        except DomainError as exc:
            print(f"from None 之后 __cause__ 是: {exc.__cause__}")  # None——旧栈被主动切断
