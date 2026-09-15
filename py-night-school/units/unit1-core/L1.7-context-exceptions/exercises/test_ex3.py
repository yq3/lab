"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

from ex3_context import DAILY_MEAL_LIMIT_CENTS, check_item, override_limit


def test_ex3_limit_overridden_inside_with() -> None:
    with override_limit(8000):
        assert check_item(6000) == "PASS"  # 限额被临时抬高


def test_ex3_limit_restored_after_with() -> None:
    with override_limit(8000):
        pass
    assert check_item(6000) == "REJECT:ITEM_OVER_LIMIT"  # 恢复 5000
    assert check_item(DAILY_MEAL_LIMIT_CENTS) == "PASS"  # 边界照旧


def test_ex3_lower_override_also_works() -> None:
    with override_limit(3000):
        assert check_item(4000) == "REJECT:ITEM_OVER_LIMIT"
    assert check_item(4000) == "PASS"


def test_ex3_limit_restored_even_on_exception() -> None:
    with pytest.raises(RuntimeError, match="审查中断"):
        with override_limit(8000):
            raise RuntimeError("审查中断")
    assert check_item(6000) == "REJECT:ITEM_OVER_LIMIT"  # 异常也没逃过恢复
