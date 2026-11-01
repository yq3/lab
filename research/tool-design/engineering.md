# 业务 API → Tool 工程化落地专题：异步任务与生产注意点

> 2026-11-01 · 工程篇（report.md 是设计原则篇，先读那篇）· 证据等级沿用：【一手】官方原文全文抓取 /【转述】第三方转述 /【摘要】仅搜索摘要 /【未找到】。

## 0. 结论速览

1. **异步任务有官方标准答案了**：MCP Tasks 扩展（2026-07-28 规范，ext-tasks 仓库）——服务端不阻塞，返回持久任务句柄（taskId + 状态机 + 建议轮询间隔 + TTL），客户端轮询/订阅、可中途输入（HITL）、可取消。官方适用清单第一条场景就是"包装已有 job-ID 风格的异步业务 API"。
2. **异步问题的本质是"等待时长分级"**：秒级同步返回；十秒级开进度通知；分钟级长轮询；分钟~小时走任务句柄三元组；跨会话走 webhook 回调唤醒。业界五个范式（MCP Tasks / A2A / OpenAI Background / Claude Code 后台任务 / Azure LRO）全部收敛到"任务状态机 + 句柄 + 轮询或推送"。
3. **最大反模式是让模型自己发明轮询协议**：Claude Code 有公开 bug 报告——模型绕过通知机制自己热轮询输出文件，浪费 token 和轮次。轮询纪律必须写进 tool description 或由协议承载。
4. **工程化侧有硬数据**：写操作加幂等键把 agent 重复写入率从 28% 降到 4%；tool 重命名是破坏性变更（后端部署成功 ≠ 存量 agent 工作流不炸）；工具输出是注入载体（Microsoft Zero Trust 专门有防御指南）。
5. **上下文经济学是持续战线**：大结果用 resource link 引用而非内嵌；structuredContent 与 content 双份冗余是已知问题（官方讨论中）；JSON 比等价结构化文本多耗约一倍 token。
6. **回调与挂起是比轮询更高层的两块拼图**（第四轮补）：MCP Tasks 的默认交付是轮询，但完整解法是三层——任务执行层（业务侧）／事件回传层（webhook push、会话内通知、产品级通知）／agent 状态层（挂起/恢复：LangGraph `interrupt()`、OpenAI Agents SDK RunState、Temporal durable execution）。**"回调 agent"是运行时（harness）能力而非模型能力**；deepagents 的"挂起机制"就是 LangGraph interrupt/checkpoint。

## 1. 异步专题：agent 调用异步业务 API 的业界实践

### 1.1 问题本质

agent 的工具调用是"请求-响应"心智，但业务系统里耗时任务（批量处理、审批流、报表生成、风控审核）天然异步：提交后只能拿任务号，结果要等。把同步协议硬套在长任务上会撞三堵墙：连接超时（客户端与中间件通常几秒~几十秒就断）、崩溃恢复（对话中断后结果丢失）、模型行为退化（长时间无反馈时模型会焦虑性重试或放弃）。

### 1.2 等待时长分级——五个范式收敛出的全景

| 预期时长 | 模式 | 业界出处 |
|---|---|---|
| < 5 秒 | 同步阻塞返回 | 常规 |
| 5 秒 ~ 1 分钟 | 保持请求 + 进度通知（progressToken + `notifications/progress`）+ 取消（`notifications/cancelled`） | MCP 基础规范 |
| 1 ~ 10 分钟 | 提交即回 + 轮询（可带 `wait`/long-poll 参数减少往返） | OpenAI Background Mode（`background:true` → `queued` → 轮询 `GET /v1/responses/{id}` 或 webhook） |
| 10 分钟 ~ 小时 | **任务句柄三元组**：`submit`（返回 taskId）+ `get_status`（状态机）+ `cancel`；结果以引用（resource/artifact）交付 | **MCP Tasks 扩展**（官方）；A2A 协议（8 态生命周期）；Azure LRO（202 + Location 轮询）；Google Operation（done 标志） |
| 跨会话 / 无人值守 | Webhook 推送 → 唤醒 agent 运行时发起下一轮 | A2A push notification（客户端提供 webhook）；Claude Code 后台任务完成时主动通知 agent；Temporal 类持久化工作流 |

要点：这条光谱是**连续的**，一个系统的工具集会同时占好几档；关键是给每个 tool 明确归档，不要让"实际上要跑 8 分钟"的操作伪装成同步工具。

