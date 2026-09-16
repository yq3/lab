# L3.3 langgraph ②：checkpoint 与 interrupt——暂停、杀进程、恢复

## 1. 本课目标

上一课我们手装了审查图（reviewer / tools / 条件边）；今晚给这张图装上**记忆与暂停**：
checkpointer 让状态活在 sqlite 文件里，interrupt 让图能在「等一个人」的时候停住。
完成后你能：

- 说清 **checkpointer** 是什么：每个 superstep 把整份图状态快照落盘；同一个 `thread_id`
  的多次 invoke（哪怕分属两个进程）共享一份状态——「杀进程后恢复」的全部秘密就这一个文件；
- 说清 **interrupt 的真实语义**（以源码为准，不是文档比喻）：节点里 `interrupt(payload)`
  第一次被调时**抛出** `GraphInterrupt`，被 pregel 引擎**捕获**后连同图状态一起**落盘暂停**——
  不是异常栈冒给调用方，`ainvoke` 正常返回；恢复时同一节点**从头重执行**，`interrupt()`
  不再抛，而是返回 `Command(resume=...)` 带来的人工决策；
- 跑通**真分进程实验**：`start` 进程把 CLM-2026-0003（脏数据单）打到人审门暂停后正常退出，
  `approve`/`deny` 进程打开同一个 db 文件把图救活——approve → `APPROVE/PASS`，
  deny → `REJECT/REJECT:HUMAN_DENIED`（枚举风格纪律）；非 ESCALATE 单零暂停；
- 用 Pydantic **模型继承**扩展共享 `Advice`：`ReviewOutcome(Advice)` 只加一个 `human` 字段。

这是毕业设计 L5.2「审批外化」的直接机制预习——那节课的 REST 建单 + SSE 推送，内核就是
今晚的暂停恢复。

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
| HttpSession / Spring Session 会话持久化 | checkpointer + `thread_id` | 存的不是「会话 bean」而是**图执行状态的快照**——每 superstep 一份、可回放历史，没有会话超时与 TTL |
| Flowable / Camunda 的 UserTask（wait state） | `interrupt()` + `Command(resume=)` | 暂停是「节点执行到一半抛-捕-落盘」，恢复是**重新 invoke**——没有常驻引擎在内存里等你 |
| 流程引擎的执行实例表（ACT_RU_*) | `Checkpoint`（channel_values / versions_seen） | 「下一步谁跑」不用另存一张表：由 `versions_seen` 与各节点已见版本的差分算出（`next` 的来源） |
| JVM 堆里的对象图 | sqlite 文件里的序列化状态 | 进程死了状态还活着——HITL 的全部底座；Java 人要警惕「状态在客户端」的旧直觉（L2.1 讲过 messages 无状态全量重发） |
| 子类 extends Bean 加字段 | `ReviewOutcome(Advice)` 加 `human` | Pydantic 的校验、序列化、JSON Schema 全部自动继承——共用验收不用改一行 |
| try-with-resources | `async with open_saver(db)` | L1.7 复课：连接用完自动关；aiosqlite 连接不关，**进程会挂住不退出**（AsyncSqliteSaver 文档原文警告） |

### 2.1 checkpointer：把图的状态外置

L3.2 的图有个没说破的弱点：`ClaimState` 活在 `ainvoke` 的调用栈里，进程一退全部蒸发。
`compile(checkpointer=...)` 之后的执行模型变成：

```text
每个 superstep 结束：checkpointer.put(整份状态快照 + metadata{source, step})
每次 invoke 开始  ：checkpointer.get_tuple(thread_id) —— 有旧状态就续着跑
```

三个关键认识（Step1 有 A/B 实验证据）：

- **`thread_id` 像会话 id，但生命周期语义完全不同**。Java 的 HttpSession 有超时驱逐、
  属于某个用户上下文；thread_id 只是一把取货钥匙——不过期、不属于任何人、谁拿到谁能读。
  生产上要自己补 TTL 清理与访问控制（L5.2 会踩到）。
