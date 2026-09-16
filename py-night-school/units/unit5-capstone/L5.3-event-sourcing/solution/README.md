# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的 append 有个刻意的顺序：词汇表校验在事务**外**（fail-closed 先于开门），序列化与
  INSERT 在事务**内**——payload 炸了整个追加回滚，seq 一个不烧。seq 分配用
  `COALESCE(MAX(seq), -1) + 1`：没有事件时取 0，链式续号；IntegrityError 翻译成
  EventSeqConflict 时 `from exc` 别丢——审计栈里要能看到「谁触发翻译」。
- ex2 的核心是 canonical：相等（dict 消息 vs langchain 对象）与「序列化相等」之间的缝，
  用显式规范形（role 归一 + 全文 + 固定顺序）填上——L4.1 §5 的坑在这里给出正解。
  命中路径一行 await 都没有，这就是「零请求」的全部含义。
- ex3 的两个函数各只有一行核心：f-string 拼 `单号@签名前 12 位`（可读性截断，全签名在
  run.started payload 留档）；比较不等即抛、相等静默放行。写反 stored/current 的话，
  异常属性断言当场红——审计要能分清「库里的旧世界」与「手上的新世界」。
