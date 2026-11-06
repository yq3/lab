"""A2A 客户端适配：把远端 subagent 包装成主 agent 的委派工具。

主 agent 通过注册表为每个远端 agent 生成一个 delegate_to_<name> 工具
（handoff-as-tool 的跨进程版本）：
- 流式消费 message/stream 事件，聚合 artifact 文本返回给模型
- input_required 状态透传给模型（带说明，让主 agent 转问用户）
- 连接失败/任务失败映射为模型可读的错误文案（不让模型看到堆栈）

参考：a2a-python v1.3.0 samples/cli.py。
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.client.errors import AgentCardResolutionError
from a2a.helpers import get_artifact_text, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from shared.config import AgentEndpoint

# 委派超时：subagent 内部是完整 agent 循环（多轮工具调用），给足预算
DELEGATE_TIMEOUT_SECONDS = 300

# input_required 结果的前缀标记：主 agent 模型看到它就知道要向用户追问
INPUT_REQUIRED_MARK = "[INPUT_REQUIRED]"


class DelegateInput(BaseModel):
    """委派任务的输入参数。"""

    task: str = Field(
        description="交给远端 agent 的完整任务描述。远端 agent 是无状态首触的，"
        "必须一次性给出全部所需信息（纳税人 ID、年度、数据、要求）"
    )


async def call_remote_agent(base_url: str, task_text: str) -> str:
    """向一个 A2A agent 委派任务并聚合其最终回复文本。

    事件流处理（对应协议的 message/stream）：
    - task 事件：任务创建确认
    - status_update 事件：状态迁移；input_required 时原样透传（带标记前缀）
    - artifact_update 事件：聚合最终产物文本
    - message 事件：直连回复（不走任务状态机的 agent 会这么回）
    """
    config = ClientConfig(httpx_client=httpx.AsyncClient(timeout=DELEGATE_TIMEOUT_SECONDS))
    client = None
    try:
        # 卡片解析（create_client 内部）与消息收发都可能因"远端不可达"抛错，统一映射
        client = await create_client(base_url, client_config=config)
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=task_text)],
            context_id=str(uuid.uuid4()),  # 同一委派工具每次调用独立上下文
        )
        artifact_chunks: list[str] = []
        input_required_text: str | None = None
        failed_text: str | None = None

        async for event in client.send_message(SendMessageRequest(message=message)):
            # proto 语义：未设置的字段是空实例而非 None，判断必须用 HasField
            if event.HasField("message"):
                return get_message_text(event.message)
            if event.HasField("status_update"):
                status = event.status_update.status
                state = status.state
                note = get_message_text(status.message) if status.HasField("message") else ""
                if state == TaskState.TASK_STATE_INPUT_REQUIRED:
                    input_required_text = note or "未说明缺什么"
                elif state == TaskState.TASK_STATE_FAILED:
                    failed_text = note or "任务失败（未附原因）"
            if event.HasField("artifact_update"):
                artifact_chunks.append(get_artifact_text(event.artifact_update.artifact))

        if input_required_text is not None:
            # 不抛异常：这是业务语义上的"需要补充"，由主 agent 模型决定怎么向用户追问
            return (
                f"{INPUT_REQUIRED_MARK} 远端 agent 暂停任务并请求补充信息：{input_required_text}\n"
                f"请向用户转达并收集所需信息，然后带上补充信息重新委派。"
            )
        if failed_text is not None:
            return f"[DELEGATE_FAILED] 远端 agent 任务失败：{failed_text}"
        if artifact_chunks:
            return "\n".join(chunk for chunk in artifact_chunks if chunk.strip())
        return "[DELEGATE_EMPTY] 远端 agent 未返回任何产物"
    except (httpx.ConnectError, AgentCardResolutionError) as exc:
        # 连接拒绝 / AgentCard 拉取失败都归为"不可达"（后者常见于 server 未启动时解析卡片失败）
        return (
            f"[DELEGATE_UNREACHABLE] 无法连接远端 agent（{base_url}）：{exc}。"
            f"请确认该 agent 已启动（scripts/start_all.sh）。"
        )
    except httpx.HTTPError as exc:
        return f"[DELEGATE_ERROR] 调用远端 agent（{base_url}）通信异常：{exc}"
    finally:
        if client is not None:
            await client.close()


def build_delegate_tool(endpoint: AgentEndpoint) -> StructuredTool:
    """为注册表里的一个远端 agent 生成委派工具。"""

    async def _delegate(task: str) -> str:
        return await call_remote_agent(endpoint.base_url, task)

    return StructuredTool(
        name=f"delegate_to_{endpoint.name}",
        description=(
            f"委派任务给「{endpoint.title}」（跨团队独立服务，经 A2A 协议跨进程调用）。"
            f"职责：{endpoint.description}。"
            f"只委派属于它职责范围内的事；委派时在 task 里一次性给出全部所需信息。"
        ),
        args_schema=DelegateInput,
        coroutine=_delegate,
    )


def build_delegate_tools(endpoints: dict[str, AgentEndpoint]) -> list[BaseTool]:
    """为注册表里的全部远端 agent 生成委派工具列表。"""
    return [build_delegate_tool(ep) for ep in endpoints.values()]


def format_tool_result_for_display(result: Any) -> str:
    """CLI 展示委派结果时的简易排版（截断长文本）。"""
    text = str(result)
    return text if len(text) <= 2000 else f"{text[:2000]}…（截断，共 {len(text)} 字）"
