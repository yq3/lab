# L3.2 langgraph ①：StateGraph——把 ReAct 循环画成图

> 昨晚 openai-agents 交卷：`Runner.run` 把循环、工具 schema、handoff、guardrail 全部
> 付掉，你写的只有装配——双 agent 转交、一道输入护栏，四张单契约照旧全绿。今晚光谱
> 进第二站**图引擎** langgraph：同一个 ReAct 循环不再藏在一把梭的 run 里，摊开成显式
> 的节点与边——你手装，引擎照图跑。新问题随之换轴：结构从「下一步调谁」变成「状态
> 怎么在节点间流动」，谁合并、谁覆盖，今晚逐个落定。

## 1. 本课目标

今晚把 L2.3 手写的 ReAct 循环**画成一张图**：用 langgraph 的 StateGraph 装配「报销单审查
agent」，统一出口 `run_review(claim_id) -> Advice` 四用例照旧全绿。完成后你能：

- 用 `add_node / add_edge / add_conditional_edges / START / END / compile` 手装一张带环的图
  （不用 prebuilt——那是 L3.4 的导读内容）；
- 说清**状态 schema**：为什么用 TypedDict 而不是 Pydantic、`Annotated` reducer 的「合并 vs
  覆盖」语义、`NotRequired` 的入口状态——这是本课最大的教学点；
- 实测 `recursion_limit` 硬终止（`GraphRecursionError`），与 L2.3 的 `AgentBudgetExceeded`
  逐条对照；
- 把「模型 + 工具」打包成**子图**挂进外层图——图即节点，对照 Java 工作流引擎的子流程。

为什么 langgraph 占三课：它是 Java 生产栈 **langgraph4j / spring-ai-alibaba graph 的同源
上游**——今晚学的 StateGraph、reducer、条件边语义，就是你在 Java 侧会遇到的同一套概念的
Python 原型。学它等于预习生产栈。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| BPMN 流程定义 + 引擎（Camunda/Flowable） | `StateGraph` + `compile()` | 装配即部署：builder 描述拓扑，compile 产出可执行单元——没有 XML/DSL，全是普通 Python |
| 流程变量 `Map<String, Object>`（ProcessVariables） | `ClaimState`（TypedDict） | 键名即契约但**运行时不校验**——校验发生在边界（Pydantic 的 `model_validate_json`） |
| 子流程 / call activity | 编译好的子图当节点 | 图即节点：`add_node("review", compiled_subgraph)` |
| 排他网关（XOR gateway） | 条件边 `add_conditional_edges` | 分支判断从画布/XML 变成**一个收状态、返回节点名的普通函数** |
| `Map.merge` / `Collectors.reducing` | `Annotated[list, reducer]` | 合并策略写进**类型注解**里给框架运行时读——Java 注解没有这种「值语义」 |
| `AtomicReference.set`（最后写赢） | 无 reducer 的键（LastValue 通道） | 同是覆盖，但更严格：同一 superstep（图引擎的一轮同步执行——所有就绪节点跑完、状态合并、进入下一轮；L3.4 §2 深讲）双写直接抛 `InvalidUpdateError` |
| 线程池拒绝策略 / 超时兜底 | `recursion_limit`（默认 25） | superstep 计数烧满抛 `GraphRecursionError`——确定性护栏对冲图里的死环 |

### 2.1 图不是调用栈：状态是唯一媒介

langgraph 的节点不是方法：它收**整份状态**、返回**一份状态更新**（dict），不共享任何局部
变量。L2.3 循环里那个 `messages` 局部变量，现在变成状态里的一个键，由引擎托管：

```python
async def reviewer(state: ClaimState) -> dict:      # 读：整份状态
    response = await model.ainvoke(state["messages"])
    return {"messages": [response]}                  # 写：只写更新的键
```

节点之间没有参数传递、没有 `this`——**一切通信都经过状态**。这带来两个直接后果：
下游节点能读到上游「碰巧没删」的一切（审计友好）；写错键名没有任何编译器/运行时报错
（§5 陷阱的入口）。

### 2.2 状态为什么用 TypedDict，而不是 L1.3 的 Pydantic

`ClaimState` 三种字段正好展示三种语义：

```python
class ClaimState(TypedDict):
    messages: Annotated[list, add_messages]      # 合并：append-only 消息史
    events: Annotated[list[str], operator.add]   # 合并：审计流水（ex2 的教学点）
    advice: NotRequired[Advice]                  # 覆盖：只有 finalize 写
```

