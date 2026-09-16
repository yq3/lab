# L3.4 langgraph ③：Send 动态扇出 + create_react_agent 源码导读

## 1. 本课目标

L3.2 你手装了一张图，L3.3 给它装了暂停恢复；今晚做两件事收尾 langgraph 三连：

- **让图「横向长」**：用 `Send` 做动态扇出——一张图同时审四张报销单（map-reduce 的图表达），
  归并靠**自定义 reducer 函数**（本课新知识点）；
- **读 `create_react_agent` 源码**：框架把 L3.2 那张手装图整个打包成**一行装配**——
  我们逐段读它的装配三件事，量化「这层抽象替你付了多少行」，与 L2.3 的 mini-agent 逐件对照。

完成后你能：

- 用条件边返回 `[Send("节点", 分支专属状态), ...]` 做运行时动态并行，并说清它与
  `ExecutorService.submit` 的本质差异（**改写图拓扑的动态边 vs 任务队列**）；
- 写自定义 reducer（`Annotated[dict[str, Advice], 你的函数]`）完成扇出-归并的归并半边；
- 在 `chat_agent_executor.py` 里指出模型节点、工具节点、条件边的装配处（带着行号与行数量化）；
- 同题 demo 契约照旧全绿：`run_review(claim_id) -> Advice` 四用例——**同一题面，
  langgraph 的第二种装配**（L3.2 手装 / L3.4 prebuilt），差异只在装配方式。

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
| `ExecutorService.submit` 返回 `Future` | 条件边返回 `Send` 列表 | Send 不是任务句柄——它是「这一超步把某节点实例化几次、每次给什么状态」的**图拓扑改写**；分支可被 checkpoint/replay |
| `Future.get` / `CompletableFuture.allOf` 收集结果 | 超步边界上的 reducer 归并 | Java 没有这一步：合并策略不在回调里，**声明在字段的 Annotated 第二参上** |
| `Stream.flatMap` + `collect(groupingBy)` | Send 扇出 + 自定义 dict reducer | 形状同构，但归并发生在**超步边界**（BSP），不是流的水槽 |
| `CyclicBarrier` / `Phaser` 屏障 | superstep（超步） | 引擎替你await所有人；屏障上做的是 reducer 合并，Java 屏障不带语义 |
| Spring Boot 自动装配（约定优于配置） | `prebuilt.create_react_agent` | 一个调用换掉整张手装图；代价是节点名/v2 语义藏在默认参数里（§5） |
| 模板方法模式里的钩子 | `pre_model_hook` / `post_model_hook` | 扩展点参数化——但主流程（循环十行）不再归你 |

### 2.1 Send：运行时才确定的并行边

L3.2 的并行是**静态**的：`START → left ∥ right → sink`，拓扑在 `compile()` 前就画死了。
`Send` 是**动态**的：条件边函数不返回节点名，返回 `Send` 对象的列表——引擎在**运行时**
为每个 `Send` 实例化一个目标节点任务，分支数到那一刻才确定：

```python
def fan_out(state: BatchState) -> list[Send]:
    return [Send("review", {"claim_id": cid, "ep_url": ...}) for cid in state["claim_ids"]]
```

`Send(node, arg)` 只有两个关键参（源码 `types.py:704-792`，ast 口径 29 行——一个小类而已）：
目标节点名 + **该分支的专属状态**。第二参是核心自由度：分支的输入状态可以和主图状态
完全不同——批量审查里每个 worker 只带自己那单的 `claim_id` 和**专属 mock 端点 URL**（§3 Step4
会看到这个设计如何救了剧本策略）。

与线程池的本质差异（§5 坑位的入口）：`submit` 把闭包丢进队列，执行器对「业务拓扑」一无所知；
`Send` 改写的是**图在这一步的形状**——每个分支是一个有 path、可排序、可 checkpoint 的任务。
这就是为什么 Send 分支能被 L3.3 的检查点机制暂停/恢复，而线程池任务不能。