- **记忆的形状是「消息史」**：第二段对话进来时，checkpointer 恢复的是整份 `messages`
  （合并语义 reducer 的功劳），模型收到的仍是全量历史重发（无状态协议没变，L2.1 §2.2）——
  变的是「历史存在哪」：从调用栈挪进了 db。
- **快照是全量的、带账本的**：`Checkpoint` 结构里有 `channel_values`（状态值）、
  `channel_versions`（每个键的版本号）、`versions_seen`（每个节点已见过的版本）——
  「下一步谁跑」就是拿最新版本与各节点已见版本做差分算出来的，不需要单独的调度表
  （源码结构见 `langgraph.checkpoint.base`，§6 路标）。

### 2.2 interrupt 的真实语义：抛、捕、落盘、重放

文档把 interrupt 说成「暂停等人」，源码给出的机制精确得多。今晚的人审门节点：

```python
async def human_gate(state: ClaimState) -> dict:
    advice = parse_last_advice(state)
    decision = interrupt({"claim_id": advice.claim_id, "reason": advice.reason})
    return {"messages": [...], "events": ["human_gate"], "human_decision": decision}
```

第一次执行（暂停）：`interrupt()` 在节点内部**raise GraphInterrupt**（继承 `GraphBubbleUp`
——「冒泡」目标是图引擎，不是你的调用方）。pregel 的任务执行器捕获它，**不把它当错误**：
把 `Interrupt(value=payload)` 作为一条挂起写入（channel 名就叫 `__interrupt__`）写进
checkpoint 的 writes 账本，图就此收工——`ainvoke` 正常返回暂停时刻的状态，**没有任何
异常栈**。恢复：另一个进程 `graph.ainvoke(Command(resume="approve"), config)`，引擎把
`("__resume__", "approve")` 也写进挂起写入；human_gate 任务**从头重执行**，这次
`interrupt()` 那行发现 scratchpad 里有自己的恢复值——**不再抛，直接返回它**，节点接着
往下跑。两条铁律（都写在 `interrupt()` 的 docstring 里）：

1. **恢复是重放，不是续传**：「The graph resumes from the start of the node,
   re-executing all logic」——interrupt 之前的代码会再跑一遍，所以那段必须幂等（本课
   human_gate 把解析放在 interrupt 之前，重放代价是一次纯函数解析，安全）；
2. **必须接 checkpointer**：没有 checkpointer 就没有落盘的暂停点，`Command(resume=...)`
   会直接 `RuntimeError`（引擎在恢复入口检查，源码 §6 路标）。

对照 Java：这是 Flowable UserTask 的「无引擎版」——Camunda 用一张 `ACT_RU_TASK` 表 +
常驻进程等回调；langgraph 用「抛-捕-落盘」把同一件事做成了**纯数据**：暂停点是可以用
sqlite3 命令行直接 SELECT 出来的一行 BLOB（Step4 实测）。

### 2.3 两种中断：静态点名 vs 动态触发

| | 静态：`compile(interrupt_before=["tools"])` | 动态：节点内 `interrupt(payload)` |
|---|---|---|
| 声明位置 | 编译期，按节点名一刀切 | 运行期，按执行到的逻辑触发 |
| 暂停点 | 节点**开跑之前**（边界上） | 节点**执行到一半** |
| payload | 没有（`snapshot.interrupts` 为空） | 有——随状态落盘，给操作员看 |
| 恢复 | `invoke(None, config)` | `invoke(Command(resume=值), config)`，值即 `interrupt()` 的返回值 |
| 适用 | 每个请求都要人看的固定审批位 | 按内容判断要不要人审（本课：ESCALATE 才摁停，干净单零暂停） |

本课主线用动态（它是 L5.2 的形态），Step5 用静态做对照实验。两者都要求 checkpointer。

### 2.4 输出模型：Pydantic 模型继承

四课共享的 `Advice` 是输出契约，本课要加「人审决策」字段——不改共享文件，用继承：

