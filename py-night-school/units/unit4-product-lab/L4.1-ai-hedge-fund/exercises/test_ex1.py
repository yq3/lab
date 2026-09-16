"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import pytest

import ex1_weights as ex1
from review import Vote


def _vote(checker: str, score: float, abstained: bool = False) -> Vote:
    metadata = {"abstained": True} if abstained else {}
    return Vote(checker=checker, claim_id="CLM-EX1", score=score, metadata=metadata)


def test_weighted_mean_is_exact() -> None:
    votes = [_vote("compliance", 0.8), _vote("budget", -0.6), _vote("invoice", 0.9)]
    weights = {"compliance": 1.0, "budget": 2.0, "invoice": 0.5}
    result = ex1.weighted_vote(votes, weights)
    assert result.conviction == pytest.approx((0.8 + 2.0 * -0.6 + 0.5 * 0.9) / 3.5)
    assert result.voters == ["compliance", "budget", "invoice"]
    assert result.abstained == []


def test_abstain_excluded_from_numerator_and_denominator() -> None:
    votes = [_vote("compliance", 0.8), _vote("budget", 0.0, abstained=True), _vote("invoice", 0.6)]
    result = ex1.weighted_vote(votes, {"compliance": 1.0, "budget": 3.0, "invoice": 1.0})
    assert result.conviction == pytest.approx((0.8 + 0.6) / 2.0)  # budget 的权重 3.0 完全不参与
    assert result.voters == ["compliance", "invoice"]
    assert result.abstained == ["budget"]


def test_all_abstain_returns_none_not_zero() -> None:
    votes = [_vote("compliance", 0.0, abstained=True), _vote("budget", 0.0, abstained=True)]
    result = ex1.weighted_vote(votes, {"compliance": 1.0, "budget": 1.0})
    assert result.conviction is None  # 显式边界：不是 0.0 的「假中性」
    assert result.voters == []
    assert result.abstained == ["compliance", "budget"]


def test_zero_weights_returns_none() -> None:
    result = ex1.weighted_vote([_vote("compliance", 0.8)], {"compliance": 0.0})
    assert result.conviction is None  # 分母为零：与全弃权同一显式边界


def test_weights_change_the_outcome() -> None:
    """meta：同一组票换权重表，结果必须变——权重即话语权。"""
    votes = [_vote("compliance", 0.8), _vote("budget", -0.6)]
    light = ex1.weighted_vote(votes, {"compliance": 1.0, "budget": 0.5})
    heavy = ex1.weighted_vote(votes, {"compliance": 1.0, "budget": 3.0})
    assert light.conviction == pytest.approx((0.8 - 0.3) / 1.5)
    assert heavy.conviction == pytest.approx((0.8 - 1.8) / 4.0)
    assert light.conviction is not None and heavy.conviction is not None
    assert light.conviction != heavy.conviction
    assert light.conviction > 0 > heavy.conviction  # 话语权翻转了结论
