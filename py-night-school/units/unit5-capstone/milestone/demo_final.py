"""L5.4 毕业演示：三条主链路全流程预演——里程碑集成测试的雏形（讲义 §3 主线）。

一条服务、一张审计库、四层合体（图 + 审批 + 事件 + 门），跑通报告 §4.6 第二期
「受控执行」的三条主链路：
- 链路① 审批暂停→恢复：建 run → interrupt 暂停 → reply once → 门 ALLOW →
  payment.executed（付款落账本）；
- 链路② 拒绝回环：reply reject+留言 → 回 drafter 重生成 → 新审批单（content_hash 变）→
  批准 → 过门付款（人审否决了修订版的 ESCALATE 建议——权威在审批面，A1）；
- 链路③ fail-closed 拒绝：换紧合同（单笔上限 5000 分）→ 8800 分的提案过门 →
  定量超限 PAUSE → 未付款 → gate.denied 事件 + ESCALATE 终态（REJECT:GATE_REAUTH_REQUIRED）。

每链路打印事件流水（type/seq）+ 终态 advice——这三段就是里程碑要长成的 pytest 集成测试
（断言点：事件序列、paid_cents、终态 reason、当日账本）。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import approvals
import audit_cache
import eventstore
import gate
import graph
import versioning

TODAY = graph.DEFAULT_TODAY
TIGHT_POLICY = gate.Policy(  # 链路③的紧合同：单笔上限 5000 分（0002 总额 8800 分必超）
    max_single_cents=5_000,
    max_daily_total_cents=1_000_000,
    max_payments_per_day=50,
    vendor_blocklist=(),
)
CLOCK = "2026-09-16T21:00:00+00:00"


def _print_stream(store: eventstore.EventStore, run_key: str, note: str = "") -> None:
    """打印一个聚合的事件流水（type/seq）——审计面的「执行史」读法。"""
    rows = store.events_for(run_key)
    print(f"    事件流水（{run_key}，{len(rows)} 条）：")
    for row in rows:
        print(f"      seq {row['seq']:>2}  {row['type']:<16} {_summary(row)}")
    if note:
        print(f"    {note}")


def _summary(row: dict) -> str:
    payload = row["payload"]
    if row["type"] == "run.started":
        return f"claim={payload['claim_id']} graph_version={payload['graph_version'][:12]}…"
    if row["type"] == "intake.loaded":
        return f"{payload['dept']} 总额 {payload['total_cents']} 分"
    if row["type"] == "plan.approved":
        return f"{len(payload['steps'])} 步计划 claim_total={payload['claim_total_cents']} 分"
    if row["type"] == "tool.called":
        return f"{payload['step_id']} {payload['tool']}→{payload['produces']}"
    if row["type"] == "llm.decision":
        return f"node={payload['node']} cached={payload['cached']}"
    if row["type"] == "cost.recorded":
        return f"node={payload['node']} prompt={payload['prompt_tokens']} completion={payload['completion_tokens']}"
    if row["type"] == "advice.drafted":
        return f"{payload['decision']}/{payload['reason']} 剩余 {payload['remaining_cents']} 分"
    if row["type"] == "gate.checked":
        return f"{payload['action']}/{payload['reason_code']} 金额 {payload['amount_cents']} 分"
    if row["type"] == "payment.executed":
        clamp = f"（clamp 自 {payload['amount_cents']} 分）" if payload.get("clamp_cents") else ""
        return f"{payload['vendor']}({payload['dept']}) 实付 {payload['paid_cents']} 分{clamp}"
    if row["type"] == "gate.denied":
        return f"{payload['action']}/{payload['reason_code']}"
    if row["type"] == "submitted":
        return "送审完成"
    return ""


def _print_report(report: dict) -> None:
    print(f"    图内审计流水: {report['events']}")
    paid = report["paid_cents"] if report["paid_cents"] is not None else "未付款"
    print(f"    终态 advice: {report['decision']} / {report['reason']} / paid={paid}")


async def _ticket_of(service: approvals.ApprovalService, run_id: str) -> dict:
    """取 run 当前唯一待审单（轮询待审总表——工作台视角，5s 上限）。"""
    for _ in range(500):
        rows = await service.pending_approvals()
        for row in rows:
            if row["run_id"] == run_id:
                return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"ticket for {run_id} never appeared")


async def link_one(db: Path, ckpt: Path) -> None:
    """链路①：审批暂停→恢复→门 ALLOW→付款。"""
    print("== 链路① 审批暂停→恢复：建 run → interrupt 暂停 → reply once → 门 ALLOW → payment.executed ==")
    async with graph.open_saver(str(ckpt)) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            cache = audit_cache.DecisionCache(db, clock=lambda: CLOCK)
            service = approvals.ApprovalService(
                saver, store=store, cache=cache, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0001")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            print(f"  [start_run 0001 → {run_id}] 待审单 {ticket['ticket_id']} 挂在 {ticket['graph_next']}")
            print(f"    （interrupt 暂停——等人的不是线程，是 checkpoint；advice={ticket['advice']}）")
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            _print_report(report)
            cache.close()
            _print_stream(store, report["run_key"])
            print("    <- 批准只是授权：submitted 之后 gate.checked→payment.executed——执行出口二次校验过才付款（A7）")
    print()


async def link_two(db: Path, ckpt: Path) -> None:
    """链路②：拒绝回环——驳回留言回喂重生成，新审批单（新 hash），批准后过门。"""
    print("== 链路② 拒绝回环：reject+留言 → 回 drafter 重生成 → 新审批单（hash 变）→ 批准 → 过门 ==")
    async with graph.open_saver(str(ckpt)) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            cache = audit_cache.DecisionCache(db, clock=lambda: CLOCK)
            service = approvals.ApprovalService(
                saver, store=store, cache=cache, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0001")
            await service.wait_run(run_id)
            first = await _ticket_of(service, run_id)
            print(f"  [start_run 0001 → {run_id}] 首版建议单 {first['ticket_id']}（hash={first['content_hash']}）")
            await service.reply(first["ticket_id"], "reject", message="客户拜访餐费需补充三级审批单")
            second = await _ticket_of(service, run_id)
            new_hash = second["content_hash"]
            print(f"  [reply reject+留言] 图回 drafter 重生成 → 新单 {second['ticket_id']}（hash={new_hash}）")
            print(f"    hash 变了：{first['content_hash']} != {second['content_hash']} ——批的是新一版内容（A6）")
            await service.reply(second["ticket_id"], "once")
            report = await service.run_report(run_id)
            _print_report(report)
            cache.close()
            _print_stream(store, report["run_key"])
            print("    <- 修订版建议单是 ESCALATE（按留言转人工），审批人仍批准——权威在审批面（A1），")
            print("       门只再查结构/定量安全；事件表里两条 advice.drafted 就是这次改稿的审计证据")
    print()


async def link_three(db: Path, ckpt: Path) -> None:
    """链路③：fail-closed 拒绝——紧合同下超限提案不付款，gate.denied + ESCALATE。"""
    print("== 链路③ fail-closed 拒绝：超 Policy 单笔上限的提案 → 门不付款 → gate.denied → ESCALATE ==")
    async with graph.open_saver(str(ckpt)) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            service = approvals.ApprovalService(
                saver, store=store, policy=TIGHT_POLICY, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0002")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            cap = TIGHT_POLICY.max_single_cents
            print(f"  [start_run 0002 → {run_id}] 提案总额 {ticket['total_cents']} 分 > 紧合同单笔上限 {cap} 分")
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            _print_report(report)
            _print_stream(store, report["run_key"])
            print("    <- 审批批了、门不放行：定量超限是 PAUSE_FOR_REAUTH（升额改的是 Policy 合同，")
            print("       不是图内回环能解决的事）——audit 上 gate.denied 记「没付」，payload.action 记「哪一态」")
    print()


async def finale(db: Path) -> None:
    """压轴：当日账本 + 图版本——事件表即账本、签名即身份。"""
    print("== 压轴：事件表即账本（当日已付清单 = payment.executed 投影）＋ 图版本 ==")
    with eventstore.connect(db, clock=lambda: CLOCK) as store:
        day_rows = store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
        print(f"  ledger:{TODAY} 当日已付 {len(day_rows)} 笔：")
        for row in day_rows:
            p = row["payload"]
            print(f"    seq {row['seq']}  {p['claim_id']}  {p['vendor']}({p['dept']})  {p['paid_cents']} 分")
        print("  <- 限额/频次的「世界状态」就是这条聚合的投影——没有第二张账本表（L5.3 的延续）")
        from demo import model_for_url  # 局部 import：只为求签名

        signature = versioning.topology_signature(graph.build_graph(model_for_url("http://unused.local/v1")))
        print(f"  L5.4 图拓扑签名: {signature[:12]}…（L5.3 是 5dbfa594e113…——多了 execute 节点）")
        print("  <- 图一改，run_key 换世界：同一单的旧 checkpoint/旧聚合自动作废（L5.3 图版本绑定的活教材）")


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        await link_one(root / "audit.db", root / "ckpt1.sqlite3")
        await link_two(root / "audit2.db", root / "ckpt2.sqlite3")
        await link_three(root / "audit3.db", root / "ckpt3.sqlite3")
        await finale(root / "audit.db")
        print()
        print("（审计库与 checkpoint 都在系统临时目录，演示结束自动销毁——克隆即学，不写学员主目录）")


if __name__ == "__main__":
    asyncio.run(main())
