"""讲义示例测试：dataclass 与手写版行为等价 + frozen 值对象 + 「dataclass 不验证」。"""

from dataclasses import FrozenInstanceError, dataclass, is_dataclass

import pytest

from dataclass_claim import ExpenseClaimData, Policy
from naive_claim import ExpenseClaimManual


def test_equivalent_to_manual_class() -> None:
    manual = ExpenseClaimManual("CLM-2026-0001", "王工", [1200], "拜访")
    auto = ExpenseClaimData("CLM-2026-0001", "王工", [1200], "拜访")
    # 字段读取与相等比较行为一致
    assert auto.claim_id == manual.claim_id
    assert auto == ExpenseClaimData("CLM-2026-0001", "王工", [1200], "拜访")
    assert auto != ExpenseClaimData("CLM-2026-0002", "王工", [1200], "拜访")
    # 与不同类型的实例比较：dataclass 生成的 __eq__ 先比 class 再比字段 -> 不等
    assert auto != manual


def test_repr_generated() -> None:
    auto = ExpenseClaimData("CLM-2026-0001", "王工", [1200], "")
    assert repr(auto) == "ExpenseClaimData(claim_id='CLM-2026-0001', submitter='王工', items_cents=[1200], note='')"


def test_default_factory_gives_each_instance_its_own_list() -> None:
    a = ExpenseClaimData("CLM-2026-0001", "王工")
    b = ExpenseClaimData("CLM-2026-0002", "李工")
    assert a.items_cents == []
    assert a.items_cents is not b.items_cents
    a.items_cents.append(100)
    assert b.items_cents == []


def test_it_really_is_a_dataclass() -> None:
    # is_dataclass 判定「类是否由 @dataclass 装饰」——练习 1 的防作弊判据也是它
    assert is_dataclass(ExpenseClaimData)
    assert not is_dataclass(ExpenseClaimManual)


def test_dataclass_validates_nothing() -> None:
    # 类型标注在 dataclass 里纯文档：垃圾数据照样构造成功（要校验用 Pydantic，见 test_claims.py）
    junk = ExpenseClaimData(claim_id="garbage", submitter="", items_cents=[-5])
    assert junk.claim_id == "garbage"
    assert junk.items_cents == [-5]


def test_bare_mutable_default_is_blocked_at_class_definition() -> None:
    # 坑位预告（§5 详讲）：dataclass 直接把「裸可变默认值」挡在类定义时——ValueError 不是运行时才炸
    with pytest.raises(ValueError, match="mutable default"):

        @dataclass
        class Bad:
            items: list[int] = []


def test_frozen_policy_is_immutable_and_hashable() -> None:
    policy = Policy(item_limit_cents=5000, total_limit_cents=500000)
    # 可哈希 -> 能当 dict 的 key（对照 record 的全字段 hashCode）
    limits = {policy: "meal-policy"}
    assert limits[Policy(item_limit_cents=5000, total_limit_cents=500000)] == "meal-policy"
    with pytest.raises(FrozenInstanceError):
        policy.item_limit_cents = 6000  # type: ignore[misc]
