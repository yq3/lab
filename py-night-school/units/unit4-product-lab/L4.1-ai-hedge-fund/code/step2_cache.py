"""Step2 缓存即审计：同一张单跑两遍，第二遍零请求（ep.requests 取证）。

对版 llm/cache.py 的三合一主张逐条落地：
  缓存——第二遍 0 次 HTTP、三票全部 cached=True、回执逐字段一致；
  审计——每个 JSON 文件含 system/user/response/parsed/claim_hash/created_at；
  调试——CLM-2026-0002 的 budget 台词不含 JSON，parse_error 连原始响应一起留盘。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cache import DecisionCache
from mock_endpoint import MockLLMEndpoint
from pipeline import run_intake, script_endpoint
from reviewers import HttpClient


def main() -> None:
    print("== Step2 缓存即审计：同一张单跑两遍 ==")
    with tempfile.TemporaryDirectory(prefix="l41-step2-") as tmp:
        cache = DecisionCache(Path(tmp))

        with MockLLMEndpoint() as ep1:
            script_endpoint("CLM-2026-0001", ep1)
            first = run_intake("CLM-2026-0001", HttpClient(ep1.url), cache)
            n1 = len(ep1.requests)
        print(f"[第一遍 冷缓存] 模型请求 {n1} 次（compliance/budget/invoice 各一；rules 零 LLM）")

        with MockLLMEndpoint() as ep2:  # 新端点且不装剧本：任何请求都会 500——取证更硬
            second = run_intake("CLM-2026-0001", HttpClient(ep2.url), cache)
            n2 = len(ep2.requests)
        cached_votes = [v.metadata.get("cached") for v in second.votes if v.checker != "rules"]
        print(f"[第二遍 同缓存目录] 模型请求 {n2} 次（ep2.requests 为空——想花钱都没门）")
        print(f"  三个人格票 cached 标记: {cached_votes}")
        print(
            f"  回执一致: advice={second.advice == first.advice} / conviction={second.conviction == first.conviction}"
        )

        files = sorted(Path(tmp).glob("*.json"))
        print(f"\n[缓存目录] {len(files)} 个 JSON——一决定一文件：")
        for path in files:
            record = json.loads(path.read_text(encoding="utf-8"))
            kind = "parsed" if "parsed" in record else "parse_error"
            claim_hash = str(record.get("claim_hash", "-"))[:8]
            print(f"  {path.name}  checker={record['checker']:<11} {kind}  claim_hash={claim_hash}…")
        print("  每颗文件同时是缓存条目、审计记录（system/user/response 全在）、调试踪迹")

        print("\n[调试踪迹] CLM-2026-0002 的 budget 票：台词不含 JSON -> 弃权 + 留盘")
        with MockLLMEndpoint() as ep3:
            script_endpoint("CLM-2026-0002", ep3)
            record2 = run_intake("CLM-2026-0002", HttpClient(ep3.url), cache)
        bad = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(tmp).glob("*.json"))
            if "parse_error" in p.read_text(encoding="utf-8")
        ]
        vote = next(v for v in record2.votes if v.checker == "budget")
        print(f"  budget 票: abstained={vote.metadata.get('abstained')}  score={vote.score}")
        print(f"  留盘文件: parse_error={bad[0]['parse_error'][:52]}…")
        print(f"  原始响应原样在盘: response={bad[0]['response']}（重放/排查两不误）")


if __name__ == "__main__":
    main()
