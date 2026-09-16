"""审批域服务：待审表、事件表、规则簿与挂起 run 的总管家（本课核心之二）。

把 opencode 的审批外化 API 组（report.md §2.1 A1/A2/A6）落成 Python：
- ApprovalService：run 的生命周期（起跑到暂停 / 回复后恢复）+ 审批单登记 + 三元回复；
- EventLog：append-only 事件表（内存版）——订阅 = 先重放历史再接实时（A2「审批是
  可重放事件」：无人订阅不丢单，单在 pending 表里；重订阅即重放）；
- RuleBook：always 规则簿（A6「批准并记住=可审计规则修订」）——每条规则带审批人/
  时间/内容 hash，是「谁、何时、批了什么」的账，不是内存 yes 集合。

分层纪律：本模块不 import fastapi——审批域逻辑离线可测（test_approvals 直接打服务面），
HTTP 只是它的一层皮（api.py）；L5.3 把事件表升级 SQLite 事件溯源时，这层的接口不变。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

import demo
import graph
import mock_tools
from advice import Advice
from mock_endpoint import MockLLMEndpoint

ReplyDecision = Literal["once", "always", "reject"]  # 三元回复（A1）


class UnknownTicket(KeyError):
    """回复了不存在（或已处理完）的审批单——api 层翻译成 404。"""


class Ticket(BaseModel):
    """审批单：interrupt payload 的登记形态（跨会话待审总表的一行）。"""

    ticket_id: str
    run_id: str
    claim_id: str
    dept: str
    total_cents: int  # 忠实重述（脏数据单的负总额照实登记——处置它是人审的事，不是登记层的事）
    advice: dict  # {decision, reason, remaining_cents}——建议单摘要
    content_hash: str  # 被审内容指纹（A6）：批的是哪一版由它锁定
    status: Literal["pending", "approved", "rejected"] = "pending"


class ApprovalRule(BaseModel):
    """always 规则（A6 可审计规则修订）：pattern=dept + total_cents≤cap 的匹配器。

    审计四问各有一列：谁批的（approved_by）、何时（approved_at）、批了什么 pattern
    （dept/max_total_cents）、当时绑的是哪一版内容（content_hash）——对照「内存 yes
    集合」的反例：那个什么也答不出来。
    """

    rule_id: str
    dept: str
    max_total_cents: int = Field(ge=0)
    approved_by: str
    approved_at: str
    content_hash: str


class RuleBook:
    """规则簿：grant 建规则、match 查命中——「批准并记住」的完整闭环（讲义 ex3 练同构）。"""

    def __init__(self) -> None:
        self._rules: list[ApprovalRule] = []

    def grant(self, dept: str, cap_cents: int, approved_by: str, content_hash: str) -> ApprovalRule:
        """建一条可审计规则；cap 取自被批单的总额——「以后该部门这个金额以下自动过」。"""
        rule = ApprovalRule(
            rule_id=f"rule-{len(self._rules) + 1:03d}",
            dept=dept,
            max_total_cents=cap_cents,
            approved_by=approved_by,
            approved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            content_hash=content_hash,
        )
        self._rules.append(rule)
        return rule

    def match(self, dept: str, total_cents: int) -> ApprovalRule | None:
        """规则命中查询：dept 相符且 total_cents ≤ cap——先建者胜。"""
        for rule in self._rules:
            if rule.dept == dept and total_cents <= rule.max_total_cents:
                return rule
        return None

    def all(self) -> list[ApprovalRule]:
        """全部规则（审计读）。"""
        return list(self._rules)


class EventLog:
    """append-only 事件表（内存版，list + id 自增）——L5.3 升级 SQLite 事件溯源。

    A2 的两条纪律都在这：
    - append 时无人订阅不丢单——事件先进表（真相之源），订阅者只是视图；
    - subscribe 先重放历史（after last_id）再接实时——重放与注册之间没有 await，
      新事件只可能走广播队列，无缝（ex2 练同构）。
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._subscribers: list[asyncio.Queue[dict]] = []

    def append(self, event: str, data: dict) -> dict:
        """记一条事件并广播给全部在线订阅者；返回带 id 的存档记录（id 单调自增）。"""
        record = {"id": len(self._events) + 1, "event": event, "data": data}
        self._events.append(record)
        for queue in self._subscribers:
            queue.put_nowait(record)
        return record

    def snapshot(self, after_id: int = 0) -> list[dict]:
        """读表（纯读，不订阅）：after_id 之后的全部事件——Last-Event-ID 截断的口径。"""
        return [record for record in self._events if record["id"] > after_id]

    async def subscribe(self, last_id: int = 0) -> AsyncIterator[dict]:
        """订阅：先重放 id > last_id 的历史，再实时收新事件（断开时自动注销）。"""
        queue: asyncio.Queue[dict] = asyncio.Queue()
        replay = self.snapshot(last_id)
        self._subscribers.append(queue)  # 与 snapshot 之间无 await——重放/实时的接缝
        try:
            for record in replay:
                yield record
            while True:
                record = await queue.get()
                yield record
        finally:
            self._subscribers.remove(queue)


