"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio
from typing import cast, get_type_hints

from langgraph.types import Send

import ex1_fanout as ex1
import mock_tools
import review_rules


def _claim_ids() -> list[str]:
    return [claim["id"] for claim in mock_tools.claims_table()]


def test_fan_out_returns_one_send_per_claim() -> None:
    state = cast(ex1.BatchState, {"claim_ids": _claim_ids()})
    sends = ex1.fan_out(state)
    assert len(sends) == 4 and all(isinstance(send, Send) for send in sends)
    assert {send.node for send in sends} == {"review"}
    assert [send.arg["claim_id"] for send in sends] == _claim_ids()  # 每个分支带自己的单号


def test_batch_results_keyed_by_claim_id_and_correct() -> None:
    mock_tools.CALL_LOG.clear()
    result = asyncio.run(ex1.build().ainvoke({"claim_ids": _claim_ids()}))
    assert set(result["results"]) == set(_claim_ids())  # 每单结果按 claim_id 落位（dict 合并 reducer 的功劳）
    for claim in mock_tools.claims_table():
        _first, _text, expected = review_rules.script_for(claim["id"])
        assert result["results"][claim["id"]] == expected, claim["id"]
    assert result["counts"] == {"APPROVE": 1, "REJECT": 2, "ESCALATE": 1}  # 汇总计数正确
    assert len(mock_tools.CALL_LOG) == 8  # 4 单 × 每单 2 个工具，全部真实执行


def test_results_annotation_is_custom_dict_merge_reducer() -> None:
    """meta：results 必须挂自定义 dict 合并 reducer（覆盖语义会让前两个测试的 results 只剩一个分支）。"""
    hints = get_type_hints(ex1.BatchState, include_extras=True)
    assert "results" in hints, "BatchState 还没有 results 字段"
    (reducer,) = hints["results"].__metadata__
    assert callable(reducer)
    assert reducer({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}  # dict 合并语义（operator.add 在 dict 上会 TypeError）
    assert reducer({"k": "old"}, {"k": "new"}) == {"k": "new"}
