# L3.6 adk-python：全家桶——连调试器与评估都配好的框架

> 昨晚 deepagents 交卷：一行 `create_deep_agent` 发来整个工作环境——审查底稿落进
> 虚拟文件系统、发票复核转交子代理、MemoryMiddleware 把「金额一律整数分」的审查
> 记忆注进 system 消息。今晚光谱压轴**全家桶**：原语层（L3.1）→ 图引擎（L3.2–L3.4）
> → harness（L3.5）→ adk（本课），前六课的每一样它都有。还多出三样别人没有的——
> 会话存储、Web 调试器、评估工具链；代价是每一层都长在它的约定上。

## 1. 本课目标

把同一道报销单审查题交给 google-adk（Python 版）重做一遍。完成后你能：

- 用 `LlmAgent + FunctionTool + LiteLlm + Runner` 装配出四课同题的审查 agent，
  统一出口 `run_review(claim_id) -> Advice` 照常离线全绿（`uv run pytest` 零 key）；
- 说清 FunctionTool 的 declaration **从签名 + docstring 自动生成**的机制——
  并能反着手写一个「会长出好 schema」的工具函数（ex1）；
- 用 `session.state` 实现「同一个 agent，不同会话不同策略」（ex2），
  用 `before_model_callback` 实现「模型零请求」的 guardrail 短路（ex3）；
- 对全家桶形态给出自己的判断：它替你付掉哪些代码（甜），你被绑进哪些约定（重）——
  这是 L3.8 决策表的最后一列数据。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 adk 物 | 一句话差异 |
|---|---|---|
| Spring Boot 全家桶 vs 裸 Servlet | adk 全家桶 vs openai-agents 库 | 库给你零件，全家桶连调试器、评估、会话存储、部署 CLI 都配好——代价是每层都长在它的约定上 |
| `HttpSession`（有状态会话） | `Session` + `session.state` | Java 的 session 在容器里、随请求走；adk 的会话是框架的一等实体，由 SessionService 持久化，state 还带 `app:` / `user:` 作用域前缀 |
| Spring 的 `${placeholder}` 配置注入 | instruction 里的 `{var}` 占位符 | 占位符在**每次模型请求前**从 session.state 填充——提示词是模板，会话状态是变量 |
| Servlet Filter / Interceptor 的 preHandle | `before_model_callback` | 返回 truthy 即短路（模型请求都不发）；Java 对照返回 false 不走后续链——同一件事的两种拼写 |
| SLF4J 门面 + 各日志实现 | LiteLlm + litellm 多供应商层 | adk 不直连任何厂商，模型字符串 `openai/gpt-4o` 前缀是 litellm 的路由记号，由 litellm 翻译到各端点 |
| JUnit + 测试夹具自己搭 | `AgentEvaluator` + eval set + 指标 | 评估是框架的一层：actual/expected Invocation 对 + 确定性指标（轨迹比对）+ LLM-as-judge 指标 |

### 2.1 全家桶 vs 库：形态差到底差在哪

L3.1 的 openai-agents 是**库**：`Runner.run(agent, input)` 一行入口，循环、会话、
评估都不管——零件拿来自己装。adk 是**全家桶**：

- **运行时**：`LlmAgent`（循环）+ `Runner`（驱动）+ `SessionService`（会话存储）+
  `ArtifactService`（文件存储）+ `MemoryService`（长期记忆）——五个可插拔服务；
- **工具带**：FunctionTool 之外还有 MCP、OpenAPI、BigQuery、代码执行器……开箱即用；
- **调试器**：`adk web` 起本地服务 + 浏览器界面，事件流、会话、state 可视化（§3 Step 5）；
- **评估**：`adk eval` + eval set + 预置指标族（eval/ 目录五十来个文件，是本教程
  见过的第一个把「评估」当框架层的框架）；
- **部署**：`adk create / deploy` 直接生成 Cloud Run 等部署形态。

Java 对照：裸 Servlet vs Spring Boot 全家桶。甜是一样的甜（约定优于配置、生态件即插即用），
重也是一样的重（你的代码必须长在它的目录约定、服务抽象和生命周期里）。

