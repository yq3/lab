"""讲义示例测试：一次性消费（静默排空）与两种修复。"""

from oneshot import read_amounts


def test_second_pass_is_silently_empty() -> None:
    gen = read_amounts()
    assert list(gen) == [1200, 3500, 2400]
    assert list(gen) == []  # 陷阱现场：没有异常，就是空


def test_fix_materialize() -> None:
    materialized = list(read_amounts())  # 物化：变成可以反复消费的 list
    assert sum(materialized) == 7100
    assert sum(materialized) == 7100


def test_fix_rebuild() -> None:
    assert sum(read_amounts()) == 7100  # 每次新建生成器
    assert sum(read_amounts()) == 7100