### 2.2 超步与归并：BSP 执行模型（执行并发，归并确定）

`pregel/main.py:2959` 的注释原文（执行引擎的自我说明）：

> Similarly to Bulk Synchronous Parallel / Pregel model computation proceeds in steps,
> while there are channel updates. Channel updates from step N are only visible in step N+1.

翻译成 Java 人语言：这是一个**带屏障的并行执行器**——每个 superstep 里：

1. 引擎把该步的所有任务（含 Send 分支）**并发执行**（sync invoke 走线程池，实测证据在 Step4）；
2. 屏障：所有任务落账后才进入下一步——`reduce` 节点因此在「全部 review 分支写完」之后才跑；
3. 归并：各分支对同一键的写入按 reducer 逐份合并——**顺序由 `apply_writes` 按 task path 排序
   决定**（`_algo.py:253-256` 的注释明说 `to ensure deterministic order`），与谁先跑完无关。

所以「Send 分支」同时具备两个 Java 直觉里矛盾的性质：**执行是真并发**（四个 worker 同时开工），
**合并是真有序**（字典里按键取值永远稳）。但没有 `Future`——你要结果，只能在下一个超步里读状态。

### 2.3 自定义 reducer：归并半边的声明

L3.2 用过标准库的 `operator.add`；本课的归并目标是 dict，`dict + dict` 是 TypeError——
所以**自己写**：

```python
def merge_results(old: dict, new: dict) -> dict:
    return {**old, **new}                       # 浅合并：new 覆盖同名键

class BatchState(TypedDict):
    results: Annotated[dict[str, Advice], merge_results]   # 第二参放「函数对象」
```

纪律三条：签名 `(旧, 新) -> 合并`；`Annotated` 第二参是**函数对象**不是函数调用（没有括号）；
各分支写**不冲突的键**（按 claim_id 分片），浅合并就无竞态。对照 Java：`Map.merge(key, v, fn)`
把合并逻辑放调用点，langgraph 把它挪到**字段声明**——一次声明，全图生效（L3.2 §2.3 的延续）。

### 2.4 prebuilt：约定优于配置的取舍

```python
agent = create_react_agent(model, tools=[check_budget, verify_invoice], prompt=SYSTEM_PROMPT)
```

一行换掉 L3.2 的整张图。框架替你做的四个约定：模型**不需要手动 `bind_tools`**（内部绑）；
工具传**裸函数**（ToolNode 自动包成 StructuredTool，参数校验白送）；`prompt` 传 str 自动包
`SystemMessage` 垫在消息史最前；状态 schema 用内置 `AgentState`（messages + remaining_steps）。
代价：节点叫什么、条件边怎么路由、每个 tool_call 是不是独立 Send 任务——这些**藏在默认参数里**，
不读源码不知道（所以有 §3 Step3 的源码导读与 ex3 的事实题）。

诚实边界：prebuilt 1.1.0 里 `create_react_agent` 已挂弃用告警（官方迁名
`langchain.agents.create_agent`，骨架相同，V2.0 才移除）——本课读的正是这个经典装配的
源码，demo 里用 warnings 过滤它的改名单（行为不受影响）。读懂数十行核心之后，
你换任何一个「一行装配」的框架都不再是黑盒。

### 2.5 追踪零外发（一句话）

与 L3.2 相同：不设 `LANGSMITH_*` 环境变量即默认关闭、零外发——本课代码与 `.env.example`
都不设它。

## 3. 动手代码

先 `uv sync`。`code/` 里除五课对版的共享模块（advice / mock_tools / review_rules /
mock_endpoint / test_contract）外，本课五个新文件：`demo.py`（契约线）、`demo_trace.py`
（轮次解剖）、`demo_batch.py`（扇出线）、`count_loc.py`（行数统计口径工具）、
`step5_toolnode.py`（错误回喂对照）。

### Step 1：一行装配跑通契约（10 分钟）

