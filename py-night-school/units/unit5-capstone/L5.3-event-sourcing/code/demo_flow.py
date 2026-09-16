"""L5.3 demo 三幕：三层审计件各自干什么，跑给你看（离线确定，固定钟）。

第一幕「全量落库」：四单跑一遍，事件表把每次 run 的全部事实按 seq 记账
（打印事件流水——type/seq 与 payload 摘要）；
第二幕「缓存全命中」：同一单第二遍，llm_decisions 全命中——零模型请求，
事件照常追加（run.started 第二条、seq 续着走），cost 分文不涨；
第三幕「改图作废旧账」：drafter 与 submit 之间加一个 audit_stamp 节点——
拓扑签名变 → 旧 run_key 续跑被 GraphVersionMismatch 拒绝（版本变了就别续旧账），
新 run_key 正常开新账（顺带观察：决策缓存按 prompt 寻址，不随图版本作废）。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import demo
import eventstore
import graph
import mock_tools
import versioning

CLOCK = demo.DEMO_CLOCK  # 固定演示钟：事件流的 created_at 两次运行逐字节相同


def _print_stream(store: eventstore.EventStore, run_key: str, limit: int | None = None) -> None:
    """打印一个聚合的事件流水（type/seq + payload 摘要）。"""
    rows = store.events_for(run_key)
    shown = rows if limit is None else rows[:limit]
    print(f"  {run_key}  {len(rows)} 条事件")
    for row in shown:
        summary = _summary(row)
        print(f"    seq {row['seq']:>2}  {row['type']:<14} {summary}")


def _summary(row: dict) -> str:
    payload = row["payload"]
    if row["type"] == "run.started":
        return f"claim={payload['claim_id']} graph_version={payload['graph_version'][:12]}… mode={payload['mode']}"
    if row["type"] == "intake.loaded":
        return f"{payload['dept']} 总额 {payload['total_cents']} 分 发票 {payload['invoice_ids']}"
    if row["type"] == "llm.decision":
        return f"node={payload['node']} cached={payload['cached']} prompt_hash={payload['prompt_hash'][:12]}…"
    if row["type"] == "cost.recorded":
        return f"node={payload['node']} prompt={payload['prompt_tokens']} completion={payload['completion_tokens']}"
    if row["type"] == "plan.approved":
        return f"{len(payload['steps'])} 步计划 claim_total={payload['claim_total_cents']} 分"
    if row["type"] == "plan.rejected":
        return f"reason={payload['reason_code']}"
    if row["type"] == "tool.called":
        return f"step={payload['step_id']} tool={payload['tool']} produces={payload['produces']}"
    if row["type"] == "advice.drafted":
        return f"{payload['decision']}/{payload['reason']} 剩余 {payload['remaining_cents']} 分"
    return str(payload)


async def act_one(db: Path) -> dict[str, str]:
    """第一幕：四单全量落库。返回 {claim_id: run_key} 供后两幕续用。"""
    print("== 第一幕：全量落库——四单跑一遍，事件表记下每一件事 ==")
    keys: dict[str, str] = {}
    for claim in mock_tools.claims_table():
        claim_id = claim["id"]
        result = await demo.run_audited(claim_id, db, mode=demo.CLAIM_MODES[claim_id], clock=lambda: CLOCK)
        keys[claim_id] = result["run_key"]
        print(f"[{claim_id}]（剧本 {demo.CLAIM_MODES[claim_id]}）模型请求 {result['requests']} 次")
    print()
    with eventstore.connect(db) as store:
        _print_stream(store, keys["CLM-2026-0001"])
        print("    …")
        _print_stream(store, keys["CLM-2026-0003"])
    print("  <- 0001 是干净路：12 条走到 submitted；0003 是超限哨兵：三轮拒绝后 advice.drafted(ESCALATE) 收尾、")
    print("     没有 tool.called（计划从未合法，工具一个都没被碰）、没有 submitted（不送审）——事件流水就是执行史")
    return keys


async def act_two(db: Path, keys: dict[str, str]) -> None:
    """第二幕：同一单第二遍——缓存全命中，零模型请求，事件照常追加。"""
    print()
    print("== 第二幕：缓存即审计——同一单第二遍，模型一个请求都没收到 ==")
    before: dict[str, int] = {}
    with eventstore.connect(db) as store:
        before["events"] = len(store.events_for(keys["CLM-2026-0001"]))
        before["cost"] = len(store.events_for(keys["CLM-2026-0001"], type="cost.recorded"))
    result = await demo.run_audited("CLM-2026-0001", db, mode="clean", clock=lambda: CLOCK)
    print(f"  第二遍模型请求: {result['requests']} 次（第一遍是 2 次——想花钱都没门）")
    with eventstore.connect(db) as store:
        run_key = keys["CLM-2026-0001"]
        after = {
            "events": len(store.events_for(run_key)),
            "cost": len(store.events_for(run_key, type="cost.recorded")),
            "runs": len(store.events_for(run_key, type="run.started")),
        }
        decisions = store.events_for(run_key, type="llm.decision")
        print(f"  事件 {before['events']} → {after['events']} 条（run.started 第 {after['runs']} 条、seq 接着走）")
        print(f"  cost.recorded 仍 {after['cost']} 条（命中不花钱）；llm.decision 共 {len(decisions)} 条:")
        for row in decisions:
            p = row["payload"]
            print(f"    seq {row['seq']:>2}  node={p['node']:<8} cached={p['cached']}")
        print("  <- 缓存命中不等于没有账：llm.decision(cached=True) 照样留痕——「这轮的决策来自缓存」也是审计事实")


async def act_three(db: Path, keys: dict[str, str]) -> None:
    """第三幕：改图——签名变，旧 run_key 续跑被拒，新 run_key 开新账。"""
    print()
    print("== 第三幕：图版本绑定——加一个节点，旧账作废 ==")
    stamp_build = lambda m, recorder, cache: graph.build_graph(m, recorder, cache, extra_stamp=True)  # noqa: E731 —— 演示用一行装配变体
    old_key = keys["CLM-2026-0004"]
    fresh = await demo.run_audited("CLM-2026-0004", db, mode="clean", clock=lambda: CLOCK)
    assert fresh["run_key"] == old_key  # 同图同单：run_key 稳定（对照断言，不是演示假设）
    with eventstore.connect(db) as store:
        old_version = store.events_for(old_key, type="run.started")[0]["payload"]["graph_version"]
    print(f"  改图前: 签名 {old_version[:12]}…  run_key {old_key}")
    try:
        await demo.run_audited(
            "CLM-2026-0004", db, mode="clean", clock=lambda: CLOCK, aggregate=old_key, graph_builder=stamp_build
        )
        print("  意外：旧 run_key 竟然续上了？")
    except versioning.GraphVersionMismatch as exc:
        print("  改图后（+audit_stamp 节点）拿旧 run_key 续跑: 被拒")
        print(f"    GraphVersionMismatch: {exc}")
    new_run = await demo.run_audited("CLM-2026-0004", db, mode="clean", clock=lambda: CLOCK, graph_builder=stamp_build)
    print(f"  新 run_key {new_run['run_key']}（签名 {new_run['graph_version'][:12]}…）正常开新账:")
    with eventstore.connect(db) as store:
        _print_stream(store, new_run["run_key"])
        print("  <- 两个可复用的观察：①旧事件一条没动（append-only），作的废是「续跑权」不是历史；")
        print("     ②llm.decision 无 cost.recorded——决策缓存按 prompt 寻址，不随图版本作废（拓扑不改变模型的输入）")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "audit.db"
        keys = asyncio.run(act_one(db))
        asyncio.run(act_two(db, keys))
        asyncio.run(act_three(db, keys))
        print()
        print(f"（审计库 {db.name} 在系统临时目录，演示结束自动销毁——克隆即学，不写学员主目录）")


if __name__ == "__main__":
    main()
