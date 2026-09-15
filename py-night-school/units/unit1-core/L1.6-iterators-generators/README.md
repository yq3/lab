# L1.6 迭代器与生成器：for 的真实面目与 yield 的暂停魔法

## 1. 本课目标

拆掉 Python 里被用得最多、被理解得最少的一对概念。完成后你能：

- 说清 `for x in items` 背后的完整协议（`iter()` / `__next__` / `StopIteration`），并手工模拟一个 for；
- 写生成器函数，并解释「执行到 yield **暂停并吐值**、状态完整保留、下次从暂停点继续」；
- 用生成器搭惰性管线（内存恒定、短路省功），并知道什么时候必须物化；
- 为 L1.9 / Unit 2 的流式输出（async generator）装好心智模型——agent 逐 token 吐字，靠的就是它。

**完成判据**：本目录下 `uv run pytest` 练习全绿，且你能不看讲义解释「为什么生成器第二次 for 是空的」。

## 2. 概念讲解

### 2.1 for 循环的真实面目：一个三步协议

你写了几天 Python 已经用了几百次 `for`。它的真实面目不是「下标循环」，而是**协议调用**：

```python
total = 0
for item in [1200, 3500, 2400]:  # 你写的 for
    total += item

# Python 解释器眼里的等价形式（糖衣完整剥掉）：
it = iter([1200, 3500, 2400])  # 第 1 步：iter() 把「可迭代物」变成「迭代器」
while True:
    try:
        item = next(it)  # 第 2 步：next() 向迭代器要下一个元素
    except StopIteration:  # 第 3 步：迭代器用「异常」宣布耗尽
        break
    total += item
```

**Java↔Python 对照表**：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `Iterator<E>`：`hasNext()` + `next()` 二段式 | 迭代器：`next()` 一段式，耗尽抛 `StopIteration` | Java 先问再取；Python 直接取、用异常收尾 |
| `Iterable<E>`（实现它才能 for-each） | 可迭代物（支持 `iter()`） | 概念同构：`iter(可迭代物)` 产迭代器，像 `iterable.iterator()` |
| `for (X x : list)` | `for x in list:` | 都是糖衣，都落在迭代器协议上 |
| `NoSuchElementException`（越界 next，一般是 bug） | `StopIteration`（正常控制流的一部分） | Python 把「结束」做成协议信号，for 靠它终止 |
| Stream 惰性、一次性 | 生成器惰性、一次性 | 像，但生成器不需要创建「流对象」，函数本身就能产流（§5 坑位细比） |

Python 这个「一段式 + 异常终止」不是偷懒，是哲学：**先斩后奏（出事了再处理）**，术语叫 EAFP，L1.7 正式讲——今天先在这里混个脸熟：迭代协议是你碰到的第一个「用异常当控制流」的 Python 惯用法。

### 2.2 可迭代物 vs 迭代器（一个关键区别）

- **可迭代物**（list / str / dict / 生成器……）：支持 `iter()`，能被 for。list 每次给**新的**迭代器，所以能反复 for；
- **迭代器**：支持 `next()`。`iter(x)` 若 x 已是迭代器，返回它**自己**（`iter(gen) is gen`）。

```python
claims = [1200, 3500]
iter(claims) is claims  # False：list 不是迭代器，iter() 现造一个
gen = (c for c in claims)
iter(gen) is gen  # True：生成器自己就是迭代器
```

判别口诀：**可迭代物是「能造迭代器的东西」，迭代器是「自己就在迭代的东西」**。list 是前者；生成器既是前者也是后者——所以生成器天生一次性（§5）。

顺手认识两个你马上会用到的东西：`enumerate(items)`（带下标迭代，≈ 自己维护 `int i`）和 `zip(a, b)`（并行迭代两个序列，短的那个先耗尽就停）——它们返回的也都是一次性迭代器。
另外 `next` 有个双参形态 `next(it, default)`：耗尽时不抛 `StopIteration` 而是返回 default，agent 循环里「取下一条消息，没有就当 None」常用它。

```python
for i, amount in enumerate([1200, 3500], start=1):  # (1, 1200) (2, 3500)
    print(f"第 {i} 笔: {amount} 分")
```

对照 Java：`enumerate` ≈ `IntStream.range(0, list.size()).mapToObj(i -> ...)` 的语法糖；`zip` 没有 Stream 对应物（得自己下标对齐）——Python 把这两个高频动作做成了语言级迭代器。

### 2.3 生成器函数：函数可以暂停（本课最重要的心智模型）

Java 的方法一旦调用就跑到底（return / 抛异常，二选一）。**Python 的生成器函数可以暂停**：执行到 `yield`，把值吐出去，然后整个函数**冻结**——局部变量、指令位置全部保留；下一次被 `next()`，从冻结点继续。看这个三段审批的完整演示：

