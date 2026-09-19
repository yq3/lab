# L1.9 asyncio ②：并发原语与异步生成器

> 昨晚你建立了事件循环 / 协程 / 让出点三个模型，写出第一个 async 主流程，诊断了「假 await」与
> 「阻塞全场」两类事故——`gather` 还只是实验里的对照组。今晚给它配上工程化的全套护栏：`gather`
> 保序、`wait_for` 预算、`Semaphore` 限流、取消这场「协作式异常」怎么接；最后写异步生成器把 token
> 一段段吐出来——L2.1 手撕 SSE（Server-Sent Events，HTTP 服务器推送流——Spring 的 SseEmitter）流时你会认出它。

## 1. 本课目标

把昨晚的「两张单据同时在飞」升级成工程化的并发控制，并集齐**学段里程碑的全部零件**。完成后你能：

- 用 `create_task` / `gather` 组织多端点并发拉取（保序收集）；
- 用 `wait_for` 给慢端点套预算、超时降级；理解取消是**协作式异常**（`CancelledError`），以及它为何是
  `BaseException` 的子类——挂在 `Exception` 家族树之外，`except Exception` 接不住它（L1.7 家族树的补全）；
- 用 `Semaphore` 做并发上限限流（对照 `java.util.concurrent.Semaphore`，几乎零成本迁移）；
- 写异步生成器（`async def` + `yield`，`async for` 消费）——这是 L2.1 手撕 SSE 流式解析的直接前置，
  也是所有框架 `astream_events` 类 API 的机制本体。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

### 2.1 `create_task` vs 直接 `await`：提交调度 vs 就地等待

| 写法 | 语义 | 时刻 |
|---|---|---|
| `result = await fetch(region)` | 就地等待：现在开始跑它，做完我才继续 | 「现在开始」 |
| `task = asyncio.create_task(fetch(region))` | 提交调度：协程**立刻进入事件循环排期**，返回 Task；稍后再 `await task` 取结果 | 「已在跑」 |

对照 Java：`create_task` ≈ `executor.submit(callable)` 返回 `Future`——先提交、后 join。但有一个 Java 没有
的陷阱：**Task 对象必须由你持有引用**（事件循环只持弱引用，官方文档明文警告）——细节见陷阱，此处先立规矩。

### 2.2 `gather`：等待一个集合

```python
results = await asyncio.gather(fetch("north"), fetch("south"), fetch("east"))
```

三个契约，每个都值得记：

1. **并发**：所有协程同时进入调度（总耗时 ≈ 最慢者，Step 2）；
2. **保序**：返回列表严格按传入顺序——谁先完成与谁排第几无关；
3. **异常默认立即传播**：任何一个炸了，`await gather(...)` 立刻抛它（其余任务不会自动取消，继续在跑）。

对照 `CompletableFuture.allOf`：`allOf` 完成时只给你「都完了」的信号，结果要自己再逐个 `join()`；
`gather` 直接交结果列表——**这层 Python 比 Java 顺手，值得点破**。异常对照：`allOf` 把第一个异常藏进
CompletionException，`gather` 默认直接抛原始异常；想「先收尸再分诊」两者都有开关：

```python
# 默认：broken 一炸，整组立刻抛
results = await asyncio.gather(fast(), broken(), slow())
# return_exceptions=True：异常变成「结果」躺进列表，拿回来逐个分诊（毕业设计的降级汇总就靠它）
results = await asyncio.gather(fast(), broken(), slow(), return_exceptions=True)
# -> [正常结果, TimeoutError(...), 正常结果]
```

### 2.3 超时与取消：`wait_for` 与 `CancelledError`

给协程套预算的两件套（本课用前者）：

```python
result = await asyncio.wait_for(fetch(region), timeout=0.1)  # 函数版：超时抛 TimeoutError
async with asyncio.timeout(0.1):  # 3.11+ 上下文管理器版：块内统一预算
    result = await fetch(region)
```

