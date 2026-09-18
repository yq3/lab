# L3.1 openai-agents：极简原语层

> 上一学段在里程碑收官：mini-agent 五块肌肉集齐，client / tools / agent / structured /
> mcp_bridge 五模块 249 行裸逻辑三条命令全绿——手写版从此成为 Unit 3 的全程对照组。
> Unit 3 今晚开张：同一道报销单审查题交给五个框架重做，按抽象光谱从最薄的一层起步——
> openai-agents 是原语层，mini-agent 里你亲手写的每一行它几乎都替你付掉。付掉不等于
> 消失：今晚逐笔对账，框架替你付的每一样，都要能指回 mini-agent 里的那几行。

## 1. 本课目标

把同一道报销单审查题（四框架同题 demo）交给 openai-agents-python 重做。完成后你能：

- 用 `Agent` + `Runner.run` 跑通「工具调用 → 回喂 → 结构化输出」全链路，并说清
  **它的循环对应 mini-agent 的哪十行**（§6 对照表）；
- 用 `function_tool` 直包普通函数（签名 + docstring 自动生成工具 schema），对照
  L2.2 手写注册表的每一条纪律；
- 装配 handoff-as-tool 双 agent 与 InputGuardrail 输入护栏，并用 wire 取证解释
  「转交」与「绊线」在协议层到底是什么；
- **第一件事形成肌肉记忆：`set_tracing_disabled(True)`**——这门框架默认把会话
  trace 外发到 api.openai.com，端点中立的工程纪律要求先关（§2.7 有源码证据）；
- （进阶）用 RunState 走一遍 HITL：工具审批「暂停 → 序列化 → 批准 → 恢复」——
  L3.3 langgraph interrupt 的预告片。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。

## 2. 概念讲解

先给全课对照表（Java 同学先看这张再往下读）：

| 你熟悉的 Java 物 | 今天的 openai-agents 物 | 一句话差异 |
|---|---|---|
| Spring 的 `@Service` + 注解装配 | `Agent(...)` dataclass 实例 | 没有容器、没有注解处理器——全是运行时普通值（§5 坑位） |
| 手写 `while` 循环（L2.3 的 run） | `Runner.run(agent, input)` | 循环进了框架：软终止（模型收敛）+ `max_turns` 硬预算 |
| 手写工具注册表（L2.2 的 `@tool`） | `@function_tool` 装饰器 | schema 从签名 + docstring **装饰时**生成，不用手写 JSON |
| Jackson `ObjectMapper` + DTO | `output_type=Advice`（Pydantic） | 请求侧 response_format 约束 + 响应侧 Pydantic 校验 |
| Servlet Filter / Spring Interceptor | `InputGuardrail` / `OutputGuardrail` | 默认与 agent **并行赛跑**而非请求级前置，本身也可以是模型调用（§2.6） |
| 线程池拒绝策略 / 熔断 | `max_turns` → `MaxTurnsExceeded` | 确定性硬终止对冲概率性软终止（L2.3 纪律的框架化） |
| Micrometer / Actuator 上报 | tracing（span 树） | 默认外发 OpenAI 服务器——本课第一件事就是关掉 |
| 工作流引擎的挂起/恢复（如 Flowable） | `RunState`（可序列化快照） | 没有引擎、没有数据库表——快照就是一个 JSON 字符串 |

### 2.1 Agent：一个 dataclass，不是一种「注解」

openai-agents 的世界观只有四个原语：`Agent`（配置）、`handoff`（转交）、
`guardrail`（护栏）、`Runner`（循环）。看 `Agent` 的定义——它就是一个
`@dataclass`（openai/openai-agents-python@fbd2dbca#src/agents/agent.py）：

```python
@dataclass
class Agent(AgentBase, Generic[TContext]):
    name: str
    instructions: str | Callable[..., str] | None = None   # system 提示，可以是函数
    handoffs: list[Agent | Handoff] = field(default_factory=list)
    model: str | Model | None = None                        # 模型名或 Model 实例
    tools: list[Tool] = field(default_factory=list)
    output_type: type | AgentOutputSchemaBase | None = None
    input_guardrails: list[InputGuardrail] = ...
```

