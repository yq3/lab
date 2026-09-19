# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""源码事实题：读完 create_react_agent 的源码，把答案写进 FACTS——pytest 拿你的答案跑行为验证。

读码对象（本地克隆 ~/develop/opensource/langgraph，HEAD e539ac122，行号按此锚定）：
  libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py
    - 装配段 861–1002：两个 add_node 就在开头——①② 的答案在它们的第一参数里；
    - 条件边函数 should_continue（831–859）：无 tool_calls → END；有 tool_calls 时
      v2 默认下的返回形态见 849 行起——③ 的三选一与 ④ 的扇出数都在这段代码里；
    - 预算哨兵（689/716 行）：remaining_steps 不足时模型节点替模型回那句英文文案；
    - response_format=... 时装配段会加一个结构化输出节点（899–910 行）。
  libs/prebuilt/langgraph/prebuilt/tool_node.py
    - _validate_tool_call（1268 行起）：未注册工具名时 ToolNode 怎么处理，答案在函数体里（⑦ 的二选一）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——七个事实全部被行为验证消费：
  ①② 节点名被用来对照真实装配产物的图节点集；③④ 路由语义与扇出任务数用 stream 轨迹验证；
  ⑤ 结构化输出节点名在 response_format=Advice 的装配里找；⑥ 哨兵文案用 recursion_limit=2 实跑比对；
  ⑦ 未注册工具的行为用 ToolNode 单节点图实测。读的时候顺手把每条事实的行号记在心里——
  验收过的才叫读过。
"""

from __future__ import annotations

# TODO(ex3): 读完源码后把七个事实的答案填进下面的值（不要改动键名与文件其余部分）
FACTS: dict[str, object] = {
    # ① 调模型的节点名（装配段 add_node 的第一个参数）
    "model_node_name": "",
    # ② 执行工具的节点名
    "tools_node_name": "",
    # ③ should_continue 在「有 tool_calls」时返回什么（v2 默认）："tools" / "end" / "send_list"
    "route_fn_behavior": "",
    # ④ 一轮选了 2 个工具时，tools 节点被实例化成几个并行任务（Send 扇出数）
    "tools_tasks_for_two_calls": 0,
    # ⑤ response_format=Advice 时，结构化输出节点的名字
    "structured_node_name": "",
    # ⑥ remaining_steps 不足时，模型节点替模型回的那句哨兵文案（源码里的字符串常量，一字不差）
    "out_of_steps_reply": "",
    # ⑦ ToolNode 收到未注册的工具名时："raise" 还是 "feed_back"
    "unknown_tool_behavior": "",
}
