# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 就一行 gather：保序是它的契约（传入序 = 返回序），不用你手动 sort——
  这也是 Java 侧 CompletableFuture.allOf 之后还要自己收结果时最想念 Python 的地方。
- ex2 的骨架是 try / except TimeoutError 包住 wait_for：超时不是异常事故，是设计内的降级分支。
- ex3 与 L1.6 的同步生成器逐字对照：`yield` 不变，前面加 `await`；消费端 `for` 变 `async for`。
  token 流的「生产慢、消费快」节奏，就是 L2.1 SSE 流式解析的心智底座。
