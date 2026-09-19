"""练习 3 验收（不要改本文件——它就是你的判卷老师）：meta-test，被测数据是自查表本身。"""

from __future__ import annotations

import ex3_selfcheck as ex3

FRAMEWORK_NAMES = ("mini-agent", "openai-agents", "langgraph", "deepagents", "adk", "dify")


def test_twelve_rows_all_filled() -> None:
    assert len(ex3.CHECKLIST) == 12  # 删行偷懒：行数对不上
    for i, row in enumerate(ex3.CHECKLIST):
        assert row["维度"].strip(), i  # 维度非空
        assert row["条目"].strip(), i  # 条目非空


def test_covers_curriculum_framework_criterion() -> None:
    # CURRICULUM §7 框架判据：「mini-agent vs 四框架决策表能自己重新推导」
    rederive = [r for r in ex3.CHECKLIST if "决策表" in r["条目"] and "重新推导" in r["条目"]]
    assert rederive  # 「能重新推导」类条目必须存在
    assert sum(1 for r in ex3.CHECKLIST if r["维度"] == "框架判据") >= 2  # 给定 1 行，至少再补 1 行


def test_every_framework_named_in_some_item() -> None:
    joined = "\n".join(r["条目"] for r in ex3.CHECKLIST)
    for name in FRAMEWORK_NAMES:
        assert name in joined, name  # deepagents 不在给定行——必须由你补


def test_dimensions_use_whitelist_only() -> None:
    used = {r["维度"] for r in ex3.CHECKLIST}
    assert used <= set(ex3.DIMENSIONS)  # 白名单外自造维度不算数
    assert len(used) >= 4  # 至少覆盖四种维度（给定 5 行已占全五种——删改给定行会被上一条抓）