```python
class ReviewOutcome(Advice):
    human: Literal["approve", "deny", "skipped"]
```

Java 对照：`extends` 一个 Bean 加字段。但 Pydantic 里父类的校验、序列化、JSON Schema
自动继承——`ReviewOutcome(**advice.model_dump(), human=...)` 一行合成；共用验收脚本认
`Advice` 的地方 `ReviewOutcome` 都能顶上（子类多一字段）。一个小工程细节：checkpoint 会把
状态里的 Pydantic 对象**整只序列化**进 db，恢复时再 import 回来——跨进程读回的类型要锁死，
`open_saver` 里显式登记了 serde 白名单（对照 Java 反序列化 allowedlists：防 schema 漂移）。

### 2.5 with 语义复课（L1.7）

`AsyncSqliteSaver.from_conn_string(path)` 是 `@asynccontextmanager`，本课包成
`demo.open_saver(db)`：两个进程各自 `async with` 打开同一个文件——**这就是它们全部的
共享**。连接不关的后果在 AsyncSqliteSaver 文档里写着：进程会挂住不退出（事件循环里
还有一个 db 线程没退）。对照 try-with-resources：Python 的 `with` 是鸭子类型的
`__aenter__/__aexit__` 协议，不要求实现某个接口（L1.2 结构化类型的又一次兑现）。

## 3. 动手代码

先 `uv sync`。`code/` 里共享模块照旧（advice / mock_tools / review_rules / mock_endpoint），
本课新增：`demo.py`（图本体：L3.2 的图 + human_gate + checkpointer 接线 + ReviewOutcome）、
`demo_resume.py`（压轴分进程实验）与四个讲义脚本。图的全部增量——L3.2 的装配只多三行：

```python
builder.add_node("human_gate", human_gate)          # 人审门节点
builder.add_edge("human_gate", "reviewer")           # 人工决策作为新消息回场
return builder.compile(checkpointer=checkpointer)   # 图从此有记忆
```

### Step 1：checkpointer 给图装记忆（10 分钟，零 HTTP）

```bash
uv run python code/step1_memory.py
```

```text
== Step1 checkpointer：给图装记忆（FakeChat 直接数每次看到几条消息） ==
[A 对照：无 checkpointer，两段对话]
  第 1 段模型看到 1 条；第 2 段模型看到 1 条 <- 跑完即忘
[B 实验：compile(checkpointer=...)，两段各自新开 saver/图实例]
  第 1 段模型看到 1 条；第 2 段模型看到 3 条 <- 第一段的对话从 db 回来了
  换 thread_id 再问：模型看到 1 条 <- 会话隔离，thread_id 是边界
  快照 messages 共 4 条（两问两答）；另一 thread 自己 2 条（一问一答）
  sqlite 文件 32768 字节——图的执行状态整只躺在里面，进程死活与它无关
```

对照组 A 就是 L3.2 的图：两段对话互不相知。B 段的两个「进程」各自开 saver、各自
compile 出自己的图实例——内存里没有任何共享变量，`[1, 3]` 这条证据只能来自 db 文件。

### Step 2：暂停 → 杀进程 → 恢复（15 分钟，本课压轴）

`demo_resume.py` 的两个子命令各自是独立进程（打印 pid 自证），共享的只有
`checkpoints/demo.sqlite3` 一个文件。第一条命令：

```bash
uv run python code/demo_resume.py start CLM-2026-0003
```

```text
== 进程 1（pid 44637）：start CLM-2026-0003 ==
db: checkpoints/demo.sqlite3（目录不存在会自动创建）
  [reviewer]
  [tools]
  [reviewer]
  [__interrupt__]
模型请求: 2 次（剧本已耗尽，本进程退出后不复存在）
图暂停：next=('human_gate',)，step=3
interrupt payload: {'claim_id': 'CLM-2026-0003', 'reason': 'REJECT:INVALID_AMOUNT'}
thread_id: claim-CLM-2026-0003-234200
本进程即将退出——内存里的图、模型连接、剧本全部消失，存活的只有 db 里的 checkpoint。
恢复命令（另开终端或紧接着执行，是新进程）：
  uv run python code/demo_resume.py approve claim-CLM-2026-0003-234200
```