对照 Java：Spring 里你写 `@Service`，容器负责实例化与注入；这里没有容器，
`Agent(name=..., tools=[...])` 就是 new 一个普通对象，字段全是运行时值——
`instructions` 甚至可以是函数（每次 run 动态生成 system 提示）。**没有魔法可依赖，
也没有魔法会背着你做事**——这是极简原语层的设计哲学（官方 README 的原话是
"no new abstractions, just plain objects"），也是 §5 坑位的根源。

`model` 字段是本课的关键注入点。OpenAI 官方端点有两套协议：老牌 **Chat Completions**
（我们 L2.1 手撕的那套）与新推的 **Responses API**（有状态、内置工具）——传字符串会
走框架默认的 Responses API；要让
Agent 走我们 mock 端点说的 chat-completions 协议，得传一个
`OpenAIChatCompletionsModel(model=..., openai_client=AsyncOpenAI(base_url=...))`
实例（openai/openai-agents-python@fbd2dbca#src/agents/models/openai_chatcompletions.py）——
模型客户端是**注入**的，端点中立因此成立（GLM/DeepSeek/本地 vLLM/mock 端点都一样）。

### 2.2 Runner.run：循环被付掉了，但还在

`Runner.run(agent, input, max_turns=...)` 的 docstring 就是循环的地图
（openai/openai-agents-python@fbd2dbca#src/agents/run.py）：调 agent → 有最终
输出就停 → 有 handoff 就换 agent 重来 → 有工具调用就执行回喂再来。一个
**turn = 一次模型调用**（含它点名的工具执行），默认预算
`DEFAULT_MAX_TURNS = 10`（src/agents/run_config.py），预算耗尽抛
`MaxTurnsExceeded`。你会认出这就是 L2.3 的十行循环 + 双终止，一行没多。

### 2.3 function_tool：docstring 就是 schema

L2.2 我们手写「Pydantic 模型 → JSON Schema → 注册表」；`@function_tool` 把这三步
压成一个装饰器（openai/openai-agents-python@fbd2dbca#src/agents/tool.py）：

```python
@function_tool
def check_budget(dept: str) -> dict:
    """查预算余额：返回部门的预算 / 已花 / 剩余，单位都是分。"""
```

装饰那一刻，框架读函数签名生成参数 JSON Schema、读 docstring 当工具描述——
**你的 docstring 就是模型看到的 API 文档**（这就是「docstring-as-schema」）。
本课 demo 直包了 `mock_tools.check_budget / verify_invoice`，零适配代码。

一个实测发现的边界：工具返回 dict 时，SDK 对非字符串返回值只做 `str()`
（src/agents/items.py 的 `_convert_tool_output`）——wire 上是 Python repr
（单引号、`True`），不是 JSON。mock 模型不在乎（台词是预生成的），真实模型
多半读得懂，但「工具边界输出 canonical JSON」的 L2.2 纪律仍然值得守：
要 JSON 就包一层 `return json.dumps(mock_tools.check_budget(dept))`（三行薄适配）。

### 2.4 output_type：结构化输出的框架化（且不多花一轮）

给 Agent 传 `output_type=Advice` 后，chat-completions 路径的行为（实测）：
**每个请求**都带 `response_format: {"type": "json_schema", ...}`（含调工具的那轮），
最终文本回来时在客户端过 Pydantic 校验（`AgentOutputSchema.validate_json`），
所以 `result.final_output` 直接就是 `Advice` 实例——不是字符串、不用自己解析。
这是 L2.4「schema 约束 + 解析校验」的框架化。注意：**当前版本不会因为结构化输出
多调一轮模型**（旧版教程常这么说）——轮数以 ep.requests 实测为准，Step 1 会贴证据。

### 2.5 handoff：转交在 wire 上就是一个工具调用

`handoffs=[handoff(specialist)]` 会把复核专员包装成一个名为
`transfer_to_<agent.name>`（全小写，驼峰压平、不拆词）的 function tool 混进工具表。
模型「调用」它之后：下一轮请求换 system（新 agent 的人设）、换工具表，**消息历史
原样保留**——「换 agent 不换对话」。对 Java 同学：这不像 Spring 的 Bean 组合，
更像把「下一步路由到谁」外包给了模型的工具选择（也把打错工具名的风险一起外包了：
拼错名字 → `ModelBehaviorError: Tool ... not found`）。源码：
openai/openai-agents-python@fbd2dbca#src/agents/handoffs/__init__.py。

