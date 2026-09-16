# 参考答案：ex2_scenario_map（练习文件的完整解法——完成前别看）
"""场景到选型映射：每个场景的关键词 → 决策表那一格的显著优势。"""

from __future__ import annotations

SCENARIOS: dict[str, str] = {
    "s1": "金融合规场景：每单必须断电可恢复（暂停→杀进程→审批→新进程续跑），状态要落在自己持有的存储里。",
    "s2": "两周即弃的一次性 POC：把两个 mock 工具串成一次审查，交付后整个项目直接扔掉。",
    "s3": "多代理研究原型：主代理派活给专职子代理、要虚拟文件台写底稿、还要跨会话记忆。",
    "s4": "团队已在 Google 栈（GCP / Vertex）：要浏览器调试器看事件流，要内建 eval 工具链做回归。",
    "s5": "流程由业务同学自己在画布上改（不写代码），跑到人工节点要弹表单、按按钮分流。",
    "s6": "想要最薄的原语层：双 agent 转交（换 agent 不换对话）就够，未来可能深度定制循环内脏。",
}

FRAMEWORKS = ("mini-agent", "openai-agents", "langgraph", "deepagents", "adk", "dify")

CHOICES: dict[str, str] = {
    "s1": "langgraph",
    "s2": "mini-agent",
    "s3": "deepagents",
    "s4": "adk",
    "s5": "dify",
    "s6": "openai-agents",
}

REASONS: dict[str, str] = {
    "s1": "断电可恢复 + 状态自持是 L3.3 压轴实验的原样需求：interrupt 落盘暂停、"
    "新进程从 checkpoint 续跑，sqlite 文件归自己持有（mini-agent 的 messages 跑完即丢）。",
    "s2": "一次性即弃要零锁定与最快拥有：milestone 的 mini-agent 249 行（Unit 2）全是自己的代码，"
    "没有装配层、没有私有格式，扔掉时什么都不欠。",
    "s3": "派活给子代理 + 文件工作台 + 跨会话记忆正是 deepagents 的 harness 三件套（L3.5）："
    "task 工具、state['files'] 虚拟文件系统、MemoryMiddleware 都是默认件——记得收窄与给预算。",
    "s4": "Google 栈 + 调试器 + eval 是 adk 全家桶的主场（L3.6）：adk web 看事件流、"
    "AgentEvaluator 跑轨迹回归，Cloud Run/Vertex 件是同一生态的一等公民（也是锁定性来源）。",
    "s5": "业务同学自己改流程且不写代码 = 平台形态题眼（L3.7）：dify 画布上图即数据，"
    "human-input 节点弹表单、按钮即出边——代价是逻辑不可 git diff、不可单测。",
    "s6": "最薄原语 + handoff 换人不换对话是 openai-agents 的定位（L3.1）：Agent 就是 dataclass，"
    "转交在 wire 上是一个工具调用；循环内脏要改时离 mini-agent 最近（先关 trace 外发）。",
}