```bash
uv run pytest code/
```

```text
..........                                                               [100%]
10 passed in 9.10s
```

10 个测试 = 共用契约 2 个（四用例逐单 + 覆盖型 meta）+ 讲义区 8 个（官方节点名、轮次结构、
逐单与剧本预期全等、reducer 直接行为、reducer 注解 meta、扇出形状、批量线 8 请求、批量跨跑确定性）。
共用验收 `test_contract.py` 与 L3.1/L3.2 字节相同——题面没动，动的只是装配。

代码量对比（`count_loc.py` 的 ast 口径，§3 Step3 有完整说明）：

| 装配 | 数量 | 说明 |
|---|---|---|
| L3.2 `demo.build_graph` | 10 loc | 手装：3 节点 + 4 边 + compile |
| L3.2 手写节点函数 | 约 40 loc | reviewer / tools_node / finalize / 路由 |
| L3.4 `demo.build_agent` | **6 loc** | 一个 `create_react_agent` 调用（含告警过滤） |
| 框架内部 `create_react_agent` | 414 loc | 其中装配三件事约 165 loc（Step3 拆账） |

抽象没有消灭复杂度，只是把它**搬进了框架**——这正是 Unit 3 要你体感的事。

### Step 2：轮次轨迹解剖（15 分钟）

```bash
uv run python code/demo_trace.py CLM-2026-0003
```

```text
== L3.4 prebuilt 审查 agent：CLM-2026-0003（离线剧本） ==
装配: create_react_agent(ChatOpenAI, [check_budget, verify_invoice], prompt=SYSTEM_PROMPT)
图节点: ['__end__', '__start__', 'agent', 'tools']

== superstep 轨迹（stream_mode='updates'） ==
  [ agent] + ai: [并行选了工具: check_budget, verify_invoice]
  [ tools] + tool: {"dept": "DEV", "budget_cents": 100000, "spe…  (id=call_budget)
  [ tools] + tool: {"id": "INV-2026-0003", "valid": true, "reas…  (id=call_invoice)
  [ agent] + ai: {"claim_id":"CLM-2026-0003","decision":"ESCA…

== 模型请求逐轮解剖（ep.requests）——对照 L2.3 循环十行 ==
  第 1 次请求: 2 条消息 ['system', 'user']；携带工具 schema ['check_budget', 'verify_invoice']
  第 2 次请求: 5 条消息 ['system', 'user', 'assistant', 'tool', 'tool']；携带工具 schema ['check_budget', 'verify_invoice']
  <- 第 2 次请求里的 2 条 tool 消息就是回喂：历史全量重发 + 工具结果垫后（L2.1 §2.2）

== 收口 ==
  advice   : ESCALATE / REJECT:INVALID_AMOUNT / 剩余 40000 分
  （剧本预期: ESCALATE / REJECT:INVALID_AMOUNT / 剩余 40000 分）
  工具执行 : ['check_budget', 'verify_invoice']（真实执行，不是剧本自说自话）
```

对着轨迹数 L2.3 的循环十行：`agent` 节点 = 「请求模型 + assistant 入史」；两个 `tools` 块
= 「遍历 tool_calls 执行回喂」；最后一个 `agent` = 软终止（无 tool_calls，文本即最终回答）。
**注意一个细节**：`tools` 出现了**两次**——一轮并行选了 2 个工具，v2 默认下每个 tool_call
是一个独立的 Send 任务（Step3 源码里看这段）。轮数结论（`ep.requests` 实测）：每单恰好
**2 次模型请求**——和 L3.2 手装图完全一致，因为它们是同一个循环。

### Step 3：源码导读 chat_agent_executor.py（30 分钟）

本地克隆 `~/develop/opensource/langgraph`（HEAD `e539ac122`，prebuilt 是独立包
`langgraph-prebuilt 1.1.0`，本课钉 `==1.1.0`）。行数结论全部用 `code/count_loc.py` 复现
（ast 口径：解析模块 → 取目标函数/类行区间 → 剔 docstring 行区间 → 数非空非注释行；
本目录已带这个工具，禁止 grep 管道口径）：

