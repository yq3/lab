"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "两段对话的图和节点一模一样，唯一的差别在接线：compile 的括号里多了什么、"
        "invoke 的第二个参数带了什么。先把「谁生产 checkpointer」想清楚——demo 里有个"
        "异步上下文管理器专门干这个。",
        "形状级三问：compile 的问号处放哪个对象、它由哪一行 async with 产出？"
        "invoke 的第二个参数（config）用 demo 里的哪个辅助函数造、thread_id 在里面哪个位置？"
        "second_segment 为什么必须重新 open + compile，而不是复用 first_segment 的图对象"
        "（「杀进程后重启」这句话缺了什么共享）？",
        "first_segment：async with demo.open_saver(db_path) as saver: 里写 "
        "await build_chat(model).compile(checkpointer=saver).ainvoke({'messages': "
        "[('user', SEGMENT_1)]}, demo.thread_config(thread_id))。second_segment 同样接线后连续"
        "两次 ainvoke：先 ('user', SEGMENT_2) 配 thread_id，再 ('user', SEGMENT_3) 配 "
        "demo.thread_config(other_thread)。",
    ],
    "ex2": [
        "human_gate 只欠一次调用与一份返回值；resume_side 只欠 invoke 的第一个参数。"
        "回忆暂停的语义：第一次执行到 interrupt 那行时图就停了（后面的 return 根本没跑）；"
        "恢复时同一节点从头重跑，interrupt 那行变成了「取人工递来的值」。",
        "形状级四问：interrupt() 的参数是什么形状（暂停时前端要展示给操作员看什么字段）？"
        "它的返回值是谁放进去的？节点返回的 dict 三个键各放什么（给模型的一条消息 / 审计事件 / "
        "给 finalize 读的决策键）？resume 侧 ainvoke 的第一个参数——平时传状态 dict，"
        "现在传一个什么对象、构造它的关键字参数叫什么、值从函数的哪个形参来？",
        "human_gate 里：advice = parse_last_advice(state)（非 None，路由保证过）；"
        "answer = interrupt({'claim_id': advice.claim_id, 'reason': advice.reason})；返回 "
        "{'messages': [{'role': 'user', 'content': f'人工审批结果：{answer}'}], "
        "'events': ['human_gate'], 'human_decision': answer}。resume 侧那一行："
        "result = await graph.ainvoke(Command(resume=decision), cfg)——顶部 import "
        "from langgraph.types import Command, interrupt。",
    ],
    "ex3": [
        "先在纸上把讲义 Step4 的 history 列表过一遍：相邻两个快照之间，前一个的 next "
        "就是这段时间实际跑过的节点；最后一个快照特殊在哪（它的 next 可能还没跑）。",
        "形状级四问：排序的 key 读每个快照的哪个字段（metadata 可能是 None，"
        "用什么写法给默认值）？相邻成对迭代用标准库哪个函数？next 元组里哪个哨兵值必须"
        "剔除、为什么它不算「跑过」？什么条件下才算「暂停」、此时 payload 从最后一个"
        "快照的哪个属性取？",
        "ordered = sorted(snaps, key=lambda s: (s.metadata or {}).get('step', -1))；"
        "ran = []；for prev, _cur in zip(ordered, ordered[1:]): ran.extend(n for n in prev.next "
        "if n not in SENTINELS)；last = ordered[-1]；paused = tuple(n for n in last.next if "
        "n not in SENTINELS)；payload = last.interrupts[0].value if paused and last.interrupts "
        "else None；supersteps 取 (last.metadata or {}).get('step', 0)；装进 Trajectory 返回。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