### 1.3【一手】MCP Tasks 扩展详解（官方标准，2026-07-28 规范）

来源：[官方文档](https://modelcontextprotocol.io/extensions/tasks/overview) + [ext-tasks 仓库](https://github.com/modelcontextprotocol/ext-tasks)（由 RFC #982"长运行工具/异步工具/可恢复性"与 Discussion #491"异步操作"演化而来）。

**核心机制**：

- 能力协商：客户端在请求 `_meta` 里声明 `io.modelcontextprotocol/tasks` 扩展，服务端在 `server/discover` 里通告；服务端**按请求自行决定**返回最终结果还是任务句柄（`resultType: "task"` 的 `CreateTaskResult`）。
- 任务句柄包含：`taskId`、初始状态、**`ttlMs`（存活时间）与 `pollIntervalMs`（建议轮询间隔）**——服务端直接告诉客户端"多久查一次"，这是防热轮询的协议级设计。任务必须在响应发出前**持久化创建**。
- 生命周期状态机：`working` →（`input_required` ⇄）→ 终态 `completed`（`result` 字段=同步场景会返回的结果）/ `failed`（JSON-RPC error）/ `cancelled`。终态不可变。
- 轮询为默认：`tasks/get`；服务端可选推送：`notifications/tasks`（订阅制，携带全量任务状态，省一次 get）。
- 中途输入（HITL）：任务进入 `input_required`，`tasks/get` 响应带 `inputRequests`（含 elicitation），客户端经 `tasks/update` 提交答复——不需要第二条连接。
- 取消：`tasks/cancel`，**cooperative**（尽力而为，服务端确认意图但不保证停）。
- 客户端要求**持久化保存 taskId**，崩溃/重启后可凭同一 ID 续查。

**官方适用清单**（逐条对照）：长运行操作（CI、批处理、训练）；人工审批门/审查步骤；**"包装本身就用 job ID 的既有 API（云部署、异步 API、队列任务）——建 job 时返回 task，job 完成时落终态"**（← 这就是"Java 业务系统已有异步任务中心"的直接官方背书）；不稳定连接（移动端、断网环境，task ID 存活于断连之外）；批处理（部分进度有意义，状态消息上报进度）。

**现状提醒**（官方原文 + 社区 + 源码复核，详见 §6）：Tasks 存在**两条规范线**——2025-11-25 wire 版本曾将其纳入核心协议（`capabilities.tasks` 协商、`tasks/get` 等方法类型，MCP Python SDK 已内置生成类型）；后又以 ext-tasks 扩展形式演进（2026-07-28，扁平 `resultType:"task"` 判别形状）。**两条线的报文形状不一致**（嵌套 `task` 字段 vs 扁平合并），接入前必须以目标 wire 版本为准核对。客户端支持不齐（官方维护 client matrix，需双方显式 opt-in）；所以：服务端按状态机+句柄语义设计，客户端（公司网关）不支持时用等价的自实现（1.5 节）。

### 1.4 各家范式对照

| 维度 | MCP Tasks | A2A（Linux 基金会） | OpenAI Background | Claude Code 后台任务 | Azure LRO / Google Op. |
|---|---|---|---|---|---|
| 句柄 | taskId（持久、有 TTL） | Task 对象（可列出/取消） | response id | bash/task id | operationId / Operation |
| 状态机 | working / input_required / completed / failed / cancelled | 8 态，含 input-required | queued / in_progress / completed / failed（+requires_action 类） | running / completed / failed | Succeeded / Failed / Cancelled（done 标志） |
| 进度 | status message + 可选通知推送 | SSE 流 + webhook | 轮询或 webhook | 完成时通知唤醒 agent | 轮询 |
| 中途输入 | inputRequests + tasks/update | input-required 状态 | requires_action | 权限确认门 | — |
| 取消 | tasks/cancel（cooperative） | tasks/cancel | — | TaskStop | 有的支持 |

共同骨架：**状态机 + 持久句柄 + 轮询或推送 + 可选中途输入/取消**。差异只在载体与集成深度。结论：不管底层协议是哪个，业务侧 tool 的语义设计按这个骨架来都不会错。

### 1.5 异步设计十条军规（合并各家）

1. **按时长分级选模式**（1.2 表），给每个 tool 显式归档；慢操作绝不伪装成同步工具。
2. **提交调用返回"句柄包"**：`task_id` + 当前状态 + 预计时长/ETA + `next_poll_seconds`（或直接给 `pollIntervalMs`）+ 用法提示（"请先继续其他工作，N 秒后再查"）。
3. **状态机对模型友好**：终态显式、互斥；`failed` 的 error 用可行动文案（原则篇 P7）；长任务状态里带阶段性进展（"已处理 340/1200 条"）防模型焦虑性重试。
4. **提交带幂等键**：agent 的重试比普通客户端凶得多（模型重发、框架重试、超时重试），submit 类工具必须收幂等键并透传给业务侧去重。
5. **别让模型发明轮询协议**：要么协议承载（MCP tasks 的 pollIntervalMs），要么 description 写死纪律（"每 30 秒查一次，最多查 10 次；期间去做别的事"）。Claude Code 的公开 bug 报告（模型绕过通知热轮询输出文件）就是反面教材。
6. **大结果落资源，状态查询只回摘要 + 引用**：终态 result 给摘要和 resource link/artifact，需要全文时模型再按需取（与上下文经济学联动，见 §2.4）。
7. **可取消是一等能力**：暴露 `cancel_task` 工具 + 传播取消到业务侧；把"不可取消"在描述里写明。
8. **HITL 状态显式化**：审批/补料用 `input_required` 语义（或 elicitation / interrupt），别用"失败重试"模拟。
9. **多步写事务在服务端编排成单一任务**：agent 编排 N 个异步写 = 放大每跳的失败面；在 Java 侧做 saga/状态机，对 agent 暴露成一个 submit。与原则篇 P1"面向结果"同源。
10. **没有回调能力就别硬撑轮询**：平台不支持唤醒时，任务完成走通知渠道（IM/邮件/下次会话注入摘要），当前会话明确告知"任务已受理，稍后可凭 task_id 查询"并结束该分支——比让模型挂着轮询几十轮强。

### 1.6 映射到我们的场景（Java 业务系统 + 公司 Python MCP 网关）

- **先盘点 Java 侧已有的异步基建**：分布式任务调度/异步任务表/状态查询接口大概率已存在（这正是 MCP Tasks 官方说的"wrap an API that already uses job IDs"）。Tool 层不新造任务系统，只做语义包装：`submit_xxx`（返回句柄包）+ `get_task_status`（映射业务状态 → 模型友好状态机）+ `cancel_task`（透传）。
- **问清公司网关的能力边界**（接入前必问清单）：支持 progress 通知吗？支持取消传播吗？支持/计划支持 MCP Tasks 扩展吗？Streamable HTTP 会话超时多长？——答案决定你的工具在 1.2 表上能站哪几档。
- **网关不支持 Tasks 时的等价自实现**：submit/status/cancel 三个普通工具 + description 写死轮询纪律，语义与 Tasks 完全对齐；将来网关升级，迁移只是换载体。
- **业务状态机翻译表**是 Java↔Python 两层间的显式契约：业务状态码（如 `PROCESSING`/`WAIT_APPROVAL`/`PARTIAL_SUCCESS`）→ 模型状态（working / input_required / completed / failed / cancelled）→ 错误文案模板。放 Python 薄层做，别让 Java 侧为模型改口径。

### 1.7 主动回调：任务完成后如何"叫醒" agent（第四轮补）

先立结论：**"回调 agent"不是模型能力，是 agent 运行时（harness）能力**。LLM 本体是无状态的请求-响应函数；要让完成事件"唤醒"它，运行时必须有三件套——持久化的会话状态、可寻址的事件入口（webhook/信号）、re-invoke 引擎（拿事件 + 旧状态再调一次模型）。业界四条路线，按工程重量排序：

| 路线 | 机制 | 代表实践 | 适用 |
|---|---|---|---|
| ① 会话内通知（最轻） | 后台任务完成 → harness 把完成事件作为新输入 re-invoke 模型，对话继续 | Claude Code 后台 Bash/子任务（`run_in_background`，完成时唤醒 agent 读结果）；OpenAI Assistants `requires_action` | 会话存活期内的分钟级任务 |
| ② Webhook + 挂起恢复（中） | 任务系统 POST 回调 → agent 运行时注入事件 → 从 checkpoint 断点恢复 | A2A push（`tasks/pushNotification/set` 注册 webhook，推送 statusUpdate/artifactUpdate 等生命周期事件）；LangGraph interrupt/checkpoint 恢复 | 分钟~小时级，agent 服务自控 |
| ③ 持久化执行引擎（重） | workflow 引擎托管 agent 生命周期，signal/事件驱动推进，进程重启无损 | Temporal（activity 发任务 → workflow 等回调 signal；有 LangGraph plugin、OpenAI Agents SDK / Pydantic AI / Claude Code 集成）；LangGraph 1.0 background runs（进程退出后继续跑） | 跨天 / 跨重启 / 强可靠 |
| ④ 产品级通知（绕开模型，最稳） | 任务完成推通知给用户（push/IM/邮件），结果落盘，下次对话再消费 | ChatGPT Tasks 与 Deep Research（后台跑完推通知，结果作为新消息进对话） | 用户可离场、时效不敏感 |

设计姿态：**能降档就降档**——④永远兜底；②是自建 agent 服务的主战场；③只在真有跨天/强一致诉求时上；①体验最好但依赖 harness 内建支持。

### 1.8 挂起/恢复机制：deepagents 与持久化执行（第四轮补）

**deepagents 是什么**（【一手】仓库 README，`gh api` 拉取）：LangChain 官方的"有主见"agent harness（batteries-included，自述灵感来自 Claude Code）。栈层次：LangGraph（图运行时）→ `create_agent`（轻 harness）→ Deep Agents（子代理 / 文件系统 / 上下文管理 / shell / 持久记忆 / **HITL** / skills / 任意 MCP 工具，全套预置）。

**挂起机制的本体是 LangGraph `interrupt()`**：

1. 代码调用 `interrupt(payload)` → 图执行暂停，**全部状态经 checkpointer 持久化**，payload（审批请求/征询内容）浮出给外部系统；
2. 外部答复后以 `Command(resume=value)` 从断点续跑——对模型而言就像那次工具调用返回了值；
3. deepagents 的 HITL（approve / edit / reject）就是把敏感工具调用包进这一层。

**把它用于异步等待**：挂起等人与挂起等事是同一机制——把挂起点放在"提交异步任务"之后，恢复条件从"审批结果"换成"任务完成事件"（webhook 到达时由服务端触发 resume），审批语义即复用为异步语义。这是 deepagents/LangGraph 栈对异步场景真正的价值：**等待不占模型轮次，事件到了才花钱调模型**。

**OpenAI Agents SDK 同构**（【摘要】官方文档）：interruptions + `RunState`——运行暂停在待审批工具调用上，状态可保存，之后 `agent.run(state)` 带决定恢复；要点：嵌套 handoff 产生的中断要在顶层 agent 上恢复。

**LangGraph 1.0（2025-10）把持久化转正**（【一手】官方博客）：durable execution 默认（执行状态自动持久化，服务重启"从离开的地方精确续跑"）；persistence 明确面向 "multi-day approval processes or background jobs that run across multiple sessions"。

**工程红线与已知坑**：

- **checkpoint ≠ durable execution**（Diagrid 批评文）：checkpoint 只保存图状态，不保证副作用可安全重放——恢复/重试时 LLM 调用与工具调用可能重复执行；兜底永远是工具幂等（呼应 §2.2）。
- 社区实锤坑：interrupt 与工具调用组合的**双执行**问题、resume 传不同值的状态保留 bug、长工具调用超时后从 checkpoint 静默重放（均见 LangGraph issues/论坛）。
- Temporal 路线用 workflow 引擎解决副作用重放（replay 边界、durable wait、side-effect 隔离），代价是引入整套工作流引擎。

**选型映射**：自建 Python agent 服务若跑在 LangGraph/deepagents 上，②路线（webhook → resume）几乎是免费的；若自研 agent loop，"状态持久化 + 事件入口 + re-invoke"三件套要自己造——这是"选框架还是自研"最实际的一条收益依据。

## 2. 工程化落地注意点清单（异步之外）

### 2.1 版本与兼容：tool schema 是"活着的契约"

重命名/改签名对普通系统是重构，对 agent 是**破坏性变更**——后端部署成功，存量 AI 工作流（已上线的 agent 提示词、缓存的工具清单）还在按旧契约调用（【摘要】"MCP tool renaming best practices"）。实践：破坏性变更走新名（`tool_v2`）或网关双路由灰度；旧版本描述先标 deprecated 过渡期；工具清单变更纳入发布评审，不当纯代码 refactor。

### 2.2 幂等与重试安全：agent 是最凶的重复调用方

写操作收**持久化幂等键**（key 由 tool 层生成并跨重试复用，透传业务侧去重）；配套 dedupe log、outbox、不可逆操作的确认门。硬数据：【转述】"给每个写操作加幂等键，把 agent 重复写入率从 28% 降到 4%"。Stripe 幂等键是祖师爷（原则篇已引）。MCP tool annotations 的 `idempotentHint` 顺手标上。

### 2.3 注入防御：工具输出是不可信数据

检索/查询类工具的返回内容可能被投毒（间接注入），Microsoft 有专门的 Zero Trust 指南（【转述】[Defend against indirect prompt injection attacks](https://learn.microsoft.com/en-us/security/zero-trust/sfi/defend-indirect-prompt-injection)）。分层防御：输出按数据标注/消毒、读后写操作（读完外部内容后紧跟写调用）加确认、工具权限最小化、出站动作白名单。这一条在"业务系统接 agent"场景特别致命——注入的跳板就是你的查询工具返回体。

### 2.4 上下文经济学：结果交付方式是持续战线

- 大结果用 **resource link / artifact 引用**替代内嵌（MCP 2025-06-18 起 CallToolResult 支持），摘要进上下文、全文按需取。
- 已知协议冗余：结构化结果在 `content` 与 `structuredContent` 双份返回（官方讨论 #1563/#1715 在推可配置），大 JSON 慎重。
- 【转述】JSON 约为等价结构化文本 2 倍 token（serena #1325 实测讨论）。
- Anthropic 自己都承认"MCP 有上下文问题"，缓解方向就是原则篇 P8 懒加载 + 本条引用化交付。

### 2.5 观测与审计：三层链路一套trace

OTel 三件套（trace/metric/log）覆盖 agent→网关→Python→Java 全链路（社区已有 MCP OTel 实践与带开箱观测的 agent gateway 方案，【摘要】）；网关侧统一视图要看模型行为指标：选错工具率、参数错误率、token 成本 per tool、幻觉调用率。**审计**是合规刚需：谁（用户身份）、何时、调了什么 tool、什么参数、结果摘要、是否经审批——写操作全量留痕。

### 2.6 限流与背压：防 agent 扇出打爆业务系统

模型 parallel tool calls 会瞬间并发打业务接口；配额按"用户 × agent × tool"三维限流在网关做；Python→Java 侧熔断 + 降级（降级返回"系统繁忙，请稍后重试"的可行动文案，而不是裸 500）；对昂贵查询工具做 TTL 缓存去重。

### 2.7 超时三层对齐与取消传播

模型侧等待窗（agent 框架的 tool 超时）、网关超时、Python→Java 超时必须显式对齐，fail fast；收到取消（MCP cancelled / tasks/cancel）要沿链路传播到 Java 侧任务系统，不能只断 Python 这跳。

### 2.8 状态与一致性：读旧写竞态

agent 先读后写跨多轮，中间业务数据可能已变（库存、价格、配额）。写工具透传乐观锁版本号（业务实体带 version，写时校验）或在服务端重校验；句柄/任务状态跨会话查询要无状态可寻址（taskId 全局唯一，不绑会话）。

### 2.9 评测与灰度：tool 变更要过评测 CI

description/schema 的每次改动都跑评测集（原则篇 P10 的 held-out 集合），防"改一句文案、掉五个点"无声回归；新版本工具先影子流量（记录不执行或双跑比对）再放量。AWS 官方指引把生产化分三根柱子：tool 设计 / server 托管 / 治理（【摘要】[AWS Prescriptive Guidance: MCP Strategies](https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/)），治理这根柱子里就有版本、评测、审计。

### 2.10 HITL 与审批：高危操作的门禁

写/删除/对外发送类工具默认挂确认门（用户侧确认或审批流），对应 OpenAI `requires_action`、A2A `input-required`、MCP elicitation/Tasks input_required 三家的共同设计；金额/权限阈值之上的操作走双人审批。与原则篇 P9（写操作 opt-in）是同一件事的两个层面：静态暴露面分级 + 运行时门禁。

## 3. 本轮新增来源表

| # | 来源 | 证据 | 要点 |
|---|---|---|---|
| E1 | [MCP Tasks 扩展官方文档](https://modelcontextprotocol.io/extensions/tasks/overview) + [ext-tasks 仓库](https://github.com/modelcontextprotocol/ext-tasks) | 【一手】 | 任务句柄/状态机/轮询间隔/TTL/HITL/取消，官方标准 |
| E2 | [A2A 规范：Task 概念](https://agent2agent.info/docs/concepts/task)（[官方 spec](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)） | 【摘要】 | 8 态生命周期、input-required、webhook push |
| E3 | [OpenAI Background Mode 官方指南](https://developers.openai.com/api/docs/guides/background)（[Deep Research](https://platform.openai.com/docs/guides/deep-research)） | 【摘要】 | background:true → queued → 轮询/webhook；~10 分钟保留期坑 |
| E4 | Claude Code 后台任务（官方文档 + 社区 bug 报告） | 【转述】 | run_in_background + 完成通知；反面教材：模型热轮询输出文件 |
| E5 | MCP RFC #982"长运行工具"、Discussion #491"异步操作" | 【摘要】 | Tasks 扩展的来龙去脉（长连接保持问题） |
| E6 | [Microsoft：Defend against indirect prompt injection](https://learn.microsoft.com/en-us/security/zero-trust/sfi/defend-indirect-prompt-injection) | 【转述】 | 工具输出不可信、分层防御 |
| E7 | 幂等专题五篇（7 patterns / idempotency key / exactly-once 等，社区工程文） | 【转述】 | 28%→4% 重复写入率数据点；durable key/outbox/确认门 |
| E8 | [AWS Prescriptive Guidance: MCP Strategies on AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/) | 【摘要】 | 生产化三支柱：工具设计/托管/治理 |
| E9 | MCP 结构化输出与上下文（讨论 #1563、#1715、SAP 25k token 响应、serena JSON 2x token） | 【转述/摘要】 | resource link 引用化交付、双份冗余、token 成本 |
| E10 | tool 重命名=破坏性变更、OTel for MCP、无状态扩展 | 【摘要】 | 版本纪律、观测、部署形态 |
| E11 | [deepagents 仓库 README](https://github.com/langchain-ai/deepagents)（gh api 拉取） | 【一手】 | harness 定位、HITL/子代理/持久记忆、LangGraph 栈层次 |
| E12 | [LangChain/LangGraph 1.0 官方公告](https://www.langchain.com/blog/langchain-langgraph-1dot0)（全文抓取） | 【一手】 | durable execution 断点续跑、多天审批/跨会话后台任务 |
| E13 | [OpenAI Agents SDK HITL 文档](https://openai.github.io/openai-agents-python/human_in_the_loop) | 【摘要】 | interruptions + RunState；嵌套中断顶层恢复 |
| E14 | A2A push（[官方规范生态](https://github.com/a2aproject/a2a-js/issues/193) + [社区示例](https://www.reddit.com/r/AI_Agents/comments/1mwhgll/a2a_pushnotifications_example)） | 【转述】 | tasks/pushNotification/set 注册 webhook，推送 statusUpdate/artifactUpdate |
| E15 | [Temporal：LangGraph plugin / durable AI agents](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) | 【摘要】 | signal 等回调、OpenAI Agents SDK / Pydantic AI / Claude Code 集成 |
| E16 | [Diagrid: Checkpoints are not durable execution](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows) | 【摘要】 | 副作用重放问题、幂等兜底 |
| E17 | ChatGPT Tasks / Deep Research 产品形态（[The Verge](https://www.theverge.com/2025/1/14)、[Zapier](https://zapier.com) 等） | 【转述】 | 后台跑完推通知、结果进对话 |
| E18 | LangGraph/deepagents interrupt 已知坑（issues #2929 / #6663、双执行、静默重放） | 【转述】 | 挂起恢复的工程红线清单 |

（E7 的五篇原始链接为搜索聚合跳转链，未逐篇核读，结论按转述级对待；写规范前应点开原文复核。）

## 4. 证据与复核记录

- 【一手】E1：MCP Tasks 扩展官方 overview 全文抓取成功（WebFetch 直达）。
- 【摘要】E2/E3/E5/E8/E10：仅搜索结果摘要，未读原文；引用只取摘要中明确陈述的结论。
- 【转述】E4（官方文档要点 + 社区 bug 报告交叉）、E6（官方指南标题级结论）、E7（数据点来自转述，标注出处文章名）、E9（官方讨论 + 仓库 issue 交叉）。
- 【未找到】Azure LRO / Google Operation 未单独检索，按通用工程常识引用（两者为十年级成熟模式，风险低）。

第四轮（2026-11-01，回调与挂起专题）：

- 【一手】E11（gh api 拉 deepagents README）、E12（LangGraph 1.0 官方博客全文抓取）；Claude Code 后台任务"完成时唤醒 agent"以官方文档 + 实测行为佐证。
- 【摘要】E13 / E15 / E16：仅搜索摘要（E13 为官方文档标题级要点，建议后续补读原文核 RunState API 细节）。
- 【转述】E14 / E17 / E18：社区示例、产品报道、issue 记录交叉。
- 复核建议：A2A push 的 webhook 鉴权细节（JWTS）本轮未核实，接入前抓 spec 原文。

## 6. 源码级复核（第五轮，2026-11-01）

> 应"非源码结论需升级"的纪律要求，对本轮三个关键断言对码核验。基线：`deepagents@9e7d62ff`（2026-09-11，复用已有克隆）、`langgraph@e539ac12`（2026-09-09，复用已有克隆）、`modelcontextprotocol/python-sdk@d7845c07`（2026-10-27，本轮经镜像新克隆，remote 已改回官方）。证据等级升至【核心】（核心代码实现）/【核心-文档】（源码内 docstring）。

### 6.1 deepagents 挂起链路——四级链路全部对码坐实【核心】

1. `deepagents/graph.py`：`create_deep_agent(..., interrupt_on={tool_name: bool | InterruptOnConfig})`，子代理可继承或覆写；`_fs_interrupt.py` 把文件系统权限规则自动翻译成 `interrupt_on` 条目（`exact`（read_file/write_file/edit_file 按路径精确）vs `bulk`（ls/glob/grep 按子树相交，pathless grep 无条件触发）两类 `when` 谓词）。
2. `langchain_v1 .../agents/middleware/human_in_the_loop.py`：`HumanInTheLoopMiddleware.after_model` 中 `decisions = interrupt(hitl_request)["decisions"]`（**第 458 行**）——挂起点；决策语义**四态**（非三态）：`approve`（原样执行）/ `edit`（人改 tool 名与参数后执行）/ `reject`（返回 error ToolMessage，**内建文案 "Do not retry this tool call unless the user explicitly requests it"**——"错误文案教模型"原则被官方写死在中间件里）/ `respond`（人代替工具回答，工具不执行、答复注入为 ToolMessage）。
3. `langgraph .../types.py:851` `interrupt()` → `:967 raise GraphInterrupt`；`pregel/_loop.py` 处理 INTERRUPT/RESUME 控制信号，replay 时丢弃缓存 RESUME。

### 6.2 恢复语义的关键工程细节——双执行坑的根因在官方语义里【核心-文档】

`langgraph/types.py` 的 `interrupt()` docstring 白纸黑字：

- **"The graph resumes from the start of the node, re-executing all logic"**——恢复时节点从头重跑，`interrupt()` 之前的节点内代码**会再次执行**；
- 多个 `interrupt` 按**节点内出现顺序**匹配 resume 值（resume 值表按 task 作用域，不跨任务共享）；
- "you must enable a checkpointer"——无 checkpointer 该特性直接不可用。

纪律推导：`interrupt()` 之前的节点内副作用必须幂等或为零（把"提交任务"放 interrupt 之前意味着恢复时可能重复提交——**这就是社区双执行 bug 的机制根源**；官方推荐把可重复计算放 interrupt 后或用幂等键兜底）。

### 6.3 MCP Python SDK 对 Tasks 的支持现状——解掉前轮悬念，并修正 §1.3 叙述【核心】

- **类型层已有**：`mcp_types/_types.py` 含 `Task`/`CreateTaskResult`/`GetTaskRequest`（`tasks/get`）/`CancelTaskRequest`（`tasks/cancel`）/`TaskStatusNotificationParams`（`notifications/tasks/status`），全部标注 "(2025-11-25 only)"。
- **Tasks 曾进入核心协议**：`_v2025_11_25/` 版本化模块由 `schema/2025-11-25.json` 生成，含 `capabilities.tasks` 能力协商与 elicitation/sampling 的 task 支持——即 2025-11-25 wire 版本把 Tasks 作为核心能力；ext-tasks 仓库（2026-07-28 系）则是把它以扩展机制重述。
- **两条线形状不一致**（修正性发现）：SDK 类型为嵌套（`CreateTaskResult.task: Task`）+ 通知方法 `notifications/tasks/status`；ext-tasks schema 为扁平合并 + `resultType:"task"` 判别 + 通知方法 `notifications/tasks`。**接入前必须锁定目标 wire 版本并对形状，不能混引两代文档。**
- **框架层已有、高层封装没有**：SEP-2133 扩展框架落地——`MCPServer(extensions=[...])`（`mcpserver/server.py:172`），扩展可贡献 tools/resources/新请求方法（`MethodBinding` 文档示例即 `tasks/get`）/`tools/call` 拦截器；内置的第一个扩展是 Skills（`mcp/shared/skills.py`）。**没有现成的 Tasks 服务端扩展实现**，走扩展路线需自写 `Extension` 子类。FastMCP 表面未确认暴露 `extensions` 参数（仅 MCPServer 组合层确认）。
- HEAD 本身（d7845c07，2026-10-27）就是"Carry `capabilities.extensions` on legacy `initialize` handshakes"——扩展协商刚补齐到 legacy 握手，生态处于"机制就绪、各自补实现"阶段。

### 6.4 复核对本报告的修正与强化

- §1.3 现状提醒段已重写（双规范线 + 形状不一致）。
- §1.8 的"已知坑"升级：双执行从【转述】issue 记录升级为【核心-文档】官方语义（节点重放），纪律更明确。
- §1.8 决策语义细化：HITL 实为四态（多一个 `respond`），reject 文案内建防重试指令——与 report.md P7"错误即提示词"互为印证（官方中间件同款做法）。
- 上轮示例代码中"interrupt 前 submit"的写法**需修正**：按 6.2 语义，submit 应放在 resume 之后或带幂等键，否则恢复重放会重复提交。
- 复核建议：写团队规范前优先补读 E1（已可全文复核）、E3、E6 原文；E2 建议抓 spec 原文核 8 态清单。

## 5. 附录：Tasks 扩展报文速查（一手：`gh api` 实拉 ext-tasks 官方 schema）

来源：`modelcontextprotocol/ext-tasks` 仓库 `schema/2026-07-28/schema.ts`（TypeScript 类型为规范的 source of truth）。E1 的证据等级由"官方 overview 全文"升级为"overview + schema 双一手"。

- 扩展标识：`io.modelcontextprotocol/tasks`（客户端在每个请求 `_meta` 的 `io.modelcontextprotocol/clientCapabilities.extensions` 里声明，空对象即支持）。
- `Task` 对象：`taskId` / `status` / `statusMessage?`（进度、阻塞原因、失败诊断、完成摘要都走这个字段）/ `createdAt` / `lastUpdatedAt` / `ttlMs`（可空=永久；服务端可中途变更）/ `pollIntervalMs?`（客户端 SHOULD 遵守）。
- 状态机：`working` / `input_required` / `completed` / `failed` / `cancelled`；后三者为终态不可逆。
- DetailedTask 变体：`InputRequiredTask` 多 `inputRequests`（键值对，匹配 `tasks/update` 的 `inputResponses`）；`CompletedTask.result` 的结构**等于原请求本该同步返回的结果形状**（如 `tools/call` 任务的 result 就是 `CallToolResult`）；`FailedTask.error` 为 JSON-RPC 错误对象。
- 三个方法：`tasks/get`（响应 `resultType:"complete"` + DetailedTask）、`tasks/update`（空 ack）、`tasks/cancel`（空 ack，cooperative、最终一致）。
- 任务创建：服务端在标准请求（如 `tools/call`）的位置直接返回 `CreateTaskResult` = `Result & Task` 扁平合并 + 判别字段 `resultType:"task"`；任务必须在响应发出前持久化创建。
- 推送（可选）：`notifications/tasks` 携带全量 DetailedTask；客户端经 `subscriptions/listen` 指定 `taskIds` 订阅；轮询仍是默认。
- SDK 现状注意：Tasks 是扩展而非核心规范，各语言 SDK/客户端支持不齐（官方维护 client matrix），工程上先用普通工具自实现等价语义（submit/get_status/cancel + 轮询纪律写进 description），语义与协议一一对应，网关将来支持时平滑迁移。