### 2.2 session 与 state：框架管理的会话存储

mini-agent 与 L3.1–L3.4 的「对话状态」都是 messages 列表，跑完即丢；adk 把它升级成
持久实体：

- `Session` 挂着**事件流**（全部对话与工具调用历史）与 **state**（键值状态）；
- state 在 `create_session(state=...)` 时注入初始值，工具里经 `tool_context.state` 读写，
  instruction 里的 `{var}` 占位符每次请求前填充——三条注入路径同一份状态；
- 生产换存储实现即可（`DatabaseSessionService` / `VertexAiSessionService`），
  代码不动——这就是 Step 3「同一个 agent 定义，不同会话不同策略」的全部原理。

Java 对照：像 `HttpSession`，但两点不同——它由框架的会话服务持久化（不在你的 Web 容器），
而且 state 键有作用域前缀（`app:` 跨会话共享、`user:` 跨会话跟人走、无前缀仅本会话）。

### 2.3 callback 链：guardrail 的框架化

L3.1 用 guardrail、L3.2–L3.4 要写进图节点；adk 把「请求链路上的钩子」统一成四类回调：
`before/after_model_callback`（模型前后）、`before/after_tool_callback`（工具前后）。
返回 truthy 即替换/短路后续调用——`before_model_callback` 返回一个 `LlmResponse`，
模型请求根本不发（Step 4 用 `ep.requests == []` 离线实证这一点）。
Java 对照：Servlet Filter / Spring Interceptor 的 preHandle 返回 false；区别是这里的
「后续链」是一次模型调用，短路省下的是真金白银的 token，而不只是响应时间。

### 2.4 LiteLlm 中转层：模型端点中立的另一条路线

本课的模型绑定不走各框架自己的客户端，而是 `LiteLlm(model="openai/mock-model",
api_base=..., api_key=...)`——构造 kwargs 原样转交 litellm 的 `acompletion`，由它路由到
任意 OpenAI 兼容端点（夜校的端点中立纪律因此继续成立）。注意两点源码事实
（google/adk-python@7b246e01#src/google/adk/models/lite_llm.py）：

- `openai/` 前缀是 **litellm 的路由记号，出网前会被剥掉**：传 `openai/mock-model`，
  端点收到的 `model` 恰是 `mock-model`（Step 1 有取证）——如果你的端点要求完整模型名，
  反而不要加前缀；
- base_url 与 key 用的是 **litellm 的参数名** `api_base` / `api_key`（不是 adk 的命名）——
  网上旧教程混用 `base_url`（google-genai 的参数）的写法在这条路径上不生效。

## 3. 动手代码

先 `uv sync`（adk 依赖较重，litellm 链路第一次同步要等一会）。共享题面
（`mock_tools.py` / `review_rules.py` / `mock_endpoint.py` / `advice.py`）六课对版
（L3.1–L3.6 字节相同），`test_contract.py` 五课对版（L3.1/L3.2/L3.4/L3.5/L3.6
字节相同）；本课新增的装配层在 `code/adk_review.py`——对照 L3.1 的同名装配层读，
差异就是框架差异。

### Step 1：库模式离线 demo——事件流与出网取证（20 分钟）

```bash
uv run python code/demo_events.py
```

```text
== adk 库模式离线 demo：审查 CLM-2026-0004 ==
[expense_reviewer] 工具调用 check_budget({'dept': 'DEV'})；工具调用 verify_invoice({'invoice_id': 'INV-2026-0005'})
[expense_reviewer] 工具回喂 check_budget；工具回喂 verify_invoice
[expense_reviewer] 文本 {"claim_id":"CLM-2026-0004","decision":"REJECT","reason":...

== 端点收到的请求（litellm 中转后的真实形态） ==
request[0] model='mock-model' messages=2 tools=['check_budget', 'verify_invoice']
request[1] model='mock-model' messages=5 tools=['check_budget', 'verify_invoice']
```