### 2.6 guardrail：绊线不是 Filter

`InputGuardrail` 是挂在第一个 agent 上的输入检查（openai/openai-agents-python@
fbd2dbca#src/agents/guardrail.py）：护栏函数返回 `GuardrailFunctionOutput`，
`tripwire_triggered=True` 就抛 `InputGuardrailTripwireTriggered`。两个和 Servlet
Filter 完全不同的语义要刻进脑子：

1. **默认并行赛跑**（`run_in_parallel=True`）：护栏与第一轮模型调用同时起跑，
   护栏赢了就取消模型任务（run.py 里是 `asyncio.gather(guardrail_task, model_task)`）。
   要「绝不发出模型调用」的硬保证，构造时传 `run_in_parallel=False`；
2. **护栏本身可能就是一次模型调用**（官方 guardrail agent 模式：用一个分类小模型
   当护栏）——成本与副作用按模型调用计，不是 Filter 那样的纳秒级链路节点。

### 2.7 tracing：默认外发，先关再说

每次 `Runner.run` 都会产一整棵 span 树（agent/turn/generation/function），
默认交给 `BatchTraceProcessor → BackendSpanExporter`，其端点**硬编码**
`https://api.openai.com/v1/traces/ingest`（openai/openai-agents-python@fbd2dbca#src/agents/tracing/processors.py）。
只要环境里有 `OPENAI_API_KEY`——配过 .env 的同学都有——即使你的模型端点是
GLM/DeepSeek/本地 vLLM，会话内容也会发往 OpenAI。没配 key 时不发只告警，
所以离线验收「看起来没事」，生产却会静默外发。两个开关（Step 2 实验）：
`set_tracing_disabled(True)` 全关；`set_trace_processors([自己的处理器])` 换目的地。

### 2.8 RunState：HITL 的可序列化快照（进阶，一瞥）

工具标 `needs_approval=True` 后，模型点到它时 run **不抛异常、正常返回**——
`result.interruptions` 里是待审批项；`result.to_state()` 把整个运行拍成快照
（`to_string()` 是 JSON，实测约 18KB），批准/拒绝后 `Runner.run(agent, state)`
从断点恢复。没有引擎、没有数据库——毕业设计「审批暂停→恢复」的最小形态（Step 5）。
源码：openai/openai-agents-python@fbd2dbca#src/agents/run_state.py（5271 行，
wc -l 口径；实现远比概念厚：会话对账、schema 版本、并发恢复守卫——导读见 §6）。

## 3. 动手代码

先 `uv sync`。共享素材与共用验收：`code/mock_tools.py`（两个 mock 工具）、
`code/review_rules.py`（规则表 + 离线剧本生成器）、`code/advice.py`（统一出口）、
`code/mock_endpoint.py`（L2.3 服役的协议级替身端点）、`code/test_contract.py`
（契约五课对版的共用验收——L3.1/L3.2/L3.4/L3.5/L3.6）。被测对象是**框架的管道**，不是模型的质量（离线台词由
review_rules 预生成，与真实模式下 system 提示里的规则同源）。

### Step 1：离线跑同题 demo（20 分钟）

```bash
uv run python code/demo.py
```

```text
== L3.1 openai-agents 同题 demo：四张单各跑一遍（离线，零 key） ==
CLM-2026-0001  requests=2  tools=['check_budget', 'verify_invoice']  -> APPROVE / PASS（剩余预算 10000 分）
CLM-2026-0002  requests=2  tools=['verify_invoice', 'check_budget']  -> REJECT / REJECT:ITEM_OVER_LIMIT（剩余预算 10000 分）
CLM-2026-0003  requests=2  tools=['check_budget', 'verify_invoice']  -> ESCALATE / REJECT:INVALID_AMOUNT（剩余预算 40000 分）
CLM-2026-0004  requests=2  tools=['check_budget', 'verify_invoice']  -> REJECT / REJECT:INVOICE_INVALID（剩余预算 40000 分）

== 第 1 单的 wire 细节（CLM-2026-0001）==
request 1: roles=['system', 'user']  tools=['check_budget', 'verify_invoice']  response_format=json_schema=True
request 2: roles=['system', 'user', 'assistant', 'tool', 'tool']  tools=['check_budget', 'verify_invoice']  response_format=json_schema=True
tool 回喂原文（注意：dict 返回值被 str()，单引号 repr 而非 JSON）：
    {'dept': 'SALES', 'budget_cents': 200000, 'spent_cents': 190000, 'remaining_cents': 10000}
    {'id': 'INV-2026-0001', 'valid': True, 'reason': '抬头、税号与报销人一致'}
final_output: Advice(claim_id='CLM-2026-0001', decision='APPROVE', reason='PASS', remaining_cents=10000)
final_output 类型: advice.Advice
```