分工的逻辑（也是框架的工程取舍）：

- **Pydantic 是边界校验器**：L2.4 的纪律——LLM 输出在出口用 `Advice.model_validate_json`
  把关。`advice` 字段的**值**仍是 Advice 实例，但**写入状态这一步**不再校验——状态是引擎
  的内部账本，节点是自己人，内部转账不设卡口，卡口设在对外边界。
- **TypedDict 是「带字段名的 dict」**：运行时它就是普通 dict（零开销），价值全在类型层——
  pyright 知道每个键的类型，键名拼错在**读**的时候会红。Java 对照：它像
  `Map<String, Object>` + 一份所有人遵守的字段表；而 record/bean 适合不可变 DTO，
  不适合「每个节点只更新几个键」的状态。
- **`NotRequired`**（typing）：`advice` 在入口状态里不存在——第一个写它的节点才让它出现。
  对照 Java 的 `Optional` 字段，但这里是「键可以整个缺席」，不是「值为 null」。

### 2.3 Annotated 与 reducer：合并 vs 覆盖

`Annotated[T, meta]` 是 typing 的**元数据包**：第一参是类型，后面随便挂什么，静态检查器
只看第一参，框架在运行时读 `__metadata__`。langgraph 用它声明「这个键怎么合并」——

- **无 reducer → LastValue 通道**：`update()` 取 `values[-1]`，谁后写谁赢（覆盖）；
- **有 reducer → BinaryOperatorAggregate 通道**：对每个新值执行 `operator(旧值, 新值)`
  （合并）。`add_messages` 是特制版：追加 + **按消息 id 去重/更新**。

三条实测纪律（`code/step1_reducer.py` 全部可复现）：

1. 顺序写无 reducer 键：**静默覆盖**——A 写的值被 B 顶掉，一个字节报错都没有；
2. 同一 superstep 并行写无 reducer 键：**响亮报错**——`InvalidUpdateError: At key '...':
   Can receive only one value per step. Use an Annotated key to handle multiple values.`
   （报错文案就在 `LastValue.update` 里，见延伸路标）；
3. 带 reducer 的键怎么写都合并——`messages` 能 append-only、L3.4 的 Send 扇出能并行累加，
   靠的都是这一条。

Java 侧最接近的心智模型：`Map.merge(key, v, Integer::sum)` 把「怎么合并」变成参数；
langgraph 把它从**调用点**挪到了**字段声明**——一次声明，全图生效。

### 2.4 条件边与 START/END：分支判断是普通函数

```python
def route_after_reviewer(state: ClaimState) -> Literal["tools", "finalize"]:
    return "tools" if state["messages"][-1].tool_calls else "finalize"
```

条件边 = 排他网关：path 函数收状态、返回下一个节点名（也可以返回 `END` 哨兵直接收工）。
L2.3 循环里的 `if not tool_calls: return` 被替换成这张两行的路由表；`Literal`（L1.2 复习）
在类型层把可去的节点列成枚举。`START`/`END` 是保留节点名（`"__start__"`/`"__end__"`），
图的入口边从 `START` 出发、出口边到 `END` 收口。

### 2.5 追踪零外发（一句话）

langchain 的 langsmith 追踪**默认关闭**：不设 `LANGSMITH_*` 环境变量就零外发——本课所有
代码与 `.env.example` 都不设它。对照 L3.1 的 openai-agents 要显式 `set_tracing_disabled(True)`，
langgraph 这边是「默认不发、想开再开」，方向相反，纪律一样。

## 3. 动手代码

先 `uv sync`。`code/` 里除了对版共享件——advice / mock_tools / review_rules /
mock_endpoint 六课对版（L3.1–L3.6 字节相同）、`test_contract.py` 五课对版
（L3.1/L3.2/L3.4/L3.5/L3.6 字节相同）——之外，本课新增六个文件：`demo.py`
（图的全部本体）、四个讲义脚本（step1_reducer / step4_recursion / step5_subgraph /
demo_trace）与讲义区测试 `test_demo.py`。

### Step 1：覆盖 vs 合并（10 分钟，零模型调用）

```bash
uv run python code/step1_reducer.py
```