```bash
uv run python code/count_loc.py def ~/develop/opensource/langgraph/libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py create_react_agent
uv run python code/count_loc.py def ~/develop/opensource/langgraph/libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py create_react_agent.call_model
uv run python code/count_loc.py def ~/develop/opensource/langgraph/libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py create_react_agent.should_continue
uv run python code/count_loc.py range ~/develop/opensource/langgraph/libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py 861 1002
```

```text
#create_react_agent: lines=278-1002 loc=414 (docstring 已剔除)
#create_react_agent.call_model: lines=661-694 loc=27 (docstring 已剔除)
#create_react_agent.should_continue: lines=831-859 loc=27 (docstring 已剔除)
#861-1002: loc=111
```

**它比想象短**：414 loc 里，真正的 ReAct 心脏只有三件事（合计约 165 loc）——

1. **模型节点 `agent`**（`call_model` / `acall_model`，661-694，27 loc）：`_get_model_input_state`
   取消息 → `static_model.invoke(...)` → `{"messages": [response]}`。就是 L2.3 循环里
   「请求 + 入史」两行的函数化；多出来的行一半在处理 `remaining_steps` 不足时的哨兵句
   （689 行 `"Sorry, need more steps to process this request."`——预算护栏的另一形态，
   ex3 ⑥ 会实测它）。
2. **条件边 `should_continue`**（831-859，27 loc）：无 tool_calls → `END`（软终止）；有 →
   **v2 默认返回 `[Send("tools", ToolCallWithContext(...)) for call in tool_calls]`**（849 行起）
   ——你今晚学的 Send 扇出，prebuilt 自己就在用：每个 tool_call 一个独立 tools 任务。
   L2.3 的 `if not tool_calls: return` 在这里就是一个 return END。
3. **装配段**（861-1002，111 loc）：`StateGraph` → `add_node("agent", ...)` / `add_node("tools",
   tool_node)` → `set_entry_point("agent")` → `add_conditional_edges("agent", should_continue)` →
   `add_edge("tools", entrypoint)` 回边成环 → `compile(...)`。与 L3.2 你的 `build_graph`
   逐行同构——多出来的行是 `pre/post_model_hook`、`response_format`（结构化输出加
   `generate_structured_response` 节点）、`return_direct` 这些可选件的分支。

剩下约 250 loc 是参数校验、动态模型（`(state, runtime) -> model` 可调用）、v1/v2 兼容——
生产框架的「可选件税」。工具节点本体在 `tool_node.py`：`ToolNode` 类 559 loc（注入、Command、
HITL 都是它管的），但 `_func` 主路径 29 loc，和 L3.2 你手写的 `tools_node` 逐行对照着读。

### Step 4：Send 动态扇出——批量审查（20 分钟）

```bash
uv run python code/demo_batch.py
```

```text
== L3.4 Send 扇出：批量审查 4 张 mock 单（离线剧本，每单一个专属 mock 端点） ==
图: START → dispatch ─条件边(返回 Send 列表)→ review ×4 ─全部落账→ reduce → END

[dispatch] 派发 4 个 Send 分支: ['CLM-2026-0001', 'CLM-2026-0002', 'CLM-2026-0003', 'CLM-2026-0004']
[review] 分支执行时序（相对最早开工分支，毫秒）：
  CLM-2026-0001  start+   0.0ms  dur 229.7ms  -> APPROVE / PASS
  CLM-2026-0002  start+   0.3ms  dur 229.0ms  -> REJECT / REJECT:ITEM_OVER_LIMIT
  CLM-2026-0003  start+   0.5ms  dur 225.2ms  -> ESCALATE / REJECT:INVALID_AMOUNT
  CLM-2026-0004  start+   0.5ms  dur 228.3ms  -> REJECT / REJECT:INVOICE_INVALID
  分支耗时合计 912.2ms vs 扇出墙钟 229.7ms —— 并发执行的直接证据

== reduce 汇总 ==
  decision 计数: {'APPROVE': 1, 'REJECT': 2, 'ESCALATE': 1}
  四单总额    : 20400 分
    CLM-2026-0001  APPROVE  PASS                       剩余 10000 分
    CLM-2026-0002  REJECT   REJECT:ITEM_OVER_LIMIT     剩余 10000 分
    CLM-2026-0003  ESCALATE REJECT:INVALID_AMOUNT      剩余 40000 分
    CLM-2026-0004  REJECT   REJECT:INVOICE_INVALID     剩余 40000 分
  模型请求    : 8 次（每单恰好 2 次 × 4 个专属端点，实测口径见 test_demo.py）
```

