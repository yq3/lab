# L5.2 毕业设计②：审批外化——REST 建单、SSE 推送与三元回复

> 昨晚 L5.1 打好地基：静态拓扑、`plan_gate` 计划门、`topology_signature` 形状签名——结尾
> 留了一个明确承诺：`submit` 还是桩，「送审」那一步的芯待换（暂停等人、恢复续跑）。今晚
> 兑现这个承诺，把审批装成产品面。注意本课不是在 L5.1 上线性叠加，而是它的**并行分支
> 之一**——与 L5.3（审计面）各长各的，L5.4 才汇合。

## 1. 本课目标

L3.3 那晚你在命令行里手动 `Command(resume="approve")` 救活一张暂停的图；今晚这套机制
**变成产品面**：图照旧在 submit 处 `interrupt()` 暂停，但等人的不再是你手敲的恢复命令，
而是一个正经的审批 API 组（蓝本 [../../../../research/agent-oss/report.md](../../../../research/agent-oss/report.md)
§2.1 A1/A2/A6，产品先例 opencode——开源编码 agent（TS），「server 即产品、TUI 只是
client」的 service 化形态即出自它）。完成后你能：

- 把 L5.1 的 submit 桩**换芯**成真审批：`interrupt(payload)` 建「审批单」，payload 含
  run_id / claim_id / dept / total_cents / 建议单摘要 / **content_hash**（A6 内容绑定：
  重生成的新建议单 hash 变，批的是新一单，不是单据号）；
- 跑通**拒绝回环**：reject 的留言作为新消息回喂 drafter 重生成（A1「reject 的 message
  回喂模型做纠错」+ A24 human 节点回环），`MAX_APPROVAL_LOOPS=2` 封顶、超限走 ESCALATE
  双哨兵（A24 max 思想）；
- 用 FastAPI 装出审批外化的最小 API 面：`POST /runs`（asyncio 后台跑到暂停）、
  `GET /approvals`（跨会话待审总表）、`POST /approvals/{id}/reply`（**once / always /
  reject 三元回复**）、`GET /approvals/stream`（SSE：新订阅者先重放历史再实时，
  Last-Event-ID 断线续传——A2「审批是可重放事件」：无人在线不丢单不隐式作答）；
- 让 **always** 长出「批准并记住」的完整闭环：规则入库（谁/何时/pattern/内容 hash 四问
  可审计，A6），新单进门先查规则，命中即自动批准（`approval.auto_applied`，零人审）。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红——13 红 1 绿：
`test_content_hash_binds_content` 考的是 given 函数，发货即绿）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| Spring MVC + `SseEmitter` | FastAPI `StreamingResponse`（SSE） | 推流的载体从「emitter 对象挂请求」变成**异步生成器 yield 帧**——连接的生命周期就是生成器的生命周期 |
| `DeferredResult` / `CompletableFuture` 挂起请求线程 | `interrupt()` + checkpoint 挂起 | **根本差异：不是线程等待，是状态落盘 + 新 invoke**——没有线程在等你，db 里有行 checkpoint（L3.3 §2.2 语义复引） |
| 审批工作台（独立 Web 控制台连业务系统） | 独立 client 连审批 API | opencode 就是产品先例：server 即产品、审批完全外化，「审批人」与「执行机」物理分离（A1） |
| 规则引擎白名单 / 授权表 | always 规则（`RuleBook`） | **可审计规则修订**：谁/何时/pattern/内容 hash 四问有账（A6）——反面是「内存 yes 集合」：批过就 true，什么都答不出来 |
| 消息队列按 offset 回溯消费（Kafka seek） | SSE `Last-Event-ID` 重放 | 断线重连从最后一条 id 之后续传；事件表 append-only 是真相之源，订阅只是视图（A2） |
| Spring `@Autowired` 构造注入 | FastAPI `Depends(get_service)` | 没有容器魔法：**每请求显式传一个函数**取依赖，看得见摸得着，也无隐式扫描 |
| `CountDownLatch.await()/countDown()` | `asyncio.Event` 的 `wait()/set()` | 等待不占线程——挂起点让出的是事件循环；一次 set 全醒 |
| `BlockingQueue.put/take` | `asyncio.Queue` | 同构不同层：阻塞队列睡线程，asyncio 队列挂协程（广播、背压都靠它） |

