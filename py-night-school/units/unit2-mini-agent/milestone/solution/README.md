# 参考答案

先完成三个 TODO 再进来。对照要点：

- T1 与 L2.3 的差异只有执行器接缝两行——「依赖注入」在 Python 里就是「传个可调用对象」，
  没有注解、没有容器；registry 传空 dict 就是「本地零工具、全走接缝」的 MCP 模式。
- T2 与 L2.4 逐字一致——里程碑考的是「不看讲义能不能复刻纪律」：先入史再校验、
  一个 except 接两种伤、耗尽 fail-loud。
- T3 与 L2.5 逐字一致——注意 content 联合类型的收窄写法（walrus + getattr），
  直接 part.text 过不了 pyright。