进程 1 正常退出——「杀进程」不需要 `kill -9`，Python 进程退干净就是等价的（内存里的
图对象、模型连接、剧本队列全部消失）。接着第二个进程（thread_id 抄上面打印的）：

```bash
uv run python code/demo_resume.py approve claim-CLM-2026-0003-234200
```

```text
== 进程 2（pid 44645）：approve claim-CLM-2026-0003-234200 ==
db: checkpoints/demo.sqlite3（与进程 1 是同一个文件，此外两进程无任何共享）
恢复前快照: next=('human_gate',)，interrupts=1 条
从 checkpoint 反推单据: CLM-2026-0003（REJECT:INVALID_AMOUNT）
模型请求: 1 次，发送 7 条消息——历史全部来自 db，剧本只供最后一轮台词
ReviewOutcome: APPROVE / PASS / 剩余 40000 分 / human=approve
events: ['reviewer', 'tools', 'reviewer', 'human_gate', 'reviewer', 'finalize']
两次 invoke 分属两个进程：状态一分不少地活过了进程死亡——这就是 HITL 的机制底座。
```

三个细节值得停下来想：

- **剧本要在恢复侧重新布置**：进程 2 的 `MockLLMEndpoint` 是全新实例，进程 1 的两份
  剧本对它不存在——它只布置「人审后收束」这一份。这就是「无状态模型 + 有状态图」的
  分界线：模型每次都是新的（7 条历史全部由引擎从 db 恢复后全量重发），图的状态却一直
  活着。把 `approve` 换成 `deny` 再跑一遍，结论变成 `REJECT / REJECT:HUMAN_DENIED`。
- **`pytest` 里的等价模拟**：测试没法真开两个进程，用「两个独立 graph 实例 + 两个
  saver 连接 + 同一个 db 文件」等价模拟（讲义明说：Step1 的 B 实验已证明这种等价——
  内存无共享，状态全在 db）。`test_demo.py` 的 resume 测试就是这么写的。
- **非 ESCALATE 单不暂停**：`start CLM-2026-0001` 会一跑到底（human=skipped），
  图里那条 `human_gate` 路径根本不会被触发。

### Step 3：approve / deny / skipped 三条路一次看全（10 分钟）

```bash
uv run python code/step3_paths.py
```

```text
== Step3 interrupt 人审门：approve / deny / skipped 三条路 ==
图: reviewer →(ESCALATE)→ human_gate --暂停--> [人工] --Command(resume)--> reviewer → finalize

[CLM-2026-0003 + approve]
  暂停: next=('human_gate',)，payload={'claim_id': 'CLM-2026-0003', 'reason': 'REJECT:INVALID_AMOUNT'}，模型请求 2 次
  恢复: Command(resume='approve')，模型再请求 1 次（带 7 条历史）
  ReviewOutcome: APPROVE / PASS / human=approve
  events: ['reviewer', 'tools', 'reviewer', 'human_gate', 'reviewer', 'finalize']

[CLM-2026-0003 + deny]
  暂停: next=('human_gate',)，payload={'claim_id': 'CLM-2026-0003', 'reason': 'REJECT:INVALID_AMOUNT'}，模型请求 2 次
  恢复: Command(resume='deny')，模型再请求 1 次（带 7 条历史）
  ReviewOutcome: REJECT / REJECT:HUMAN_DENIED / human=deny
  events: ['reviewer', 'tools', 'reviewer', 'human_gate', 'reviewer', 'finalize']

[CLM-2026-0001 + approve]
  非 ESCALATE 单不暂停（expect=APPROVE），一跑到底：
  ReviewOutcome: APPROVE / PASS / human=skipped
  events: ['reviewer', 'tools', 'reviewer', 'finalize']，模型请求 2 次（零恢复）
```

