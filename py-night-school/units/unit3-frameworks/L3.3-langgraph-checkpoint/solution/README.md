# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的关键就一行 `compile(checkpointer=saver)`，但要看懂两件事：saver 的生命周期
  （每个「进程」自己 `async with demo.open_saver(...)` 开连接、用完自动关——连接
  不关进程挂住）；thread_id 只出现在 config 里，图代码对「会话」一无所知。
- ex2 的 human_gate 与讲义同构：`interrupt(payload)` 在前、`return` 在后——第一次
  执行永远走不到 return（图在那一行抛停了）；恢复重执行时 payload 那行变成了
  「取值」。resume 侧的一行是 `graph.ainvoke(Command(resume=decision), cfg)`：
  第一个参数不再是状态 dict——状态从 checkpoint 来，人工只递「决策」。
- ex3 的重建只有两条规则：相邻快照之间，前者的 next 就是已跑节点；最后者的
  next 非空即暂停点。`__start__` 必须剔除（它是哨兵不是节点，input 快照的 next
  就是它）。payload 与 next 都来自同一个快照——「暂停点」的全部信息都在那里。
