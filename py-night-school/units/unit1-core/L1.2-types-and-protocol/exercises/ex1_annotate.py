# 练习 1（单变量编辑约束：只给下面四个函数补类型标注，函数体一行都不要动）
"""给报销函数族补全类型标注——你的第一批「写给 pyright 看」的签名。

四个函数的行为已经写好且测试全过；缺的是签名上的标注。
照着代码/ 目录 typed_rules.py 的风格补：参数类型 + 返回值类型。

验收双通道（见 test_ex1.py）：
  1. 行为不变（原测试照跑）；
  2. 标注正确——用 typing.get_type_hints() 在运行时取出你写的标注，逐个比对。
     这也顺便证明了一件事：标注虽然不强制，但它是**真实存储在函数对象上的数据**。
"""

from typing import get_type_hints  # noqa: F401  ← 仅供你在本文件底部做自查实验（可删可留）


def parse_amounts(raw):
    """把 "1200,3500,2400" 解析成 [1200, 3500, 2400]。"""
    # TODO(ex1): 补标注 —— 预期 raw: str，返回 list[int]
    return [int(part) for part in raw.split(",")]


def first_rejected(results):
    """返回第一张被拒单据的 id；全部放行返回 None（注意返回类型的联合）。"""
    # TODO(ex1): 补标注 —— 预期 results: list[tuple[str, str]]，返回 str | None
    for claim_id, verdict in results:
        if verdict != "PASS":
            return claim_id
    return None


def reject_tally(results):
    """统计每种判定的单据数：{"PASS": 2, "REJECT:ITEM_OVER_LIMIT": 1}。"""
    # TODO(ex1): 补标注 —— 预期 results: list[tuple[str, str]]，返回 dict[str, int]
    counts: dict[str, int] = {}
    for _, verdict in results:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def is_clean(verdicts):
    """整组判定是否全部放行（无任何 REJECT）。"""
    # TODO(ex1): 补标注 —— 预期 verdicts: list[str]，返回 bool
    return all(v == "PASS" for v in verdicts)


# 自查实验（可选）：取消下行注释，uv run python ex1_annotate.py 看标注长什么样
# print(get_type_hints(parse_amounts))