两路唯一的差异是 `Command(resume=...)` 里的一个字符串——图结构、暂停点、恢复流程
全部相同。`remaining_cents` 两路都是 40000：预算镜像是工具结果，人工否决改变的是
decision/reason，不改变账目。

### Step 4：翻开 checkpoint——暂停点长什么样（15 分钟）

```bash
uv run python code/step4_inside.py
```

```text
== Step4 翻开 checkpoint：暂停点长什么样 ==
[1] StateSnapshot（aget_state——不跑图，纯读）
  next        = ('human_gate',)   <- 恢复后第一个要执行的节点
  interrupts  = [{'claim_id': 'CLM-2026-0003', 'reason': 'REJECT:INVALID_AMOUNT'}]
  tasks       = [('human_gate', (Interrupt(value={'claim_id': 'CLM-2026-0003', 'reason': 'REJECT:INVALID_AMOUNT'}, id='b8ef6a248f314ab4d334989eed4b3e2f'),))]
  metadata    = {'source': 'loop', 'step': 3, 'parents': {}}   <- source=loop：循环里存的；step=superstep 计数
  values keys = ['events', 'messages']   <- events 已有 3 条：reviewer/tools/reviewer
  created_at  = 2026-09-15T15:42:03.499126+00:00

[2] get_state_history（新→旧迭代，这里反转为旧→新）
  step=-1 source=input next=('__start__',)
  step= 0 source=loop  next=('reviewer',)
  step= 1 source=loop  next=('tools',)
  step= 2 source=loop  next=('reviewer',)
  step= 3 source=loop  next=('human_gate',)

[3] 直接查 sqlite（两个进程之外，第三个读者）
  checkpoints 表 5 行（每个快照一行的 BLOB，含 channel_values 整只状态）
  writes 表 12 行（任务执行后的写入都落在账上；暂停的秘密在最后一行）：
    channel='messages'       type='msgpack' task=d891ceea…
    channel='branch:to:reviewer' type='null'   task=d891ceea…
    ...
    channel='__interrupt__'  type='msgpack' task=dede08de…
  <- channel='__interrupt__' 的那行就是 interrupt() 的 payload；
     恢复时 Command(resume=...) 会在这里追加 channel='__resume__' 的行（源码 _loop.py）
```

对着 §2.2 的机制各指认一遍：`next` 是 versions_seen 差分算出的待跑节点；history 每个
快照的 next 就是那一拍要跑的节点（最后那个没跑成——它在等人）；`__interrupt__` 账本行
就是「抛-捕-落盘」的落盘现场（恢复后这张表里还会多出 `__resume__` 行——讲义验证过，
ex3 的审计就建立在这套账本上）。然后跑讲义区验收：

```bash
uv run pytest code/
```

```text
...........                                                              [100%]
11 passed in 7.04s
```

11 个测试：状态 schema 与 ReviewOutcome 继承的 meta 检查、三路条件边、跨实例记忆、
暂停证据四件套（next/interrupts/metadata/请求数）、approve/deny 双路恢复、非 ESCALATE
零暂停、history 逐 superstep 断言、静态中断对照、四单统一出口。

### Step 5（可选）：静态中断对照 + 真实端点加餐

```bash
uv run python code/step5_static.py
```

```text
== Step5 静态中断：compile(interrupt_before=['tools']) 对照动态 interrupt() ==
[第一次 invoke] 停在 ('tools',) 之前（step=1）
  interrupts = []   <- 空：静态中断没有 payload
  messages 共 3 条——tools 还没跑，模型只出声过一次
[invoke(None, config)] 放行到 END：模型共请求 2 次（第一次 1 次 + 恢复后 1 次）
  ReviewOutcome: APPROVE / PASS / human=skipped
  events: ['reviewer', 'tools', 'reviewer', 'finalize']

对照：动态 interrupt() 暂停在节点执行到一半（payload 落盘），
恢复必须 Command(resume=值)——值就是 interrupt() 的返回值；静态恢复传 None 就够。
```

真实端点加餐（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：
`copy .env.example .env`）：