### 2.1 挂起：今晚的主角有两种，别混

「等一个人」在今晚出现两次，机制完全不同（Step1 零 API 实验逐个拆开）：

- **内存挂起**（asyncio 层）：`POST /runs` 里 `asyncio.create_task` 跑图，跑到
  `interrupt()` 正常返回（L3.3：抛-捕-落盘，`ainvoke` 不抛异常）——HTTP handler 立刻
  回 `{"run_id": ...}`。这里「挂起」的是**任务**：等待期间不占线程，循环照跑别的请求
  （对照 `DeferredResult`：容器把请求线程还回池子——但线程模型完全不同）；
- **落盘挂起**（checkpoint 层）：图的状态连同 interrupt payload 落进 sqlite，**进程死了
  暂停点还在**；恢复是新一段 invoke（`Command(resume=...)`），不是「唤醒原线程」。
  审批等待可以横跨进程重启——这是 DeferredResult 给不了的（它逾期即作废）。

### 2.2 审批单：interrupt payload 的产品化

L3.3 的人审门 payload 只有两个字段；今晚的审批单（`graph.submit` 组装）长成一张工单：

```python
payload = {
    "run_id": config["configurable"]["thread_id"],   # thread_id 即 run_id：归属凭证
    "claim_id": advice.claim_id, "dept": view["dept"], "total_cents": ...,
    "advice": {"decision": ..., "reason": ..., "remaining_cents": ...},
    "content_hash": content_hash(advice, total_cents),  # A6：被审内容指纹
}
decision = interrupt(payload)
```

三个设计点：**run_id 从 config 读**——thread_id 是 L3.3 说的「取货凭证」，丢了暂停点就
无人认领，本课把它产品化为 REST 建单的关联键；**dept/total_cents 进 payload**——它们是
always 规则的匹配维度；**content_hash**——建议单 + 总额的规范序列化 sha256，内容一变
指纹变（第二幕实测：`9a29… != fa80…`），「批的是哪一版」由它锁定，不是靠单据号。

### 2.3 三元回复与拒绝回环（A1 + A24）

| reply | 服务侧做什么 | 图侧发生什么 |
|---|---|---|
| `once` | 登记 `approval.replied` → `Command(resume={"action": "approve"})` | submit 收口 `sent=True` → END |
| `always` | 规则命中查询（去重）→ 未命中入库 → 同 once 恢复 | 同上；规则留给后面的单 |
| `reject`（可带 message） | 留言缺省给默认反馈 → `Command(resume={"action": "reject", "message": ...})` | submit 把留言作为 user 消息回喂 → 条件边送回 **drafter 重生成** → 新建议单再到 submit → **新审批单（新 hash）** |

拒绝回环是今晚唯一改图形状的地方：`submit --(reject)--> drafter` 回边 + `route_after_submit`
三分支（approve→END / reject 未超限→drafter / 超限→escalate）。封顶 `MAX_APPROVAL_LOOPS=2`：
第 3 次驳回时回环已用满 → escalate 哨兵以 `REJECT:APPROVAL_LOOPS_EXCEEDED` 收口（与重规划
烧满的 `REJECT:PLAN_REPLANS_EXCEEDED` 是两个码——审计看码就知道烧在哪条环，A24 max 思想）。

对照 Java：这就是 DataAgent 的 human 节点回环（interruptBefore + checkpoint.nextNodeId +
updateState(反馈) + resume，A24）——反馈走**状态与消息**，不是走异常。

### 2.4 事件表与 SSE：审批是可重放事件（A2）

`approvals.EventLog` 是 append-only 内存表（list + id 自增，L5.3 升级 SQLite 事件溯源），
四类事件五种名字：`run.started` / `approval.requested` / `approval.replied` /
`approval.auto_applied` / `run.completed`。两条纪律：

- **无人订阅不丢单**：`append` 先记表（真相之源），订阅者只是视图——广播队列是空的
  也不影响事实发生；单同时挂在 pending 表里，`GET /approvals` 随时可查。绝不因为
  「没人看」而隐式作答（A2）；
