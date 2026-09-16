"""L3.4 线 B：Send 动态扇出——批量审查四张 mock 单（map-reduce 的图表达）。

图结构（扇出在运行时发生——条件边返回 Send 列表，不是画布上的静态并行边）：

    START → dispatch ──(条件边 fan_out：返回 [Send('review', 单据专属状态) × N])──→ review × N
                     （N 个 review 分支并行执行、各写各的 claim_id 键）→ reduce → END

三条实测纪律（讲义 §2.2 逐条展开，全部可由本脚本输出复现）：

1. **Send 分支真的并发**：sync invoke 下分支跑在引擎的线程池里（PregelRunner→BackgroundExecutor），
   四个分支的开工时刻几乎重合；但**没有 Future**——归并不靠 get()，靠超步边界上的 reducer；
2. **合并顺序确定，执行顺序不保证**：分支写进 results 键的顺序由 apply_writes 按 task path
   排序决定（源码注释明说 deterministic order），与谁先跑完无关——所以按 claim_id 取值永远稳；
   但「分支消费共享资源」的次序（比如共享一个剧本队列）是竞态——所以每单一个专属 mock 端点，
   剧本互不干扰（这就是本脚本的剧本策略与 ep.requests 取证依据）；
3. **归并靠自定义 reducer**：results/timing 用 Annotated[dict, merge_results] 声明——
   merge_results 是本课新知识点「自定义 reducer 函数」：各分支写不同的 claim_id 键，
   浅合并天然无冲突。

对照 Java：Send 扇出 ≈ Stream.flatMap + collect(groupingBy)，但归并发生在超步边界（BSP），
且「怎么合并」声明在字段上（Annotated 第二参）而不是收集器调用点。
"""

from __future__ import annotations

import time
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

import demo
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def merge_results(old: dict, new: dict) -> dict:
    """自定义 dict 合并 reducer：浅合并，new 的键覆盖 old 的同名键。

    这是「扇出-归并」的归并半边：N 个 Send 分支各返回 {claim_id: advice}，
    引擎在超步边界对 results 键逐份执行 merge_results(累计值, 本分支更新)。
    对照 L3.2 的 operator.add——reducer 不必来自标准库，任何 (旧, 新) -> 合并 的函数都行。
    """
    return {**old, **new}


class BatchState(TypedDict):
    """主图状态：claim_ids/ep_urls 入口给定；results/timing 靠自定义 reducer 合并；report 只由 reduce 写。"""

    claim_ids: list[str]
    ep_urls: dict[str, str]  # 每单一个专属 mock 端点的 URL（Send 分支的剧本互不干扰）
    results: Annotated[dict[str, Advice], merge_results]  # 归并：按 claim_id 落位的建议单
    timing: Annotated[dict[str, tuple[float, float]], merge_results]  # 归并：各分支 (开工, 收工) 时刻取证
    report: NotRequired[dict]  # 汇总（decision 计数 / 总金额），覆盖语义，只有 reduce 写


class WorkerState(TypedDict):
    """Send 分支的专属状态：与主图状态完全不同——Send 的 arg 就是 worker 的整个输入。

    这就是 Send 的核心自由度：分支状态可以比主图状态「窄」（只带本单需要的字段），
    离线剧本策略正靠它成立——每个分支拿到自己端点的 URL。
    """

    claim_id: str
    ep_url: str
    messages: Annotated[list, add_messages]  # 入口消息（system 由 prebuilt 的 prompt= 负责）


def dispatch(state: BatchState) -> dict:
    """入口节点：不写状态——它存在的意义是给扇出条件边一个锚点（L3.2 ex3 的 precheck 同款纪律）。"""
    return {}


def fan_out(state: BatchState) -> list[Send]:
    """扇出条件边：按 claim 列表在运行时造 N 个动态分支——每个 Send 带一份专属 worker 状态。

    对照静态并行边（L3.2 step1 的 left∥right）：拓扑在 compile 前就定死；Send 的分支数
    直到条件边执行那一刻才确定——这就是「动态」的含义（Java 对照：任务数在 submit 循环里才知道）。
    """
    return [
        Send(
            "review",
            {
                "claim_id": claim_id,
                "ep_url": state["ep_urls"][claim_id],
                "messages": [{"role": "user", "content": demo.user_brief(claim_id)}],
            },
        )
        for claim_id in state["claim_ids"]
    ]


def review(state: WorkerState) -> dict:
    """单审 worker（sync 节点）：分支内部再跑一个完整的 prebuilt agent（两轮剧本，装配复用 demo）。

    它读的是 WorkerState（Send arg），写的是主图的 results/timing 键——节点返回值
    永远是对主图通道的更新，与它收到的输入 schema 无关（map-reduce 的 map 半边）。
    剧本早已排在它专属的端点上（run_batch 预灌），消费次序无关紧要。
    """
    start = time.perf_counter()
    agent = demo.build_agent(demo.model_for_url(state["ep_url"]))
    result = agent.invoke(
        {"messages": state["messages"]},
        config={"recursion_limit": demo.RECURSION_LIMIT},
    )
    advice = Advice.model_validate_json(result["messages"][-1].content.strip())
    end = time.perf_counter()
    return {
        "results": {state["claim_id"]: advice},
        "timing": {state["claim_id"]: (start, end)},
    }