```bash
uv run python code/demo_resume.py --real start CLM-2026-0003
uv run python code/demo_resume.py --real approve <thread-id>
```

图一行不改：模型自己决定调什么工具、给什么建议单；脏数据单照旧在 ESCALATE 处触发
人审门（规则写在 system 提示里），审批后由真实模型收束最终结论。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_memory.py` | checkpointer 接线：compile(checkpointer=) 与 thread_id；两个「进程」等价模拟杀进程，断言第二段读到第一轮状态、跨 thread 隔离 |
| ex2 | `exercises/ex2_gate.py` | interrupt 双路：补 human_gate 的 interrupt 调用与恢复侧 Command(resume=)；断言 approve/deny 结论不同、非 ESCALATE 单零暂停 |
| ex3 | `exercises/ex3_audit.py` | 恢复后轨迹审计：从 state history 重建执行轨迹（相邻快照 next 推已跑节点、最后快照 next 是暂停点），断言序列与 events 流水互证 |

三题都是改造题（在 demo 同构结构上完成指定修改），零真实网络。验收（三条同时
全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：interrupt 找 catch 坑（把暂停当异常处理）

这是本课的命名化失败模式——Java 人看到 `interrupt()` 这个名字，直觉会全部指错方向。

- **现象**：两种典型翻车。其一：在节点外面包 `try: ... except GraphInterrupt:`，或
  写 `finally` 清理「恢复点」——永远捕不到，`ainvoke` 压根不抛。其二：以为图暂停后
  进程还挂在内存里等（像 `Object.wait()` / `CountDownLatch.await()`），于是「恢复」
  写成「让原线程继续」——但原进程早就退出了，你手里只有一个 sqlite 文件。
- **最小复现**（讲义 Step2 的输出就是证据）：`start` 进程打完整条日志后**正常退出**，
  没有 traceback，`ainvoke` 正常返回了暂停时刻的状态 dict。人审信息不在异常里，在
  返回值之外的地方——`snapshot.next` 与 `snapshot.interrupts`。对比例子：

  ```python
  decision = interrupt({"claim_id": ..., "reason": ...})  # 抛 GraphInterrupt（引擎内部）
  return {"human_decision": decision, ...}                # 第一次执行永远走不到这里
  ```

- **Java 直觉为何失效**：Java 的 interrupt 是**控制流跳转**——`Thread.interrupt()` 设
  标志、`InterruptedException` 可捕获、catch 块就是处理点。langgraph 的 interrupt 是
  **「图暂停 + 状态序列化 + 正常返回」**：`GraphInterrupt` 继承 `GraphBubbleUp`，源码
  docstring 写明 "Never raised directly, or surfaced to the user"——它在 pregel 的任务
  执行器里被捕获、转成 `__interrupt__` 挂起写入落盘，从不冒到你的调用栈。恢复也不是
  栈展开（unwinding 的逆过程不存在）：是**新进程重新 invoke + Command(resume=)**，
  值经 scratchpad 回到 `interrupt()` 的返回值——同一节点从头重执行。
- **修复与纪律**：① 把 `interrupt()` 当「带外返回值」而不是异常——它下面的代码是
  「恢复重放路径」，必须幂等（重放会再执行一遍）；② 暂停信息用 `aget_state` 读
  （next / interrupts），不要等异常或轮询进程内存；③ 恢复入口统一
  `invoke(Command(resume=...), config)`，config 带同一个 thread_id——thread_id 丢了，
  暂停点就成了 db 里永远无人认领的一行；④ 审计从「看日志栈」改成「看账本」：
  `get_state_history` + writes 表就是这条执行线的全部事实（ex3 练的就是这个）。

## 6. 延伸

- 官方文档：Human-in-the-loop 概念页（interrupt / Command / 恢复语义）与 Persistence
  概念页（checkpointer / thread_id / state history）——
  https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop ，
  https://docs.langchain.com/oss/python/langgraph/persistence 。
- 源码路标（本地克隆 `~/develop/opensource/langgraph`，按图索骥）：
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/types.py` ——
    `interrupt()` 本体：第一次调用 raise `GraphInterrupt`；恢复时从 scratchpad 取值
    返回；docstring 白纸黑字写着 "resumes from the start of the node, re-executing
    all logic" 与 "you must enable a checkpointer"。`Command(resume=...)` 与
    `StateSnapshot`（next/tasks/interrupts 字段）也在这里；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/errors.py` ——
    `GraphInterrupt(GraphBubbleUp)`：docstring「抑制于根图、不直接抛给用户」——
    §5 坑位的源码证据；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/_runner.py` ——
    任务执行器的 `commit()`：捕获 GraphInterrupt 后写入 `(INTERRUPT, interrupts)`
    挂起写入——「暂停点落盘」的现场；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/_loop.py` ——
    恢复入口：`Command(resume=...)` 被映射成 `(RESUME, 值)` 挂起写入并 `put_writes`；
    没有 checkpointer 时的 RuntimeError 也在这个分支；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/_algo.py` ——
    `_scratchpad()`：恢复值从 pending writes 进入 `scratchpad.resume`，节点重执行时
    `interrupt()` 按出现顺序（index）匹配取值；
  - `langchain-ai/langgraph@e539ac122#libs/checkpoint/langgraph/checkpoint/base/__init__.py` ——
    `BaseCheckpointSaver` 接口（put / get_tuple / list / put_writes）与 `Checkpoint`
    结构：`channel_values / channel_versions / versions_seen`——`next` 的来源；
  - `langchain-ai/langgraph@e539ac122#libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py` ——
    `SqliteSaver`（同步版；`from_conn_string` 是 `@contextmanager`；异步方法显式
    `NotImplementedError`——本课用 aio 版的原因）；
  - `langchain-ai/langgraph@e539ac122#libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py` ——
    `AsyncSqliteSaver`（`@asynccontextmanager`；「连接不关进程挂住」的警告原文）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/graph/state.py` ——
    `compile(checkpointer=..., interrupt_before=..., interrupt_after=...)`：静态中断
    与 checkpointer 的装配参数（Step5 的出处）；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py` ——
    `get_state` / `get_state_history`：快照与历史的读取入口（Step4 / ex3 的地基）。

