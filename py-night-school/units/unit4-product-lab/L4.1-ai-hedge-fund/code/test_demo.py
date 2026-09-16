"""讲义区验收：机制件的数学与边界（与 exercises/ 的改造题互补——这里管机制本身）。

覆盖五块：blend 数学与边界 / cache 命中与留盘 / clamp 三纪律 / 四单管线端到端 /
Reviewer ABC 契约（外加快照哈希与规则表走查）。全部离线：MockLLMEndpoint + 剧本表。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import blend
import cache as cache_mod
import limits
import pipeline
import reviewers
from cache import DecisionCache, decision_key
from mock_endpoint import MockLLMEndpoint
from review import Vote
from reviewers import ComplianceReviewer, HttpClient, Reviewer, RuleChecker
from snapshot import ClaimSnapshot, build_snapshot

EXPECT = {  # 与 data/expense/review_mock.json 的 expect_* 同表（明线的判分依据）
    "CLM-2026-0001": ("APPROVE", "PASS", 10000),
    "CLM-2026-0002": ("REJECT", "REJECT:ITEM_OVER_LIMIT", 10000),
    "CLM-2026-0003": ("ESCALATE", "REJECT:INVALID_AMOUNT", 40000),
    "CLM-2026-0004": ("REJECT", "REJECT:INVOICE_INVALID", 40000),
}


def _vote(checker: str, score: float, abstained: bool = False) -> Vote:
    metadata = {"abstained": True} if abstained else {}
    return Vote(checker=checker, claim_id="CLM-TEST", score=score, metadata=metadata)


def _run(claim_id: str, cache: DecisionCache) -> tuple:
    """带剧本跑一趟 run_intake，返回 (record, 请求数)。"""
    with MockLLMEndpoint() as ep:
        pipeline.script_endpoint(claim_id, ep)
        record = pipeline.run_intake(claim_id, HttpClient(ep.url), cache)
        return record, len(ep.requests)


# ---- blend：数学与边界 ----


def test_blend_weighted_mean_is_exact() -> None:
    """加权平均：含小数的精确断言（分子分母各自怎么来的，逐项可手算）。"""
    votes = [_vote("compliance", 0.8), _vote("budget", -0.6), _vote("invoice", 0.9)]
    weights = {"compliance": 1.0, "budget": 2.0, "invoice": 0.5}
    result = blend.weighted_vote(votes, weights)
    assert result.conviction == pytest.approx((0.8 + 2.0 * -0.6 + 0.5 * 0.9) / 3.5)
    assert result.voters == ["compliance", "budget", "invoice"]
    assert result.abstained == []


def test_blend_abstain_excluded_from_numerator_and_denominator() -> None:
    """弃权票：分子分母同剔——「没意见」不能冒充「意见：中性」。"""
    votes = [_vote("compliance", 0.8), _vote("budget", 0.0, abstained=True), _vote("invoice", 0.6)]
    result = blend.weighted_vote(votes, {"compliance": 1.0, "budget": 3.0, "invoice": 1.0})
    assert result.conviction == pytest.approx((0.8 + 0.6) / 2.0)  # budget 的权重 3.0 完全不参与
    assert result.voters == ["compliance", "invoice"]
    assert result.abstained == ["budget"]


def test_blend_all_abstain_and_zero_weights_return_none() -> None:
    """显式边界：全弃权 / 权重全零 -> conviction 是 None（不是 0.0）——下游据此转人审。"""
    all_abstain = blend.weighted_vote(
        [_vote("compliance", 0.0, abstained=True), _vote("budget", 0.0, abstained=True)],
        {"compliance": 1.0, "budget": 1.0},
    )
    assert all_abstain.conviction is None
    zero_weights = blend.weighted_vote([_vote("compliance", 0.8)], {"compliance": 0.0})
    assert zero_weights.conviction is None


def test_blend_weights_change_the_outcome() -> None:
    """meta：同一组票换权重表，结果必须变——权重即话语权。"""
    votes = [_vote("compliance", 0.8), _vote("budget", -0.6)]
    light = blend.weighted_vote(votes, {"compliance": 1.0, "budget": 0.5})
    heavy = blend.weighted_vote(votes, {"compliance": 1.0, "budget": 3.0})
    assert light.conviction == pytest.approx((0.8 - 0.3) / 1.5)
    assert heavy.conviction == pytest.approx((0.8 - 1.8) / 4.0)
    assert light.conviction is not None and heavy.conviction is not None
    assert light.conviction > 0 > heavy.conviction  # 同一组票，话语权翻转了结论


# ---- cache：命中、留盘、损坏 ----


def test_cache_second_intake_is_zero_http(tmp_path: Path) -> None:
    """缓存即缓存：同单第二趟 0 次 HTTP，回执与第一趟一致（ep.requests 取证）。"""
    cache = DecisionCache(tmp_path)
    first, n1 = _run("CLM-2026-0001", cache)
    second, n2 = _run("CLM-2026-0001", cache)
    assert n1 == 3  # 三个人格各一次
    assert n2 == 0  # 全部命中，一分钱不花
    assert second.advice == first.advice
    assert second.conviction == pytest.approx(first.conviction)
    assert all(v.metadata["cached"] is True for v in second.votes if v.checker != "rules")


def test_cache_parse_error_keeps_raw_response_on_disk(tmp_path: Path) -> None:
    """缓存即调试踪迹：解析失败的原始响应留盘（0002 的 budget 台词不含 JSON）。"""
    cache = DecisionCache(tmp_path)
    record, _n = _run("CLM-2026-0002", cache)
    vote = next(v for v in record.votes if v.checker == "budget")
    assert vote.metadata["abstained"] is True  # 失败即弃权
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 3  # 一决定一文件：两票成功 + 一票 parse_error
    bad = [json.loads(p.read_text(encoding="utf-8")) for p in files if "parse_error" in p.read_text(encoding="utf-8")]
    assert len(bad) == 1
    assert bad[0]["checker"] == "budget"
    assert bad[0]["response"] == "这单预算没问题，我同意。"  # 原始响应原样在盘
    assert bad[0]["claim_hash"] == record.claim_hash  # 审计绑定：哪张单的快照


def test_cache_corrupt_file_is_a_miss(tmp_path: Path) -> None:
    """损坏条目当 miss：get 不炸、返回 None（下一次 put 会重写）。"""
    cache = DecisionCache(tmp_path)
    key = decision_key("compliance", "mock-model", "s", "u")
    (tmp_path / f"{key}.json").write_text("{ 这不是 JSON", encoding="utf-8")
    assert cache.get(key) is None


def test_decision_key_is_deterministic_and_content_addressed() -> None:
    """key 的两条纪律：同输入同 key；任一输入变了 key 必须变（内容寻址）。"""
    a = decision_key("compliance", "mock-model", "system", "user")
    assert a == decision_key("compliance", "mock-model", "system", "user")
    assert len(a) == 24  # sha256 hex 截前 24 位
    assert a != decision_key("budget", "mock-model", "system", "user")
    assert a != decision_key("compliance", "other-model", "system", "user")
    assert a != decision_key("compliance", "mock-model", "system", "user2")


# ---- limits：三纪律 + 幂等 ----


def test_limits_single_cap_fires_before_total_and_order_is_recorded() -> None:
    """先单后总：单笔事件在前、批次级事件在后，金额与事件逐条对得上。"""
    result = limits.apply_limits({"A": 8000, "B": 6000}, 5000, 8000)
    assert result.amounts == {"A": 4000, "B": 4000}
    kinds = [c.limit for c in result.clamps]
    assert kinds == ["max_single_cents", "max_single_cents", "max_dept_total_cents"]
    single_a, single_b, total = result.clamps
    assert (single_a.item, single_a.before, single_a.after) == ("A", 8000, 5000)
    assert (single_b.item, single_b.before, single_b.after) == ("B", 6000, 5000)
    assert (total.item, total.before, total.after) == (None, 10000, 8000)


def test_limits_only_shrink_never_grow_and_floor_keeps_sum_under_cap() -> None:
    """只缩不放：低于上限的金额一个不动；等比缩 floor 后总和不超过上限。"""
    untouched = limits.apply_limits({"A": 3000, "B": 800}, 5000, 4000)
    assert untouched.amounts == {"A": 3000, "B": 800}
    assert untouched.clamps == []
    awkward = limits.apply_limits({"A": 3334, "B": 3333, "C": 3333}, 5000, 8000)
    assert awkward.amounts == {"A": 2667, "B": 2666, "C": 2666}  # floor(0.8*x)
    assert sum(awkward.amounts.values()) == 7999 <= 8000
    assert all(after <= before for after, before in zip(awkward.amounts.values(), (3334, 3333, 3333), strict=False))


def test_limits_idempotent_double_run() -> None:
    """幂等：apply(apply(x)) 与 apply(x) 全等，第二遍零事件。"""
    first = limits.apply_limits({"A": 8000, "B": 6000}, 5000, 8000)
    second = limits.apply_limits(first.amounts, 5000, 8000)
    assert second.amounts == first.amounts
    assert second.clamps == []


# ---- 管线端到端：四单 ----


def test_pipeline_four_claims_end_to_end() -> None:
    """四单全跑：decision/reason/剩余预算逐单对表；票数、clamp、hash 各就各位。"""
    with tempfile.TemporaryDirectory(prefix="l41-test-") as tmp:
        cache = DecisionCache(tmp)
        for claim_id, (decision, reason, remaining) in EXPECT.items():
            record, requests = _run(claim_id, cache)
            advice = record.advice
            assert advice.decision == decision, claim_id
            assert advice.reason == reason, claim_id
            assert advice.remaining_cents == remaining, claim_id
            assert len(record.votes) == 4  # 三人格 + 规则表
            assert record.claim_hash == build_snapshot(claim_id).content_hash
            assert record.amount_before_cents == build_snapshot(claim_id).total_cents
            assert requests == 3  # 每单恰好三次模型请求（冷缓存）
        # 0002 的单笔超标被砍到上限（虽然整单已被拒绝——回执仍要记刀）
        record2, _ = _run("CLM-2026-0002", DecisionCache(tmp))
        assert record2.amount_before_cents == 8800
        assert record2.amount_after_cents == 5000
        assert [c.after for c in record2.clamps] == [5000]
        # 0003：conviction 为负但脏数据优先转人审（决策门的短路顺序）
        record3, _ = _run("CLM-2026-0003", DecisionCache(tmp))
        assert record3.conviction is not None and record3.conviction < 0
        assert record3.advice.decision == "ESCALATE"


def test_pipeline_rules_checker_never_calls_the_llm(tmp_path: Path) -> None:
    """混编证据：RuleChecker 是零 LLM 的量化检查员——单独调用不产生任何 HTTP。"""
    with MockLLMEndpoint() as ep:  # 不装剧本：任何请求都会 500
        vote = RuleChecker().review(build_snapshot("CLM-2026-0001"))
    assert ep.requests == []
    assert vote.checker == "rules"
    assert vote.metadata["rule_code"] == "PASS"
    assert vote.score == pytest.approx(0.85)


def test_decide_gate_all_abstained_escalates(tmp_path: Path) -> None:
    """决策门的显式边界：全弃权 -> ESCALATE，不捏造中性（合成层 None 的下游语义）。"""
    advice = pipeline._decide("CLM-TEST", "PASS", None, 1000)
    assert (advice.decision, advice.reason) == ("ESCALATE", "REJECT:ALL_ABSTAINED")
    soft_reject = pipeline._decide("CLM-TEST", "PASS", -0.1, 1000)
    assert (soft_reject.decision, soft_reject.reason) == ("REJECT", "REJECT:CHECKER_VOTE")
    approve = pipeline._decide("CLM-TEST", "PASS", 0.42, 1000)
    assert (approve.decision, approve.reason) == ("APPROVE", "PASS")


# ---- Reviewer ABC 契约 ----


def test_reviewer_abc_contract() -> None:
    """ABC 契约：抽象类不可实例化；人格与规则表同属 Reviewer、name 全队唯一。"""
    with pytest.raises(TypeError):
        Reviewer()  # type: ignore[abstract]
    with MockLLMEndpoint() as ep:
        client = HttpClient(ep.url)
        personas = [
            reviewers.ComplianceReviewer(client, DecisionCache("/tmp/l41-unused-1")),
            reviewers.BudgetReviewer(client, DecisionCache("/tmp/l41-unused-2")),
            reviewers.InvoiceReviewer(client, DecisionCache("/tmp/l41-unused-3")),
        ]
    checkers: list[Reviewer] = [*personas, RuleChecker()]
    assert all(isinstance(c, Reviewer) for c in checkers)
    names = [c.name for c in checkers]
    assert sorted(names) == ["budget", "compliance", "invoice", "rules"]
    assert set(names) == set(pipeline.CHECKER_WEIGHTS)  # 权重表与队伍对齐


def test_persona_is_just_a_system_prompt() -> None:
    """对版 buffett.py：人格 = name + system prompt；基类只认这两个表面。"""
    with MockLLMEndpoint() as ep:
        persona = ComplianceReviewer(HttpClient(ep.url), DecisionCache("/tmp/l41-unused-4"))
    assert persona.name == "compliance"
    assert "stance" in persona.get_system_prompt()  # schema 写在人格里

    class Bare(reviewers.LLMCheckerBase):  # 只补 name、不补 prompt——基类必须拒绝服务
        @property
        def name(self) -> str:
            return "bare"

    with pytest.raises(NotImplementedError):
        Bare(HttpClient("http://127.0.0.1:9"), DecisionCache("/tmp/l41-unused-5")).get_system_prompt()


# ---- 快照与规则表 ----


def _synth(items: dict[str, int], total: int, invoice_valid: bool, remaining: int) -> ClaimSnapshot:
    return ClaimSnapshot(
        claim_id="CLM-SYNTH",
        submitter="合成",
        purpose="规则表走查",
        items=items,
        total_cents=total,
        dept="DEV",
        remaining_cents=remaining,
        invoice_ids=["INV-SYNTH"],
        invoice_valid=invoice_valid,
        invoice_reason="",
    )


def test_snapshot_hash_is_stable_and_sensitive() -> None:
    """内容寻址：同数据同 hash；内容一变 hash 必变；render() 携带关键事实。"""
    snap1 = build_snapshot("CLM-2026-0001")
    snap2 = build_snapshot("CLM-2026-0001")
    assert snap1.content_hash == snap2.content_hash  # 同数据不二次付费的地基
    changed = snap1.model_copy(update={"total_cents": snap1.total_cents + 1})
    assert changed.content_hash != snap1.content_hash
    text = snap1.render()
    assert "CLM-2026-0001" in text and "7100" in text and "10000" in text  # 事实验证过才给 LLM


def test_rule_checker_walkthrough_all_five_rules() -> None:
    """规则表全走查：五条规则各配一个合成快照（mock 四单只命中 1/2/3/5，
    规则 4 总额超预算无用例触达——留白由合成入参补上，L3.2 同款纪律）。"""
    cases = [
        ("规则1 非正数金额", _synth({"明细1": -100}, -100, True, 40000), "INVALID_AMOUNT"),
        ("规则2 单笔超限", _synth({"明细1": 6000}, 6000, True, 40000), "ITEM_OVER_LIMIT"),
        ("规则3 发票未过", _synth({"明细1": 1000}, 1000, False, 40000), "INVOICE_INVALID"),
        (
            "规则4 总额超预算",
            _synth({"明细1": 4000, "明细2": 4000, "明细3": 3000}, 11000, True, 10000),
            "BUDGET_EXCEEDED",
        ),
        ("规则5 全不命中", _synth({"明细1": 1000, "明细2": 2000}, 3000, True, 40000), "PASS"),
    ]
    checker = RuleChecker()
    for name, snap, code in cases:
        assert checker.rule_code(snap) == code, name
        vote = checker.review(snap)
        expected_score = 0.85 if code == "PASS" else -0.95
        assert vote.score == pytest.approx(expected_score), name
        assert vote.metadata["rule_code"] == code


def test_cache_module_stays_small() -> None:
    """meta：讲义量化结论对码——本课 cache.py 的三合一机制确实小巧（口径：文本行数）。"""
    lines = len((Path(cache_mod.__file__).read_text(encoding="utf-8")).splitlines())
    assert lines < 60  # 「一决定一文件」的全部机制不到 60 行——产品同款 48 行量级
