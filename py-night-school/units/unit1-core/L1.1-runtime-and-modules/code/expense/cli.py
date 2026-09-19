"""expense 包的命令行入口——`python -m expense.cli` 的标准形态。

对照 Java：Python 没有 `public static void main` 的方法签名约定，
「入口」就是模块底部那个 if __name__ == "__main__" 块（本课 §2 的主角）。

注意顶部的相对导入 `from .rules import ...`：
  - 以 `python -m expense.cli` 启动：cli 是包成员，`.rules` 解析为 expense.rules，正常；
  - 以 `python expense/cli.py` 直接启动：文件失去包身份，相对导入当场炸——
    这正是讲义 §5「直跑包内脚本」，别修 import，修启动方式。
"""

import sys

from .rules import preapprove


def parse_amounts(raw: str) -> list[int]:
    """把 "1200,3500,2400" 解析成 [1200, 3500, 2400]。"""
    return [int(part) for part in raw.split(",")]


def main(argv: list[str]) -> int:
    """主流程：返回进程退出码（0 = 放行，1 = 拒绝）——对照 System.exit 的约定。"""
    items = parse_amounts(argv[0]) if argv else [1200, 3500, 2400]
    verdict = preapprove(items)
    print(f"报销单金额（分）：{items}")
    print(f"预审结果：{verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":  # 入口约定：被 import 时这段不会执行
    sys.exit(main(sys.argv[1:]))