- **重订阅即重放**：`subscribe(last_id)` 先 yield `id > last_id` 的历史再接实时——
  重放快照与订阅注册**之间没有 await**，新事件只可能走广播队列，不重不漏。
  HTTP 侧即 SSE：每帧 `id:` 行 + `event:` 行 + `data:` 行 + 空行；重连带
  `Last-Event-ID` 头就从断点续传（压轴实测：全量 17 条 vs 断点后 14 条）。

### 2.5 新 Python 件与 Java 类比（三条）

- **`Depends`** ≈ 显式版 `@Autowired`：`service: ApprovalService = Depends(get_service)`
  声明在端点形参上，FastAPI 每请求调一次 `get_service`——没有容器扫描、没有 bean 生命周期，
  依赖从哪来一行看穿（本题用它从 `app.state` 取服务）；
- **`asyncio.Event` / `asyncio.Queue`** ≈ `CountDownLatch` / `BlockingQueue`：形态同构，
  机制不同——`await gate.wait()` 是**挂起点**（零 CPU 让出循环），不是线程睡眠；
  `Queue.put_nowait` 是广播投递的原子动作（ex2 练的就是这个）；
- **`StreamingResponse` + 异步生成器** ≈ `SseEmitter.send`：Java 侧你拿着 emitter 对象
  往里 send；Python 侧你 yield 帧、框架负责推——**生成器不结束，连接就不断**（这也是
  内存直连测试读不到常开流的原因：ASGITransport 会等 app 跑完——§3 Step4 的实测坑）。

## 3. 动手代码

先 `uv sync`。`code/` 对版共享件照旧（advice / mock_tools / review_rules / mock_endpoint
与 L5.1 字节相同；plan / executor 原样复制；demo / prompts / graph 的合理差异在各自
docstring 里声明）。本课新模块：`graph.py`（submit 换芯 + 拒绝回环）、`approvals.py`
（审批域服务：待审表 / 事件表 / 规则簿）、`api.py`（HTTP 面）、`step1_suspend.py`（挂起
实验）、`demo_flow.py`（三幕 demo）。

```bash
uv sync
```

### Step 1：挂起的两种形态——内存门闩 vs 落盘暂停（10 分钟，零 API 零模型）

```bash
uv run python code/step1_suspend.py
```

```text
== Step1 挂起的两种形态：内存门闩 vs 落盘暂停（零 API） ==
[1] asyncio.Event：两个等待者并发挂起，一次 set 全醒（对照 CountDownLatch）
  两个等待者 × 0.2s 门闩 → 总耗时 0.202s
  轨迹: ['waiter-A 挂起', 'waiter-B 挂起', 'waiter-A 醒来', 'waiter-B 醒来']
  <- 串行等待应 ≈ 2× 门闩时长；实测 ≈ 1×：等待是并发的，set 一次全醒
[2] 挂起不占线程：等待者挂住的同时，同一个循环还在跑别的任务
  总耗时 0.201s
  轨迹: ['waiter-C 挂起', 'loop alive: tick 1', 'loop alive: tick 2', 'loop alive: tick 3', 'waiter-C 醒来']
  <- waiter-C 挂着不动的那 0.2s 里，heartbeat 打了 3 个点：等待者让出的是循环，不是线程
[3] 反例：threading.Event.wait() 在 async 里冒充挂起——冻结整个循环
  总耗时 0.310s（正确写法应 ≈ 0.15s）
  轨迹: ['waiter-D 阻塞 wait(0.15)', 'waiter-D 返回', 'loop alive: tick 1', 'loop alive: tick 2', 'loop alive: tick 3']
  <- 阻塞 wait 期间一个心跳点都没有：循环被冻住了——§5 陷阱的内核
[4] 对照表：内存门闩 vs interrupt+checkpoint（本课审批的内核）
  挂起时占什么     | 内存门闩：一个等待点（await）
             | 落盘暂停：一个 checkpoint 行（db 落盘）
  谁来唤醒       | 内存门闩：set() 的任务（同进程）
             | 落盘暂停：Command(resume=)（任意进程，取货凭证 thread_id）
  进程死了怎样     | 内存门闩：等待点蒸发，没有然后
             | 落盘暂停：暂停点还在 db 里，新进程接着跑
  Java 最近似物  | 内存门闩：CountDownLatch / CompletableFuture
             | 落盘暂停：DeferredResult 逾期作废 vs 状态可恢复
  <- L3.3 的结论今晚产品化：审批等待的不是线程，是 db 里那行 checkpoint
```