读三个证据：

- **四个分支几乎同时开工**（0.0–0.5ms 内），分支耗时合计 912ms 但墙钟只有 230ms——
  sync invoke 下 Send 分支确实跑在线程池里（§2.2 第 1 条）；
- **结果按 claim_id 精确落位**、两次独立跑全等（`test_demo.py` 的确定性测试）——
  归并顺序由 `apply_writes` 排序决定，与执行次序无关（§2.2 第 3 条）；
- **每单一个专属 mock 端点**：剧本队列是分支共享的 FIFO，执行次序又不保证——若四单共享
  一个端点，B 单可能吃掉 A 单的剧本。Send 的 arg 是分支专属状态，端点 URL 放进去，
  剧本互不干扰（这就是「ep.requests 取证后定的剧本策略」，也是 §5 坑位的正面教材）。

`review` worker（13 loc）内部跑的是一个完整的 `create_react_agent` 装配——扇出的每个分支
都是一个标准 ReAct 循环；`reduce` 节点在屏障后收割（decision 计数 + 总额）。对照 Java：
`claims.stream().flatMap(c -> reviewAsync(c).stream())` + `collect(groupingBy)`——
但归并发生在超步边界，且 groupingBy 的等价物是字段上的 `merge_results`。

### Step 5（可选）：ToolNode 错误回喂 + 真实端点（15 分钟）

```bash
uv run python code/step5_toolnode.py
```

```text
== Step5 ToolNode 错误回喂（对照 L2.2 纪律 / L3.2 手写 tools 节点） ==
[未注册工具名]
  call_unknown -> Error: no_such_tool is not a valid tool, try one of [check_budget, verify_invoice].
[参数类型不对]
  call_bad_args -> Error invoking tool 'check_budget' with kwargs {'dept': 123} with error: dept: Input should be a valid string
[正常调用]
  call_ok -> {"dept": "DEV", "budget_cents": 100000, "spent_cents": 60000, "remaining_cents": 40000}
CALL_LOG: ['check_budget'] <- 只有「正常调用」真实执行；前两种回喂 error、不抛异常
```

L2.2 的纪律（错误回喂不抛）在 ToolNode 里是参数化的 `handle_tool_errors`；且框架把裸函数
包成 StructuredTool 时**白送了一层 pydantic 参数校验**（第二个 case）——L3.2 手写版没有这层，
这是「约定优于配置」的又一份红利。零模型调用、零 HTTP，随改随跑。

真实端点加餐（契约线支持；批量线的每单专属端点是离线剧本策略，线上版直接把 `ep_urls`
换成真实端点即可——分支代码一行不改）：

```bash
uv run python code/demo_trace.py --real CLM-2026-0001
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。）

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given 部分用到的）。
卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_fanout.py` | Send 扇出：补自定义 dict 合并 reducer（Annotated 第二参）+ 条件边返回 Send 列表 + 装配；断言每单结果按 claim_id 落位、汇总计数正确、注解 meta |
| ex2 | `exercises/ex2_prebuilt.py` | prebuilt 装配：补 create_react_agent 调用 + ainvoke + `Advice.model_validate_json` 出口；验收含契约四用例 + 轮数断言（恰好 2 次模型请求）+ 官方节点名断言 |
| ex3 | `exercises/ex3_facts.py` | 源码事实题：读 chat_agent_executor.py / tool_node.py 后把七个事实写进 FACTS dict；pytest 用你的答案跑行为验证（按名取节点、stream 数扇出任务、实测哨兵句）——防止「读完就忘」 |

