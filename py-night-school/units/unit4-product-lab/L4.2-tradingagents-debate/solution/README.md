# 参考答案

先完成练习再进来。对照要点：不追求与你的写法一致，追求**通过验收 + 读得舒服**。

- ex1 的改造是「同一条数据流的两个端口」：DebateRouter 的构造器收轮次（对版
  ConditionalLogic(max_debate_rounds=...)）、build 把 config.max_debate_rounds 传进去——
  `should_continue_debate` 的函数体一行没动。改配置不改逻辑，这正是产品
  default_config → ConditionalLogic 这条依赖方向的意义。
- ex2 的四行顺序是全部要点：**检查在放行前**（不超卖）、**计数在放行后**（被拒的不计）、
  委托给被包装模型、原样返回。顺序错了测试会抓：「先转发再检查」会让 inner.request_count
  变成 3（超卖），「先计数再检查」会让 used 超过 cap。recursion_limit 那条轴的测试则在
  提醒：预算罩的是模型调用，不是 superstep——「整理」节点两轴上的开销不一样。
- ex3 的取向比代码更重要：百分比与带小数货币串**不可抢救**（定不了单位），与占位串同样
  丢成 None——一个坏字段不毁整份裁决；整份输出解析不了才升级成 REVIEW 哨兵。两道闸
  的分工：字段级归一保住结构化调用，哨兵保住「失败可见」。