### 与 mini-agent 对照

mini-agent（L2.3）的循环没有任何暂停/恢复能力——一轮到底，`messages` 是局部变量，
进程退出即蒸发。checkpointer + interrupt 是框架补上的整层，拆成三件：

| 能力 | mini-agent（L2.3） | langgraph（今晚） |
|---|---|---|
| 状态快照 | 无——历史在调用栈的局部变量里，跑完即丢 | `checkpointer.put`：每 superstep 落盘一份 `Checkpoint`，thread_id 隔离多条执行线 |
| 恢复入口 | 无——想续只能整个重跑 | `invoke(任意输入, config 带 thread_id)`：新进程从 db 取快照续跑（恢复传 `Command(resume=)`） |
| 人工决策注入 | 无——人工只能开新一轮对话 | `Command(resume=值)` → scratchpad → `interrupt()` 的返回值，直达节点内部 |

一句话总结：mini-agent 的 `while` 循环里没有「等一个人」这个动词——今晚这层装上之后，
「跑一步、停下来等人、再继续」从产品话术变成了三个可对源码指认的机制件。

## 离毕业又近的一块

毕业设计 L5.2「审批外化」的机制内核就是今晚这一套：执行器跑到达标节点 → `interrupt()`
建审批单（payload 就是单据内容）→ 图暂停、状态入库（REST 建单）→ 审批回调 → 新进程
`Command(resume=)` 恢复（SSE 推送结论）。你会遇到的生产问题今晚都预演过了：恢复侧模型
是全新实例（剧本要重布）、thread_id 是唯一凭证（丢了暂停点就无人认领）、审计要靠账本
不靠栈（ex3）。下一课 L3.4 收 langgraph 三连的尾：`Send` 动态扇出与 prebuilt 源码导读。
