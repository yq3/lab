"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

import ex1_extract as ex1


def test_three_layers_all_pass() -> None:
    for label, text in ex1.SAMPLES[:4]:  # 前四个样本都要剥出 dict
        payload = ex1.extract_json(text)
        assert payload["claim_id"].startswith("CLM-2026-"), label


def test_garbage_raises_value_error() -> None:
    with pytest.raises(ValueError, match="找不到 JSON"):
        ex1.extract_json(ex1.SAMPLES[4][1])


def test_syntax_error_translated() -> None:
    with pytest.raises(ValueError, match="语法错误"):
        ex1.extract_json("```json\n{verdict: PASS}\n```")  # 键没加引号：语法伤不是「找不到」