```python
def audit_steps(claim_id):
    print(f"  [进入] {claim_id} 开始审批")
    print("  [执行] 第一段：校验金额")
    yield "OK:金额"  # 吐值 -> 冻结在这里
    print("  [执行] 第二段：查预算")  # 下次 next 从这里继续
    yield "OK:预算"
    print("  [执行] 第三段：出结论")
    yield "PASS"
```

逐次 `next` 的完整输出（`code/iter_basics.py` 亲手跑）：

```text
[main] 拿到生成器对象，函数体一行都没执行: <generator object ...>
  [进入] CLM-2026-0001 开始审批（此刻函数体刚启动）
  [执行] 第一段：校验金额
[next ] 第 1 次吐出: OK:金额
[main] 函数此刻冻结在第一个 yield 处，我在干别的事……
  [执行] 第二段：查预算
[next ] 第 2 次吐出: OK:预算
  [执行] 第三段：出结论
[next ] 第 3 次吐出: OK:PASS
[next ] 第 4 次: StopIteration（生成器耗尽）
```

三个要点（Java 里没有对应物，值得逐条内化）：

1. **def 不执行**：调用 `audit_steps(...)` 只造生成器对象，函数体一行都没跑——直到第一次 `next`；
2. **yield 是暂停不是返回**：吐值后函数冻结，所有局部状态保留，next 时续跑（对照：Java 方法 return 后栈帧就没了）；
3. **自然结束即耗尽**：最后一个 yield 之后再 next，函数体跑完、抛 `StopIteration`——正好接上 §2.1 的 for 协议，所以 for 能直接吃生成器。

「暂停的函数」就是流式输出的心智底座：把 `yield "OK:金额"` 想成 `yield 下一个 token`，你就理解了 chat 界面里逐字输出的机制（L1.9 换成 async 版）。

### 2.4 生成器表达式 vs 推导式：一次性 vs 可复用

L1.4 讲过列表推导式 `[x * 2 for x in items]`。把方括号换圆括号就是**生成器表达式**——不建 list，边消费边算：

```python
amounts = [1200, 3500, 8800]
total = sum(a for a in amounts)  # 生成器表达式：sum 边拉边加，不建中间 list
doubled = [a * 2 for a in amounts]  # 推导式：立即物化成 list，可反复用
```

选择规则：**消费一次就用 genexp（省内存）；要复用就用 list**。`sum(...)` / `any(...)` / `max(...)` 里直接塞 genexp 是 Python 最常见的姿势。

### 2.5 yield from：把一段管线委托给另一个生成器

```python
def meal_lines(lines): ...
def hotel_lines(lines): ...


def all_expenses(lines):
    yield from meal_lines(lines)  # 逐个转发 meal_lines 吐的每个值
    yield from hotel_lines(lines)  # ≈ Java 里把两个 Stream 接起来依次消费
```

`yield from g` ≈「for v in g: yield v」的语法糖，但语义更完整（还能转发 send/异常）。见到要认得；本课动手里 langgraph 的 `stream()` 源码就是用它组装输出的（§6）。

### 2.6 itertools 四件套（对照 Java Stream）

| itertools | 作用 | Java Stream 对应 |
|---|---|---|
| `islice(gen, 5)` | 只取前 5 个 | `.limit(5)` |
| `takewhile(cond, gen)` | 条件成立就一直取，第一个不成立立刻停 | `.takeWhile(pred)` |
| `chain(a, b)` | 两段迭代器接一段 | `Stream.concat(s1, s2)` |
| `count(1)` | 从 1 开始的无限计数 | `Stream.iterate(1, i -> i + 1)` |

它们全部惰性：没人拉就不算。`count` 是无限流，配 `islice` 才能落地——这正是「惰性 + 短路」的组合拳。

### 2.7 惰性的价值：内存恒定 + 短路省功

- **内存恒定**：处理一个 10 GB 流水文件，`readlines()` 要全装进内存；生成器管线任意时刻只握一行。本课 Step 2 用 tracemalloc 实测峰值差异；
- **短路**：`any(c > 5000 for c in amounts)` 找到第一个超标就停，后面的数根本不会被拉出来。Step 3 用「计数器」把这件事变成可见的断言（练习 2 的考点）。

### 2.8 预告：async generator（L1.9 的主角）

把 `def` 换成 `async def`、`next` 换成 `async for`，生成器就变成**异步生成器**——暂停点从「等下一次拉取」变成「等 I/O 就绪」。
agent 的流式输出（langgraph 的 `astream`、OpenAI SDK 的 token 流）全是它。今天只记一件事：**yield 的暂停语义在 async 世界原样成立**。

## 3. 动手代码

四个模块都在 `code/`，先 `uv sync` 再逐个跑；配套测试在 `code/test_*.py`。

### Step 1 手工 for + 三 yield 逐次 next（本课最重要演示）

```bash
cd units/unit1-core/L1.6-iterators-generators
uv sync
uv run python code/iter_basics.py
```