对着输出核对三件事：① `requests=2`——工具轮 + 结论轮，`output_type` 没有多花一轮
（§2.4 的实测证据）；② tool 回喂是 Python repr（§2.3 的边界发现）；③ 工具顺序
两次运行可能不同——两个工具是**并行执行**的（同步函数被丢进 `asyncio.to_thread`），
CALL_LOG 的顺序不作承诺。然后逐行读 `code/demo.py`（191 行，含文档注释）：模块级的
`set_tracing_disabled(True)`、`_build_tools` 的原生直包、`_build_model` 的端点注入、
`run_review` 的契约入口。讲义区验收：

```bash
uv run pytest code/
```

七个测试：共用契约 2 个（四张单 × expect_* 字段 + CALL_LOG 取证 + 覆盖型 meta
检查）+ `code/test_demo.py` 5 个（docstring-as-schema、逐字段等于剧本预期、
handoff/guardrail/HITL 机制确定性）。

### Step 2：trace 默认外发的证据（10 分钟）

```bash
uv run python code/demo_trace.py
```

```text
== 实验 1：tracing 打开 + 自定义 processor，跑一次 run ==
processor 收到的事件（10 条）:
    span:generation ×2
    span:function ×2
    span:turn ×2
    span:agent ×1
    span:task ×1
结论：一次 run 产了一整棵 span 树（agent/turn/generation/function...）——
      这些数据默认交给 BatchTraceProcessor → BackendSpanExporter。

== 实验 2：默认 exporter 发去哪（源码证据，不发真请求） ==
端点常量: https://api.openai.com/v1/traces/ingest
含义：只要 OPENAI_API_KEY 在环境里（配过 .env 的同学都有），
      即使你的模型端点是 GLM/DeepSeek/本地 vLLM，会话 trace 仍会发往 OpenAI。
      没配 key 时不发送、只打 warning——离线验收因此不被它打扰，但生产会意外外发。

== 实验 3：set_tracing_disabled(True) 后再跑一次 ==
processor 新收到事件: 0 条
结论：全局开关连自定义 processor 一起静默——想留本地链路追踪就别关，
      只想把默认外发换成自己的后端时，用 set_trace_processors 替换而不是关。
```

实验 1 挂的是自己的 `TracingProcessor`（离线、只计数）——这也是生产里接
自建可观测后端的正规姿势；实验 3 证明全局开关一视同仁。读完源码路标 §2.7
那条再关掉这一页。

### Step 3：handoff-as-tool 双 agent（20 分钟）

```bash
uv run python code/demo_handoff.py
```

```text
== 双 agent（handoff-as-tool）四张单 ==
CLM-2026-0001  requests=2  last_agent=Reviewer        handoff=否  -> APPROVE / PASS
CLM-2026-0002  requests=2  last_agent=Reviewer        handoff=否  -> REJECT / REJECT:ITEM_OVER_LIMIT
CLM-2026-0003  requests=3  last_agent=HumanSpecialist handoff=是  -> ESCALATE / REJECT:INVALID_AMOUNT
CLM-2026-0004  requests=2  last_agent=Reviewer        handoff=否  -> REJECT / REJECT:INVOICE_INVALID

== ESCALATE 单（CLM-2026-0003）逐请求取证 ==
request 1: system=你是报销单审查员。先用 ch…  tools=['check_budget', 'verify_invoice', 'transfer_to_humanspecialist']  roles=['system', 'user']
request 2: system=你是报销单审查员。先用 ch…  tools=['check_budget', 'verify_invoice', 'transfer_to_humanspecialist']  roles=['system', 'user', 'assistant', 'tool', 'tool']
request 3: system=你是人工复核专员：对转来的报…  tools=[]  roles=['system', 'user', 'assistant', 'tool', 'tool', 'assistant', 'tool']
看点：第 3 次请求 system 换成复核专员的人设、工具表清空，历史消息原样带上——
      这就是 handoff：换 agent 不换对话。
```