```text
== Step1 覆盖 vs 合并（零模型调用） ==
[顺序图 START→a→b→END]
  note  = '节点B写的'  <- 无 reducer：b 静默覆盖 a（LastValue.update 取 values[-1]）
  trail = ['a', 'b']   <- 有 reducer：operator.add 逐次合并
[并行图 START→left∥right→sink，left/right 都写 note]
  InvalidUpdateError: At key 'note': Can receive only one value per step. Use an Annotated key to handle multiple values.
  <- 同一 superstep 双写无 reducer 键被拒绝；带 reducer 的键本可以安然合并
[并行图（只留 trail 键）]
  trail = ['left', 'right'] <- 并行写 + reducer = 合并——L3.4 的 Send 扇出靠的就是这个语义
```

对着输出把 §2.3 的三条纪律各指认一遍：哪一行是覆盖、哪一行是报错、哪一行是合并。

### Step 2：装图（读 code/demo.py，15 分钟）

`demo.py` 的 `build_graph` 是全课核心——**7 行装配**（3 个 `add_node` + 4 条边）装出一张带环的图：

```python
builder = StateGraph(ClaimState)
builder.add_node("reviewer", make_reviewer(model))
builder.add_node("tools", tools_node)
builder.add_node("finalize", finalize)
builder.add_edge(START, "reviewer")
builder.add_conditional_edges("reviewer", route_after_reviewer)
builder.add_edge("tools", "reviewer")     # 回边成环：ReAct 循环的图形态
builder.add_edge("finalize", END)
return builder.compile()
```

三个节点对着 mini-agent 逐个读：`reviewer` = 模型请求；`tools` = L2.2 的注册表分发
（含 unknown_tool 回喂不抛）；`finalize` = L2.4 的 `model_validate_json` 出口。
模型的工具绑定只剩一行——`ChatOpenAI(...).bind_tools([check_budget, verify_invoice])`：
框架读函数签名自动生成 JSON Schema，对照 L2.2 你手写的那份，一个字段不差。

### Step 3：离线跑通四用例（10 分钟）

```bash
uv run python code/demo_trace.py CLM-2026-0004
```

```text
== L3.2 StateGraph 审查 agent：CLM-2026-0004（离线剧本） ==
图: START → reviewer ─条件边→ tools → reviewer（成环）；无 tool_calls → finalize → END

== superstep 轨迹（stream_mode='values'，每步给全量状态） ==
  [reviewer] + system: 你是报销单审查助手。审查规则（先命中先停）： 1) 明细含非正数金额 → ESCALAT…
  [reviewer] + human: 请审查报销单 CLM-2026-0004（钱工，展会物料采购（发票校验未过））。 明细（…
  [reviewer] + ai: [并行选了工具: check_budget, verify_invoice]
  [   tools] + tool: {"dept": "DEV", "budget_cents": 100000, "spe…
  [   tools] + tool: {"id": "INV-2026-0005", "valid": false, "rea…
  [reviewer] + ai: {"claim_id":"CLM-2026-0004","decision":"REJE…
  [finalize] （不新增消息——只读状态收束，advice 键被写入）

== 收口 ==
  advice   : REJECT / REJECT:INVOICE_INVALID / 剩余 40000 分
  （剧本预期: REJECT / REJECT:INVOICE_INVALID / 剩余 40000 分）
  events   : ['reviewer', 'tools', 'reviewer', 'finalize']
  模型请求 : 2 次（第 1 次带 2 个工具 schema；第 2 次带 2 条 ToolMessage 回喂）
  绑定工具 : ['check_budget', 'verify_invoice']（bind_tools 自动生成的 schema，对照 L2.2 手写版）
```

看三个证据：`events` 审计流水恰好是执行序列（reducer 合并的直接应用）；模型请求 2 次
（第 1 轮并行选两个工具、第 2 轮收束——与 review_rules 剧本一一对应）；发票校验
`valid: false` 真的来自 mock 工具。然后跑共用验收——

```bash
uv run pytest code/
```

```text
.........                                                                [100%]
9 passed in 5.49s
```

9 个测试 = 共用契约 2 个（四用例逐单 + 覆盖型 meta）+ 讲义区 7 个（路由分支、工具分发与
unknown_tool 回喂、节点序列与审计流水、逐单与剧本预期全等、finalize 解析、reducer 注解
meta、规则表五条走查）。走查测试补的是规则表视角的留白：mock 四单只命中规则 1/2/3/5，
规则 4（总额超剩余预算 → BUDGET_EXCEEDED）无用例触达——由讲义区测试用合成视图直接
调 `review_rules.decide` 对表，五条规则的 decision/reason 全覆盖。

### Step 4：recursion_limit 硬终止实测（10 分钟）

```bash
uv run python code/step4_recursion.py
```

