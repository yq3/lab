# 参考答案（范本改造说明）

先做完自己的改造说明再进来。与 notes/ 的关系（先例 Unit 3 里程碑 solution/notes）：

- **完成态以本目录为准**：notes/ 三页是模板（含 `TODO(改造)` 占位符），本目录是对应的
  完成版——五节齐、无占位符。学员完成里程碑 = 把 notes/ 三页的占位符全部替换为自己的
  结论；卡住或想收口时来这里誊写对照（`tests/test_notes_meta.py` 只判结构齐，不判
  「你写得跟范本一样」——你的产品观察不必与范本相同，结构必须相同）。
- **诚实声明（范本的三处降级）**：
  1. **diff 是示意**：改造点、文件、字段名都对准产品源码（三个克隆 HEAD 即锚定
     commit：fc1bf25 / be952b8 / f84b2977），但行号与上下文行数以你克隆里的实际
     `git diff` 为准——范本不假装贴过你的仓库；
  2. **证据用机制件输出做替身**：范本无法替你产出真产品的运行日志（需要你自己的
     key 与网络），证据节贴的是 L4.x `code/` 机制件的真实输出——同一机制的离线版，
     并注明「真产品证据需自己跑」。你交作业时必须换成自己跑出来的摘录；
  3. **改造二（TradingAgents 预算封顶）的贯穿点只给一种可行形状**：检查放路由器还是
     辩手节点都能达标（超限即停、检查在放行前），范本选了改动最小的一种。

- **三态布局说明**（写给 curious 的同学）：本目录只有 `.md`（范本说明），没有 `.py`——
  三态验证毕业态的 solution 覆盖规则只 glob `solution/*.py` 覆盖到目录根，本里程碑的
  verify.py 是给定基础设施（不含 TODO，无需覆盖），学员作答区是 notes/*.md（文档不
  参与覆盖）。所以毕业态镜像与发货态同构，三命令本来就全绿——里程碑的作答物是文档，
  这是宪法 §4「开放设计题不硬造判分」在里程碑布局上的形态。

| 页 | 范本覆盖的改造 |
|---|---|
| [notes/ai-hedge-fund.md](./notes/ai-hedge-fund.md) | 改人格 prompt（buffett.py）+ 改话语权（mandate YAML `weight:`） |
| [notes/tradingagents.md](./notes/tradingagents.md) | 轮次参数化两态观察 + `max_debate_llm_calls` 预算封顶贯穿 conditional_logic |
| [notes/vibe-trading.md](./notes/vibe-trading.md) | `check_mandate` 抄改到报销付款域 + per-limit pytest |
