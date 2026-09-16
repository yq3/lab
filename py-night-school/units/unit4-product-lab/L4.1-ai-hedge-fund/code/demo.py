"""全管线离线 demo：review_mock.json 四单逐单跑 run_intake，打印每单回执摘要。

离线确定性：MockLLMEndpoint + pipeline.SCRIPTS 剧本表 + 临时缓存目录。
每单用独立端点（请求计数按单归零）；缓存目录共享——同单重跑即命中（Step2 专门演示）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from cache import DecisionCache
from mock_endpoint import MockLLMEndpoint
from pipeline import CHECKER_WEIGHTS, run_intake, script_endpoint
from reviewers import HttpClient
from snapshot import build_snapshot


def _vote_line(vote) -> str:  # noqa: ANN001 -- Vote 具名导入会让行超长，讲义脚本从简
    if vote.metadata.get("abstained") is True:
        return f"{vote.checker:<11} 弃权      ({vote.reasoning[:36]}…)"
    if vote.checker == "rules":
        return f"{vote.checker:<11} {vote.score:+.2f} 规则表  ({vote.reasoning[:32]}…)"
    cached = "缓存" if vote.metadata.get("cached") else "请求"
    return f"{vote.checker:<11} {vote.score:+.2f} {cached}  ({vote.reasoning[:32]}…)"


def main() -> None:
    print("== L4.1 层级投票·报销初审：四单全跑（离线剧本） ==")
    print(f"权重表: {CHECKER_WEIGHTS}（rules 是零 LLM 的量化检查员）\n")
    with tempfile.TemporaryDirectory(prefix="l41-cache-") as tmp:
        cache = DecisionCache(Path(tmp))
        for claim_id in ("CLM-2026-0001", "CLM-2026-0002", "CLM-2026-0003", "CLM-2026-0004"):
            snapshot = build_snapshot(claim_id)
            with MockLLMEndpoint() as ep:
                script_endpoint(claim_id, ep)
                record = run_intake(claim_id, HttpClient(ep.url), cache)
                requests = len(ep.requests)
            print(f"-- {claim_id}（{snapshot.submitter}，{snapshot.purpose}）hash={record.claim_hash[:8]} --")
            for vote in record.votes:
                print(f"  {_vote_line(vote)}")
            print(
                f"  合成: conviction={record.conviction:+.4f}（弃权 "
                f"{sum(1 for v in record.votes if v.metadata.get('abstained'))} 票已从分子分母剔除）"
            )
            clamps = record.clamps or "无"
            print(f"  clamp: {clamps}")
            advice = record.advice
            print(
                f"  回执: {advice.decision} / {advice.reason} / 金额 {record.amount_before_cents}"
                f" -> {record.amount_after_cents} 分 / 剩余预算 {advice.remaining_cents} 分"
                f" / 模型请求 {requests} 次\n"
            )
        cache_files = len(list(Path(tmp).glob("*.json")))
    print(f"缓存目录留档: {cache_files} 个 JSON（一决定一文件=缓存即审计，Step2 细看）")


if __name__ == "__main__":
    main()