```text
== Step4 recursion_limit：图引擎的硬终止 ==
[无限 ping-pong 图，recursion_limit=6]
  GraphRecursionError: Recursion limit of 6 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT
  实际执行 superstep 数: 6（ping/pong/ping/pong/ping/pong）——预算烧满即停，一个不多
  对照 L2.3: AgentBudgetExceeded('5 轮预算耗尽')——同一条纪律换成了图引擎的配置项
  默认 recursion_limit=25（langchain_core 的 DEFAULT_RECURSION_LIMIT）——生产图应显式给，
  demo.py 的 run_review 里 config={'recursion_limit': 8} 就是这句话的落地。
[收敛循环图：条件边 count<3 继续，否则 END]
  正常结束: count=3, steps=['tick', 'tick', 'tick']——正常出口是条件边，预算只是护栏
```

双终止在图形态下的新表述：**软出口**是条件边（模型的 tool_calls 有没有停），**硬预算**是
`config["recursion_limit"]`（数 superstep——本图一个 superstep 一个节点，reviewer 跑两轮 +
tools + finalize = 4 步，预算 8 绰绰有余）。

### Step 5：subgraph——图即节点（15 分钟）

```bash
uv run python code/step5_subgraph.py
```

```text
== Step5 subgraph：把审查循环打包成一个节点（CLM-2026-0001） ==
外层: START → intake → review(子图) → report → END
advice: APPROVE / PASS / 剩余 10000 分
外层 events: ['intake', 'report']  <- 子图是黑盒，内部审计留在内部
消息史: 6 条（intake 写 2 条 + 子图回 4 条，add_messages 跨边界按 id 去重）
模型请求: 2 次——整条流水线的行为与 demo.py 的扁平图完全一致
```

两个工程细节值得停下来想：

- **`add_node("review", compiled_subgraph)`**：编译产物本身就是合法节点——对照 Java 工作流
  引擎的子流程（call activity）：外层只关心进出的状态键（messages/advice），内部拓扑封装。
- **子图状态刻意不含 events**：外层把状态传给子图、子图把结果合回外层，**共享的 reducer
  键会被施加两次**——实测把 events 放进子图，外层流水会变成
  `['intake', 'intake', 'reviewer', ...]`（前缀重复累加）。messages 没这个问题，因为
  `add_messages` 按消息 id 去重。所以本课的纪律：**子图状态只放真正需要跨边界的键**。

### Step 6（可选）：真实端点加餐

```bash
uv run python code/demo_trace.py --real CLM-2026-0001
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。）
图一行不改，模型自己决定调什么工具、按什么顺序；预算 8 步兜底。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given 部分用到的）。
卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_wiring.py` | 图装配：节点函数给定，补 add_node/add_edge/条件边/compile；验收含节点执行序列精确断言 |
| ex2 | `exercises/ex2_events.py` | 自定义 reducer：给状态加 `events: Annotated[list[str], operator.add]`，各节点登记审计事件；两条分支流水精确断言 + 注解 meta 检查 |
| ex3 | `exercises/ex3_gate.py` | subgraph 改造：模型+工具打包成子图，外层 precheck 拦非法单号直接短路；验收断言 mock 端点请求数为 0 |

形态标注（诚实起见）：ex2 是**改造前可跑型**——装配已给定、TODO 前图就能跑，改的是给
运行中的图加审计通道；ex1/ex3 是**连线型骨架**——TODO 前图尚未装配（build 直接
NotImplementedError），可跑参照见讲义 `code/demo.py`（ex1 同构）与 Step 5 的
`code/step5_subgraph.py`（ex3 的外层图）。骨架自包含：ex1/ex2 零 HTTP，ex3 用
L2.3 服役至今的 mock 端点。验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：图不是调用栈（状态键静默吞没）

这是本课的命名化失败模式——Java 人的直觉是「写错字段名编译器会拦我」，在图引擎里这层
保护不存在。

- **现象**：图「跑通了」但结果不对——某个节点写状态时键名拼错（`mesages`），或两个节点
  先后写同一个无 reducer 的键，下游读到旧值/空值，**没有任何报错**；直到审计断言
  （events 流水对不上）才暴露。更阴的版本：并行两个节点写同一个无 reducer 键——这个会
  报错，但报错文案是 `Can receive only one value per step. Use an Annotated key...`，
  Java 人第一反应是「并发 bug」，实际是「语义声明缺失」。
