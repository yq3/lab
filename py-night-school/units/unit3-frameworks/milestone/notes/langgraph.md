# 对照笔记：langgraph（L3.2 手装图 / L3.3 checkpoint / L3.4 prebuilt 与扇出）

> 本教程主干框架（三连课），也是毕业设计的执行器（spoiler 已明示）。这页信息量
> 最大——手装 vs prebuilt 两种装配的行数差（tablegen：63 vs 28）就在这页解释。
> 固定小节五个（`tests/test_notes_meta.py` 按结构把关）；问题是脚手架，
> 回答完删掉、留结论——`TODO(笔记)` 占位符必须全部替换。

## 它替 mini-agent 付掉了什么

对照 L3.2/L3.4 结尾的对照表，分两种装配写（这正是 tablegen 两行的语义）：
手装图（L3.2）替掉的是「循环形态本身」——`while True` 变成回边成环、
`if not tool_calls: return` 变成条件边路由表、messages 入史变成 `add_messages`
reducer（还白送按 id 去重）；prebuilt（L3.4）再把手装的整张图（63 行）压成
`create_react_agent` 一个调用（28 行）——`ToolNode` 连参数校验与错误回喂都白送。

- TODO(笔记)：两段清单（手装替掉什么 / prebuilt 再替掉什么），对上行号与机制名。

## 它没替你付什么

状态 schema 还是你的（`ClaimState`：哪个键合并、哪个键覆盖是**类型注解**声明的设计
决策，L3.2 §2.3）；节点函数还是你的（读状态 → 返回更新，纯函数纪律）；
出口的 schema 把关也还是你的（`Advice.model_validate_json` 在 L3.2/L3.4 都亲手调）；
`recursion_limit` 默认 25 得自己记得给（对照 L2.3 的 max_turns 纪律）。

- TODO(笔记)：列「没替你付」，每条注一句「这留下的是哪类设计决策」。

## 最惊讶的一个机制

候选（挑一个，注明课次）：reducer 的合并语义写在**类型注解**里
（`Annotated[list, add_messages]` vs 无注解的 LastValue 覆盖——L3.2 §2.3/Step 1，
对 Java 人：这不是注解处理，是运行时读类型元数据）；checkpoint/interrupt 的
「暂停 → 杀进程 → 恢复」（L3.3——手写版永远给不了的那件事）；`Send` 动态扇出
与「执行并发、归并确定」的 BSP 超步（L3.4 §2.2）。

- TODO(笔记)：一个机制 + 课次 + 一句「为什么惊讶」+ 它在毕业设计里对应哪块。

## 锁定性一句话

方向：显式图是你的代码（可 git、可单测节点），但生态词汇（StateGraph/reducer/
interrupt/Send）是 langgraph 私有的——好消息是它是 Java 生产栈
（langgraph4j / spring-ai-alibaba graph）的同源上游，锁定可翻译。你自己写一句。

- TODO(笔记)：一句话，别超一行。

## 什么时候选它

提示方向：需要 HITL 暂停恢复 / 显式可审计拓扑 / 动态并行归并（L3.3/L3.4 的机制）；
要预习 Java 侧同源栈时。反例：只要一个最薄循环时它偏重（对照 openai-agents 29 行）。

- TODO(笔记)：两个选它的场景 + 一个不选它的场景，各一句理由。