def reduce_results(state: BatchState) -> dict:
    """reduce 节点：全部分支落账后的下一个超步统一收割——decision 计数 + 四单总额 + 明细表。"""
    counts: dict[str, int] = {}
    for claim_id in sorted(state["results"]):
        decision = state["results"][claim_id].decision
        counts[decision] = counts.get(decision, 0) + 1
    total_cents = sum(mock_tools.claim_view(cid)["total_cents"] for cid in state["results"])
    return {"report": {"counts": counts, "total_cents": total_cents}}


def build_batch_graph() -> CompiledStateGraph:
    """装配批量图：dispatch →（Send 扇出）→ review ×N → reduce → END。"""
    builder = StateGraph(BatchState)
    builder.add_node("dispatch", dispatch)
    builder.add_node("review", review)
    builder.add_node("reduce", reduce_results)
    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", fan_out)  # 路由函数返回 Send 列表 = 动态并行分支
    builder.add_edge("review", "reduce")  # N 个分支全部落账后，reduce 在下一个超步统一收割
    builder.add_edge("reduce", END)
    return builder.compile()


def run_batch(claim_ids: list[str] | None = None, endpoints: dict[str, MockLLMEndpoint] | None = None) -> dict:
    """离线确定性跑批量审查：每单起一个专属 mock 端点、预灌两轮剧本，sync invoke 收全量状态。

    返回最终 BatchState（results / timing / report 都在）——讲义汇总表由 main 打印。
    endpoints 参数供测试注入自备端点（取证 ep.requests）；None 时本函数自起自停。
    """
    mock_tools.CALL_LOG.clear()
    claim_ids = claim_ids if claim_ids is not None else [claim["id"] for claim in mock_tools.claims_table()]
    owned = endpoints is None
    if endpoints is None:
        endpoints = {claim_id: MockLLMEndpoint() for claim_id in claim_ids}
        for endpoint in endpoints.values():
            endpoint.start()
    try:
        for claim_id in claim_ids:
            first_turn, advice_json, _expected = review_rules.script_for(claim_id)
            endpoints[claim_id].script_tool_calls(first_turn)
            endpoints[claim_id].script_text(advice_json)
        graph = build_batch_graph()
        return graph.invoke(
            {
                "claim_ids": claim_ids,
                "ep_urls": {claim_id: endpoints[claim_id].url for claim_id in claim_ids},
                "results": {},
                "timing": {},
            },
            config={"recursion_limit": demo.RECURSION_LIMIT},
        )
    finally:
        if owned:
            for endpoint in endpoints.values():
                endpoint.stop()


def main() -> None:
    claim_ids = [claim["id"] for claim in mock_tools.claims_table()]
    print("== L3.4 Send 扇出：批量审查 4 张 mock 单（离线剧本，每单一个专属 mock 端点） ==")
    print("图: START → dispatch ─条件边(返回 Send 列表)→ review ×4 ─全部落账→ reduce → END\n")
    state = run_batch(claim_ids)
    print(f"[dispatch] 派发 {len(claim_ids)} 个 Send 分支: {claim_ids}")
    starts = [span[0] for span in state["timing"].values()]
    first_start = min(starts)
    print("[review] 分支执行时序（相对最早开工分支，毫秒）：")
    for claim_id in sorted(state["timing"]):
        start, end = state["timing"][claim_id]
        advice = state["results"][claim_id]
        print(
            f"  {claim_id}  start+{(start - first_start) * 1000:6.1f}ms  dur {(end - start) * 1000:5.1f}ms"
            f"  -> {advice.decision} / {advice.reason}"
        )
    branch_total = sum(end - start for start, end in state["timing"].values()) * 1000
    wall = max(end for _start, end in state["timing"].values()) - first_start
    print(f"  分支耗时合计 {branch_total:.1f}ms vs 扇出墙钟 {wall * 1000:.1f}ms —— 并发执行的直接证据")
    print("\n== reduce 汇总 ==")
    report = state["report"]
    print(f"  decision 计数: {report['counts']}")
    print(f"  四单总额    : {report['total_cents']} 分")
    for claim_id in sorted(state["results"]):
        advice = state["results"][claim_id]
        print(f"    {claim_id}  {advice.decision:<8} {advice.reason:<26} 剩余 {advice.remaining_cents} 分")
    print("  模型请求    : 8 次（每单恰好 2 次 × 4 个专属端点，实测口径见 test_demo.py）")


if __name__ == "__main__":
    main()
