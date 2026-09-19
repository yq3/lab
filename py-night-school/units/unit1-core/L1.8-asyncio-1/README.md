# L1.8 asyncio ①：事件循环与协程

> 昨晚你给报销域立起了异常分层（`ExpenseError` → `AmountParseError`，`raise ... from exc` 保留因果
> 链），还用 `@contextmanager` 写了临时限额覆盖——错误处理与资源清理两块拼图归位。今晚进入学段压轴
> 主题 asyncio 的第一课：建立事件循环 / 协程 / 让出点三个模型，看 `await` 怎么让「两张单据同时
> 在飞」，以及为什么 Java 的线程心智（含虚拟线程）在这里是同一问题的相反解法。

## 1. 本课目标

建立 asyncio 的三个核心心智模型：**事件循环**、**协程**、**让出点**；理解它与 Java 线程模型（含虚拟线程）
本质上是同一问题的相反解法。完成后你能：

- 写出第一个 async 程序，并说清 `asyncio.run` / `async def` / `await` 各自在干什么；
- 用「总耗时」和「事件顺序」两类证据区分真并发与顺序执行；
- 诊断两类新手事故：**「假 await」**（调了 async 函数但没等它跑）与**「阻塞全场」**（一个同步调用冻住整个循环）。

**为什么这课最重要**：之后你要读写的每一个 agent 框架，入口清一色 `async def`——langgraph 的图执行、
openai-agents 的 `Runner.run()`、MCP client 的工具调用全是协程。不懂 asyncio，框架源码对你就是天书。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest          # 做完后练习全绿（发货态＝刚 clone 时：讲义示例绿、练习 TODO 未填是设计内的红）
uv run ruff check .    # 无 lint 违规
uv run pyright         # 无类型错误
```

## 2. 概念讲解

### 2.1 两种并发世界观：本课最重要的一张表

Java 世界里你已经拥有三种并发写法：线程池 + `Future`、`CompletableFuture` 装配、虚拟线程。asyncio 与它们
目标相同（IO 密集任务的高并发），机制相反。**与虚拟线程的对照是全课的锚点**——两者都让你写**顺序命令式代码**
拿到高并发（不写回调、不装配算子链），但「让出」的位置完全不同：虚拟线程把让出藏在 JVM 里，asyncio 把让出写进语法里。

| 维度 | Java 平台线程/线程池 | Java 虚拟线程（Loom） | asyncio 协程 |
|---|---|---|---|
| 谁调度 | OS 内核，抢占式 | JVM 调度器，挂载到载体线程 | 你写的 `await` + 事件循环，纯协作式 |
| 何时让出 | 任何时刻（随时被抢占） | 阻塞调用时**自动**让出（对代码透明） | **只有显式 `await` 才让出** |
| sleep 的后果 | 合法：只挂起自己 | 合法：自动让出载体线程 | **毒药：`time.sleep` 冻住整个事件循环** |
| 某任务死循环 | 饿死一个线程 | 占住一个载体线程，其余虚拟线程还能长在别的载体上 | **整个程序唯一线程卡死，全员陪葬** |
| 写法外观 | 同步代码 | 同步代码（最大卖点） | 全链路 `async`/`await`「传染」 |
| 切换成本 | 内核级微秒上下文切换 | 极低 | 接近一次函数调用（无栈协程：暂停不靠线程栈切换，靠函数自身的 await 点——延伸段给了深读入口） |
| 心智负担 | 锁与竞态 | 几乎零新增 | **让出点纪律**：两个 `await` 之间是原子的 |

三条推论，正好对应今晚的两类事故与一类传染：

1. 让出是显式的 → 漏写 `await` 时不会报错，只会「什么都没发生」（陷阱一）；
2. 阻塞不再只害自己 → `time.sleep` 冻结全场（陷阱二）；
3. 只有一个线程 → 没有「锁保护共享变量」的默认焦虑，但换来「谁不让出谁害人」的纪律。

写过 WebFlux 的同学再补一层对照：Reactor 是「声明式装配流水线」（`flatMap`/`subscribeOn` 算子图），
asyncio 是「命令式顺序代码 + 显式让出点」——少一层算子心智，多一层让出点纪律。写过 `CompletableFuture`
的同学：asyncio ≈ 单线程版的 CF 链，但不再需要线程池替你执行——等待不占线程，事件循环自己就是调度者。

### 2.2 事件循环是什么：一个 while 循环

剥掉所有优化，事件循环的心智模型就这么大（伪代码，讲义版；真实实现在 CPython `Lib/asyncio/base_events.py`）：

```python
ready = deque()  # 就绪队列：可以接着跑的任务
waiting = []  # 等待队列：在等 IO / 定时器的任务