超时的内部机制就是**取消**：`wait_for` 到点后对内部任务 `cancel()`（你没 `create_task` 也有任务可取消——`wait_for` 会先把协程包成 Task；`await` 裸协程时事件循环在幕后也这么干）。而取消的语义是本课最要紧的新心智：
**`CancelledError` 在任务的下一个让出点被注入**。由此两条推论：

- 协作式：循环里没有 `await` 就没有落点——纯 CPU 循环杀不死（Step 6B 实测）；
- `CancelledError` 继承自 **`BaseException`** 而不是 `Exception`（L1.7 异常家族树回收）：

```python
try:
    await asyncio.sleep(1)
except Exception:  # 接不住 CancelledError！它不在 Exception 的子树里
    ...  # 取消发生时这里不会执行——这正是设计意图：取消不该被业务异常处理误吞
except asyncio.CancelledError:
    ...  # 要接它得点名；接住做清理后必须 re-raise（「吞掉取消」会破坏取消协议）
```

对照 Java `Future.cancel(mayInterruptIfRunning)`：

| | Java `cancel(true)` | asyncio `task.cancel()` |
|---|---|---|
| 机制 | 置中断标志；阻塞在 sleep/wait/join 的线程被吵醒抛 `InterruptedException` | 在下一个 `await` 点注入 `CancelledError` |
| 不配合的下场 | 循环不查 `isInterrupted` 就无事发生 | `except Exception` 接不住；清理后须 re-raise |
| 纯 CPU 循环 | 查标志才停 | 无 `await` 即无落点，杀不死 |

### 2.4 `Semaphore` 限流：Java 老朋友

并发上限的经典四行模式（对照 `java.util.concurrent.Semaphore`，几乎同构——差别只在等待时挂起的是协程不是线程）：

```python
sem = asyncio.Semaphore(2)  # ① 造闸机：2 个车道


async def limited_fetch(region: str) -> dict:  # ② 限流版拉取
    async with sem:  # ③ 进块拿名额，出块自动还（≈ acquire/release）
        return await fetch_region(region)


results = await asyncio.gather(*(limited_fetch(r) for r in REGIONS))  # ④ 并发排队过闸机
```

| | `java.util.concurrent.Semaphore` | `asyncio.Semaphore` |
|---|---|---|
| 拿 / 还 | `acquire()` / `release()` | `async with sem:`（进块拿，出块还） |
| 拿不到时 | 线程挂起 | 协程挂起（让出事件循环，不占线程） |
| 许可数 / 公平性 | 有 | 有（同构，零迁移成本） |

### 2.5 异步生成器：流式输出的机制本体

L1.6 的同步生成器「翻译」成异步版，只动两处：

| | 同步生成器（L1.6） | 异步生成器（本课） |
|---|---|---|
| 定义 | `def f(): ...; yield x` | `async def f(): ...; await ...; yield x` |
| 消费 | `for x in f():` | `async for x in f():` |
| 手动一步 | `next(it)` | `await anext(it)` |
| 节奏来源 | 惰性计算（拉一算一） | 网络事件（`await` 等下一段到达） |

流式心智：**生产端一段段吐、消费端一段段处理，两端都在异步世界里等对方**。LLM 的流式输出（token 一段段
到达）、langgraph 的 `astream`、SSE 的 event 流，全是这个形状（Step 5 是它的最小完整标本）。

### 2.6 优雅收尾：TaskGroup（一句话）

3.11+ 还有 `async with asyncio.TaskGroup()` 的结构化并发（块内任务全成功才通过、任一失败自动取消其余、
自动持有引用）。本课不深入——里程碑与 Unit 2 先用 `gather` 把零件练熟，延伸段给出官方文档入口。

## 3. 动手代码

六个 Step 都在 `code/` 目录（先 `uv sync`），输出全为实测。明线场景：报销汇总要并发拉 5 个区域台账端点。

### Step 1 + 2：create_task 双任务并发；gather 5 端点保序

