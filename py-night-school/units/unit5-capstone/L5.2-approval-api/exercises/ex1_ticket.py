# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""审批登记与三元回复核心：ApprovalService.reply 的三分支路由（讲义 approvals.py 的同构迷你版）。

迷你图 drafter→submit（interrupt 送审门）：drafter 是纯代码替身（无模型），第 n 轮产出
「第 n 版建议单」，submit 的 interrupt payload 带 draft_version——内容指纹的替身：版本一
变 payload 变（讲义里换成了 sha256 的 content_hash，语义相同）。
given：迷你图全部装配、start()（起跑到暂停 + 登记审批单）、_drive()（恢复到下一个停点
并登记新单/收尾）、HTTP 翻译层；TODO 只在最该练的一处：reply 的三分支路由——

- once：批准本单；always：批准 + 存规则（先查命中，已命中复用 rule_id，不重复建）；
- reject：留言（缺省给本文件顶部的 DEFAULT_FEEDBACK）恢复进回环——迷你图 submit 会把它
  作为消息回喂 drafter，新版本自动再建单；
- 恢复入口是 L3.3 学过的那个（顶部补 import）；载荷要让迷你图 submit 里
  decision.get("action") / decision.get("message") 读到对应内容——对照 submit 源码反推；
- approval.replied 事件的 data：{"ticket_id", "decision"} 加上 once/always 的 "rule_id"
  （once 时为 None）或 reject 的 "message"；
- 返回回执 {"ticket_id", "decision", "rule_id"}（once/reject 时 rule_id=None）；
- 单从 pending 表取、取不到抛 UnknownTicket（given 的 FastAPI 层翻译成 404）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——5 个测试：
  once：run 完成（next 空、sent=True）、总表清空、事件序列 requested→replied→completed；
  reject+留言：留言进 messages（回喂）、drafter 重跑（drafts==[1,2]）、新单在场（版本 2）；
  reject 无留言：默认反馈进 messages 且进事件；
  always：规则入库、命中查询去重（同 pattern 二次 always 不新建规则）、rule_id 回执；
  未知单：HTTP 404（合法单同端点 200）。
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
from langgraph.types import interrupt
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
    """送审门（given）：interrupt() 把图摁停；恢复时 decision 就是当时的审批决策。

    reject 分支把留言作为 user 消息回喂（A1 纠错回路）；approve 置 sent=True 收口。
    恢复是重放：interrupt 之前的两行是纯函数，重跑一遍安全（L3.3 铁律①）。
    """
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
    """条件边（given）：批准→END；驳回→回 drafter（迷你图不设封顶——讲义图才有 MAX_APPROVAL_LOOPS）。"""
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
    """极简规则表（given：match 直接给实现——写 matcher 是 ex3 的题，本题只练「接入」）。

    always 的「批准并记住」：先查命中（不重复建），未命中才 grant（cap=本单 total_cents）。
    """

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
    """checkpoint 库（given）：迷你图状态全是原生类型，不需要 serde 白名单。"""
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn)


class ApprovalService:
    """迷你审批服务：pending 表 + 事件表 + 图句柄（讲义 approvals.ApprovalService 的同构迷你版）。"""

    def __init__(self, checkpointer: BaseCheckpointSaver[str]) -> None:
        self._graph = build(checkpointer)
        self._cfg: RunnableConfig = {}
        self.pending: dict[str, dict] = {}
        self.events: list[dict] = []
        self.rules = MiniRules()
        self._seq_ticket = 0
        self._seq_run = 0

    def _emit(self, event: str, data: dict) -> None:
        """事件表（given：极简版——讲义 EventLog 的 list 半边，订阅面是 ex2 的题）。"""
        self.events.append({"event": event, "data": data})

    async def state(self):
        """当前快照（given：验收与自查用——next/values 一眼可见）。"""
        return await self._graph.aget_state(self._cfg)

    async def _register(self) -> str:
        """登记审批单（given）：interrupt payload → pending 表 + approval.requested 事件。"""
        snapshot = await self._graph.aget_state(self._cfg)
        payload = dict(snapshot.interrupts[0].value)
        self._seq_ticket += 1
        ticket_id = f"tkt-{self._seq_ticket:03d}"
        self.pending[ticket_id] = {"ticket_id": ticket_id, **payload}
        self._emit("approval.requested", dict(self.pending[ticket_id]))
        return ticket_id

    async def start(self) -> str:
        """起跑（given）：图跑到 submit 暂停，登记审批单。每次 start 是新 thread（新 run）。"""
        self._seq_run += 1
        self._cfg = {"configurable": {"thread_id": f"ex1-run-{self._seq_run}"}, "recursion_limit": 12}
        await self._graph.ainvoke({"messages": [], "drafts": []}, self._cfg)
        return await self._register()

    async def _drive(self, command) -> None:
        """恢复执行到下一个停点（given）：再暂停 → 登记新单；跑完 → 登记 run.completed。"""
        await self._graph.ainvoke(command, self._cfg)
        snapshot = await self._graph.aget_state(self._cfg)
        if snapshot.interrupts:
            await self._register()
        else:
            run_id = (self._cfg.get("configurable") or {}).get("thread_id", "")
            self._emit("run.completed", {"run_id": run_id, "sent": bool(snapshot.values.get("sent"))})

    async def reply(self, ticket_id: str, decision: str, message: str | None = None) -> dict:
        """三元回复（你的 TODO）：once / always / reject 三分支路由——题干 docstring 有完整契约。

        问：三分支各自「先记什么事件、再怎么恢复」？恢复指令用哪个构造器、载荷里放哪些键
        （对照迷你图 submit 读 decision 的那两行）？always 的规则命中查询在什么时候做？
        """
        # TODO(ex1): 三分支路由 + 恢复指令构造 + 规则命中查询
        #   （恢复入口需要顶部补 import；杂务已给：await self._drive(<恢复指令>)）
        raise NotImplementedError("TODO(ex1): reply 三分支")


# ---- HTTP 翻译层（given）：reply 端点 + 404 语义 ----


class ReplyRequest(BaseModel):
    decision: str
    message: str | None = None


def create_app(service: ApprovalService) -> FastAPI:
    """审批面的最小 HTTP 形态（given）：讲义 api.py 的同构一角。"""
    app = FastAPI()

    @app.post("/approvals/{ticket_id}/reply")
    async def reply_endpoint(ticket_id: str, body: ReplyRequest) -> dict:
        try:
            return await service.reply(ticket_id, body.decision, body.message)
        except UnknownTicket:
            raise HTTPException(status_code=404, detail=f"unknown_ticket: {ticket_id}") from None

    return app