while True:  # ① 永动主循环（asyncio.run 跑的就是它）
    if not ready:
        ready = collect_done(waiting)  # ② 没人可跑：等最早的定时器/IO 事件，唤醒等它的任务
    task = ready.popleft()  # ③ 取队头任务
    state = task.resume()  # ④ 让它一直跑——直到下一个 await（让出）或跑完
    if state.finished:
        deliver_result(task)  # ⑤ 跑完：结果交给 await 它的人
    else:
        waiting.append((state.waiting_for, task))  # ⑥ 让出了：记下它在等什么，到了再排回 ready
```

有 Netty 经验的读者到这里已经秒懂：这就是 `EventLoop`——`while + selector + 就绪回调`。差别在载体：
Netty 跑的是回调（`channelRead`），asyncio 跑的是协程（`await` 处自动挂起/恢复），写法从回调地狱回到顺序代码。
没接触过 Reactor 模型也不亏：上面六行就是全部机制——**单线程 + 就绪队列 + 只在 await 处交换任务**。

### 2.3 `async def`：调用 ≠ 执行

`async def` 定义的是**协程函数**；**调用它不执行任何函数体，只是返回一个协程对象**——一张「待办单」。
这是 Java 里不存在的东西：Java 方法调用即执行，最接近的形态是拿到一个没调 `run()` 的 `Runnable`。

实测（本课 Step 3 的真实输出）：

```python
async def review(claim_id: str) -> str: ...


coro = review("CLM-A")
print(coro)  # <coroutine object review at 0x102543780>
print(type(coro).__name__)  # coroutine —— 此刻函数体一行都没跑
```

协程对象只有三个正经归宿（外加一个事故）：

| 归宿 | 写法 | 发生什么 |
|---|---|---|
| 被 `await` | `result = await coro` | 挂起当前协程，等它跑完拿结果 |
| 被 `asyncio.run` 驱动 | `asyncio.run(coro)` | 创建事件循环，把它跑到完，返回结果 |
| 被关闭 | `coro.close()` | 不打算跑了，显式作废（否则留 never awaited 警告） |
| （事故）被丢弃 | `review("X")` 不接返回值 | 什么都不发生 + 解释器回收时报 RuntimeWarning |

还要点破一句：**只 `await` 不产生并发**。`await a` 再 `await b` 是顺序执行——`await` 的语义是
「等它做完我再继续」，与并发无关。并发来自「把多个协程同时交给循环」（`gather`/`create_task`，L1.9 正餐）。

### 2.4 `await` 做什么：挂起 → 让权 → 恢复

`await x` 三步：① 把当前协程挂起；② 控制权交回事件循环（回到 2.2 伪代码第 ④ 步的下一步）；③ `x` 完成后被
排回就绪队列、恢复执行。所以 **`await` 是让出点，两个 `await` 之间是原子的**——中间的代码不可能被别的
任务插队（单线程 + 协作式的直接推论，Step 5 眼见为实）。

`await` 后面能跟的东西统称 awaitable，三层一句话分层：

- **协程**：没跑完的可暂停函数（`async def` 的调用结果）——日常 `await` 的绝对主力；
- **Task**：已被提交给事件循环排期的协程包装（`create_task` 的产物）——L1.9 的主角；
- **Future**：「最终结果」的底层占位符——业务代码很少直接碰，知道它是 Task 的内胆即可。

### 2.5 入口：`asyncio.run` 与「async 传染性」

`asyncio.run(main())` 做三件事：创建事件循环 → 在循环上跑 `main` 直到结束 → 关闭循环。纪律：**每个程序
只有这一个入口**（通常叫 `main`），其余全是 `async def`；`asyncio.run` 不能嵌套（循环里不能再开循环）。

「async 传染性」：想拿到 `await` 的好处，调用链上每一层自己必须是 `async`——从 `main` 到最底层的 IO 函数
一路 `async def` + `await`。**对照 Java：虚拟线程完全不传染**（任何同步方法都能跑在虚拟线程上）；
传染的最像物是 Java 的 checked exception——同样是「能力沿调用链逐层标注，标注到哪层哪层签名就要改」。
这个传染也是框架全是 `async def` 的原因：库的底层是异步的，上层 API 就没有选择的余地。

### 2.6 `await` 什么才让出：不是写了 await 就高枕无忧

让出的触发条件是「await 到一个未完成的东西」：`await asyncio.sleep(0)` 是**显式让出**——立刻把我排到
就绪队列尾（Step 5）。反过来，**`time.sleep` 是阻塞毒药**：它不是 awaitable、不经过事件循环、也不让出——
在单线程世界里，它睡的每一毫秒都是全场的。同理：同步 IO（比如 `requests` 库的请求）、CPU 重活（大循环、
解析大 JSON），都会把循环冻住。修复方向一句话预告：同步重活用 `asyncio.to_thread` 扔进线程池（后续课程用到再展开）。

## 3. 动手代码

五个实验都在 `code/` 目录（先 `uv sync`）。每个都是可独立运行的脚本，输出全是实测。

### Step 1 + 2：第一个 async 程序，与「一行换并发」

```bash
uv run python code/first_steps.py
```

```text
== Step 1：顺序 await（总耗时 = 两段延迟相加）==
  log: ['start:CLM-A', 'done:CLM-A', 'start:CLM-B', 'done:CLM-B']
  结果: ['CLM-A:OK', 'CLM-B:OK']
  总耗时: 0.202s ≈ 0.1 + 0.1
  ——await 的字面意思：等它做完，我才能继续。

