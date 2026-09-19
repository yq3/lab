# 练习 1（单变量编辑约束：只改本文件 TODO 标注处，其余不要动）
"""审单日报生成器——同一个文件，两种身份（本课核心机制的第一次实弹）。

被 import 时：只提供 format_daily_report / main 两个函数，不产生任何输出；
被直接运行时：打印一张示例日报，退出码 0。

日报行的精确格式（验收按此断言）：
    CLM-2026-0001 -> PASS
"""


def format_daily_report(claim_id: str, verdict: str) -> str:
    """返回一行日报，格式："CLM-2026-0001 -> PASS"（claim_id 与 verdict 之间是 " -> "）。"""
    raise NotImplementedError("TODO(ex1a): 用 f-string 拼出精确格式的一行")


def main() -> int:
    """直接运行时的主流程：打印 format_daily_report("CLM-2026-0001", "PASS")，返回退出码 0。"""
    raise NotImplementedError("TODO(ex1b): 调用 print 打印那行日报，然后返回 0")


if __name__ == "__main__":
    # TODO(ex1c): 入口约定的最后一环——在文件顶部补需要的 import，在本块内调用 sys.exit(main())
    raise NotImplementedError("TODO(ex1c): 直接运行时以 sys.exit(main()) 收尾")
