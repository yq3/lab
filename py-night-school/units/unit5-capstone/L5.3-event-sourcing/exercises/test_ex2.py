"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import demo
from ex2_cache import DecisionCache, audit_query, cached_complete, canonical_prompt, prompt_hash
from mock_endpoint import MockLLMEndpoint


def _planner_messages() -> list[dict]:
    return [
        {"role": "system", "content": "你是规划器。"},
        {"role": "user", "content": "请规划 CLM-2026-0001 的取数步骤。"},
    ]


def test_canonical_prompt_equates_dict_and_langchain_messages() -> None:
    """canonical 键：dict 消息与同内容 langchain 消息（human=user、assistant=ai）同一个 hash。"""
    dict_form = _planner_messages()
    object_form = [SystemMessage(content="你是规划器。"), HumanMessage(content="请规划 CLM-2026-0001 的取数步骤。")]
    assert canonical_prompt(dict_form) == canonical_prompt(object_form)
    assert prompt_hash("mock-model", dict_form) == prompt_hash("mock-model", object_form)
    assert canonical_prompt([{"role": "assistant", "content": "答"}]) == canonical_prompt([AIMessage(content="答")])


def test_different_prompt_or_model_changes_hash() -> None:
    """不同 prompt 或不同模型 → 不同 key（内容寻址：变一字符就换 key，不误命中的根）。"""
    base = prompt_hash("mock-model", _planner_messages())
    changed_prompt = prompt_hash(
        "mock-model", [SystemMessage(content="你是规划器？"), HumanMessage(content="请规划 CLM-2026-0001 的取数步骤。")]
    )
    changed_model = prompt_hash("glm-4.6", _planner_messages())
    assert len({base, changed_prompt, changed_model}) == 3


def test_second_pass_hits_cache_with_zero_requests(tmp_path) -> None:
    """命中零请求：第一遍真调用并落缓存；第二遍新端点（不装剧本）零请求、响应同文。"""

    async def scenario() -> tuple[tuple[str, bool], tuple[str, bool], int, int]:
        db = tmp_path / "c.db"
        with DecisionCache(db, clock=lambda: "t") as cache:
            with MockLLMEndpoint() as ep1:  # 第一遍：装一条剧本，真调用一次
                ep1.script_text("第一遍的原话")
                model = demo.model_for_url(ep1.url)
                first = await cached_complete(cache, model, _planner_messages(), "mock-model")
                requests1 = len(ep1.requests)
            with MockLLMEndpoint() as ep2:  # 第二遍：不装剧本——任何请求都会 500
                model2 = demo.model_for_url(ep2.url)
                second = await cached_complete(cache, model2, _planner_messages(), "mock-model")
                requests2 = len(ep2.requests)
        return first, second, requests1, requests2

    first, second, requests1, requests2 = asyncio.run(scenario())
    assert requests1 == 1 and first == ("第一遍的原话", False)  # 第一遍真调用
    assert requests2 == 0 and second == ("第一遍的原话", True)  # 第二遍零请求、同文、命中标记


def test_audit_query_returns_full_original_text(tmp_path) -> None:
    """审计查询：完整原话（prompt 全文 + response 全文 + 模型名），不截断。"""

    async def scenario() -> str:
        db = tmp_path / "c.db"
        with DecisionCache(db, clock=lambda: "t") as cache:
            with MockLLMEndpoint() as ep:
                ep.script_text("response 原话全文")
                model = demo.model_for_url(ep.url)
                await cached_complete(cache, model, _planner_messages(), "mock-model")
            digest = prompt_hash("mock-model", _planner_messages())
            record = audit_query(cache, digest)
            assert record is not None
            return f"{record['model']}|{record['prompt']}|{record['response']}"

    text = asyncio.run(scenario())
    assert "mock-model" in text
    assert "你是规划器。" in text and "请规划 CLM-2026-0001 的取数步骤。" in text  # prompt 全文在场
    assert "response 原话全文" in text  # response 全文在场


def test_different_claim_does_not_falsely_hit(tmp_path) -> None:
    """不同单不误命中：prompt 内容不同 → 新 key → 真调用发生、响应是新的。"""

    async def scenario() -> tuple[int, str]:
        db = tmp_path / "c.db"
        with DecisionCache(db, clock=lambda: "t") as cache:
            with MockLLMEndpoint() as ep:
                ep.script_text("第一单的回答")
                model = demo.model_for_url(ep.url)
                await cached_complete(cache, model, _planner_messages(), "mock-model")
            other_messages = [
                {"role": "system", "content": "你是规划器。"},
                {"role": "user", "content": "请规划 CLM-2026-0004 的取数步骤。"},
            ]
            with MockLLMEndpoint() as ep2:
                ep2.script_text("第四单的回答")
                model2 = demo.model_for_url(ep2.url)
                text, hit = await cached_complete(cache, model2, other_messages, "mock-model")
                return len(ep2.requests), text

    requests, text = asyncio.run(scenario())
    assert requests == 1  # 换单 = 新 prompt = 真调用发生（不是第一单的缓存）
    assert text == "第四单的回答"
