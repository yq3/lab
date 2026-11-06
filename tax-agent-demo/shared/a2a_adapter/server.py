"""A2A 服务端适配：把 deepagents 编译图包成标准 A2A agent。

协议细节（JSON-RPC 分发、SSE 流、Task 状态机、AgentCard 发现）全部由
a2a-sdk 承接，本文件只做两件事：

1. DeepAgentExecutor：每个 A2A 任务 = deepagents 图上一次独立 thread 的执行
   （thread_id = task_id，同一任务的后续消息自动续在同一线程）。
2. build_server_app / build_agent_card：装配 AgentCard + FastAPI 路由。

参考：a2a-python v1.3.0 samples/hello_world_agent.py。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Part,
    Task,
    TaskState,
    TaskStatus,
)
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 每次委派的工具调用预算（反失控：deepagents 默认递归上限 9999，形同虚设）
RECURSION_LIMIT = 60

# 图工厂：返回 deepagents 编译图。做成工厂而不是实例，一是支持懒加载
# （服务启动时不构建图），二是测试可注入 fake model 的图。
GraphFactory = Callable[[], CompiledStateGraph]

# input_required 约定：deepagents 图的最终回复以该前缀开头时，executor 不把任务
# 置为 completed，而是翻译成 A2A 的 input-required 状态（业务 agent 用文本标记
# 声明状态，协议翻译收敛在适配层——业务代码不感知 A2A 状态机）。
NEED_INPUT_PREFIX = "[[NEED_INPUT]]"


def _extract_reply(result: dict[str, Any]) -> str:
    """从 deepagents 图的最终 state 提取回给调用方的文本。

    deepagents 若配了 response_format，最终 state 里有 structured_response
    （pydantic 模型时序列化为 JSON）；否则取最后一条非空 AIMessage 文本。
    """
    structured = result.get("structured_response")
    if structured is not None:
        if isinstance(structured, BaseModel):
            return structured.model_dump_json()
        return str(structured)
    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage) and message.content:
            if isinstance(message.content, str) and message.content.strip():
                return message.content
            # content 为块列表时取其中 text 块
            if isinstance(message.content, list):
                texts = [b.get("text", "") for b in message.content if isinstance(b, dict)]
                joined = "\n".join(t for t in texts if t)
                if joined.strip():
                    return joined
    return "（agent 未产出文本回复）"


class DeepAgentExecutor(AgentExecutor):
    """把 deepagents 图暴露为 A2A 任务的执行器。

    Task 生命周期：submitted（框架自动）→ working → completed / failed。
    同一 task_id 的后续消息（如 input_required 后的补充）会续在同一
    deepagents thread 上，由图自身（checkpointer 需自行注入）维持上下文。
    """

    def __init__(self, graph_factory: GraphFactory) -> None:
        self._graph_factory = graph_factory
        self._graph: CompiledStateGraph | None = None

    def _get_graph(self) -> CompiledStateGraph:
        if self._graph is None:
            self._graph = self._graph_factory()
        return self._graph

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """取消任务：deepagents 图的协作式中断在 demo 里不做（演进点），仅置状态。"""
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id or "",
            context_id=context.context_id or "",
        )
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id, context_id = context.task_id, context.context_id
        if not context.message or not task_id or not context_id:
            return

        updater = TaskUpdater(event_queue=event_queue, task_id=task_id, context_id=context_id)
        user_text = context.get_user_input()
        logger.info("[%s] 收到任务 %s：%s", type(self).__name__, task_id, user_text[:80])

        # 协议要求：先入队初始 Task（submitted，携带用户消息进 history），再发状态更新
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[context.message],
            )
        )
        await updater.start_work()
        try:
            result = await self._get_graph().ainvoke(
                {"messages": [HumanMessage(content=user_text)]},
                config={"configurable": {"thread_id": task_id}, "recursion_limit": RECURSION_LIMIT},
            )
            reply = _extract_reply(result)
            if reply.startswith(NEED_INPUT_PREFIX):
                note = reply.removeprefix(NEED_INPUT_PREFIX).strip()
                await updater.requires_input(message=updater.new_agent_message(parts=[Part(text=note)]))
                logger.info("[%s] 任务 %s 挂起等待补充信息：%s", type(self).__name__, task_id, note[:60])
                return
            await updater.add_artifact(parts=[Part(text=reply)], name="response", last_chunk=True)
            await updater.complete()
            logger.info("[%s] 任务 %s 完成", type(self).__name__, task_id)
        except GraphRecursionError:
            # 每次委派带工具调用预算：模型失控循环时截断为可读的 failed 任务，
            # 而不是跑满 deepagents 默认的 9999 层递归
            logger.error("任务 %s 超出工具调用预算（%d）", task_id, RECURSION_LIMIT)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[
                        Part(
                            text=(
                                f"任务在 {RECURSION_LIMIT} 步工具调用预算内未完成（疑似执行循环），已中止。"
                                "请简化或拆分任务后重新委派；若持续出现请联系该 agent 团队排查。"
                            )
                        )
                    ]
                )
            )
        except Exception:
            logger.exception("任务 %s 执行失败", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(text="agent 内部执行失败，请稍后重试或联系该 agent 团队")]
                )
            )


def build_agent_card(
    *,
    name: str,
    description: str,
    port: int,
    version: str = "0.1.0",
    skills: list[AgentSkill] | None = None,
) -> AgentCard:
    """构建本 demo subagent 的标准 AgentCard（JSONRPC 1.0 绑定）。"""
    host = "127.0.0.1"
    return AgentCard(
        name=name,
        description=description,
        provider=AgentProvider(organization="tax-agent-demo", url=f"http://{host}:{port}"),
        version=version,
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text", "task-status"],
        skills=skills
        or [
            AgentSkill(
                id="generic",
                name=name,
                description=description,
                tags=["tax"],
            )
        ],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://{host}:{port}/a2a/jsonrpc",
            ),
        ],
    )


def build_server_app(card: AgentCard, executor: AgentExecutor) -> FastAPI:
    """装配 FastAPI 应用：AgentCard 发现 + JSONRPC 端点。"""
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store, agent_card=card)
    app = FastAPI(title=card.name, description=card.description)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card=card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler=handler, rpc_url="/a2a/jsonrpc"),
    )
    return app
