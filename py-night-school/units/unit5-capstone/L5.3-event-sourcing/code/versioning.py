"""图版本绑定（本课核心之三，A15）——审计记录必须绑定产生它的拓扑版本。

设计出处：research/agent-oss/report.md §2.1 A15（图形状签名进 checkpoint key：
改图自动作废旧执行态）；产品先例：TauricResearch/TradingAgents 的 `_run_signature`
（讲义 §6 路标——分析师选择/辩论轮次/资产模式拼进 checkpoint thread_id，#1089：
换了配置的 resume 不许静默续旧检查点）。

三个件：
- topology_signature：L5.1 step2_signature.py 的**字节副本**（函数体逐字相同）。
  复制而非 import 的原因：step2_signature 顶部 `import demo`，而本课 demo 又要用
  versioning 组 run_key——import 会成环（对版纪律：合理差异就地注释声明）；
- run_key(aggregate_id, signature)：聚合键 = 单号 + 签名前 12 位——checkpoint
  thread_id 与事件表的 run 元数据都用它，图一改 key 自动换；
- assert_compatible(stored, current)：续跑守门——不一致抛 GraphVersionMismatch。
  语义不是「报错完蛋」，是「版本变了就别续旧账」：旧执行态作废，重开新 run。
"""

from __future__ import annotations

import hashlib
import json

from langgraph.graph.state import CompiledStateGraph


def topology_signature(compiled: CompiledStateGraph) -> str:
    """图形状签名：节点名 + 边（source/target/条件性）排序序列化后 sha256。

    （L5.1 step2_signature.py 的字节副本，docstring 合并自原处——序列化口径不变：
    节点名排序；边按 (source, target, 是否条件边) 排序；节点/边的「函数体内容」
    不进签名——签的是拓扑形状，不是实现。）
    """
    drawable = compiled.get_graph()
    nodes = sorted(drawable.nodes)  # get_graph 的 nodes 是 {id: Node}，__start__/__end__ 在内
    edges = sorted((edge.source, edge.target, "cond" if edge.conditional else "edge") for edge in drawable.edges)
    payload = json.dumps({"nodes": nodes, "edges": [list(edge) for edge in edges]}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class GraphVersionMismatch(RuntimeError):
    """续跑时的图版本不符——旧执行态作废（不是报错完蛋：重开新 run 就是了）。"""

    def __init__(self, stored: str, current: str) -> None:
        self.stored = stored
        self.current = current
        super().__init__(
            f"graph version mismatch: stored={stored[:12]}… current={current[:12]}…"
            "（图形状变了，旧执行态作废——请用新 run_key 重开 run，不要续旧账）"
        )


def run_key(aggregate_id: str, signature: str) -> str:
    """聚合键：单号@签名前 12 位。

    前 12 位（48 bit）只为日志与表里可读——同规模下碰撞概率可忽略；全签名在
    run.started 事件的 payload 里留了完整档（graph_version 字段）。
    """
    return f"{aggregate_id}@{signature[:12]}"


def assert_compatible(stored_sig: str, current_sig: str) -> None:
    """续跑守门：库里记的版本必须等于当前装配的版本，不等即抛。

    调用方（demo.run_audited）在 append run.started 前对聚合已有的 run.started
    逐条核对——同图允许续（同 key 事件照常追加），改图拒绝续（A15 的本地实现）。
    """
    if stored_sig != current_sig:
        raise GraphVersionMismatch(stored_sig, current_sig)