读点：mini-agent 的「消息轨迹」在 adk 里是 `Runner.run_async` 吐出的 **Event 流**——
工具调用、回喂、最终回答都是事件（`event.is_final_response()` 标记软终止轮）；
`request[0]` 的取证对照 §2.4：model 名剥了前缀、鉴权与路径由 mock 端点把关。
讲义区验收：`uv run pytest code/`（8 个测试，含 test_contract.py 的四单全量契约）。

### Step 2：FunctionTool 的 schema 自动生成（15 分钟）

```bash
uv run python code/demo_schema.py
```

```text
-- check_budget --
description: 查预算余额：返回部门的预算 / 已花 / 剩余，单位都是分。
parameters_json_schema: {"properties": {"dept": {"title": "Dept", "type": "string"}}, "required": ["dept"], "title": "check_budgetParams", "type": "object"}
```

对照 L2.2：同样的 OpenAPI 风格 schema，那时手写 Pydantic 模型、这时从签名 + docstring
长出来（连 `title: check_budgetParams` 都是框架内部 `create_model` 的痕迹）。两个细节：
`ToolContext` 参数被自动剔除（模型永远看不见框架上下文参数）；adk 2.9.0 的
JSON-schema 路径下，**docstring 的 Args 描述不进参数 schema**，信息全在工具
description 里（旧版行为不同——按你装的版本源码为准）。

### Step 3：session.state——同一个 agent，两个会话两套策略（15 分钟）

```bash
uv run python code/demo_state.py
```

```text
-- 注入 item_limit_cents=5000 --
  ① instruction 填充后: 你是报销审查助手。本会话的单笔上限是 5000 分。先调用 limit_report 了解本会话策略，再回答。
  ② 工具回喂(第2轮请求里): {"item_limit_cents": 5000}
工具取证 CALL_LOG: ['limit_report:5000', 'limit_report:3000']
```

agent 与工具的代码一行没换——差异全部来自 `create_session(state=...)`。
两条注入路径（instruction 占位符 / `tool_context.state`）都在取证里。

### Step 4：before_model_callback 当 guardrail（15 分钟）

```bash
uv run python code/demo_callback.py
```

```text
-- 坏单号(格式错): '请审查报销单 CLM-26-2'
   模型请求次数: 0（为 0 即拦截发生在网络调用之前）
   工具执行: <未执行>
   回答: REJECT:CLAIM_ID_INVALID（单号不合规：必须是 CLM-YYYY-NNNN 格式）
```

L3.1 guardrail 的 adk 拼写。验收断言不是「回答像被拦了」，而是 `ep.requests == []`——
拦截发生在网络调用之前，这是离线可证的。

### Step 5：eval 工具链与 `adk web`（导读 + 加餐，30 分钟）

```bash
uv run python code/demo_eval.py
```

```text
== 与剧本期望比对: score=1.0 status=EvalStatus.PASSED
== 标错部门参数的期望: score=0.0 status=EvalStatus.FAILED
```

这是 eval 体系的最小离线切片：真实跑一遍 agent，把事件流折叠成 actual `Invocation`，
与标注的 expected 用**确定性指标** `TrajectoryEvaluator`（ANY_ORDER 比对工具轨迹）打分——
零 key、零裁判模型。完整工具链是 `AgentEvaluator.evaluate(agent_module, eval_set)` +
`.test.json` eval set + 指标族（final_response_match 确定性；轨迹质量 / 幻觉 / rubric
要 LLM-as-judge 裁判模型）——诚实边界：裁判类指标需要真实端点，本课离线不跑。

