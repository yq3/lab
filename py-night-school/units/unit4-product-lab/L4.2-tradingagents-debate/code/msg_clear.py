"""L4.2 MsgClear：阶段结束裁剪上下文（对版 agent_utils.py#create_msg_delete）。

对版 TauricResearch/TradingAgents@be952b8#tradingagents/agents/utils/agent_utils.py：
- 产品在每个分析师阶段结束放一个 MsgClear 节点：RemoveMessage 清空全部消息，
  换一条**锚定占位** HumanMessage——下一阶段从干净的上下文起步，报告以独立 str 字段
  （market_report 等）传下游，不靠消息史。这是长工作流防上下文膨胀与阶段串扰的图级方案。
- 占位不能是干巴巴的 "Continue"：某些 OpenAI 兼容端点会把它当字面任务、对着「继续」二字
  发挥（#888）——锚定到具体业务对象（产品锚 instrument_context + 日期；本课锚争议单号
  与已归档的政策结论）才能把下一阶段钉在任务上。

Java 对照：没有直接对应物——最接近的心智模型是「定期清理 Session 防膨胀」：
HttpSession/本地缓存不清理就无限长大，这里是消息史；差别在于清理是**图拓扑里的一等
节点**（可审计、可断点），不是后台定时任务。

RemoveMessage 语义：add_messages reducer 认 id——RemoveMessage(id=X) 是「按 id 删除」
的删除指令，不是新消息。这就是「清空」能走合并通道完成的原因。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, RemoveMessage

from states import AppealState


def create_msg_delete():
    """MsgClear 节点工厂（对版 create_msg_delete）：清空 messages + 换锚定占位。"""

    async def clear_messages(state: AppealState) -> dict:
        messages = state["messages"]
        removals = [RemoveMessage(id=m.id) for m in messages if m.id is not None]
        placeholder = HumanMessage(
            content=(
                f"报销争议上诉 {state['claim_id']} 已受理：政策分析阶段已完成，"
                "结论已归档到 policy_report 字段。请开始辩论阶段——围绕 POL-7.2 常态规则"
                "与 POL-9.1 例外条款的适用争议发表立场。"
            )
        )
        return {"messages": removals + [placeholder]}

    return clear_messages
