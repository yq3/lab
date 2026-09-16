# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的认知支点是「handoff 在 wire 上就是一个工具调用」：离线剧本第 2 轮
  `script_tool_calls` 点名 `transfer_to_humanspecialist`，与点名 `check_budget` 没有
  任何语法差异——转交之后框架换 system、换工具表、保留历史。忘了 `arguments: {}`
  或拼错工具名是最常见的翻车点（框架会抛 `ModelBehaviorError: Tool ... not found`）。
- ex2 的护栏体只有三步：归一 input → 抽单号查表 → 包 `GuardrailFunctionOutput`。
  `tripwire_triggered=not known` 这种「反向布尔」值得停一秒再写——绊线语义是
  「True = 拦下」，与你的直觉「True = 通过」正好相反。
- ex3 的记账必须放 `finally`：预算异常上抛也会路过它；不 import
  `MaxTurnsExceeded` 不是偷懒——不捕获的异常不需要点名（L1.7 纪律的落地）。