[1][2] 是 §2.1 的内存挂起（并发证据 + 循环活性证据）；[3] 是 §5 陷阱的预告；[4] 的对照
表就是本课架构决策：审批的「等」选了右边那列。

### Step 2：读三个模块——换芯的图、审批服务、HTTP 皮（20 分钟）

- `graph.py`：对照 L5.1 版找差异——`submit` 从桩变成 `interrupt(payload)` + 三态返回
  （approve 收口 / reject 回喂留言），新增 `route_after_submit` 三分支与 `approval_rejects`
  合并语义账本；`open_saver` / `run_config` 是 L3.3 接线的产品化（serde 白名单换成 L5.2
  的状态类型）。**拓扑只多一条条件边**——静态图的「换芯不换壳」；
- `approvals.py`：域逻辑全在这（不 import fastapi）——`_invoke` 每段起一个专属
  MockLLMEndpoint、消费后扣减剧本（L3.3「恢复侧剧本重布」的纪律）；`_register_ticket`
  先查规则命中（自动批准半边）再广播 `approval.requested`；`reply` 三元路由；
  `EventLog` 与 `RuleBook` 是 ex2/ex3 的同构蓝本；
- `api.py`：只有「HTTP 翻译」——Pydantic 请求体、404/400 语义、`_sse_frame` 的帧格式、
  `Depends` 取服务。`mode=replay` 查询参数给轮询客户端一个「只重放即关」的拉取面。

### Step 3：三幕 demo——once / reject 回环 / always 自动批准（15 分钟，本课压轴）

```bash
uv run python code/demo_flow.py
```