`adk web`（加餐，需真实端点；本课离线未实测起过它——目录约定以 cli 源码为证）：
`adk web <agents 目录>` 起本地 API 服务 + 浏览器调试器，可以看事件流、翻会话、
改 state 再重放——全家桶里「调试器」那一格。动手姿势：**每个 agent 一个子目录**，
本课 agent 放成 `google_adk/agents/expense_reviewer/agent.py`（模块级 `root_agent`
——`adk create` 生成的就是这个形态），命令指向 agents 父目录：
`uv run adk web google_adk/agents`。发现逻辑在 `cli/utils/agent_loader.py` 的
`AgentLoader`：只把该目录下的子目录当 agent 认（子目录里要有 `agent.py` /
`__init__.py` / `root_agent.yaml` 之一，`agent.py` 里定义模块级 `root_agent`）。
`.env` 配好三变量；默认它用 Gemini 系模型——加 `LiteLlm` 前缀（§2.4）即可指到
你的 OpenAI 兼容端点。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区（与所需的顶部 import）；卡住先想 5 分钟，
再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_tool.py` | 工具注册改造：新写 lookup_policy，让 declaration 从你的 docstring + 签名长出来（meta 验证 schema 三信息源） |
| ex2 | `exercises/ex2_state.py` | 状态改造：单笔上限从硬编码改为 create_session 注入，同一单注入 3000/5000 断言不同 decision |
| ex3 | `exercises/ex3_guardrail.py` | guardrail 改造：before_model_callback 拦不合规单号，断言模型零请求（ep.requests 空） |

形态标注（诚实起见）：ex1 是**新写型填空骨架**——docstring 与函数体都是 TODO，填空前
不可跑（非「改造前可跑」型），可跑参照见讲义 Step 2 与 `code/mock_tools.py` 的既有
工具；ex2/ex3 的给定件（装配、剧本、预期生成器）已完整，TODO 是待补的行为/装配函数。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：全家桶默认件（内存会话上了生产）

- **现象**：demo 跑得很好，部署后「用户上一句还在，服务一重启全忘了」；或者更隐蔽——
  起两个副本做负载均衡，同一个用户的会话在 A 副本建、请求轮到 B 副本就 404。
- **最小复现**：本课的 `build_runner`（`code/adk_review.py`）用的是
  `InMemorySessionService`——把 demo_state.py 跑两遍（两个进程），第二个进程里
  第一个进程注入的 `item_limit_cents` 根本不存在：会话与 state 都活在进程内存里，
  进程即生命周期。
- **Java 直觉为何失效**：Spring Boot 老兵看见 starter 默认件（H2、内存 session）会条件反射地
  问「生产换什么实现」；但 adk 把这件事藏得太顺滑——`InMemoryRunner(agent)` 一行就跑通
  全部教程，`session.state` 功能完整、测试全绿，**没有任何报错提醒你这是个默认件**。
  源码自己说得很清楚（google/adk-python@7b246e01#src/google/adk/runners.py 的
  InMemoryRunner docstring）：*"An in-memory Runner **for testing and development**"*——
  但谁会在全绿的时候去读 Runner 的 docstring 呢。
- **修复与纪律**：生产装配显式换服务实现——`Runner(agent=..., session_service=
  DatabaseSessionService(db_url=...))` 或 `SQLiteSessionService`（sessions/ 目录里
  就备着这三个替换件，接口同为 `BaseSessionService`）；部署多副本时先回答两个问题：
  会话粘不粘（同一用户固定路由到同一副本）、不粘的话存储共享了没有。Java 迁移直觉：
  这是 Spring Session 把 HttpSession 外置到 Redis 的同一道题，adk 把答案也做成了
  可插拔件——你只需要在「全绿」的时候记得问那一句。

## 6. 延伸

- google/adk-python@7b246e01#src/google/adk/agents/llm_agent.py —— LlmAgent 本体：
  `model / instruction / tools / output_schema / 四类 callback` 全在一处声明，
  读它的字段 docstring 比读教程更快（本课依赖钉 2.9.0，字段以这份源码为准）。
- google/adk-python@7b246e01#src/google/adk/tools/function_tool.py —— FunctionTool：
  declaration 如何由 docstring + 签名生成（`_get_declaration`）、ToolContext 参数
  如何被注入与剔除（`_ignore_params`）——Step 2 与 ex1 的全部机制。
- google/adk-python@7b246e01#src/google/adk/runners.py —— Runner 与 InMemoryRunner：
  `run_async` 的事件驱动循环、会话的取用与创建（§5 陷阱的现场）。
- google/adk-python@7b246e01#src/google/adk/models/lite_llm.py —— LiteLlm：
  构造 kwargs 如何转交 litellm 的 acompletion、`openai/` 前缀的路由语义
  （§2.4 的两条源码事实都在这里核验）。
- google/adk-python@7b246e01#src/google/adk/sessions/state.py —— State 的
  `app:` / `user:` / `temp:` 作用域前缀；同目录 in_memory / sqlite / database /
  vertex_ai 四个 SessionService 实现是 §5 的替换件清单。
- google/adk-python@7b246e01#src/google/adk/evaluation/agent_evaluator.py 与
  google/adk-python@7b246e01#src/google/adk/evaluation/trajectory_evaluator.py —— eval 工具链的库入口与
  确定性轨迹比对（Step 5 用的就是后者的 ANY_ORDER 语义）。
- google/adk-python@7b246e01#src/google/adk/cli/cli_tools_click.py —— `adk web`
  命令的真实形态（挂 get_fast_api_app + 浏览器调试器），同文件还有 `adk eval`。
- google/adk-python@7b246e01#src/google/adk/cli/utils/agent_loader.py ——
  AgentLoader：`adk web` 的 agent 发现逻辑（每个 agent 一个子目录、`agent.py` 里
  模块级 `root_agent`——Step 5 目录约定的源码出处；`cli_create.py` 的 `adk create`
  生成的也是同一形态）。
- 官方文档（版本对齐 2.x）：https://google.github.io/adk-docs/ —— 快速开始的
  目录约定（agents 目录 + 每 agent 一个子目录）与 `adk web` 截图。

### 与 mini-agent 对照

抽象光谱走完，把 adk 放回对照组——它 ≈ 把 mini-agent 的整个 `agent.py` 框架化，
但多出 mini-agent 完全没有的整层（会话存储、调试器、评估）：

| 能力 | mini-agent（Unit 2） | adk 给了什么 | 锁定代价 |
|---|---|---|---|
| agent 循环 | 有，81 行亲手写 | `LlmAgent` + flows 全内建 | 循环语义黑盒化：预算、终止、消息装配都在框架深处 |
| 工具注册表 | 有，L2.2 手写 schema | FunctionTool 从签名+docstring 自动生成 | docstring 成为 API 的一部分，改一个字模型行为就变 |
| 结构化输出 | 有，L2.4 校验回喂重试 | output_schema / set_model_response 工具路线 | 走框架的 schema 管道，出问题时得读 _output_schema_processor |
| guardrail | 写在循环体最前面 | 四类 callback 挂点 | 回调执行顺序与短路语义绑定框架版本 |
| 会话与状态 | 无（messages 列表，跑完即丢） | Session + state + 可插拔 SessionService | 换存储学它的服务抽象；state 前缀作用域是 adk 私有词汇 |
| 调试器 | 无（print 大法） | `adk web` 事件流可视化 | 代码必须长在 adk 的目录约定上才被调试器认 |
| 评估 | 无（pytest 手搓契约） | AgentEvaluator + eval set + 指标族 | eval set 格式与指标绑定框架；judge 指标绑端点 |
| 部署 | 无 | `adk create / deploy` | 平台形态偏向 GCP（Cloud Run 一等公民） |

一句话：**mini-agent 是你拥有的地基，adk 是精装修的整栋楼**——住进去快，
但图纸（四类回调、五种服务、目录约定）只有它家有。L3.8 会把这一列填进决策表。

## 离毕业又近的一块

毕业设计的四块拼图今晚集齐最后一块：L5.2 审批外化的「暂停→恢复」需要会话状态跨请求
存活——今晚的 SessionService 就是它的存储层选型候选（对照 langgraph 的 checkpoint，
L3.3 已预习）；L5.4 fail-closed 检查链的「零请求短路」验收手法（ep.requests 为空）
今晚在 ex3 练过；毕设的回归测试可以直接借 Step 5 的 actual/expected Invocation 思路。
Unit 3 四框架全部跑完——下一课 L3.8 把它们放进同一张决策表，你的选型不再靠听说。
