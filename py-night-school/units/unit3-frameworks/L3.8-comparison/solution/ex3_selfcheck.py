# 参考答案：ex3_selfcheck（练习文件的完整解法——完成前别看）
"""结业自查表：12 行结构化数据——条目全部是「能……」句式并带课次证据。"""

from __future__ import annotations

DIMENSIONS = ("成本", "能力", "锁定性", "跳读", "框架判据")

CHECKLIST: list[dict[str, str]] = [
    {
        "维度": "框架判据",
        "条目": "CURRICULUM §7 框架判据：mini-agent vs 四框架的决策表能自己重新推导——每个数字说得出口径",
    },
    {
        "维度": "成本",
        "条目": "能背出依赖数光谱 44→51→54→70→88 的顺序与两端（mini-agent 最轻、adk 最重），并说出 dify 为何不在这列",
    },
    {
        "维度": "能力",
        "条目": "HITL 三种形态各能给一个机制证据：RunState 快照（openai-agents，L3.1）、"
        "interrupt+checkpoint（langgraph，L3.3）、human-input 表单（dify，L3.7）",
    },
    {
        "维度": "锁定性",
        "条目": "能对「trace 默认外发」与「litellm 中转」各给一句源码级证据（L3.1 Step2 / L3.6 §2.4）",
    },
    {
        "维度": "跳读",
        "条目": "五仓跳读路线各能说出一个核心抽象入口（crewai 的 Crew/Task、"
        "agentscope 的 Agent.reply、langchain 的 create_agent……）",
    },
    {
        "维度": "能力",
        "条目": "能解释 deepagents 同题 demo 为什么 5 轮而其他框架 2 轮"
        "（task 子代理独立对话两轮 + write_file + Advice 收尾轮，L3.5 Step1）",
    },
    {
        "维度": "成本",
        "条目": "能现场重数装配 loc：口径是 def 行计入、docstring 剔除的非空非注释行"
        "（L3.4 count_loc / 本课 tablegen 同款）",
    },
    {
        "维度": "锁定性",
        "条目": "能说出 Checkpoint 的私有格式风险（msgpack BLOB + serde 白名单）与对策："
        "跨版本恢复前锁类型（L3.3 Step4）",
    },
    {
        "维度": "能力",
        "条目": "能指出 adk 独有的两件：adk web 调试器与 AgentEvaluator eval 工具链的入口"
        "（L3.6 Step5）——四框架里仅此一家",
    },
    {
        "维度": "跳读",
        "条目": "能带着 L3.1 的 handoff-as-tool 视角去读 llama_index 的 AgentWorkflow："
        "agent 间转交在它家的拼写（L3.8 §3 Step3）",
    },
    {
        "维度": "框架判据",
        "条目": "能说出「何时选 mini-agent 级自研」：一次性 POC、零锁定要求、循环内脏要深度定制"
        "——决策表「—」格的含义（L3.8 §3 Step4）",
    },
    {
        "维度": "能力",
        "条目": "能讲清 langgraph Send 扇出「执行并发、归并确定」与线程池 submit 的本质差异（L3.4 §2.2/§5）",
    },
]