- **最小复现**（两段都在 step1_reducer.py / 冒烟实测过）：

  ```python
  class S(TypedDict):
      note: str

  async def a(state: S) -> dict:
      return {"note": "a", "mesage": "拼错键"}   # 拼错的键被静默丢弃——不报错、不落账

  # 顺序图：a 写 note，b 再写 note —— b 静默覆盖 a，值丢了无声无息
  ```

- **Java 直觉为何失效**：Java 里写错成员变量（`this.mesage`）编译直接红；方法参数有签名，
  Spring 注入失败启动就炸。Python dict 接受任意键；而 langgraph 面对更新里「不认识的键」
  选择**静默忽略**、面对无 reducer 键的顺序写选择**静默覆盖**——它以为你在声明式地更新
  状态，不知道你在打错字。类型层本可以救你（pyright 对 `ClaimState` 键名敏感），但只在
  **读**的时候——写侧的 dict 返回值是 `dict`，键名不检查。
- **修复与纪律**：① 状态 schema 当唯一契约写——每个键先想清楚语义（合并/覆盖）再声明，
  需要累积就给 `Annotated[..., reducer]`，别让「覆盖」成为默认；② 子图/外层只共享真正
  跨边界的键（Step5 的 events 教训）；③ 让「谁在写」可观测——events 审计流水 +
  `test_demo.py` 的注解 meta 测试把 reducer 语义钉死在验收里；④ 读状态时相信 pyright：
  `Unknown` 报警别 ignore，那多半是键名拼错的唯一线索。

## 6. 延伸

- 官方文档：StateGraph 概念页（states / reducers / 图 API）——
  https://docs.langchain.com/oss/python/langgraph/overview ，搜 `Annotated` 与
  `recursion_limit` 两个关键词。
- 源码路标（本地克隆 `~/develop/opensource/langgraph`，按图索骥）：
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/graph/state.py` ——
    StateGraph 本体：`add_node` / `add_edge` / `add_conditional_edges` / `compile`，
    以及把注解翻译成通道的 `_get_channels`（无 reducer 的 fallback 就是 LastValue）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/channels/last_value.py` ——
    `LastValue.update`：覆盖语义与「Use an Annotated key」报错文案的本体（§2.3 的证据）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/channels/binop.py` ——
    `BinaryOperatorAggregate.update`：`self.value = self.operator(self.value, value)`，
    你写的 `operator.add` 在这里被逐值执行；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/graph/message.py` ——
    `add_messages`：按 id 去重/更新的特制 reducer（子图边界安全的原因）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/errors.py` ——
    `GraphRecursionError(RecursionError)`：硬终止异常，继承自 RecursionError；
  - `langchain-ai/langchain@348c9dc57#libs/core/langchain_core/runnables/config.py` ——
    `DEFAULT_RECURSION_LIMIT = 25`：默认预算的出处（langgraph 复用 RunnableConfig）；
  - `langchain-ai/langchain@348c9dc57#libs/partners/openai/langchain_openai/chat_models/base.py` ——
    `bind_tools`：工具 schema 自动生成的入口（对照 L2.2 手写 JSON Schema）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py` ——
    Pregel 执行循环：superstep 调度本体，`Recursion limit of ... reached` 的报错就在这里。

### 与 mini-agent 对照

| mini-agent（L2.3） | langgraph（今晚） |
|---|---|
| `while True` + `if not tool_calls: return` | 条件边 `route_after_reviewer` + 回边成环 |
| `messages.append(assistant)` / 回喂 ToolMessage | `Annotated[list, add_messages]` reducer（还多了按 id 去重） |
| `REGISTRY` 注册表分发 + unknown_tool 回喂 | `tools` 节点（同样的注册表、同样的纪律） |
| `max_turns` 轮数预算 → `AgentBudgetExceeded` | `recursion_limit` superstep 预算 → `GraphRecursionError` |
| `AgentResult`（回答/轨迹/轮数三件套） | 状态本身（messages/events/advice 就是档案） |
| 手写轨迹打印 | `astream(stream_mode=...)` 免费获得 |

一句话总结：**框架替你付掉的就是 while 那十行**，外加免费的流式可观测——以及 L3.3 即将
登场的、手写版永远给不了的检查点。

## 离毕业又近的一块

毕业设计 L5.1 的执行器「取数→分析→生成建议单→送审」就是今晚这张图的放大版：固定拓扑 +
计划驱动路由，StateGraph 的确定性拓扑正是 fail-closed（L5.4）要的地基；events 审计流水
是 L5.3 事件溯源的雏形。下一课 L3.3 给图装上「暂停→杀进程→恢复」——毕业设计审批外化的
直接机制。
