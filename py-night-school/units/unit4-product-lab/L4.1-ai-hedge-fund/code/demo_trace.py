"""单细看 demo：挑一张单（默认 CLM-2026-0002——弃权 + clamp + 拒绝俱全）打印全管线轨迹。

对照 run_cycle 的「一个 tick」：快照 -> 逐票 -> 合成 -> clamp -> 回执，
每一步的输入输出都看得见——这就是 CycleRecord 式回执存在的意义。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from cache import DecisionCache
from mock_endpoint import MockLLMEndpoint
from pipeline import CHECKER_WEIGHTS, LLM_CHECKER_ORDER, SCRIPTS, run_intake, script_endpoint
from reviewers import HttpClient
from snapshot import build_snapshot


def main() -> None:
    claim_id = sys.argv[1] if len(sys.argv) > 1 else "CLM-2026-0002"
    print(f"== L4.1 层级投票·报销初审：{claim_id}（离线剧本） ==")
    snapshot = build_snapshot(claim_id)
    print("== ① 快照（检查员被允许知道的全部；render() 即 user prompt） ==")
    print(snapshot.render())
    print(f"content_hash = {snapshot.content_hash}（model_dump_json 的确定性序列化 -> sha256 截 24 位）\n")

    with tempfile.TemporaryDirectory(prefix="l41-trace-") as tmp:
        cache = DecisionCache(Path(tmp))
        with MockLLMEndpoint() as ep:
            script_endpoint(claim_id, ep)
            record = run_intake(claim_id, HttpClient(ep.url), cache)
            requests = list(ep.requests)

        print("== ② 逐票（零通信：每个检查员独立对同一快照投票，互相看不见） ==")
        for vote in record.votes:
            meta = vote.metadata
            if meta.get("abstained") is True:
                print(f"  [{vote.checker:<11}] 弃权  reason={meta.get('abstain_reason', '')[:60]}")
            else:
                key = meta.get("prompt_key")
                extras = f"prompt_key={key[:8]}…" if key else "零 LLM"
                print(f"  [{vote.checker:<11}] score={vote.score:+.2f}  {extras}  {(vote.reasoning or '')[:40]}")
        print(f"（剧本台词按调用顺序入队：{'/'.join(LLM_CHECKER_ORDER)}；rules 零 LLM）\n")

        print("== ③ 合成（纯算术，弃权从分子分母同剔） ==")
        voting = [v for v in record.votes if not v.metadata.get("abstained")]
        for vote in voting:
            w = CHECKER_WEIGHTS[vote.checker]
            print(f"  {w} * ({vote.score:+.4f}) = {w * vote.score:+.4f}   <- {vote.checker}")
        conviction = record.conviction
        assert conviction is not None  # 四单剧本里至少 rules 永远投票
        print(f"  conviction = {conviction:+.6f}\n")

        print("== ④ 风控 clamp（先单笔封顶再总额等比缩，只缩不放） ==")
        if record.clamps:
            for clamp in record.clamps:
                item = clamp.item if clamp.item is not None else "（批次级）"
                print(f"  {clamp.limit}: {item} {clamp.before} -> {clamp.after} 分")
        else:
            print("  两道上限都没触发，零事件")
        print(f"  金额: {record.amount_before_cents} -> {record.amount_after_cents} 分\n")

        print("== ⑤ 回执（ReviewRecord——对版 CycleRecord 的「一个 tick 的完整真相」） ==")
        advice = record.advice
        print(f"  {advice.decision} / {advice.reason} / 剩余预算 {advice.remaining_cents} 分")
        print("  留档: 每票 reasoning+prompt_key、合成前后金额、clamps——回放免费")
        n_cache = len(list(Path(tmp).glob("*.json")))
        print(f"  模型请求: {len(requests)} 次（3 个人格各 1 次；rules 0 次；缓存目录 {n_cache} 个 JSON）")
        if claim_id in SCRIPTS and "stance" not in SCRIPTS[claim_id].get("budget", ""):
            print("  备注: 本单 budget 的剧本台词不含 JSON -> parse_error 留盘（Step2 看那颗文件）")


if __name__ == "__main__":
    main()
