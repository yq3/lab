# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的三层 dict 是纯组装题；真正的知识点是 `model_json_schema()` 的约束映射——
  `min_length` → `minItems`、`gt` → `exclusiveMinimum`，模型端点看得懂的就是这份 JSON。
- ex2 与 L1.5 带参装饰器逐层同构：多出来的只有「从函数对象提取元数据」两行
  （`__name__` / `__doc__`）——Spring 靠组件扫描 + 反射做的事，Python 用装饰器副作用一行搞定。
- ex3 的三种失败都返回 JSON 而不是 raise——这是 agent 与传统分层最大的心态差：
  异常往上抛给「人」，错误回喂给「模型」。raise 出去的栈模型永远看不见；
  回喂的 error JSON 模型下一轮就能修。