```bash
uv run python code/tasks_and_gather.py
```

```text
== Step 1：create_task 双任务并发 ==
  log: ['start:north', 'start:south', 'done:north', 'done:south']
  总耗时: 0.102s（两个 0.1s 任务同时在飞，≈ max 而非相加）

== Step 2：gather 并发拉取 5 个区域台账 ==
  完成序（log 里 done 的出现序）: ['south', 'east', 'west', 'central', 'north']
  结果序（gather 的返回序）:      ['north', 'south', 'east', 'west', 'central']
  总耗时: 0.202s（串行 = 0.6s 相加；并发 ≈ 0.2s 最大延迟）
```

Step 1 看 log 前两项：两个 `start` 挤在一起——`create_task` 的「已提交调度」眼见为实。Step 2 看两行序：
south 最先完成却排在结果第二位——保序契约不是理论，是可断言的事实。

### Step 3：wait_for 超时降级

```bash
uv run python code/timeout_demo.py
```

```text
结果: {'region': 'north', 'total_cents': 0, 'status': 'DEGRADED'}
总耗时: 0.102s（慢端点要 0.3s，预算 0.1s 在到点时把它掐断）
```

慢端点没有拖垮任何人：预算到点，`wait_for` 取消内部任务、抛 `TimeoutError`，我们捕获后交付降级空台账。

### Step 4：Semaphore(2) 限流，峰值眼见为实

```bash
uv run python code/semaphore_demo.py
```

```text
峰值并发: 2（上限 2——5 个端点排队过 2 车道闸机）
log: ['start:north', 'start:south', 'done:south', 'start:east', 'done:east',
      'start:west', 'done:north', 'start:central', 'done:west', 'done:central']
总耗时: 0.354s（全串行 = 0.6s；2 车道排队 ≈ 0.4s）
```

log 就是闸机记录：north 与 south 先进；south 出、east 进……始终最多 2 个在飞。限流不是「变慢的元凶」，
是「别打挂对方」的礼数——里程碑会把峰值并发写进验收断言。

### Step 5：异步生成器 token 流（L2.1 的彩排）

```bash
uv run python code/token_stream.py
```

```text
async for 消费完毕: 「单据CLM-2026-0001金额1200分，结论PASS」（共 8 段）
anext 手动推进一段: 「单据」——首 token 到手即可开始渲染，不必等全文
```

mock 模型按词吐出审批意见，消费端一段段拼——把 `CHUNK_DELAY` 想成网络节奏，这就是 SSE 流式的全部心智。

### Step 6：取消的两种下场

```bash
uv run python code/cancel_demo.py
```

> **IDE 侧**：Step 1 的 gather 实验同样可 Debug——两个任务函数首行各打断点，Frames 同屏出现两个任务帧，「同时在飞」具象化；本步则在 `except asyncio.CancelledError` 行打断点，亲眼看取消异常落在哪个 await 点、清理后 re-raise 的走向。

```text
== A：有 await 的任务，取消干净落地 ==
  AUD-1:CANCELLED_CLEANUP
  main:观察到任务已取消
  ——CancelledError 在 await 点抛入，清理后 re-raise，主流程 await 观察到取消。

== B：纯 CPU 循环，取消来晚了 ==
  HOG-1:RAN_TO_COMPLETION
  main:终于醒了（睡了 0.05s 却被拖到 0.2s 后），此刻才想取消 HOG-1
  main:cancel() 返回 False（任务已完成，无从取消）
  main:await 拿到 HOG-1 的正常结果 'HOG-1'——取消来晚了
```