三题都是改造题（在能跑的 demo 同构结构上完成指定修改），骨架自包含：ex1 零模型零 HTTP，
ex2/ex3 用 mock 端点。验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：Send≠线程池坑（把动态边当任务队列）

这是本课的命名化失败模式——Java 人看到「并行分支」，`ExecutorService.submit` 的心智模型
自动上线，然后被两个方向各打一拳。

- **现象**：方向一：四个 Send 分支共享一个 mock 端点的剧本队列，偶发地 B 单吃掉 A 单的台词、
  四单结果张冠李戴（复跑几次必现）；方向二：笃信「提交顺序 = 执行顺序」，在分支里做顺序敏感
  的消费（比如「第 N 个分支该读第 N 份剧本」），本地一直绿，上了多核机器/flaky CI 才炸。
- **最小复现**（`demo_batch.py` 的设计过程就是这个坑的取证）：让 4 个 worker 各睡 50ms 并记录
  开工时刻——四个分支在 0.5ms 内**同时开工**（并发执行）；而合并顺序跨进程跨次稳定（确定性
  归并）。两个性质同时成立，恰恰说明「执行」与「归并」是两件事——Java 的任务队列心智模型
  里它们是同一件事。

  ```python
  # 反例（demo_batch 的否决设计）：四单共享一个端点的 FIFO 剧本队列
  ep.script_tool_calls(script_for("CLM-2026-0001"))   # 谁的请求先到，谁吃掉 0001 的剧本
  ep.script_tool_calls(script_for("CLM-2026-0002"))   # ——执行次序无保证，配对必然错乱
  # 正解：Send arg 是分支专属状态——每单一个专属端点，剧本互不干扰
  Send("review", {"claim_id": cid, "ep_url": endpoints[cid].url, ...})
  ```

- **Java 直觉为何失效**：`submit` 给你 `Future`，收集是你的事（`get`/`allOf`），执行器不理解
  业务拓扑；`Send` 没有句柄——它改写的是**图在这一超步的形状**，归并在引擎的屏障上由 reducer
  完成（顺序按 task path 排序，确定），执行却在线程池里并发（次序不保证）。把两件事揉进
  「任务队列」一个模型，就会在「顺序」上做出错误承诺。更深的差异：Send 分支是图的一部分，
  有 path、可排序、可被 L3.3 的 checkpoint 暂停恢复——线程池任务没有这些。
- **修复与纪律**：① **分支无共享可变资源**——分支需要什么，放进 Send 的 arg（专属端点、
  专属上下文），而不是让分支去抢全局；② 归并键**必须带 reducer 且分支写不冲突的键**
  （按 claim_id 分片），自定义 reducer 就是为这准备的；③ 顺序敏感的逻辑放 **reduce 节点**
  （屏障之后，确定性顺序里做汇总），不要放分支里；④ 想要「分支完成回调」，那是 Java 的
  词汇——这里等价物是「下一个超步」。

## 6. 延伸

- 官方文档：Send 与 map-reduce 模式——https://docs.langchain.com/oss/python/langgraph/overview ，
  搜 `Send` 与 `map-reduce` 两个关键词；`create_react_agent` 的 API 页看 `version` 参数的
  v1/v2 差异说明。