```text
== 第一幕 once：建单 → 批准本单 → 完成 ==
  [POST /runs 0004 → run-0001] 待审单 tkt-0001 已登记
    总表行: dept=DEV  total=5000分  advice={'decision': 'REJECT', 'reason': 'REJECT:INVOICE_INVALID', 'remaining_cents': 40000}
    graph_next=['submit']（单挂在 submit——无人订阅也不丢，单在 pending 表里）
  [POST /approvals/{ticket}/reply {"decision": "once"}] 事件流时序：
    run.started            {}
    approval.requested     {'ticket_id': 'tkt-0001', 'dept': 'DEV', 'total_cents': 5000, 'advice': {'decision': 'REJECT', 'reason': 'REJECT:INVOICE_INVALID', 'remaining_cents': 40000}, 'content_hash': '38233543f505989b'}
    approval.replied       {'ticket_id': 'tkt-0001', 'decision': 'once', 'rule_id': None}
    run.completed          {'decision': 'REJECT', 'reason': 'REJECT:INVOICE_INVALID', 'sent': True}
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.approved']
    收口: REJECT / REJECT:INVOICE_INVALID / sent=True

== 第二幕 reject：驳回+留言 → 回环重生成 → 新单（hash 变）→ 再批准 ==
  [POST /runs 0001 → run-0002] 首版建议单 tkt-0002（content_hash=9a2914bfde8ce4a8）
  [reply reject+留言] 图回 drafter 重生成 → 新单 tkt-0003
    （content_hash=fa80fac7933b8af8）
    hash 变了：9a2914bfde8ce4a8 != fa80fac7933b8af8 ——批的是新一版内容，不是单据号（A6）
  [reply once] 事件流时序：
    run.started            {}
    approval.requested     {'ticket_id': 'tkt-0002', 'dept': 'SALES', 'total_cents': 7100, 'advice': {'decision': 'APPROVE', 'reason': 'PASS', 'remaining_cents': 10000}, 'content_hash': '9a2914bfde8ce4a8'}
    approval.replied       {'ticket_id': 'tkt-0002', 'decision': 'reject', 'message': '客户拜访餐费需补充三级审批单，补齐前先转人工复核'}
    approval.requested     {'ticket_id': 'tkt-0003', 'dept': 'SALES', 'total_cents': 7100, 'advice': {'decision': 'ESCALATE', 'reason': 'REJECT:APPROVAL_FEEDBACK', 'remaining_cents': 10000}, 'content_hash': 'fa80fac7933b8af8'}
    approval.replied       {'ticket_id': 'tkt-0003', 'decision': 'once', 'rule_id': None}
    run.completed          {'decision': 'ESCALATE', 'reason': 'REJECT:APPROVAL_FEEDBACK', 'sent': True}
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.rejected', 'drafter', 'submit.approved']
    收口: ESCALATE / REJECT:APPROVAL_FEEDBACK / sent=True

== 第三幕 always：批准并记住 → 同部门小额单零人审自动过 ==
  [reply always] 规则已存：rule-001 = dept SALES 且总额 ≤ 8800 分
    审计四问：谁 审批人-老王 / 何时 2026-09-16T04:20:17+00:00
    pattern (SALES≤8800) / 绑定 a9e4e2488eb10c99
  [POST /runs 0001 → run-0004] 零人审——事件流时序：
    run.started            {}
    approval.auto_applied  {'ticket_id': 'tkt-0005', 'rule_id': 'rule-001', 'content_hash': '9a2914bfde8ce4a8'}
    run.completed          {'decision': 'APPROVE', 'reason': 'PASS', 'sent': True}
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.approved']
    收口: APPROVE / PASS / sent=True

== 压轴 A2：审批是可重放事件——断线重连的工作台 ==
  [不带 Last-Event-ID 重订阅] 全量重放 17 条（先发生的事件一条不丢）：
    ['run.started', 'approval.requested', 'approval.replied', 'run.completed', 'run.started', 'approval.requested', 'approval.replied', 'approval.requested', 'approval.replied', 'run.completed', 'run.started', 'approval.requested', 'approval.replied', 'run.completed', 'run.started', 'approval.auto_applied', 'run.completed']
  [带 Last-Event-ID: 3] 只重放其后 14 条：['run.completed', 'run.started', 'approval.requested', 'approval.replied', 'approval.requested', 'approval.replied', 'run.completed', 'run.started', 'approval.requested', 'approval.replied', 'run.completed', 'run.started', 'approval.auto_applied', 'run.completed']
    <- 断线期间不丢单也不隐式作答：重订阅即重放（无人在线时单都在 pending 表里）

checkpoint 库（图状态活过每一段 invoke）: /var/folders/9k/4ts9r9n92737zx0fjkqtrnym0000gn/T/tmp0wwg0qww/approval.sqlite3
```

五个证据值得停下来看：

- **第一幕的事件流时序**：`run.started → approval.requested → approval.replied →
  run.completed`——REST 动作（POST /runs、POST reply）与 SSE 事件一一对应，`graph_next`
  说明单挂在 submit 节点上等；
- **第二幕的 hash 变化**：同一 run、同一单据，重生成后 `content_hash` 从 `9a29…` 变
  `fa80…`——审批单 tkt-0003 是**新一单**；图内审计流水里 `submit.rejected → drafter`
  的回环清晰可见（drafter 出现两次）；
- **第三幕的审计四问**：规则记录能回答谁批的、何时、批了什么 pattern、绑哪版内容——
  对照「内存 yes 集合」反例（A6）；第二张同部门小额单（SALES 7100 ≤ 8800）零人审：
  事件流里**没有** approval.requested，只有 `approval.auto_applied`；
- **压轴的重放**：断线重连的工作台不带 Last-Event-ID 能看到全部 17 条历史（先发生的
  一条不丢）；带 `Last-Event-ID: 3` 只重放其后 14 条——这就是 A2；
- **全剧本零 key**：三幕全部走 MockLLMEndpoint 剧本（`demo.offline_run_scripts`），
  离线确定性——事件序列、hash、审计流水每次跑完全一致（hash 是确定性的 sha256）。

### Step 4：讲义区验收 + 一个实测坑（10 分钟）

```bash
uv run pytest code/
```

