# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1：四个签名就是本课 §2 的类型词汇表——`list[int]`、`list[tuple[str, str]]`、
  `dict[str, int]`、`str | None`。注意 `first_rejected` 的返回类型是联合：
  函数体里有一条 `return None` 的路，签名必须如实说出来。
- ex2：两个类与 AuditSink 没有继承关系（`__bases__ == (object,)`），但
  `isinstance(sink, AuditSink)` 通过——结构化类型的全部要点就在这一对反差里。
  runtime_checkable 的 isinstance 只查「record 这个名字在不在」，不查签名，
  所以「长得像」的最终裁判仍是 pyright（静态）+ 行为测试（动态）。
- ex3：Any → 精确类型的依据全在函数体里：`min(a, 5000)` 圈定 int、
  `.startswith` 圈定 str、`counts.get` 圈定 dict 的键值形状。
  meta-test 还会递归扫「套壳 Any」（如 `dict[str, Any]`）——Any 是逃生舱，
  用它就得在 code review 里给理由。
