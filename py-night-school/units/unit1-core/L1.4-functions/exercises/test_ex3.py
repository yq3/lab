"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import inspect

import pytest

from ex3_report import format_claim_line, format_from_config


def test_ex3_default_format() -> None:
    assert format_claim_line("王工", 1200) == "王工: 1200 分"


def test_ex3_keyword_options() -> None:
    assert format_claim_line("王工", 1200, unit="元") == "王工: 1200 元"
    assert format_claim_line("王工", 1200, bracket=True) == "[王工] 1200 分"
    assert format_claim_line("王工", 1200, unit="元", bracket=True) == "[王工] 1200 元"


def test_ex3_unit_is_keyword_only_by_call_shape() -> None:
    # 调用形态断言：`*` 之后的参数按位置传 -> TypeError（这正是 keyword-only 的意义）
    with pytest.raises(TypeError):
        format_claim_line("王工", 1200, "元")  # type: ignore[arg-type]


def test_ex3_signature_shape() -> None:
    # 形态的元判定：签名里 unit/bracket 的种类必须是 KEYWORD_ONLY
    params = inspect.signature(format_claim_line).parameters
    assert params["unit"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["bracket"].kind is inspect.Parameter.KEYWORD_ONLY


def test_ex3_config_passthrough() -> None:
    assert format_from_config("王工", 1200) == "王工: 1200 分"
    assert format_from_config("王工", 1200, unit="元", bracket=True) == format_claim_line(
        "王工", 1200, unit="元", bracket=True
    )


def test_ex3_unknown_option_blows_up() -> None:
    # 透传不许吞错：不认识的键在摊开调用处炸 TypeError（**options: Any 收下，对岸签名拒收）
    with pytest.raises(TypeError):
        format_from_config("王工", 1200, unti="元")
