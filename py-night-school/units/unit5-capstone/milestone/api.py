"""FastAPI 应用：审批外化的 HTTP 面（REST 建单 + SSE 推送，opencode 形态的最小面）。

L5.4 副本声明（对版纪律「合理差异就地注释」）：路由、请求模型、SSE 帧、build_app /
create_app 与 L5.2 相同——审批面的 HTTP 契约在四层合体后原样存活（test_api 回归为证）；
差异只有 docstring、标题与默认 checkpoint 库名。

端点一览（对照 sst/opencode 的 permission 端点组，report.md §2.1 A1）：
- POST /runs                                {claim_id}      → {run_id}（后台跑到暂停）
- GET  /approvals                                           → 跨会话待审总表（A2）
- POST /approvals/{ticket_id}/reply         {decision, message?}
  三元：once=批准本单 / always=批准+存规则 / reject=带留言进回环（A1）
- GET  /approvals/stream                                    → SSE（先重放历史再实时，A2；
  Last-Event-ID 头支持断线续传；?mode=replay 只重放即关——轮询型拉取面）

分层纪律：全部审批域逻辑在 approvals.ApprovalService（离线可测），本文件只有「HTTP 翻译」
——参数模型、状态码、SSE 帧。测试与 demo 用 build_app(app, service) 内存直连
（httpx ASGITransport，不起端口）；真服务是 uv run uvicorn api:app --app-dir code（加餐）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import approvals
import graph

DEFAULT_DB_PATH = "checkpoints/l54-execution-gate.sqlite3"  # uvicorn 加餐的默认 checkpoint 库


class RunRequest(BaseModel):
    """建 run 的请求体。"""

    claim_id: str = Field(min_length=1, description="报销单号，形如 CLM-2026-0001")


class ReplyRequest(BaseModel):
    """三元回复的请求体（A1：once / always / reject+message）。"""

    decision: approvals.ReplyDecision = Field(description="once=批准本单 / always=批准并记住 / reject=驳回")
    message: str | None = Field(default=None, description="驳回留言——回喂模型做纠错（reject 时用）")
    approver: str = Field(default="human-1", description="审批人标识——always 规则的审计字段（A6）")


def get_service(request: Request) -> approvals.ApprovalService:
    """Depends 注入：每请求显式传函数取依赖——没有 Spring 容器魔法（讲义 §2.5）。"""
    return request.app.state.service


def _sse_frame(record: dict) -> str:
    """一条事件 → 一个 SSE 帧（id 行 + event 行 + data 行 + 空行，协议规定帧以空行收尾）。"""
    data = json.dumps(record["data"], ensure_ascii=False)
    return f"id: {record['id']}\nevent: {record['event']}\ndata: {data}\n\n"


def build_app(service: approvals.ApprovalService) -> FastAPI:
    """装一个挂好服务的 app——测试/demo 内存直连用（ASGITransport 不跑 lifespan，
    服务由调用方 async with graph.open_saver(...) 开和关）。"""
    app = _bare_app()
    app.state.service = service
    return app


def create_app(db_path: str = DEFAULT_DB_PATH) -> FastAPI:
    """uvicorn 入口（加餐）：lifespan 里开 saver——aiosqlite 连接随 app 生灭（L3.3 的警告）。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with graph.open_saver(db_path) as saver:
            app.state.service = approvals.ApprovalService(saver)
            yield

    app = _bare_app()
    app.router.lifespan_context = lifespan
    return app


def _bare_app() -> FastAPI:
    """路由装配（不挂服务——build_app 与 create_app 各自负责挂）。"""
    app = FastAPI(title="L5.4 执行门与结业 API", version="0.1.0")

    @app.post("/runs", status_code=202)
    async def post_runs(body: RunRequest, service: approvals.ApprovalService = Depends(get_service)) -> dict:
        """建 run：立即返回 run_id，图在后台任务里跑到 submit 暂停（asyncio 挂起教学点①）。"""
        try:
            run_id = service.start_run(body.claim_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"claim_not_found: {body.claim_id}") from None
        return {"run_id": run_id}

    @app.get("/approvals")
    async def list_approvals(service: approvals.ApprovalService = Depends(get_service)) -> dict:
        """跨会话待审总表：pending 表 + 图快照（A2——无人在线不丢单，单都躺在这）。"""
        return {"pending": await service.pending_approvals()}

    @app.post("/approvals/{ticket_id}/reply")
    async def post_reply(
        ticket_id: str, body: ReplyRequest, service: approvals.ApprovalService = Depends(get_service)
    ) -> dict:
        """三元回复：once / always / reject（A1）——非法 ticket 404。"""
        try:
            outcome = await service.reply(ticket_id, body.decision, message=body.message, approver=body.approver)
        except approvals.UnknownTicket:
            raise HTTPException(status_code=404, detail=f"unknown_ticket: {ticket_id}") from None
        return outcome

    @app.get("/approvals/stream")
    async def stream_events(
        request: Request,
        service: approvals.ApprovalService = Depends(get_service),
        last_event_id: str | None = Header(default=None),
        mode: Literal["live", "replay"] = "live",
    ) -> StreamingResponse:
        """SSE 事件流：新订阅者先重放历史（A2 重订阅即重放），live 再实时推送。

        - mode=live（默认）：重放完接实时推送——真连接形态（curl -N / EventSource /
          uvicorn 加餐），流常开直到客户端断开；
        - mode=replay：只重放历史然后关流——轮询型客户端的拉取面（EventSource 不可用
          时的降级），也是无端口内存直连测试能读到的形态（ASGITransport 会等 app 跑完，
          常开的流在它那永远读不到——讲义 §3 的实测坑）。
        Last-Event-ID 请求头 = 断线前收到的最后一条 id——重放从它之后开始（续传）。
        """
        last_id = 0
        if last_event_id:
            try:
                last_id = int(last_event_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"bad Last-Event-ID: {last_event_id!r}") from None

        async def frames() -> AsyncIterator[str]:
            if mode == "replay":
                for record in service.log.snapshot(last_id):
                    yield _sse_frame(record)
                return
            async for record in service.log.subscribe(last_id):
                if await request.is_disconnected():
                    break
                yield _sse_frame(record)

        return StreamingResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()  # uv run uvicorn api:app --app-dir code 的入口（加餐）
