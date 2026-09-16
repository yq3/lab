# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的 reply 是「先记账再恢复」的三分支：reject 分支唯一多的键是 message（缺省从
  DEFAULT_FEEDBACK 来），once/always 唯一多的键是 rule_id（once 恒 None）。恢复指令是
  `Command(resume={"action": ..., ...})`——action 的两个取值对着迷你图 submit 里
  `decision.get("action")` 的判断反推。always 的命中查询在 grant **之前**：已有规则直接
  复用 rule_id（同 pattern 不重复建），这是「批准并记住」去重语义的落点。
- ex2 的两半各一行核心：广播是 `queue.put_nowait(record)`（非阻塞——append 是同步方法，
  谁也不等谁）；订阅的无缝在「snapshot 与 append 之间没有 await」——单线程事件循环里
  不会有事件插队，登记前的事件只可能来自重放、登记后的只可能来自队列，不重不漏。
  finally 的 remove 是断开注销（不然队列越积越多）。
- ex3 的 match 是两维合取：`rule.dept == dept and total_cents <= rule.max_total_cents`，
  边界「恰等 cap 也命中」（≤ 而非 <）——test 的 boundary 断言钉的就是这个；grant 的
  时间戳用 `datetime.now(UTC).isoformat(...)`（UTC 不是本地区时——审计时间戳的可比性）。
  admit 只做「查 + 事件 + 返回」，不碰图：自动批准的恢复动作在讲义服务的
  _register_ticket 里，题目把它剥出来练纯决策面。
