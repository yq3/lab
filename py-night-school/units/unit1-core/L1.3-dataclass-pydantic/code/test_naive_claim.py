"""讲义示例测试：手写朴素类的行为基线（dataclass 版要与之行为等价）。"""

import pytest

from naive_claim import ExpenseClaimManual


def test_attributes() -> None:
    claim = ExpenseClaimManual("CLM-2026-0001", "王工", [1200, 3500], "客户拜访")
    assert claim.claim_id == "CLM-2026-0001"
    assert claim.submitter == "王工"
    assert claim.items_cents == [1200, 3500]
    assert claim.note == "客户拜访"


def test_repr_is_readable() -> None:
    # 不写 __repr__ 的话这里是 <naive_claim.ExpenseClaimManual object at 0x...>
    claim = ExpenseClaimManual("CLM-2026-0001", "王工", [1200])
    assert repr(claim) == (
        "ExpenseClaimManual(claim_id='CLM-2026-0001', submitter='王工', items_cents=[1200], note='')"
    )


def test_eq_compares_all_fields() -> None:
    a = ExpenseClaimManual("CLM-2026-0001", "王工", [1200])
    b = ExpenseClaimManual("CLM-2026-0001", "王工", [1200])
    c = ExpenseClaimManual("CLM-2026-0002", "王工", [1200])
    assert a == b  # 没写 __eq__ 时这里是 False：默认按身份（≈ 引用）比较
    assert a != c
    assert a != "不是报销单"  # __eq__ 返回 NotImplemented 后，退回身份比较 -> 不等


def test_default_items_are_independent() -> None:
    # 手写的 None 哨兵纪律：两个默认实例各拿各的列表，不是同一个对象
    a = ExpenseClaimManual("CLM-2026-0001", "王工")
    b = ExpenseClaimManual("CLM-2026-0002", "李工")
    assert a.items_cents == []
    assert b.items_cents == []
    assert a.items_cents is not b.items_cents  # is 比较身份：不是同一个列表对象
    a.items_cents.append(100)
    assert b.items_cents == []  # a 的追加不会串到 b


def test_defining_eq_removes_hash() -> None:
    # Java 的「重写 equals 必须重写 hashCode」在 Python 的镜像：定义 __eq__ 自动失去 __hash__
    claim = ExpenseClaimManual("CLM-2026-0001", "王工")
    with pytest.raises(TypeError):
        hash(claim)