```text
..................                                                          [100%]
18 passed in 19.55s
```

18 个讲义区测试 = 图侧 6（payload 形态含 run_id/content_hash、approve 恢复零模型调用、
reject 回环回喂+新 hash、无留言默认反馈、回环封顶双哨兵、reducer 注解 meta）+ API 侧
10（建单与待审总表、once/reject/always 三路、HTTP 封顶、404/400、SSE 重放与
Last-Event-ID 截断、帧格式、live 生成器顺序）+ demo 侧 2（剧本形态、三幕服务面集成）。

那个实测坑：测试里 SSE 断言走 `?mode=replay` 而不是默认的 live 流——httpx 的
`ASGITransport` 会**等整个 ASGI app 跑完**才把响应交出来，常开的 live 流（生成器不结束）
在它那里永远读不到（一读就挂起）。`mode=replay` 是「重放完即关流」的拉取面（轮询型
客户端的正当形态），live 推送的顺序断言则直接测事件生成器（`test_api.py` 最后一个
测试）——两条路各测各的，都是真断言。

### Step 5（可选，加餐）：起真服务，用 curl 当工作台

```bash
uv run uvicorn api:app --app-dir code --port 8000
```

（macOS / Windows / Linux 命令一致；`--port` 可换。ctrl+c 停。）另开一个终端，先挂上
SSE（`-N` 关闭 curl 缓冲，才能看到实时推送）：

```bash
curl -N http://127.0.0.1:8000/approvals/stream
```

再开第三个终端建单与回复（SSE 那个窗口会实时蹦出事件）：

```bash
curl -s -X POST http://127.0.0.1:8000/runs -H "Content-Type: application/json" -d "{\"claim_id\": \"CLM-2026-0001\"}"
```

（Windows PowerShell 5.1 注意：`curl` 是 `Invoke-WebRequest` 的别名，`-N`/`-d` 语法不通——
用 `curl.exe -N ...` 强制走真 curl，或换 `Invoke-RestMethod`；以下 curl 命令同。）

```bash
curl -s http://127.0.0.1:8000/approvals
```

```bash
curl -s -X POST http://127.0.0.1:8000/approvals/tkt-0001/reply -H "Content-Type: application/json" -d "{\"decision\": \"once\"}"
```