对照输出与 §2.3 的逐行解释：第一段验证「手工 while + next + StopIteration 与 for 等价」，第二段看函数怎么在 yield 处冻结、被 next 唤醒。

### Step 2 报销流水惰性管线（内存恒定的实测）

`code/expense_flow.txt` 是 300 行报销流水（生成规则见 `code/pipeline.py` 文件头）。管线四段：**读行 -> 解析 -> 过滤超标餐 -> 汇总**，每段都是生成器，全程内存恒定：

```bash
uv run python code/pipeline.py
```

输出末尾有 tracemalloc 实测：同一份流水放大 200 倍（60000 行）再走两条路——lazy 逐行峰值只有几十 KiB 且不随行数涨，eager 全量 splitlines 近似线性上涨。文件越大差距越大，这就是处理超大流水不必整读的原因。

### Step 3 itertools 组合 + 短路证明

```bash
uv run python code/itertools_demo.py
```

`counting_source` 是「测速仪」：底层每被拉一次记一笔。输出会证明 `islice` 取 3 个底层恰好被拉 3 次、`takewhile` 在 8800 处即停（后面还有两笔根本没被拉）。

### Step 4 一次性消费实验（坑位先行演示）

```bash
uv run python code/oneshot.py
```

同一个生成器 for 两遍：第一遍 `[1200, 3500, 2400]`，第二遍 `[]`——**没有异常**。以及两种修复（物化 / 重建）。§5 会解剖为什么。

```bash
uv run pytest code/        # 讲义示例测试应全绿（它不是你的练习）
uv run ruff check code/
```

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 | 验收要点 |
|---|---|---|---|
| ex1 | `exercises/ex1_paginate.py` | 生成器函数基本形 | 页数与内容（不满尾页 / 整除无空页 / 空输入 / `size<=0` 抛 `ValueError`） |
| ex2 | `exercises/ex2_pipeline.py` | 三段管线组合 + 惰性 | 聚合结果 14000 + **计数器断言**：只消费前 2 条超标时底层恰好被拉 4 行 |
| ex3 | `exercises/ex3_oneshot.py` | 修复一次性消费 bug | 两遍结果一致且正确（物化修复） |

ex2 是本课的灵魂题：**惰性看不见，计数器让它现形**——测试里 `next()` 两次后断言 `len(pulled) == 4`，短路就是少干活。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：生成器一次性坑

- **现象**：生成器第一次 for 有数据，第二次 for **静默空**——不报错、不警告、返回零元素。下游常常表现为「统计值神秘为 0」「报表第二页全空」，离案发现场很远才炸。
- **最小复现**：

  ```python
  def read_amounts():
      for amount in [1200, 3500, 2400]:
          yield amount


  gen = read_amounts()
  print(sum(gen))  # 7100：第一次消费，正常
  print(sum(gen))  # 0：第二次消费，静默空——没有异常！
  ```

- **Java 直觉为何失效**：Java 集合天然可重复迭代（每次 for-each 都新造 Iterator）；Java Stream 也一次性，但重用会抛 `IllegalStateException: stream has already been operated upon`——**响亮地失败**。
  Python 选择静默：`StopIteration` 被 for 当正常结束吞掉，于是第二次循环体一次都不进。响亮失败 vs 静默空，后者阴险得多。
- **修复与纪律**：① 要复用就**物化** `data = list(gen)`，之后随便消费；② 每次要「新鲜数据」就**重建生成器**（调用生成器函数造新的）；③ 别把生成器存成模块级常量再多处消费（练习 3 的坏代码就是这么写的）。

## 6. 延伸

- itertools 官方文档：https://docs.python.org/zh-cn/3.12/library/itertools.html —— 重点读 **"Itertools Recipes"** 一节（社区积攒的算法小抄，面试也常考）；
- 迭代协议官方教程（yield 语义的权威叙述）：https://docs.python.org/zh-cn/3.12/reference/expressions.html#yieldexpr
- 《Fluent Python》第 2 版「Iterators, Generators, and Classic Coroutines」章（第 17 章）：惰性管线的深水区；
- 框架真实流式源码：langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py —— 搜 `def stream(`（约 2616 行起）：
  agent 图的流式输出就是一个生成器函数，`while loop.tick()` 的每个执行步里 `yield from _output(...)` 把本步产出逐段吐出；同文件 3024 行起的 `astream` 是它的 async 版（§2.8 的预告在这里兑现）。
  对照读一遍，「流式输出 = 生成器」就从口号变成事实。

## 离毕业又近的一块

毕业设计 L5.2 的「SSE 推送审批进度」与 L2.1 手撕的 token 流，运行机制都是今晚的生成器：`yield` 吐一个事件、暂停、等下一个客户端拉取。
管线四段（读行->解析->过滤->汇总）就是毕设「事件溯源」里事件流处理的雏形——今晚你已经把「流」这块地基浇好了。
