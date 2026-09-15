"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

import sys


def format_daily_report(claim_id: str, verdict: str) -> str:
    return f"{claim_id} -> {verdict}"


def main() -> int:
    print(format_daily_report("CLM-2026-0001", "PASS"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
