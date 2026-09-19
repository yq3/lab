# 对照笔记：adk-python（L3.6）

> 抽象光谱第四格：全家桶——框架之外还多给会话/调试器/评估一整层平台件（库里的小平台）。
> 固定小节五个（`tests/test_notes_meta.py` 按结构把关）；问题是脚手架，
> 回答完删掉、留结论——`TODO(笔记)` 占位符必须全部替换。

## 它替 mini-agent 付掉了什么

对照 L3.6 结尾的对照表：整个 `agent.py` 的框架化（`LlmAgent` + Runner 的事件驱动
循环）；工具 schema 自动生成（FunctionTool 从 docstring + 签名出 declaration）；
**mini-agent 完全没有的整层**——会话存储（Session + state + 可插拔
SessionService）、`adk web` 调试器、eval 工具链（AgentEvaluator + 轨迹比对）、
`adk create/deploy` 部署件。

- TODO(笔记)：两层清单（替掉 mini-agent 的件 / mini-agent 没有的件），注机制名。

## 它没替你付什么

L3.5 式问题在这课换了个方向：全家桶给了很多，但**循环语义黑盒化**——预算、终止、
消息装配都在框架深处；`InMemorySessionService` 是「testing and development」的
默认件（§5：全绿时没有任何报错提醒你）；LiteLlm 中转层的参数名是 litellm 的
（api_base/api_key，不是 adk 的命名）；state 前缀（app:/user:/temp:）是 adk
私有词汇。

- TODO(笔记)：列「给了但藏着成本」的件 + 你要亲手问的问题（对照 §5 的两个问题：
会话粘不粘 / 存储共享了没有）。

## 最惊讶的一个机制

候选（挑一个，注明 L3.6 的位置）：session 是一等概念——同一个 agent、两个会话
两套策略（Step 3 的 `item_limit_cents` 实验）；或「一个 API 两种护栏哲学」——
L3.1 的 guardrail 并行赛跑 vs 这里的 before_model_callback 链（Step 4，
回调执行顺序绑定框架版本）；或 eval 的确定性轨迹比对（Step 5 的 ANY_ORDER）。

- TODO(笔记)：一个机制 + 出处 + 一句「为什么惊讶」。

## 锁定性一句话

方向：四个框架里锁定最重——图纸（四类回调、五种服务、目录约定 `google_adk/agents/`）
只有它家有，部署形态偏向 GCP（Cloud Run 一等公民）；换掉它≈搬整栋楼。
你自己写一句（往「多给了什么、多收了什么」压）。

- TODO(笔记)：一句话，别超一行。

## 什么时候选它

提示方向：要调试器与评估工具链开箱即用（eval set 驱动的回归）；团队要
「平台件但仍是库」的形态（对照 L3.7 的真平台）；端点走 LiteLlm 生态。
反例：要轻（88 包 vs 51）、要显式控制循环语义时。

- TODO(笔记)：两个选它的场景 + 一个不选它的场景，各一句理由。