@dataclass
class _RunHandle:
    """挂起 run 的句柄：thread 凭证、未消费剧本与最近一次的图实例（aget_state 用）。"""

    run_id: str
    claim_id: str
    scripts: list[str] = field(default_factory=list)
    cfg: RunnableConfig = field(default_factory=lambda: {})
    graph: CompiledStateGraph | None = None
    initial: dict = field(default_factory=dict)


class ApprovalService:
    """审批服务：图跑到 submit 暂停 → 登记审批单 + 事件广播；reply 三元恢复。

    离线确定性：模型台词由 scripts_for_run 预计算（默认 demo.offline_run_scripts），
    每段 invoke 起一个专属 MockLLMEndpoint、布置「未消费」的剧本——L3.3 的纪律
    （恢复侧剧本重布，历史来自 checkpoint）。跑真模型时换掉这个工厂即可，服务零改动。
    """

    def __init__(
        self,
        saver: BaseCheckpointSaver[str],
        scripts_for_run: Callable[[str], list[str]] = demo.offline_run_scripts,
    ) -> None:
        self._saver = saver
        self._scripts_for_run = scripts_for_run
        self.log = EventLog()
        self.rules = RuleBook()
        self._runs: dict[str, _RunHandle] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._pending: dict[str, Ticket] = {}
        self._seq_run = 0
        self._seq_ticket = 0

    # ---- run 生命周期 ----

    def start_run(self, claim_id: str) -> str:
        """起一个 run：后台任务跑到 submit 暂停即返回 run_id（asyncio 挂起教学点①）。

        图的 ainvoke 在 interrupt 处正常返回（L3.3：不是异常栈），登记审批单后任务收工——
        等人的不是线程，是 db 里那行 checkpoint。claim 不存在抛 KeyError（api 层 404）。
        """
        mock_tools.claim_view(claim_id)  # 校验单据存在（纯读取）
        self._seq_run += 1
        run_id = f"run-{self._seq_run:04d}"
        handle = _RunHandle(
            run_id=run_id,
            claim_id=claim_id,
            scripts=self._scripts_for_run(claim_id),
            cfg=graph.run_config(run_id),
            initial=graph.initial_state(claim_id),
        )
        self._runs[run_id] = handle
        self.log.append("run.started", {"run_id": run_id, "claim_id": claim_id})
        self._tasks[run_id] = asyncio.create_task(self._invoke(run_id))
        return run_id

    async def wait_run(self, run_id: str) -> None:
        """等初始起跑段收工（跑到暂停或终点）——测试与 demo 的确定性钩子。"""
        await self._tasks[run_id]

    async def _invoke(self, run_id: str, command: Command | None = None) -> None:
        """跑一段图：command=None 从头起跑，否则从暂停点恢复；跑到下一个停点分流。"""
        handle = self._runs[run_id]
        with MockLLMEndpoint() as ep:
            for text in handle.scripts:
                ep.script_text(text)
            compiled = graph.build_graph(demo.model_for_url(ep.url), checkpointer=self._saver)
            payload = command if command is not None else handle.initial
            await compiled.ainvoke(payload, handle.cfg)
            handle.scripts = handle.scripts[len(ep.requests) :]  # 未消费的台词留给下段 invoke
            handle.graph = compiled
        snapshot = await handle.graph.aget_state(handle.cfg)
        if snapshot.interrupts and "submit" in snapshot.next:
            await self._register_ticket(run_id, dict(snapshot.interrupts[0].value))
        elif not snapshot.next:
            advice: Advice = snapshot.values["advice"]
            self.log.append(
                "run.completed",
                {
                    "run_id": run_id,
                    "claim_id": handle.claim_id,
                    "decision": advice.decision,
                    "reason": advice.reason,
                    "sent": bool(snapshot.values.get("sent")),
                },
            )

    async def _register_ticket(self, run_id: str, payload: dict) -> str:
        """登记审批单：先查规则（A1「批准并记住」的自动半边），命中即代行批准。"""
        rule = self.rules.match(payload["dept"], payload["total_cents"])
        self._seq_ticket += 1
        ticket = Ticket(ticket_id=f"tkt-{self._seq_ticket:04d}", **payload)  # payload 自带 run_id（submit 写进）
        if rule is not None:
            ticket.status = "approved"
            self.log.append(
                "approval.auto_applied",
                {
                    "ticket_id": ticket.ticket_id,
                    "run_id": run_id,
                    "claim_id": ticket.claim_id,
                    "rule_id": rule.rule_id,
                    "content_hash": ticket.content_hash,
                },
            )
            await self._invoke(run_id, Command(resume={"action": "approve"}))
        else:
            self._pending[ticket.ticket_id] = ticket
            self.log.append(
                "approval.requested",
                {
                    "ticket_id": ticket.ticket_id,
                    "run_id": run_id,
                    "claim_id": ticket.claim_id,
                    "dept": ticket.dept,
                    "total_cents": ticket.total_cents,
                    "advice": ticket.advice,
                    "content_hash": ticket.content_hash,
                },
            )
        return ticket.ticket_id

    # ---- 三元回复（A1）----

    async def reply(
        self, ticket_id: str, decision: ReplyDecision, message: str | None = None, approver: str = "human-1"
    ) -> dict:
        """三元回复：once=批准本单；always=批准+存规则；reject=带留言恢复进回环。

        恢复一律 Command(resume=...)（L3.3 的恢复入口）；reject 的留言回喂模型做纠错
        （A1）——图里 submit→drafter 的回环替我们消化它，新建议单会再来建单（新 hash）。
        """
        ticket = self._pending.pop(ticket_id, None)
        if ticket is None:
            raise UnknownTicket(ticket_id)
        base = {"ticket_id": ticket_id, "run_id": ticket.run_id}
        if decision == "reject":
            feedback = message or graph.DEFAULT_REJECT_FEEDBACK
            ticket.status = "rejected"
            self.log.append("approval.replied", {**base, "decision": "reject", "message": feedback})
            await self._invoke(ticket.run_id, Command(resume={"action": "reject", "message": feedback}))
        else:
            rule_id: str | None = None
            if decision == "always":
                rule = self.rules.match(ticket.dept, ticket.total_cents)  # 命中查询：已有规则不重建
                if rule is None:
                    rule = self.rules.grant(
                        dept=ticket.dept,
                        cap_cents=ticket.total_cents,
                        approved_by=approver,
                        content_hash=ticket.content_hash,
                    )
                rule_id = rule.rule_id
            ticket.status = "approved"
            self.log.append("approval.replied", {**base, "decision": decision, "rule_id": rule_id})
            await self._invoke(ticket.run_id, Command(resume={"action": "approve"}))
        return {**base, "decision": decision, "rule_id": rule_id if decision == "always" else None}

    # ---- 读面 ----

    async def pending_approvals(self) -> list[dict]:
        """跨会话待审总表（A2：审批端是能力声明，谁在线谁就能领）：pending 表 + 图快照组装。"""
        rows: list[dict] = []
        for ticket in self._pending.values():
            row = ticket.model_dump()
            handle = self._runs.get(ticket.run_id)
            if handle is not None and handle.graph is not None:
                snapshot = await handle.graph.aget_state(handle.cfg)
                row["graph_next"] = list(snapshot.next)
            rows.append(row)
        return rows

    async def run_report(self, run_id: str) -> dict:
        """run 的当前状态报告：图审计流水 events、建议单、送审标志（demo 与验收共用）。"""
        handle = self._runs[run_id]
        if handle.graph is None:
            return {"run_id": run_id, "claim_id": handle.claim_id, "started": False}
        snapshot = await handle.graph.aget_state(handle.cfg)
        advice = snapshot.values.get("advice")
        return {
            "run_id": run_id,
            "claim_id": handle.claim_id,
            "next": list(snapshot.next),
            "events": list(snapshot.values.get("events") or []),
            "decision": advice.decision if isinstance(advice, Advice) else None,
            "reason": advice.reason if isinstance(advice, Advice) else None,
            "sent": bool(snapshot.values.get("sent")),
        }
