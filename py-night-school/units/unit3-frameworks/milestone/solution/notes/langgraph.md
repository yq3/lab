# 对照笔记：langgraph（L3.2 手装图 / L3.3 checkpoint / L3.4 prebuilt 与扇出）

## 它替 mini-agent 付掉了什么

手装图（L3.2，63 行）替掉「循环形态本身」：`while True` 变回边成环、
`if not tool_calls: return` 变条件边路由表、assistant 入史 + ToolMessage 回喂变
`add_messages` reducer（白送按 id 去重）、`astream` 免费送流式可观测；
`recursion_limit` → `GraphRecursionError` 是 max_turns 纪律的图形态。
prebuilt（L3.4，28 行）再替掉整张手装图：`create_react_agent` 一个调用 =
模型节点 + ToolNode（连参数校验与错误回喂）+ should_continue 条件边，
`prompt=` 自动垫 SystemMessage。63 → 28 的差就是「约定优于配置」的定价。

## 它没替你付什么

状态 schema 是我的设计决策：`ClaimState` 哪个键 `Annotated` 合并、哪个键
LastValue 覆盖（L3.2 §2.3）——图引擎只执行注解，不替我选语义；节点函数是我的
（「读状态 → 返回更新」的纯函数纪律）；出口 schema 把关是我的
（`Advice.model_validate_json` 在 L3.2/L3.4 都亲手调——LLM 不是序列化层）；
`recursion_limit` 默认 25，要自己显式给（宁可小了调大）。

## 最惊讶的一个机制

checkpoint/interrupt（L3.3）：跑到 `interrupt()` 图**正常停下**，序列化成 checkpoint
（字节串）→ 杀进程 → 换个进程从 checkpoint 恢复继续跑——手写版永远给不了的
能力，而机制本体只是「把 state 存下来 + 恢复时重放」。它就是毕业设计
「审批暂停 → 恢复」（L5.2）的直接机制。次惊讶：reducer 语义写在类型注解里
（运行时读类型元数据，不是注解处理器）与 Send 扇出「执行并发、归并确定」
（L3.4 §2.2 的 BSP 超步，`sorted(tasks)` 保证归并顺序）。

## 锁定性一句话

图与节点是我的代码（可 git、可单测），但 StateGraph/reducer/interrupt/Send 是
langgraph 私有词汇——好在它与 langgraph4j / spring-ai-alibaba graph 同源，
锁定可以翻译回 Java 栈。

## 什么时候选它

选它：要 HITL 暂停恢复（L3.3）、显式可审计拓扑（fail-closed 的地基）、动态并行
且归并要确定（L3.4 Send）；或要预习 Java 生产栈语义时。不选它：只要一个最薄
循环 + 结构化输出时偏重（63 行装配 vs openai-agents 29 行，且显式图对小流程
是杀鸡用牛刀）。
