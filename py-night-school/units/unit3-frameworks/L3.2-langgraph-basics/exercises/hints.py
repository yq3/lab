"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "先画图再写码：三个节点各叫什么；START 出发到谁；条件边挂在哪个节点之后、"
        "它的 path 函数已经给你（route_after_reviewer，返回值就是节点名）；tools 之后回到哪成环；"
        "finalize 收口到哪。",
        "形状级：add_node 的两个参数分别是什么？add_edge 里 START/END 这种「哨兵」放在哪一端？"
        "add_conditional_edges 的 source 挂谁、path 传哪个函数？"
        "装配完必须做什么才能得到可 invoke 的对象？",
        "完整装配：builder = StateGraph(LoopState)，依次 builder.add_node('reviewer', reviewer)、"
        "add_node('tools', tools_node)、add_node('finalize', finalize)；"
        "builder.add_edge(START, 'reviewer')；builder.add_conditional_edges('reviewer', route_after_reviewer)；"
        "builder.add_edge('tools', 'reviewer')；builder.add_edge('finalize', END)；"
        "return builder.compile()。",
    ],
    "ex2": [
        "两件事：状态里的字段怎么声明「合并语义」（对照讲义 demo.ClaimState：messages/events 与 advice 的"
        "注解差在哪）？每个节点的返回值里多登记一个键。",
        "形状级：Annotated 的第二个参数放一个什么样的函数——标准库 operator 模块里哪个函数是 "
        "(a, b) -> a + b？节点返回值里那个键的值，是「一个事件字符串」还是「装一个事件的列表」？"
        "（想想 reducer 每次收到的是什么）",
        "状态字段写 events: Annotated[list[str], operator.add]（顶部 import operator）；每个节点的返回值"
        '加一个键，如 intake 里与 messages 并列写 "events": ["intake"]——事件名与节点名一致，'
        "check/reject/approve 同理。",
    ],
    "ex3": [
        "先内后外：build_review_subgraph 与讲义 demo.build_graph 同构（Step5 的 build_review_subgraph "
        "就是同构范本）；外层图的关键新知——编译好的子图可以整个当 add_node 的第二个参数（图即节点）。",
        "形状级：子图的三个 add_node 各挂什么；外层 add_node('review', ???) 的问号处传什么表达式？"
        "条件边挂在 precheck 之后、path 用 route_after_precheck——它返回的两个名字必须与外层哪两个"
        "节点的名字一致？review 与 deny 各自的终点是什么？",
        "子图：builder = StateGraph(ReviewState)，add_node 三节点，add_edge(START, 'reviewer')，"
        "add_conditional_edges('reviewer', route_after_reviewer)，add_edge('tools', 'reviewer')，"
        "add_edge('finalize', END)，compile 返回。外层：StateGraph(GateState)，"
        "add_node('precheck', precheck)、add_node('review', build_review_subgraph(model))、"
        "add_node('deny', deny)，add_edge(START, 'precheck')，"
        "add_conditional_edges('precheck', route_after_precheck)，add_edge('review', END) 与 "
        "add_edge('deny', END)，compile 返回。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
