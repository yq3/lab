# 对照笔记：adk-python（L3.6）

## 它替 mini-agent 付掉了什么

两层。第一层替掉 mini-agent 本体：`LlmAgent` + Runner 的事件驱动循环（整个
`agent.py` 框架化）；FunctionTool 从 docstring + 签名自动生成 declaration
（对照 L2.2 手写 schema）。第二层是 mini-agent 完全没有的「库里的小平台」：
会话存储（Session + state + 可插拔 SessionService：InMemory/SQLite/Database/
VertexAI）、`adk web` 调试器（事件流可视化）、eval 工具链（AgentEvaluator +
轨迹比对 + eval set）、`adk create/deploy` 部署件。

## 它没替你付什么

给了很多，但循环语义黑盒化：预算、终止、消息装配都在框架深处；默认件藏着成本
——`InMemorySessionService` 的 docstring 自己写着「for testing and development」，
但全绿时没有任何报错提醒你（§5：服务一重启会话全忘、双副本就 404）；LiteLlm
中转层的参数名是 litellm 的（api_base/api_key，不是 adk 命名）；state 前缀
（app:/user:/temp:）与四类 callback 挂点是 adk 私有词汇；代码还得长在
`google_adk/agents/` 目录约定上才被调试器认。要亲手问：会话粘不粘、
存储共享了没有。

## 最惊讶的一个机制

session 是一等概念（L3.6 Step 3）：同一个 agent、两个会话两套策略——往
session.state 注入 `item_limit_cents`，agent 行为随会话变而代码不变。「同一个
组件，不同实例不同记忆」在 Java 里是 prototype/request scope Bean 的老朋友，
但这里的作用域前缀（user:/app:/temp:）是框架语义不是容器语义。次惊讶：
guardrail 的两种哲学——L3.1 并行赛跑 vs 这里的 before_model_callback 链。

## 锁定性一句话

四框架锁定最重：图纸（四类回调、五种服务、目录约定）只有它家有，部署形态偏向
GCP——mini-agent 是你拥有的地基，adk 是精装修的整栋楼，搬走要重买家具。

## 什么时候选它

选它：要调试器与评估工具链开箱即用（eval set 驱动回归、轨迹比对）；团队要
「平台件但仍是库」的形态（比 L3.7 的真平台可控，比框架多一整层工具）；端点
走 LiteLlm 生态。不选它：要轻（88 包 vs openai-agents 51）、要显式控制循环
语义、或部署不打算绑 GCP 生态时。
