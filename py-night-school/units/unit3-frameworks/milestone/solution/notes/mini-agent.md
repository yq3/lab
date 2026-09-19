# 对照笔记：mini-agent（Unit 2 对照组）

## 它替 mini-agent 付掉了什么

对照组没有「它」，这节记的是 86 行（solution 口径）各在买什么控制权：

- `agent.py::ReActAgent.run`（循环 + 双终止）：回喂格式、裁剪策略、终止条件想改就改——
  每一行业务可见，没有一行在框架深处；
- `tools.py::tool / to_openai_tools / run_tool`（schema 生成 + 分发）：工具边界输出
  canonical JSON 的纪律、unknown_tool 回喂 error 而不是 raise，全是我写的也是我能改的；
- `structured.py::ask_structured`（校验回喂重试）：先入史再校验的审计取舍、attempts
  预算、feedback 措辞——L2.4 的每个设计决策都在明面上。

## 它没替你付什么

比四个框架都多，至少五件：流式可观测（得靠 print_trace 手搓）；检查点/暂停恢复
（L3.3 才见到，mini-agent 的 messages 列表跑完即丢）；多 agent 转交（要自己再造
一层循环）；会话存储（无，跨请求失忆）；评估工具链（只有手写 pytest 契约——
虽然这恰好是本教程最看重的一件）。补任何一件都是「再造一个小框架」的工时。

## 最惊讶的一个机制

协议级 mock 端点（L2.3 引入、L3.x 全学段服役）：起真 HTTP 服务、预生成台词，
agent 的整条管道被 pytest 离线确定地测——Java 里等价物是 WireMock，但这里
被测对象是「我的 agent 循环 + 框架的管道」而不只是 HTTP 层。惊讶点在于：
agent 应用居然可以像普通服务一样做契约测试，零 key、三态可验收。

## 锁定性一句话

零框架依赖：每个行为都是你要亲手的行，也因此每个行为都是你能改的行。

## 什么时候选它

选它：教学与原型（想看清 agent 每层协议）；极端审计要求——每个行为可指认、
可单测、可改动，合规解释成本最低的场景。不选它：需要 checkpoint/HITL、动态扇出、
会话存储这些「一个人写不完」的件时——再写下去就是在重造 langgraph。
