# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1：三个 TODO 其实是一条链——函数（被 import 时对外提供的能力）→ main（直接运行时的主流程）→
  guard（入口约定）。同一个文件靠 `__name__` 的两种取值切换身份，这就是 Python 版的
  「库代码 + main 方法二合一」。
- ex2：修的是启动方式不是 import。补上 guard 后，`python -m claimfix.runner` 走 main；
  直接跑仍然炸出 `attempted relative import`——验收第三条专门钉死了这一点，防止用
  「改成绝对导入」绕过考点、破坏包结构。
- ex3：B 场景的关键是「import 执行被导入文件但 guard 不触发」；C 场景的关键是
  「直接运行的 probe_c 是 __main__，链上的 probe_a/probe_b 都是普通模块名」。
  预测输出时最容易漏的是 B 场景第一行——它来自 probe_a 而不是 probe_b。
