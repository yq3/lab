"""参考答案（ex2）——只补了文件末尾的入口块，顶部相对导入原样保留。"""

import sys

from .rules import preapprove


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "1200,3500"
    items = [int(part) for part in raw.split(",")]
    verdict = preapprove(items)
    print(f"claimfix 审单：{items} -> {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
