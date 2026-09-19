"""讲义示例测试：手工 for 与三 yield 生成器。"""

from iter_basics import CLAIMS, audit_steps, manual_total


def test_manual_for_matches_sum() -> None:
    assert manual_total(CLAIMS) == sum(CLAIMS) == 7100
    assert manual_total([]) == 0
    assert manual_total([42]) == 42


def test_manual_for_works_on_any_iterable() -> None:
    # iter() 对 list / tuple / 字符串 / 生成器都成立——协议统一
    assert manual_total((1, 2, 3)) == 6
    assert manual_total(x * 2 for x in (10, 20)) == 60


def test_generator_yields_in_order() -> None:
    gen = audit_steps("CLM-2026-0001")
    assert next(gen) == "OK:金额"
    assert next(gen) == "OK:预算"
    assert next(gen) == "PASS"


def test_generator_is_its_own_iterator() -> None:
    gen = audit_steps("CLM-2026-0001")
    assert iter(gen) is gen  # 生成器本身就是迭代器


def test_generator_body_not_run_until_first_next() -> None:
    # def 到第一次 next 之间：函数体一行都没执行
    import pytest

    gen = audit_steps("CLM-2026-0001")
    assert list(gen) == ["OK:金额", "OK:预算", "PASS"]  # 消费它
    with pytest.raises(StopIteration):
        next(gen)  # 耗尽后再要：StopIteration
