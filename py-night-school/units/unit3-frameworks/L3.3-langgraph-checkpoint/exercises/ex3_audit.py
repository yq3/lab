# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""恢复后轨迹审计：从 checkpoint 的 state history 重建执行轨迹。

考察点：get_state_history 给的快照序列怎么读——每个快照的 next 是「那一拍要跑的
节点」，最后一个快照的 next 若非空就是暂停点（还没跑）；interrupt payload 藏在
暂停快照的 interrupts 里。重建算法（讲义 Step4 只展示了原始列表，重建是你的活）：

  按 step 升序排好 → 相邻两个快照之间，前一个的 next 就是已经跑过的节点 →
  最后一个快照的 next 非空 = 暂停在等谁（注意 START 哨兵 '__start__' 不是真节点）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——三个测试：
  暂停态轨迹：nodes_ran 恰好 (reviewer, tools, reviewer)、paused_at == ("human_gate",)、
  supersteps == 3、payload 带 claim_id/reason；
  恢复后轨迹：六个节点全跑完、paused_at 为空、supersteps == 6、payload 为 None；
  交叉验证：最新快照的 events 审计流水与重建出的 nodes_ran 完全一致（两种口径互证）。
TODO 所需的顶部 import：无——快照类型 StateSnapshot 已在顶部 import。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langgraph.types import Command, StateSnapshot

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint

SENTINELS = ("__start__", "__end__")  # 保留节点名不是真节点，重建轨迹时要剔除


@dataclass
class Trajectory:
    """重建出的执行轨迹（字段给定，rebuild 负责填值）。"""

    nodes_ran: tuple[str, ...]  # 已执行的节点，按顺序
    paused_at: tuple[str, ...]  # 最后一个快照的 next：非空 = 图在等这些节点（暂停点）
    supersteps: int  # 最后一个快照的 step：暂停 3 / 跑完 6
    interrupt_payload: dict[str, Any] | None  # 暂停快照 interrupts[0].value；没暂停为 None


async def pause_claim(db_path: str, claim_id: str = "CLM-2026-0003") -> str:
    """（给定）跑到人审门暂停，返回 thread_id——ex2 start_side 的迷你版。"""
    thread_id = f"ex3-{claim_id}"
    cfg = demo.thread_config(thread_id)
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        async with demo.open_saver(db_path) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            await graph.ainvoke({"messages": demo.initial_messages(claim_id)}, cfg)
    return thread_id


async def resume_claim(db_path: str, thread_id: str, decision: Literal["approve", "deny"]) -> None:
    """（给定）恢复到跑完——ex2 resume_side 的迷你版（Command(resume=) 在这里明示）。"""
    cfg = demo.thread_config(thread_id)
    with MockLLMEndpoint() as ep:
        async with demo.open_saver(db_path) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            snapshot = await graph.aget_state(cfg)
            paused = demo.parse_advice_text(snapshot.values["messages"][-1].content)
            if paused is None:
                raise ValueError("暂停点状态里解析不出建议单")
            ep.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            await graph.ainvoke(Command(resume=decision), cfg)


async def fetch_history(db_path: str, thread_id: str) -> list[StateSnapshot]:
    """（给定）读这条 thread 的全部快照——aget_state_history 天然新→旧，原样返回。"""
    async with demo.open_saver(db_path) as saver:
        graph = demo.build_graph(demo.model_for_url("http://127.0.0.1:1"), checkpointer=saver)
        return [snap async for snap in graph.aget_state_history(demo.thread_config(thread_id))]


def rebuild(snaps: list[StateSnapshot]) -> Trajectory:
    """重建轨迹（你的 TODO）：输入是 fetch_history 的原始列表（新→旧）。"""
    # TODO(ex3): 先按 metadata["step"] 升序排序；相邻快照两两一组，前一个的 next
    #   （剔除 SENTINELS）就是这段时间跑过的节点；最后一个快照的 next（同样剔除
    #   哨兵）非空即暂停点——此时从它的 interrupts[0].value 取 payload；
    #   supersteps 取最后一个快照的 step。
    raise NotImplementedError("TODO(ex3): 补全轨迹重建")
