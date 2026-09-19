# 参考答案：ex3_facts（练习文件的完整解法——完成前别看）
"""源码事实题答案：七个事实，全部可在 e539ac122 的源码里按行号路标复核。"""

from __future__ import annotations

FACTS: dict[str, object] = {
    "model_node_name": "agent",  # 装配段 add_node("agent", RunnableCallable(call_model, acall_model))
    "tools_node_name": "tools",  # 装配段 add_node("tools", tool_node)
    "route_fn_behavior": "send_list",  # should_continue 在 v2 默认下返回 [Send("tools", ...) for ...]
    "tools_tasks_for_two_calls": 2,  # 每个 tool_call 一个 Send 任务（849 行起的列表推导）
    "structured_node_name": "generate_structured_response",  # response_format 分支的 add_node
    "out_of_steps_reply": "Sorry, need more steps to process this request.",  # 689/716 行的哨兵文案
    "unknown_tool_behavior": "feed_back",  # _validate_tool_call 回喂 error ToolMessage，不 raise
}