模型仍走离线剧本（审批面的加餐验的是 HTTP/SSE 传输形态，不是模型质量）；断线重连试法：
Ctrl+C 掉 curl 再重连，加头 `-H "Last-Event-ID: 3"` 看续传。跑完删掉自动生成的
`checkpoints/` 目录即可。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_ticket.py` | 审批登记与三元回复核心：reply 的三分支路由 + 恢复指令构造 + 规则命中查询；验收含 once 收口、reject 留言回喂与回环取证（drafts 轮数 / next 断言）、默认反馈、always 去重、非法单 404 |
| ex2 | `exercises/ex2_replay.py` | SSE 事件流与断线重放：EventLog 的广播（非阻塞投递）与订阅（重放 + 无缝接实时 + 断开注销）；验收含新订阅者全量重放、Last-Event-ID 截断、双订阅者同序 |
| ex3 | `exercises/ex3_always.py` | always 规则修订：匹配器两维判定 + 自动批准接入 + 可审计规则记录（谁/何时/pattern/内容 hash）；验收含逐维断言、auto_applied 事件、超 cap/异部门留人工、内容变 hash 变 |

三题都是同构填空（ex1 在讲义 ApprovalService 的迷你版上补 reply；ex2/ex3 补事件表与
规则簿的核心函数），零真实网络。验收命令同 §1 的完成判据（三条同时全绿 = 本课毕业）。

## 5. Java 直觉陷阱：事件循环里睡死

这是本课的命名化失败模式——Java 人把「挂起」的直觉带进 asyncio，一不留神把整个服务
冻住。

- **现象**：一个 async 端点里调了同步阻塞函数（`time.sleep`、同步 IO 客户端、CPU 密集
  循环）——不只是这个请求慢，**全部并发请求排队**，SSE 全场冻结：挂着的事件流一条都
  推不出去，新请求进不来，健康检查超时。
- **最小复现**（两个并发请求 × 0.5s 等待，实测数字）：

  ```python
  @app.get("/block")
  async def block():
      time.sleep(0.5)          # 阻塞：冻住整个事件循环
      return {"ok": True}

  @app.get("/yield")
  async def yield_():
      await asyncio.sleep(0.5) # 让出：别的请求趁等待间隙跑
      return {"ok": True}
  ```

  两个并发请求打 `/block`：总耗时 **1.02s**（串行！）；打 `/yield`：**0.50s**（并发）。
  同样是「等 0.5 秒」，差的那 0.5s 就是别人的请求在队列里干等的时间。
- **Java 直觉为何失效**：Spring MVC 的线程模型里 `Thread.sleep` 只睡当前请求线程，
  线程池还有几百个兄弟接着干活——「阻塞一个无关大局」是真实直觉。asyncio 是**单循环
  协作式**：全服务共用一个事件循环线程，「阻塞」没有局部性——一个不 yield，全场等。
  你在 Java 里买的「线程池兜底」，这边不存在。
- **修复与纪律**：① async 路径一律 `await asyncio.sleep(...)`——图的所有 IO 走
  `ainvoke`/`astream`（langgraph 的异步面天生合规）；② 真有同步重活（pandas、同步 SDK），
  丢线程池：`await asyncio.to_thread(func, ...)`（或 `anyio.to_thread`、执行器的
  `run_in_executor`——FastAPI 的 `def` 端点就是这么被自动丢线程池的）；③ 验收钉死它：
  Step1 [3] 的心跳实验就是最小探测器——阻塞期间 heartbeat 一个点都打不出来。

## 6. 延伸

- 官方文档：FastAPI Custom Response（搜 `StreamingResponse` 一节：异步生成器流式响应
  与取消语义）—— https://fastapi.tiangolo.com/advanced/custom-response/ ；
  MDN Server-Sent Events 指南（`event:`/`id:`/`data:` 帧格式与 `Last-Event-ID` 协议
  语义）—— https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events 。
- 源码路标（本地克隆 `~/develop/opensource/langgraph`，按图索骥）：
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/types.py` ——
    `interrupt()` / `Command(resume=...)` / `StateSnapshot`：L3.3 已锚、今晚的产品化内核
    ——「恢复是节点从头重执行、interrupt 返回 resume 值」的 docstring 原文仍在这里；
  - `langchain-ai/langgraph@e539ac122#libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py` ——
    `AsyncSqliteSaver`（L3.3 复引）：`open_saver` 的接线出处；「连接不关进程挂住」的
    警告原文——api.py 的 lifespan 就是照它写的；
  - `sst/opencode@95daf90670#packages/protocol/src/groups/permission.ts` ——
    审批外化 API 组的产品原型（opencode 的 permission 端点协议）：POST 建请求 /
    GET 待审总表 / reply / saved 授权 CRUD，配 SSE 事件推送——本课四个端点的语义
    蓝本（A1 出处，Effect HttpApi 自动进 OpenAPI）。
- 研究蓝本（lab 仓内，写作输入）：审批外化 API 组与三条纪律的出处
  [../../../../research/agent-oss/report.md](../../../../research/agent-oss/report.md)
  §2.1 表 A1（reply 三元 + reject 回喂纠错）/ A2（审批是可重放事件）/ A6（批准并记住
  =可审计规则修订 + 内容 hash 绑定）；端点语义细读见
  [../../../../research/agent-oss/profiles/opencode.md](../../../../research/agent-oss/profiles/opencode.md) §5.3。

## 离毕业又近的一块

审批面就位：图会停（interrupt 审批单）、人会答（三元回复 + 拒绝回环）、账会记（事件表
+ 可审计规则）。但今晚的「断线重放不丢单」还是**进程内承诺**——事件表是内存 list，
服务一重启全蒸发。下一课 L5.3 把它升级成 SQLite 事件溯源：事件表 append-only 落盘、
缓存即审计（每个 LLM 决策的 prompt/response 按内容寻址留痕）、图版本签名绑定执行态
（L5.1 的 `topology_signature` 在这里归位）——「不丢单」从进程内承诺变成跨重启承诺。
