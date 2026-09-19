# 参考答案（ex1）：与骨架的差异只在 reply 的实现与顶部补的 import——其余 given 原样。
"""审批登记与三元回复核心：ApprovalService.reply 的三分支路由（讲义 approvals.py 的同构迷你版）。

题目与契约见 exercises/ex1_ticket.py 的 docstring；本文件是它的参考答案。
"""

from __future__ import annotations

import operator
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, NotRequired, TypedDict

import aiosqlite
from fastapi import FastAPI, HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

DEFAULT_FEEDBACK = "审批人驳回且未留留言：请复核建议单后重新起草。"


class GateState(TypedDict):
    """迷你图状态：消息史（驳回留言回喂的载体）+ 起草轮数（回环取证）+ 送审标志。"""

    messages: Annotated[list, add_messages]
    drafts: Annotated[list[int], operator.add]
    sent: NotRequired[bool]


async def drafter(state: GateState) -> dict:
    """起草员（given：纯代码替身）——每轮回一条新版建议单文本，轮数入 drafts。"""
    version = len(state.get("drafts") or []) + 1
    return {
        "messages": [{"role": "assistant", "content": f"第 {version} 版建议单：APPROVE/PASS/10000"}],
        "drafts": [version],
    }


async def submit(state: GateState) -> dict:
    """送审门（given）：interrupt() 把图摁停；恢复时 decision 就是当时的审批决策。"""
    payload = {
        "claim_id": "CLM-2026-0001",
        "dept": "SALES",
        "total_cents": 7100,
        "draft_version": len(state.get("drafts") or []),
    }
    decision = interrupt(payload)
    if decision.get("action") == "reject":
        message = decision.get("message") or DEFAULT_FEEDBACK
        return {"messages": [{"role": "user", "content": f"驳回留言（任务数据）：{message}"}]}
    return {"sent": True}


def route_after_submit(state: GateState) -> str:
    """条件边（given）：批准→END；驳回→回 drafter。"""
    if state.get("sent"):
        return END
    return "drafter"


def build(checkpointer: BaseCheckpointSaver[str]) -> CompiledStateGraph:
    """装配（given）：START → drafter → submit ─(approve)→ END / ─(reject)→ drafter 回环。"""
    builder = StateGraph(GateState)
    builder.add_node("drafter", drafter)
    builder.add_node("submit", submit)
    builder.add_edge(START, "drafter")
    builder.add_edge("drafter", "submit")
    builder.add_conditional_edges("submit", route_after_submit)
    return builder.compile(checkpointer=checkpointer)


class UnknownTicket(KeyError):
    """回复了不存在（或已处理完）的审批单——HTTP 层翻译成 404。"""


class MiniRules:
    """极简规则表（given）：match 直接给实现——写 matcher 是 ex3 的题。"""

    def __init__(self) -> None:
        self._rules: list[dict] = []

    def grant(self, dept: str, cap_cents: int) -> str:
        rule_id = f"rule-{len(self._rules) + 1:03d}"
        self._rules.append({"rule_id": rule_id, "dept": dept, "cap_cents": cap_cents})
        return rule_id

    def match(self, dept: str, total_cents: int) -> str | None:
        for rule in self._rules:
            if rule["dept"] == dept and total_cents <= rule["cap_cents"]:
                return rule["rule_id"]
        return None

    def count(self) -> int:
        return len(self._rules)


@asynccontextmanager
async def open_db(db_path: str) -> AsyncIterator[AsyncSqliteSaver]:
    """checkpoint 库（given）。"""
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn)


class ApprovalService:
    """迷你审批服务：pending 表 + 事件表 + 图句柄。"""

    def __init__(self, checkpointer: BaseCheckpointSaver[str]) -> None:
        self._graph = build(checkpointer)
        self._cfg: RunnableConfig = {}
        self.pending: dict[str, dict] = {}
        self.events: list[dict] = []
        self.rules = MiniRules()
        self._seq_ticket = 0
        self._seq_run = 0

    def _emit(self, event: str, data: dict) -> None:
        """事件表（given）。"""
        self.events.append({"event": event, "data": data})

    async def state(self):
        """当前快照（given）。"""
        return await self._graph.aget_state(self._cfg)

    async def _register(self) -> str:
        """登记审批单（given）。"""
        snapshot = await self._graph.aget_state(self._cfg)
        payload = dict(snapshot.interrupts[0].value)
        self._seq_ticket += 1
        ticket_id = f"tkt-{self._seq_ticket:03d}"
        self.pending[ticket_id] = {"ticket_id": ticket_id, **payload}
        self._emit("approval.requested", dict(self.pending[ticket_id]))
        return ticket_id

    async def start(self) -> str:
        """起跑（given）。"""
        self._seq_run += 1
        self._cfg = {"configurable": {"thread_id": f"ex1-run-{self._seq_run}"}, "recursion_limit": 12}
        await self._graph.ainvoke({"messages": [], "drafts": []}, self._cfg)
        return await self._register()

    async def _drive(self, command) -> None:
        """恢复执行到下一个停点（given）。"""
        await self._graph.ainvoke(command, self._cfg)
        snapshot = await self._graph.aget_state(self._cfg)
        if snapshot.interrupts:
            await self._register()
        else:
            run_id = (self._cfg.get("configurable") or {}).get("thread_id", "")
            self._emit("run.completed", {"run_id": run_id, "sent": bool(snapshot.values.get("sent"))})

    async def reply(self, ticket_id: str, decision: str, message: str | None = None) -> dict:
        """三元回复（参考答案）：先取单记事件，再按分支构造恢复指令交给 _drive。

        - reject：留言缺省给 DEFAULT_FEEDBACK；事件带 message；恢复载荷 {action, message}；
        - always：先 match（已命中复用，不重复建规则），未命中 grant；事件带 rule_id；
        - once/always 的恢复载荷只有 action——approve 后图直接收口，没有回环。
        """
        ticket = self.pending.pop(ticket_id, None)
        if ticket is None:
            raise UnknownTicket(ticket_id)
        if decision == "reject":
            feedback = message or DEFAULT_FEEDBACK
            self._emit("approval.replied", {"ticket_id": ticket_id, "decision": "reject", "message": feedback})
            await self._drive(Command(resume={"action": "reject", "message": feedback}))
            return {"ticket_id": ticket_id, "decision": "reject", "rule_id": None}
        rule_id: str | None = None
        if decision == "always":
            rule_id = self.rules.match(ticket["dept"], ticket["total_cents"])
            if rule_id is None:
                rule_id = self.rules.grant(ticket["dept"], ticket["total_cents"])
        self._emit("approval.replied", {"ticket_id": ticket_id, "decision": decision, "rule_id": rule_id})
        await self._drive(Command(resume={"action": "approve"}))
        return {"ticket_id": ticket_id, "decision": decision, "rule_id": rule_id}


# ---- HTTP 翻译层（given）：reply 端点 + 404 语义 ----


class ReplyRequest(BaseModel):
    decision: str
    message: str | None = None


def create_app(service: ApprovalService) -> FastAPI:
    """审批面的最小 HTTP 形态（given）。"""
    app = FastAPI()

    @app.post("/approvals/{ticket_id}/reply")
    async def reply_endpoint(ticket_id: str, body: ReplyRequest) -> dict:
        try:
            return await service.reply(ticket_id, body.decision, body.message)
        except UnknownTicket:
            raise HTTPException(status_code=404, detail=f"unknown_ticket: {ticket_id}") from None

    return app
