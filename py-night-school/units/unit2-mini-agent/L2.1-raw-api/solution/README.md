# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的 None 归一化写在导航之后一行：先取到值再处理，别在导航表达式里塞条件。
- ex2 与讲义 `SSEDecoder` 同构——你的答案若是生成器函数（yield 而非 return 列表），
  那正是 L1.6 惰性管线的用武之地：块到事件到文本一条流水线。
- ex3 的 `json.loads(tool_call["function"]["arguments"])` 就是「字符串套娃」的日常拆封动作；
  L2.2 起这行会被 Pydantic 的 `model_validate_json` 升级成「解析 + 校验」一步到位。