- 源码路标（本地克隆 `~/develop/opensource/langgraph`，HEAD `e539ac122`，按图索骥）：
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/types.py` —— `Send` 本体
    （704-792 行，ast 口径 29 loc）：docstring 里就写着 map-reduce 用法与「sent state can
    differ from the core graph's state」；
  - `langchain-ai/langgraph@e539ac122#libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py` ——
    本课重头：`create_react_agent`（278-1002 行，414 loc；`call_model` 661-694 / `should_continue`
    831-859 / 装配段 861-1002），v2 的 Send 扇出就在 849 行起；
  - `langchain-ai/langgraph@e539ac122#libs/prebuilt/langgraph/prebuilt/tool_node.py` —— `ToolNode`
    （622-1579 行，559 loc）：`_func` 主路径 793-826（29 loc）、错误回喂的
    `_validate_tool_call` 1268 行起、独立可复用的路由函数 `tools_condition` 1582-1659；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py` —— 2959 行起的
    BSP 注释（本课 §2.2 的原文出处）与 superstep 调度循环；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/_algo.py` —— `apply_writes`
    253-256 行：`sorted(tasks, key=task_path_str)` ——「归并顺序确定」的证据；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/channels/binop.py` ——
    `BinaryOperatorAggregate.update`（123 行起）：`self.value = self.operator(self.value, value)`，
    你的 `merge_results` 在这里被逐份执行；
  - `langchain-ai/langgraph@e539ac122#libs/prebuilt/langgraph/prebuilt/interrupt.py` —— prebuilt
    的 HITL 封装（`HumanInterrupt` / `ActionRequest` / `HumanResponse`）：L3.3 学的裸
    `interrupt()` 是底层机制，这一层给它套了「工具审批表单」的 schema（动作请求 + 允许的
    回复种类 accept/edit/respond/ignore）——一段话了解即可，毕设 L5.2 的审批外化会用到同构思路；
  - `langchain-ai/langchain@348c9dc57#libs/core/langchain_core/runnables/config.py` ——
    `get_executor_for_config`：sync invoke 的线程池从哪来（`max_concurrency` 可配）。

### 与 mini-agent 对照

| mini-agent（L2.3，81 行 agent.py） | create_react_agent（prebuilt 1.1.0） |
|---|---|
| `run` 的 for 循环 + 请求模型 + 入史（24 loc） | `agent` 节点 `call_model`（27 loc，含哨兵句） |
| `REGISTRY` 注册表分发 + unknown_tool 回喂 | `tools` 节点 = `ToolNode`（还白送参数校验） |
| `if not tool_calls: return`（软终止） | `should_continue` 返回 `END`（v2 有 tool_calls 时返回 Send 列表） |
| `max_turns` → `AgentBudgetExceeded`（硬终止） | `recursion_limit` + `remaining_steps` 哨兵句（双保险，都不抛） |
| 手拼 messages（system + user） | `prompt` 参数自动垫 SystemMessage |
| `ScriptedModel` 替身可换 | 任意 ChatModel 可换——mock 端点就是 ChatOpenAI 换个 base_url |
| ——（做不到） | Send 扇出：worker 内再跑 agent、外层按 claim_id 归并 |

一句话总结：**create_react_agent ≈ L2.3 整个 agent.py 的官方打包版**——循环十行、注册表、
双终止、出口组装，一件不少地映射进「模型节点 + 工具节点 + 条件边」。而 Send 扇出是
mini-agent **没有**的横向扩展能力：一张图的节点数在运行时生长，归并还有确定性保证。

## 离毕业又近的一块

毕业设计 L5.1 的执行器大概率就用 prebuilt 起步——今晚你已经把它的源码读穿，选它不再是
「听说好用」而是「知道它 414 loc 里哪些在替你干活」；毕设需求里的「多单并行审查」就是
今晚的 Send 扇出 + 自定义 reducer 直接放大；L5.2 审批外化的表单语义，在 prebuilt 的
interrupt.py 里已经预演过一遍。langgraph 三连（L3.2 图 / L3.3 暂停恢复 / L3.4 扇出与装配）
到此收口——下一课换 harness 形态的 deepagents，对照眼光继续带着。