注意工具表里混着 `transfer_to_humanspecialist`——复核专员在 wire 上就是审查员的
第三个工具；`last_agent` 证明谁收的尾。这是练习 ex1 的同构样板。

### Step 4：InputGuardrail 拦幻觉单号（15 分钟）

```bash
uv run python code/demo_guardrail.py
```

```text
== 坏单号 CLM-2026-9999（护栏应拦） ==
InputGuardrailTripwireTriggered: tripwire={'claim_id': 'CLM-2026-9999', 'known': False}
模型请求数: 0（护栏与模型并行赛跑，护栏先到即取消模型任务）

== 好单号 CLM-2026-0001（护栏放行，正常审查） ==
APPROVE / PASS（模型请求 2 次，工具 ['verify_invoice', 'check_budget']）

== 不带单号的消息（护栏同样绊线——宁拒收不猜） ==
InputGuardrailTripwireTriggered: output_info={'claim_id': None, 'known': False}
```

护栏函数在 `code/demo_guardrail.py` 里只有三步：抽单号 → 查 mock 用例表 →
包 `GuardrailFunctionOutput`。异常类型从 `agents.exceptions` 导入——框架异常
也是 API 的一部分（ex2 会再写一遍）。

### Step 5（进阶）：RunState 的 HITL 试跑（20 分钟，可留到 L3.3 前）

```bash
uv run python code/demo_hitl.py
```

```text
== 第 1 段：跑到记台账，run 在审批点暂停 ==
模型请求: 2 次（查询轮 + 记台账轮）
CALL_LOG: ['check_budget', 'verify_invoice']（log_decision 还没执行——等批准）
待审批: tool=log_decision  arguments={"claim_id": "CLM-2026-0002", "decision": "REJECT"}
final_output: None（没有结论——run 没跑完）

== 第 2 段：快照 → 杀进程（字符串进出）→ 批准 → 恢复 ==
RunState 快照: 18039 字符的 JSON（含历史、审批状态、轮数）
模型请求累计: 3 次（+1：恢复后的建议单轮）
CALL_LOG: ['check_budget', 'verify_invoice', 'log_decision']（log_decision 被批准后真实执行了）
final_output: Advice(claim_id='CLM-2026-0002', decision='REJECT', reason='REJECT:ITEM_OVER_LIMIT', remaining_cents=10000)
```

诚实边界：`run_state.py` 是这个 commit 上最重的模块（5271 行，wc -l 口径：
会话对账、schema 版本门禁、并发恢复守卫），本课只消费它的**公共契约**（to_state / approve /
from_string / Runner.run 恢复），不深入实现——L3.3 讲 checkpoint 时会拿它当
「另一个框架的同一件事」对照。

### Step 6（可选）：真实端点

```bash
cp .env.example .env
```

（Windows PowerShell：`copy .env.example .env`；填 `OPENAI_BASE_URL` /
`OPENAI_API_KEY` / `MODEL_NAME` 三变量。）

```bash
uv run python code/demo.py --real
uv run python code/demo.py --real CLM-2026-0003
```

台词不再预生成——调哪个工具、按什么顺序、给什么结论，全由模型自己决定；
`max_turns` 默认 10 兜底。注意两点：① 模型质量不可控，四张单可能不是全对
（共用契约只担保离线确定性）；② `output_type` 的 response_format 要求端点支持
json_schema——个别端点不支持时，去掉 `output_type` 回到文本模式自己解析（L2.4 纪律）。

## 4. 练习（本课过关点）

