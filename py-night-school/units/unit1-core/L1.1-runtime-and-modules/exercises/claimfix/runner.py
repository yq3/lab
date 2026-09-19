# 练习 2（单变量编辑约束：只在本文件末尾补 TODO 要求的入口块，其余不要动）
"""claimfix.runner——一个带伤的命令行入口，等着你修。

事故现场（在 exercises/ 目录下重放）：
    uv run python claimfix/runner.py
    → ImportError: attempted relative import with no known parent package

正确启动方式（修好后再试）：
    uv run python -m claimfix.runner
    uv run python -m claimfix.runner 1200,3500
"""

import sys

from .rules import preapprove


def main() -> int:
    """主流程：从命令行读一串金额（无参数用内置示例），打印判定，返回退出码。"""
    raw = sys.argv[1] if len(sys.argv) > 1 else "1200,3500"
    items = [int(part) for part in raw.split(",")]
    verdict = preapprove(items)
    print(f"claimfix 审单：{items} -> {verdict}")
    return 0 if verdict == "PASS" else 1


# TODO(ex2): 上面 main() 写好了，但以 python -m 方式运行时它永远不会被调用——
# 缺了入口约定。在文件末尾补上 __main__ guard：
#     if __name__ == "__main__":
#         sys.exit(main())
# （不要动顶部的相对导入 from .rules import ...：包内相对导入是对的，
#   错的是「直接当脚本跑」的启动方式——见讲义 §5 的纪律。）