B 面比 A 面更值得看：main 只想睡 0.05s，却被 HOG 的纯 CPU 循环拖到 0.2s 才醒——**连「想取消」这个动作
都排不到它前面**。协作式并发的边界，实测给你看。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_gather_fetch.py` | gather 并发拉取补全（验收：保序结果 + 总时长阈值 + 5 个 start 挤最前的并发证据） |
| ex2 | `exercises/ex2_timeout_fallback.py` | wait_for 超时降级补全（验收：快端点真值保留、慢端点降级 0、总时长被预算掐住） |
| ex3 | `exercises/ex3_token_stream.py` | 异步生成器模拟 token 流（验收：完整句子 + 分段数 + 逐段节奏时长下限） |

验收（三条同时全绿 = 本课毕业，随后进 [milestone/](../milestone/README.md) 结业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：create_task 无引用（fire-and-forget 静默丢任务）

- **现象**：后台任务写成 fire-and-forget——`asyncio.create_task(save_audit_log(...))` 不存变量。任务可能在
  完成前被垃圾回收，**静默消失**：没有异常、没有日志、没有尸体。CPython 官方文档（`asyncio.create_task` 条目）
  原文警告：*保存本函数结果的引用，以免任务在执行中途消失。事件循环只持有任务的弱引用。未被其他地方引用的
  任务可能在任何时候被回收——甚至还没跑完。*
- **最小复现**（文档化演示——GC 时机不确定，无法稳定复现，这本身就是坑的一部分：它是**概率性静默丢任务**，
  生产环境最难抓的那一类）：

  ```python
  async def main() -> None:
      for i in range(100):
          asyncio.create_task(background_flush(i))  # 不存引用：官方文档明说可能中途被 GC
          await asyncio.sleep(0)  # 制造回收窗口
  ```

  讲义不伪造必现复现；「弱引用」是文档保证的事实，本坑的复现方式就是读文档 + 偶发线上丢任务。
- **Java 直觉为何失效**：`executor.submit(task)` 返回的 `Future` 你随手丢弃也没事——线程池对队列里与
  worker 中的任务持**强引用**，任务不可能因「没人看」而消失。「后台任务不需要人持有」是线程池给你的隐性
  承诺；asyncio 事件循环把生存期责任还给了你。
- **修复与纪律**：① 最简单：`task = asyncio.create_task(...)` 存住引用；② 后台任务多的地方用集中管理模式：

  ```python
  background: set[asyncio.Task[None]] = set()

  task = asyncio.create_task(flush())
  background.add(task)  # 集合持有强引用
  task.add_done_callback(background.discard)  # 完成后自清，集合不泄漏
  ```

  ③ 3.11+ 优先 `TaskGroup`：`async with asyncio.TaskGroup() as tg` 块内 `tg.create_task(...)`，
  引用、取消、异常聚合一并解决（见延伸）。

## 6. 延伸

- asyncio 官方文档 [Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html)——
  本课全部原语的权威定义；`create_task` 条目里「保存引用」的警告原文也在这里。
- 同页 [Task Groups](https://docs.python.org/3/library/asyncio-task.html#task-groups)——3.11+ 结构化并发，
  本课一句话带过的 `TaskGroup` 的完整语义（Unit 2 起会用到）。
- langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py —— 框架流式实现的实物：搜 `async def astream`
  （约 3060 行起）——图遍历的流式输出就是一个异步生成器（`-> AsyncIterator[dict[str, Any]]`）；
  同文件约 3720 行起是 `astream_events` 公共入口。今晚的 2.5 节就是读懂它的全部语法前置。
- 毕设预告：L5.1 执行层的「并发取数 + 重试 + 超时降级 + 限流」= 本课 `gather` + 装饰器（L1.5）+ `wait_for`
  + `Semaphore` 的拼装——里程碑（`../milestone/`）就是这个拼装的结业考。

## 离毕业又近的一块

学段里程碑（下一个目录）就是毕设执行层的雏形验收：5 个区域台账端点并发拉取、带参 retry 装饰器、
超时降级、限流、结构化汇总报告——零件今晚全部到齐，剩下的只是拼装。过了它，你就拿到了 CURRICULUM
结业自查的第一条：「不查资料手写 async 并发 fetcher + retry 装饰器」。