Unit 3 的练习是**改造题**：在能跑的 demo 上完成指定修改。规则不变——单变量编辑
约束：只改 TODO 标注的函数体/区域**与所需的顶部 import**；卡住先想 5 分钟再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_handoff.py` | 单 agent → 审查员+复核专员双 agent（handoff-as-tool）；验收：四用例契约决策不变、ESCALATE 单 3 请求且 last_agent 换人 |
| ex2 | `exercises/ex2_guardrail.py` | 无护栏入口 → InputGuardrail 拦不存在单号；验收：好单号照常出 Advice、坏单号抛 tripwire 异常且 output_info 对口径 |
| ex3 | `exercises/ex3_budget.py` | 默认预算 → 显式小预算 + 取证记账；验收：`MaxTurnsExceeded` 恰在第 N 轮、REQUESTS 账本兑现 |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：注解幻觉坑（把 Agent 当 Spring 注解用）

这是本课的命名化失败模式——Java 人看到 `Agent(name=..., tools=[...])` 会本能地
把它理解成「声明」，然后按声明式的预期写代码，全部落空。

- **现象**：你想「给线上审查 agent 临时加个规则」，于是写了第二处
  `Agent(name="Reviewer", ...)` 的新实例挂新 instructions，却困惑为什么另一个
  入口的行为没变；或者你反复修改某个 `Agent` 实例的 `tools` 列表，跑出来时而生效
  时而不生效；或者你以为 `instructions` 写了「必须先查预算」框架就会保证顺序——
  它只是发给模型的 system 提示，模型可以不理。
- **最小复现**（`code/` 下一分钟版）：

  ```python
  a = Agent(name="Reviewer", instructions="你是审查员。", model=model, tools=[...])
  b = Agent(name="Reviewer", instructions="你是复核员。", model=model, tools=[...])
  # a 和 b 没有任何关系：没有容器注册表，没有单例语义，没有「同名覆盖」——
  # 它们只是两个恰好同名的 dataclass 实例。行为由你把哪个传给 Runner.run 决定。
  ```

  再看工具侧：`@function_tool` 在**装饰执行的那一刻**就把签名读成 schema 存进
  `FunctionTool.params_json_schema`（openai/openai-agents-python@fbd2dbca#src/agents/tool.py，
  `_create_function_tool` 里的 `function_schema(...)` 调用）——之后你再改函数签名
  或 docstring，schema 不会跟着变；它不是注解处理器，没有编译期扫描。
- **Java 直觉为何失效**：Java 的 `@Service` / `@Bean` 是**容器托管**的声明——同名
  Bean 有注册表、有覆盖规则、有生命周期；Spring AOP 甚至能在不改业务代码时改变
  行为。这套心智让你默认「配置是集中且被管理的」。而 `Agent` 是**运行时普通值**：
  没有注册中心（谁拿谁用）、没有不可变性（字段随时可改，改了只在下一次 run 生效）、
  没有代理（guardrail 不是 AOP，是显式挂到字段上的检查）。声明式语言给了你
  「写下来就生效」的幻觉，命令式世界生效的是**你传给 Runner 的那个对象**。
- **修复与纪律**：① 单一事实源——agent 的装配集中在一个工厂函数（demo 的
  `_build_agent`），入口只从工厂拿，不散落 new；② 把 agent 实例当**配置版本**管理，
  行为变更 = 换实例或改工厂，别在运行途中偷偷改字段（要动态就学框架自己的做法：
  `instructions` 传函数、`tools` 用 `is_enabled`）；③ 记住 schema 冻结时机——
  docstring 是「装饰时」的 API 文档，改了文档要重新装饰（对 Java 人：注解是
  编译期读一次，装饰器是 import 时跑一次，语义意外地相似——这次让直觉帮你）。

## 6. 延伸

官方文档（仓库 docs/ 目录，克隆即读）：

- `docs/agents.md`（Agent 原语与动态 instructions）、`docs/tools.md`（function_tool
  与 needs_approval）、`docs/handoffs.md`、`docs/guardrails.md`、
  `docs/human_in_the_loop.md`（RunState 的完整用户手册）。

源码路标（本地克隆 `~/develop/opensource/openai-agents-python`，HEAD fbd2dbca
＝发布版 0.22.2 之后 5 个提交——CI/文档为主，唯一代码修复在 server-managed resume
路径，本课引用的文件两版一致；依赖按宪法钉 `openai-agents==0.22.2`）：

- openai/openai-agents-python@fbd2dbca#src/agents/agent.py —— `Agent` dataclass
  与全部字段语义（instructions 可为函数、handoffs/output_type/guardrails 的挂载点）；
- openai/openai-agents-python@fbd2dbca#src/agents/run.py —— `Runner.run` 的循环
  docstring（四步循环 + 两类异常）；1737 行起 `asyncio.gather(guardrail_task,
  model_task)` 是「护栏并行赛跑」的现场；
- openai/openai-agents-python@fbd2dbca#src/agents/tool.py —— `function_tool` 的
  schema 生成（签名 + docstring → params_json_schema）与 strict 模式；
- openai/openai-agents-python@fbd2dbca#src/agents/handoffs/__init__.py ——
  `handoff()` 与 `default_tool_name`（转交工具名的全小写变换）；
- openai/openai-agents-python@fbd2dbca#src/agents/guardrail.py ——
  `InputGuardrail`/`OutputGuardrail`、`GuardrailFunctionOutput`、`run_in_parallel`；
- openai/openai-agents-python@fbd2dbca#src/agents/models/openai_chatcompletions.py
  （及同目录 chatcmpl_converter.py）—— chat-completions 路径的请求组装：
  `convert_response_format`（output_type → response_format）、工具与 handoff 的
  转换、`items_to_messages`（消息历史回放）；
- openai/openai-agents-python@fbd2dbca#src/agents/tracing/processors.py ——
  `BackendSpanExporter._OPENAI_TRACING_INGEST_ENDPOINT`（默认外发端点，§2.7 证据）；
- openai/openai-agents-python@fbd2dbca#src/agents/run_state.py —— RunState：
  先读类 docstring（764 行起）与 `to_json/from_string`，体会「无引擎 HITL」的
  快照边界；实现深水区（会话对账、schema 版本）留给 L3.3 之后回头再读；
- openai/openai-agents-python@fbd2dbca#src/agents/exceptions.py —— 框架异常谱系：
  `AgentsException` 基类与 `MaxTurnsExceeded` / `InputGuardrailTripwireTriggered`
  / `ModelBehaviorError`（练习 ex2/ex3 断言的就是它们）。

### 与 mini-agent 对照

| mini-agent（Unit 2 手写） | openai-agents（本课） | 替你付掉了什么 |
|---|---|---|
| L2.3 `agent.py` 的 while 循环 + 双终止 | `Runner.run` + `max_turns`（默认 10） | 十行循环、轮数计数、异常抛点（`MaxTurnsExceeded` ≈ `AgentBudgetExceeded`） |
| L2.2 `tools.py` 注册表（手写 schema） | `@function_tool`（签名 + docstring） | schema 生成、参数校验、错误回喂（`failure_error_function`） |
| L2.4 结构化输出（schema 约束 + 回喂重试） | `output_type=Advice` | response_format 注入、Pydantic 校验、失败转 `ModelBehaviorError` |
| L2.3 `ScriptedModel` + mock 端点 | 同一套 mock 端点 + `OpenAIChatCompletionsModel` 注入 | 无——对照组原样服役，这正是它的价值 |
| （没做：多 agent 路由） | `handoff` / handoff-as-tool | 转交工具的包装与历史衔接 |
| （没做：输入检查） | `InputGuardrail` + tripwire 异常 | 护栏调度（并行赛跑/前置）、结果对象 |
| L2.3 无预算外掐秒表的事故复盘 | `MaxTurnsExceeded` 有名异常 | 「让上层知道为什么停」的结构 |

体感结论：openai-agents 是四重奏里**离 mini-agent 最近**的一层——它的每个原语都能
在 Unit 2 找到同构的手写件，抽象没有发明新概念，只把「注册表、循环、schema、预算」
变成了字段与装饰器。代价是控制粒度也停在字段级：想改「回喂格式」或「裁剪策略」
这种循环内脏，你就得绕开它（下一课 langgraph 用显式图把同一批能力做成**可重组的
节点**——光谱的另一端）。

## 离毕业又近的一块

毕业设计的执行器选型今晚有了第一个数据点：openai-agents 的 `max_turns`/`output_type`
就是 L5.1 执行器要的成本护栏与建议单 schema，RunState 的审批暂停是 L5.2
「审批外化」的备胎方案（spoiler：主角是 L3.3 的 langgraph checkpoint）。
mini-agent 对照表 +1 行——决策表（L3.8）的「openai-agents」列，今晚记满。