== Step 2：gather 并发（总耗时 ≈ 最大延迟）==
  log: ['start:CLM-A', 'start:CLM-B', 'done:CLM-A', 'done:CLM-B']
  结果: ['CLM-A:OK', 'CLM-B:OK']
  总耗时: 0.100s ≈ max(0.1, 0.1)——两张单据同时在飞
```

看两处：①的 log 里 B 要等 A 完全结束；②只改驱动方式（`gather`），两张单据同时在飞，总耗时 0.2s → 0.1s。
`gather` 的完整规格（保序、异常传播）是 L1.9 的正餐，今晚只把它当「并发对照组」。

### Step 3：协程对象——调用 ≠ 执行

```bash
uv run python code/coroutine_object.py
```

```text
code/coroutine_object.py:25: RuntimeWarning: coroutine 'review' was never awaited
  review("CLM-C")  # pyright: ignore[reportUnusedCoroutine]
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
== 1. 调用 async 函数：只拿到协程对象 ==
    coro = <coroutine object review at 0x102543780>
    type(coro).__name__ = coroutine
    （注意：上面没有出现 review 函数体的输出——它还没执行）

== 2. 归宿之一：asyncio.run 直接驱动 ==
    review('CLM-B') 的函数体此刻才真正开始执行
    asyncio.run 的返回值: PASS

== 3. 事故现场：造了协程对象却谁也不管 ==
    （往上翻 stderr：RuntimeWarning: coroutine 'review' was never awaited）
```

第 1 节：`review("CLM-A")` 之后函数体一行没跑。第 3 节故意丢弃协程对象，解释器在回收瞬间报出
`never awaited` 警告——这就是陷阱一的现场。开头那行被忽略的 `# pyright: ignore` 注释说明：
pyright 本来能静态抓住这个事故（见陷阱一的修复纪律）。

### Step 4：阻塞事故——一个 time.sleep 冻住全场

```bash
uv run python code/blocking_disaster.py
```

```text
== 事故版：CLM-X 用 time.sleep(0.3) ==
[ 0.00s] start CLM-X
[ 0.30s] done  CLM-X
[ 0.30s] start CLM-Y      <- Y 等 X 完全结束才起步！
[ 0.30s] start CLM-Z
[ 0.41s] done  CLM-Y
[ 0.41s] done  CLM-Z
  总耗时: 0.406s（理想 0.3s；Y/Z 被冻到 0.3s 后才起步，再多花 0.1s）

== 健康版：CLM-X 改用 await asyncio.sleep(0.3) ==
[ 0.00s] start CLM-X
[ 0.00s] start CLM-Y
[ 0.00s] start CLM-Z
[ 0.11s] done  CLM-Y
[ 0.11s] done  CLM-Z
[ 0.30s] done  CLM-X
  总耗时: 0.300s（= max(0.3, 0.1, 0.1)，达到理想值）
```

三个任务名义上「并发」，但事故版里 CLM-X 的 `time.sleep(0.3)` 让事件循环 0.3 秒无暇他顾——Y/Z 连
「开始等待」的资格都被剥夺。同样等 0.3s，换成 `await asyncio.sleep` 立刻回到理想值。眼见为实。

### Step 5：`asyncio.sleep(0)` 手动让出——交替的可见证据

```bash
uv run python code/yield_point.py
```

> **IDE 侧**：在 `await asyncio.sleep(0)` 行打断点、Debug 跑——Frames 面板里两个协程帧轮流成为当前帧，这就是「让出点」的肉眼版（PyCharm 对 asyncio 默认启用 Async 调试模式，协程按颜色分组）。

```text
窗口A 处理第 1 单
窗口B 处理第 1 单
窗口A 处理第 2 单
窗口B 处理第 2 单
窗口A 处理第 3 单
窗口B 处理第 3 单
log: ['窗口A:1', '窗口B:1', '窗口A:2', '窗口B:2', '窗口A:3', '窗口B:3']
```

