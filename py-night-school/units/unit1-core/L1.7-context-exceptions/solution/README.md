# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1：`else` 只在无异常时执行——把成功路径的 `return "OK"` 放进 else，`finally` 自然成为两条路共同的最后一站；`return` 不会跳过 finally（顺序铁律：`["try", "else"/"except", "finally"]`）。
- ex2：基类 `__init__` 里 `super().__init__(message)` 保证 `str(e)` 可用，再把领域证据（`context`）挂成属性；`from exc` 设的是 `__cause__`，与隐式的 `__context__` 是两条通道。
- ex3：`global` 声明 + 保存旧值 + `try: yield` + `finally: 恢复`——这套四步是「临时改全局状态」类上下文管理器的万能模板。
