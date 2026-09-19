"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from ex1_flow import record_transfer


def test_ex1_normal_path_order() -> None:
    trace: list[str] = []
    result = record_transfer("CLM-2026-0001", 1200, trace)
    assert result == "OK"
    assert trace == ["try", "else", "finally"]  # else 只在无异常时执行


def test_ex1_exception_path_order() -> None:
    trace: list[str] = []
    result = record_transfer("CLM-2026-0003", -500, trace)
    assert result == "FAILED"
    assert trace == ["try", "except", "finally"]  # else 不出现，finally 仍然收尾


def test_ex1_zero_amount_is_invalid() -> None:
    trace: list[str] = []
    assert record_transfer("CLM-0009", 0, trace) == "FAILED"
    assert trace == ["try", "except", "finally"]


def test_ex1_finally_runs_even_when_returning_early() -> None:
    # 正常路径的 return 在 else 里也不影响 finally：顺序铁律
    trace: list[str] = []
    record_transfer("CLM-0002", 8800, trace)
    assert trace[-1] == "finally"  # 无论哪条路，finally 都是最后一个