两个协程严格交替——每次 `await asyncio.sleep(0)` 都是一次让出。按讲义提示把这一行改成 `pass` 再跑：
窗口A 连跑三轮窗口B 才动。「两个 await 之间原子」从此不再是讲义的一句话，是你的实验数据。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，其余文件与代码区不要动。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_main_flow.py` | 补全 async 主流程：`async def` + 顺序 `await` + `asyncio.run` 入口（验收：LOG 顺序断言 + 总耗时 ≥ 两段延迟相加） |
| ex2 | `exercises/ex2_fix_blocking.py` | 修复混入的 `time.sleep` 毒药（验收：总时长阈值 + 三个 start 挤在最前的并发证据；修完删掉失效 import） |
| ex3 | `exercises/ex3_coroutine_fates.py` | 协程对象三归宿实验：`type` 观察 / `await` 一次 / `run` 一次（验收：三键断言） |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱（本课两个）

### 陷阱一：协程未 await（「假 await」）

- **现象**：调用了 async 函数，但忘了 `await`——什么都没发生，功能静默失效；唯一的线索是解释器回收协程对象时
  的 `RuntimeWarning: coroutine ... was never awaited`。更阴的是协程对象是真值、能打印、能当参数传——
  它不会像 None 一样在下一个分支炸出来。
- **最小复现**（Step 3 第 3 节的浓缩）：

  ```python
  async def send_report(claim_id: str) -> bool: ...


  def process() -> None:
      send_report("CLM-A")  # 没接、没 await、没 close——单据永远没发出去
  ```

- **Java 直觉为何失效**：Java 里「调用」与「执行」是同一个动作，不存在「调了但没跑」的方法形态；最接近的
  类比是拿到 `Runnable` 忘了 `run()`、或建了 `CompletableFuture` 忘了链下去——但 Java 编译器至少让你
  显式地看到「拿到一个对象」，Python 的裸调用看起来和普通函数调用一模一样。
- **修复与纪律**：① 见到 `coroutine object` 字样或 `never awaited` 警告，立刻回头找漏写的 `await`；
  ② pyright 的 `reportUnusedCoroutine` 检查能静态抓住裸调用（本课工具链已默认开启——Step 3 里那行
  `# pyright: ignore[reportUnusedCoroutine]` 正是先关掉它才能演示事故）；③ 不打算跑的协程显式 `close()`。

### 陷阱二：time.sleep 毒害（「阻塞全场」）

- **现象**：async 函数里一句 `time.sleep(0.3)`，全场所有任务被冻结 0.3 秒——并发消失、超时误报、
  心跳停止，且没有任何报错指向肇事者（Step 4：总耗时 0.406s，两个 0.1s 的任务连起步都被推迟）。
- **最小复现**（Step 4 的浓缩）：

  ```python
  async def fetch(claim_id: str) -> str:
      time.sleep(0.3)  # 毒药：不是 awaitable，也不让出
      return claim_id


  # gather 里三个任务并发？不——全场串行陪它冻
  ```

- **Java 直觉为何失效**：平台线程里 `Thread.sleep` 只挂起自己，完全合法；虚拟线程里它同样合法——JVM 会
  自动把载体线程让给别人。你的肌肉记忆是「sleep 是无害的礼貌行为」；asyncio 里只有一条线程，你睡的
  每一毫秒都是**全场的**。
- **修复与纪律**：① async 函数里只准 `asyncio.sleep`（把「等一下」翻译成 `await asyncio.sleep(秒)` 是
  肌肉记忆级别的迁移）；② 同步 IO 库（如 `requests`）与 CPU 重活不进 async 函数，需要时用
  `asyncio.to_thread(func, ...)` 扔进线程池（后续课程实战）；③ 排查手段：`asyncio.run(main(), debug=True)`
  会报告「卡住循环超过 100ms 的回调」——事故定位器。

## 6. 延伸

- asyncio 官方文档 [Developing with asyncio](https://docs.python.org/3/library/asyncio-dev.html)——
  调试模式、并发原语选择、常见陷阱的官方清单（本课陷阱二提到的 debug 模式在这里有完整说明）。
- openai-agents-python@fbd2dbca#src/agents/run.py —— OpenAI 官方 agent SDK 的执行入口。翻到 `class Runner`
  的第一个方法：`@classmethod async def run(...)`。你之后要写的每一个 agent 入口都是这个形状——
  这就是「框架全是 async def」的实物证据。
- 《Fluent Python》第 2 版讲并发的两章（concurrent.futures 与 asyncio）选读：比夜校深两档，
  事件循环内幕与无栈协程的细节在那里展开，适合周末精读。

## 离毕业又近的一块

毕业设计执行层的每一次 LLM 调用、每一个工具拉取都是 IO 等待——asyncio 的主场。今晚你已经能写出
async 主流程、并看穿两类事故；还差的是把「两张单据同时在飞」升级成工程化的「N 个端点并发拉取 +
超时降级 + 重试 + 限流」——这正是下一课 L1.9 与学段里程碑的内容。agent 的血管，今晚通了一半。
