# 长任务落地专题：等待归属、事件投递、进度反馈与凭证生命周期

> 2026-11-08 · 承接 [report.md](report.md)（设计原则篇）与 [engineering.md](engineering.md)（异步与生产注意点篇）。
> 本文不重复前两篇的结论，只回答真实落地时才会暴露的五个问题：**长任务到底该由谁等、为什么不该做成 interrupt、完成事件怎么真正送进对话、进度怎么给用户看、用户凭证过期时任务怎么办。**
> 全文用直白语言写，术语第一次出现时解释；证据按本目录纪律分级并标注来源。

## 目录

- [0. 定位、与前文的关系，以及对 §1.8 的一处修正](#0-定位与前文的关系以及对-18-的一处修正)
- [1. 重新问问题：轮询的成本到底花在哪](#1-重新问问题轮询的成本到底花在哪)
- [2. 等待归属的五个层级](#2-等待归属的五个层级)
- [3. 除了轮询的六种方式](#3-除了轮询的六种方式)
- [4. 为什么不该把异步等待做成 interrupt](#4-为什么不该把异步等待做成-interrupt)
- [5. 事件投递机制：从头讲一遍](#5-事件投递机制从头讲一遍)
- [6. 业界实现对照](#6-业界实现对照)
- [7. 进度反馈：三条通道，各管一段](#7-进度反馈三条通道各管一段)
- [8. 凭证生命周期：长任务不能用用户 cookie 跑](#8-凭证生命周期长任务不能用用户-cookie-跑)
- [9. 反模式清单](#9-反模式清单)
- [10. 落地检查清单](#10-落地检查清单)
- [11. 证据与基线](#11-证据与基线)

---

## 0. 定位、与前文的关系，以及对 §1.8 的一处修正

### 0.1 本文接在哪些结论之后

| 已有结论 | 在哪 | 本文如何接续 |
|---|---|---|
| 异步问题的本质是"等待时长分级"，业界五范式收敛到"状态机 + 句柄 + 轮询或推送" | engineering.md §1.2、§1.4 | 往下追一层：**这个"等"由哪个组件承担**，成本差几个数量级 |
| 异步设计十条军规（句柄包 / 状态机 / 幂等 / 不热轮询 / 取消） | engineering.md §1.5 | 全部沿用，不再复述 |
| 主动回调四条路线（会话内通知 / webhook+挂起 / 持久化执行 / 产品级通知） | engineering.md §1.7 | §3 重排为按"等待归属"分类，并把每档的适用边界写清 |
| 四家 harness 全是"通知注入"派，无一家用挂起执行等长任务 | engineering.md §7 | §6 补三家实现细节与投递粒度差异，作为本次证据升级 |

### 0.2 对 engineering.md §1.8 的修正

engineering.md §1.8 有一句：

> "把它用于异步等待：**挂起等人与挂起等事是同一机制**——把挂起点放在'提交异步任务'之后，恢复条件从'审批结果'换成'任务完成事件'。"

**这句话在机制层面成立，在语义层面不成立，且工程上会出问题。** 本文主张：

> **HITL 的挂起（等人）与异步任务的挂起（等事）不是同一件事。**
> 区别只有一条，但足够致命：**等待期间，对话能不能继续。**
> - 等人：对话本来就不该继续，用户的下一条消息就是答复 → 挂起正确
> - 等事：对话必须能继续，用户和 agent 都会往前走 → 挂起错误

理由见 §4，证据见 §4.2（LangGraph 官方 docstring 原文）与 §4.3（四种具体故障）。

这条修正不影响 §1.7 的四条路线本身——**"webhook + 挂起恢复"这条路线对企业审批流（等人）依然正确**，只是不该拿它承载"跑一小时的数据集成"（等事）。

### 0.3 证据等级说明

沿用本目录既有分级，本文新增两类：

| 标记 | 含义 |
|---|---|
| 【核心】 | 源码实现级，可追溯到文件与行号 |
| 【核心-文档】 | 源码仓库内的 docstring / 注释原文 |
| 【还原源码】 | sourcemap 还原的闭源仓库代码（先例：agent-oss 轮） |
| 【随包文档】 | 随发布包分发的官方包 README（DeepSeek Harness asar 内） |
| 【一手】/【转述】/【摘要】 | 沿用 README.md 的定义 |

本文中凡是**推理**而非实证的结论，显式标注「〔推理〕」。

---

## 1. 重新问问题：轮询的成本到底花在哪

"agent 可以不断轮询去拿结果"——这句话里藏着一个成本陷阱，值得先算一笔账。

### 1.1 一笔具体的账

一个跑 1 小时的数据集成，agent 每 30 秒查一次状态：

| 项 | 数值 |
|---|---|
| 查询次数 | 60 分钟 × 2 = **120 次** |
| 每次调用模型的输入 | 5k ~ 20k token（完整上下文，且越往后越大） |
| 总 token | **约 60 万 ~ 240 万** |
| 其中有效信息 | 最后一次 —— 前 119 次都是"还在跑" |

钱是一方面，更麻烦的是**行为风险**：

- 模型在长时间无反馈时会焦虑，可能把 `running` 误判成"卡住了"而重复提交
- 120 次判断里只要错一次，副作用就被放大一次
- 上下文被 119 条"还在跑"污染，真正的信息被稀释

### 1.2 所以问题应该怎么问

不要问"轮询好不好"，而要问：

> **这段等待，由谁承担？**

同样是等 1 小时，让不同的组件承担，成本可以差三四个数量级——下一节展开。

---

## 2. 等待归属的五个层级

| 等待由谁承担 | 机制 | 模型调用次数 | 工程重量 |
|---|---|---|---|
| **模型轮次** | 模型反复调 `get_status` | 120+ | 最低（什么都不用做） |
| **HTTP 连接** | long-poll：一次调用内挂 20~25 秒 | ~144 | 低（加一个参数） |
| **Agent 运行时** | 后台任务 + 完成通知；或 deferred tool | **1**（只在终态） | 中（需要 harness 支持） |
| **编排引擎** | Temporal / 工作流 signal / background run | 0（进程可退出） | 重 |
| **人或产品** | IM / 邮件 / 待办收件箱，下次会话消费 | 0（跨会话） | 轻，但体验降级 |

**这张表是本文的组织骨架。** 后面所有方案，本质都是在回答"能不能把等待从第 1 层挪到第 2~5 层"。

一个关键认知贯穿全文：

> **long-poll、webhook、挂起恢复、后台通知——这些方案在协议内部往往照样在查，但它们把"查"从语义层压到了实现层。**
> 判据不是"有没有轮询"，而是**模型有没有看见轮询**。

MCP Tasks 用 `pollIntervalMs` 和 `ttlMs` 告诉客户端"多久查一次"、A2A 用 push notification 代替轮询、OpenAI Background Mode 提供 webhook——都是同一个方向的不同实现。

---

## 3. 除了轮询的六种方式

按工程重量从轻到重排列。每种都给出适用条件与代价。

### 3.1 Long-poll：改动最小、收益最大

**做法**：在状态查询接口上加一个 `wait_seconds` 参数，服务端最多挂 20~25 秒再返回。

```jsonc
GET /tasks/{id}?wait_seconds=25
→ 200 { "status": "working", "seq": 17 }   // 25 秒内没变化，返回当前状态
→ 200 { "status": "completed", "seq": 18 } // 25 秒内完成，立刻返回
```

**收益**：往返次数从 120 次降到可控，且不会因为"空轮询"白烧模型。

**代价**：连接占用、网关超时配置要对齐。

**适用**：已经有一堆同步 tool、不想改架构，只想先止血。

> 注：这是唯一一个"模型仍然在等，但等得便宜"的方案。它不解决根本问题，但成本极低。

### 3.2 运行时后台等待：模型零成本，体验最好

**做法**：模型只发起一次，agent 运行时（harness）在模型之外盯着任务，完成时**把结果作为新输入重新调用模型**。

**收益**：模型根本没有机会"焦虑性轮询"。

**代表**：Claude Code 的 `run_in_background`、DeepSeek Harness 的 `job_output(wait:true)` + 完成通知。

**适用**：自建 agent 服务，且能改运行时。

> 这是本文推荐的主战场——详见 §5、§6。

### 3.3 Webhook → 挂起/恢复

**做法**：业务侧任务完成发事件 → agent 服务接收 → 注入会话。

**关键提醒**：**接收之后不要"恢复旧的执行快照"，要"当作一条新消息注入"**。理由见 §4。

**适用**：跨系统、需要事件驱动、会话可能跨越长时间。

### 3.4 持久化工作流引擎

**做法**：Temporal 这类引擎托管任务生命周期，activity 发任务、workflow 等 signal，进程重启无损。

**收益**：跨天、跨重启、强可靠。

**代价**：引入整套引擎，运维复杂度上一个台阶。

**适用**：真的存在"跨天、跨重启"诉求时才上。

### 3.5 产品级通知：最稳的兜底

**做法**：任务跑完推 IM / 邮件 / 站内消息，结果落"我的任务"/收件箱，用户下次进来看。

**为什么它常常是实际最优解**：用户本来也不会盯着屏幕等 1 小时。

**适用**：用户可离场、时效不敏感——而这恰恰是 1 小时任务的常态。

### 3.6 不等待：拆阶段 + 提交即结束

**做法**：把 1 小时任务拆成可检查点的阶段，每阶段产出增量结果（"已处理 340/1200"），agent 拿第一阶段就能回话。

**收益**：这是唯一改善**首字延迟**的方案；其余方案都只是改善"怎么等"。

**适用**：任务本身可分段（数据集成、批量导入通常都可以）。

### 3.7 六种的选型速查

| 方案 | 模型调用 | 需要谁配合 | 什么时候选 |
|---|---|---|---|
| Long-poll | 多（但便宜） | 网关 | 只想止血 |
| 运行时后台等待 | 1 | harness | 自建服务，首选 |
| Webhook 注入 | 1~N（按事件） | 业务侧有事件源 | 跨系统 |
| 工作流引擎 | 0 | 基础设施 | 跨天/强可靠 |
| 产品级通知 | 0 | 前端 + IM | 用户可离场 |
| 拆阶段 | 分段数 | 业务侧 | 要求首字延迟 |

**组合使用是常态**：一次 1 小时的集成，典型组合是「拆阶段（3.6）+ 运行时等待（3.2）+ 产品级通知兜底（3.5）」。

---

## 4. 为什么不该把异步等待做成 interrupt

这一节是本文的核心论证，也是对 engineering.md §1.8 的修正依据。

### 4.1 先把场景摆出来

有人在实践里会这样设计：

```python
def node(state):
    task = submit_integration(...)      # 提交异步任务
    result = interrupt({"task_id": task.id})   # 挂起，等任务完成
    return {"result": result}
```

想法很自然："提交完就挂起，任务完成再恢复，这不就等价于同步调用了吗？"

问题在于：**挂起期间，用户会继续说话。**

### 4.2 源码证据：三处硬事实

**证据 A —— 恢复是"节点重跑"，不是"接着跑"**【核心-文档】

`langgraph@e539ac122`，`libs/langgraph/langgraph/types.py:851-868`，`interrupt()` 的 docstring 原文：

> The `interrupt` function **enables human-in-the-loop workflows** by pausing graph execution and surfacing a value to the client.
>
> A client resuming the graph must use the `Command` primitive to specify a value for the interrupt and continue execution.
> **The graph resumes from the start of the node, re-executing all logic.**

两句话连起来读，官方定性很清楚：**它是 HITL 原语，且恢复是重放式的。**

〔推理〕这意味着 `interrupt()` 之前的代码会再执行一次——包括 `submit_integration`。任务被提交两次。只有幂等键能救。

**证据 B —— 用户在挂起期间发消息，不会被当作"恢复"**【核心】

`libs/langgraph/langgraph/pregel/_loop.py` 的 `_first()`，判断"是否恢复"的条件写得很明确：

```python
# 1. A prior checkpoint exists (channel_versions is non-empty)
# 2. The input signals continuation (not a fresh run with new input)
is_resuming = ... (
    self.input is None
    or input_is_command
    or (same run_id ...)
)
```

也就是说：`input is None` 或传 `Command` 才算恢复；**传新输入 = 一次全新的运行**。

用户在挂起期间发消息，就是"传新输入"。那个 pending interrupt **不会被消费，只是挂在那里**。

**证据 C —— 挂起的中断会累积**【核心】

同文件的 `_pending_interrupts()`：

```python
"""Return the set of interrupt ids that are pending without corresponding resume values."""
...
# Keep only interrupts whose interrupt_id is not resumed
hanging_interrupts = { ... }
```

它专门维护"没有被 resume 的挂起中断"集合。配合 `types.py:811`（`Command.resume` 支持 **"Mapping of interrupt ids to resume values"**），可以确认：

> 官方预期**一个 thread 上可以同时挂多个中断**，恢复时按 id 指定。

对 HITL 这是合理的（多个审批并行）。对异步任务，这就是麻烦的开始。

**证据 D —— 从旧检查点恢复会开分支**【核心】

`libs/langgraph/langgraph/pregel/main.py:1819` / `:2282`，复制检查点时写入元数据：

```python
{
    "source": "fork",
    "step": step + 1,
    "parents": ...,
}
```

〔推理〕从 1 小时前的检查点恢复，等于在检查点树上从那个点分叉；中间 30 轮对话成为兄弟分支，不在 HEAD 路径上。UI 要么显示分叉历史，要么用户这 1 小时的工作被丢。

### 4.3 四种具体故障

把上面的机制翻译成用户能感知的现象：

| # | 故障 | 机制来源 | 用户看到什么 |
|---|---|---|---|
| 1 | **悬空中断堆积** | 证据 B/C | 聊了 20 轮、发了 2 个任务后，thread 上挂着 3 个陈年中断，前端不知道该恢复哪个 |
| 2 | **分叉** | 证据 D | 恢复 1 小时前的中断，要么出现两条历史，要么中间的对话消失 |
| 3 | **重复执行** | 证据 A | 从旧检查点继续，`submit_integration` 被再执行一次——任务重复提交 |
| 4 | **上下文错位** | 推理 | 模型看到的是 1 小时前的世界，据此做出已经过时的判断（"给张三发邮件"，但张三的事半小时前已处理完） |

再叠加一个 UI 层面的错用：interrupt 的交互语义是"等你一个答复"，用它承载 1 小时任务，前端要么挂 1 小时 loading，要么显示一个永远不会消失的审批框。

### 4.4 根因一句话

```
interrupt  →  暂停点 = 调用栈位置 = 检查点 = 对话的"唯一下一步"
异步等待   →  对话可以往前走
```

**调用栈天然是单线程、不可并行的，而对话是要继续的。这两件事放在同一个结构里必然冲突。**

### 4.5 那 interrupt 什么时候还是对的

判据只有一句：

> **用户的下一条消息，是不是就是这个等待的答案？**

| 场景 | 下一条消息是答案吗 | 用什么 |
|---|---|---|
| 审批通过/拒绝 | 是 | ✅ interrupt |
| 补一个缺失参数 | 是 | ✅ interrupt |
| A/B 方案二选一 | 是 | ✅ interrupt |
| 跑批 / 数据集成 / 报表生成 | 不是 | ❌ 用事件注入 |
| 风控审核排队 | 不是 | ❌ 用事件注入 |

即使是 interrupt，也要保证恢复落在**当前 HEAD**。如果期间用户发了新消息，说明他绕过了这道门——那这道门就不该是硬中断，应该是软提示。

### 4.6 一个更准确的表述

与其说"不要用 interrupt 做异步"，不如说：

> **不要把等待放进调用栈。**
> 把等待放进调用栈，你就必须让对话停下来；
> 把等待放进收件箱，对话就可以继续。

下一节讲收件箱怎么工作。

---

## 5. 事件投递机制：从头讲一遍

### 5.1 先破除一个误解：模型不是常驻进程

你调用模型一次，它回答一次，然后它"消失"了。下一次调用它是全新的存在，它不知道中间发生了什么。

所以这句话**不成立**：

> "agent 监听 MQ，收到消息后知道自己有任务完成了"

模型不会监听任何东西。监听 MQ 的是一段普通程序。

这里有两个东西容易混：

| 名字 | 是什么 | 特点 |
|---|---|---|
| **agent 服务** | 一段常驻程序 | 有进程、能监听 MQ、能读写数据库 |
| **agent（模型）** | 一个函数 | 被调用时才有，调完就没了 |

两者都叫"agent"，是混乱的根源。

**一句话**：**"感知"和"读取"是同一件事——在被调用的那一刻，把信塞进它的输入里。**

### 5.2 一个比喻

把模型想象成**只在被叫进办公室时才睁眼的人**：

- 他不在办公室时，外面发生了什么他完全不知道
- 他没有手机，不能主动看收件箱
- 想让他知道一件事，只有一个办法：**下次叫他进来时，把便签贴在他面前的桌上**

对应关系：

| 概念 | 现实对应 |
|---|---|
| 信箱 | 秘书桌上放便签的盒子（一张数据库表） |
| 程序 | 秘书，负责收信、放便签 |
| "感知有事件" | 秘书决定"该叫他进来了" |
| "读取事件" | 他进来坐下，看到桌上的便签 |

他没有"感知"这个动作，**是被安排看到便签的**。

### 5.3 完整时间轴

以 1 小时数据集成举例：

```text
10:00:00  用户：帮我集成 A→B

10:00:02  agent 调用 submit_integration → 拿到 task_123
10:00:03  agent 回复："已受理，预计 40 分钟，跑完我告诉你"
          ← 这一轮结束。模型"下班消失"了。

10:00:03 ~ 10:40
          模型：完全不存在，没有任何调用。
          但 agent 服务还活着，一直挂着等 MQ。

10:40:00  业务系统往 MQ 发消息：task_123 完成
10:40:01  agent 服务的 MQ 消费者收到
          → 往信箱表里插一行：
            { 会话: sess-888, 类型: 完成, 内容: "...", 状态: 待读 }

10:40:01  接下来这一步是关键 ↓
```

### 5.4 "如何感知"：程序查一下，只有两种结果

MQ 消费者插完那一行之后，程序会查一个问题：

> **这个会话现在有人用吗？**

**情况 A：空闲**（用户没在对话，模型没在跑）

程序**直接调用模型**，把信箱里那条拼进输入。模型"醒过来"，看到消息，生成回复，前端推给用户。

这就是**唤醒**（wakeup）。

**情况 B：繁忙**（用户正在聊，或 agent 正在跑工具）

程序**不打断**，只把那条标成"待读"，然后什么都不做。

等当前这一轮/这一步跑完，在下一次调模型之前，把待读的消息一起拼进去。模型在"下一步"自然就看到。

**只有这两种情况。** 因为模型没有"运行中"这个状态——它不是线程，没法被打断。

### 5.5 "何时读取"：永远是下一次被叫进来的时候

| 时机 | 什么场景 |
|---|---|
| **步骤之间** | agent 正在干活，刚跑完一个工具，要调下一次模型 |
| **新一轮开始** | 上一轮结束了，现在要开新的（被事件唤醒，或用户发消息） |
| **会话恢复** | 用户第二天打开这个会话，历史一起加载 |

注意：**模型不是"去读信箱"，是信箱内容被塞进它的输入里。**

这两者差别很大：前者意味着模型有主动查询能力（它没有），后者意味着模型只是被动接收拼好的材料。

### 5.6 伪代码：看这个循环就懂了

```python
# 这是 agent 服务，一段常驻程序
mailbox = []       # 信箱。真实系统里就是一张数据库表
running = False    # 模型现在是不是在跑

# ---------- 收到 MQ 消息 ----------
def on_job_completed(msg):
    mailbox.append({
        "task_id": msg.task_id,
        "text": f"任务 {msg.task_id} 完成：成功 9，失败 2",
        "status": "pending"
    })
    if not running:
        wake_up()      # 空闲 → 立刻叫醒
    # 繁忙 → 什么都不做，等它自己下一步来拿

# ---------- 叫醒 = 再调一次模型 ----------
def wake_up():
    global running
    running = True

    while True:
        # ↓↓↓ 这就是"读取信箱"：每次调模型前检查一遍
        pending = [m for m in mailbox if m["status"] == "pending"]
        for m in pending:
            m["status"] = "delivered"

        reply = llm.chat(
            system=SYSTEM_PROMPT,
            messages=history + pending,   # ← 信箱内容拼进输入
            tools=TOOLS
        )
        history.append(reply)

        if reply.has_tool_calls:
            run_tools(reply.tool_calls)
            continue          # ← 回到循环顶部再检查一次 pending
                              #   这个 continue 就是"步骤之间投递"
        else:
            break             # 没有工具调用 = 这一轮结束

    running = False
    push_to_frontend(reply)
```

三个关键点：

| 代码 | 对应的问题 |
|---|---|
| `mailbox.append(...)` | 事件写进信箱 |
| `if not running: wake_up()` | "感知"机制 |
| 循环顶部的 `pending` 过滤 | "读取"时机 |

模型自始至终**不知道信箱的存在**。它只是每次醒来时桌上多了一张便签。

### 5.7 信箱其实就是一张表

```sql
CREATE TABLE inbox (
  id          BIGINT PRIMARY KEY,
  session_id  VARCHAR(64),   -- 这条给哪个会话看
  type        VARCHAR(32),   -- job_done / job_failed / milestone
  content     TEXT,          -- 给模型看的话
  status      VARCHAR(16),   -- pending / delivered / discarded
  created_at  TIMESTAMP
);
```

`status` 是最关键的字段：

- `pending` = 还没给模型看过
- `delivered` = 已经塞进 prompt 了
- `discarded` = 作废（比如用户已经取消了任务）

**所谓"事件驱动"，驱动的是"服务要不要现在调一次模型"，不是模型去检查什么。**

### 5.8 为什么必须这么设计

因为模型每次被调用，都要把**全部上下文重新读一遍**。

如果让模型自己去查信箱：

- 查一次 = 一次模型调用 = 几万 token
- 1 小时查 120 次 = 几百万 token
- 其中 119 次都是"没有新消息"的空转

而程序查一张表是**微秒级、零 token** 的。

> **用程序的"眼睛"盯着表，只在有新东西时才花钱叫模型。**

**"轮询"没有消失，它只是从模型层下沉到了程序层，于是变得免费了。**

### 5.9 工业实现会踩的五个坑

| # | 坑 | 后果 | 对策 |
|---|---|---|---|
| 1 | 重复投递 | 模型看到两份完成 | 按 `task_id` 去重 + 原子 notified 标记 |
| 2 | 会话已销毁 | 信没人读 | 转存"用户级消息中心"，或明确丢弃并告警 |
| 3 | 模型抢跑 | 模型自己查过结果，事件又来一遍 | 检测到已读取 → **撤回**未投递的事件 |
| 4 | 一次来 5 封 | 调 5 次模型 | 合并成一次投递 |
| 5 | 自激 | 被唤醒 → 发新任务 → 完成又唤醒…… | 设连续唤醒预算上限 |

这五条在 §6 的三家实现里都能找到对应机制，不是理论推演。

---

## 6. 业界实现对照

> engineering.md §7 已给出四家 harness 的产品级实证与结论（"无一例外全是事件注入派"）。本节只补**投递粒度**与**防坑机制**两处细节，作为本次证据升级。

### 6.1 投递粒度：三个不同的切法

| 实现 | 投递发生在 | 依据 |
|---|---|---|
| **Claude Code** | 轮次边界（between-turn drain） | 【还原源码】 |
| **DeepSeek Harness** | 步骤边界（步骤之间就领）+ 轮次边界（空闲唤醒） | 【随包文档】+【源码】 |
| **MCP Tasks / A2A** | 任务对象状态变更，由客户端订阅 | 【一手】/【摘要】 |

**Claude Code**：`restored-src/src/utils/messageQueueManager.ts:157-166` 的 `dequeue` 注释原文：

> This lets **between-turn drains** (SDK, REPL) restrict to main-thread commands...

`src/coordinator/coordinatorMode.ts:168` 更直白：

> Each "You:" block is a separate coordinator turn. The "User:" block is a `<task-notification>` **delivered between turns**.

**DeepSeek Harness** 往下切了一刀，`@deepseek-ai/dsh-agent-loop/README.zh.md`：

> 在轮次边界，它先打开持久轮次，再原子领取待处理的 next-step 输入与一条排队提示词；**在步骤之间则只领取 next-step 输入。**

配合 `@deepseek-ai/dsh-tool-jobs/README.zh.md`：

> 繁忙的 agent 会在**下一步**收到注入的通知——**inbox 尚有内容时轮次无法结束**，因此同时结算的多个任务只花掉一步，而不是各占一轮。空闲的 agent 则被一个 **follow-up 轮次唤醒**。

两个值得抄的细节：

1. **步骤中间就能收到**，不必等这一轮收尾，模型能更早改计划
2. **inbox 有内容时轮次不允许结束**，保证"同时完成 5 个任务只花 1 步"

### 6.2 防坑机制对照

| 坑（§5.9） | Claude Code | DeepSeek Harness |
|---|---|---|
| 重复投递 | 原子 `notified` 标记【还原源码】 | `awaited` 状态 + 撤回待领通知【随包文档】 |
| 结果太大 | 只给 `<output_file>` 路径 | 超 `inlineOutputBytes`（默认 2048）转 `job_output` |
| 输出丢失 | 文件持久化 | "从未抵达模型的通知会把输出留给 `job_output`" |
| 自激 | — | `maxConsecutiveWakes` 预算，用户发言重置 |
| 被抢跑 | `notified` 标记 | 读取会**撤回**待领通知 |
| 卡死检测 | `STALL_CHECK_INTERVAL_MS` 轮询输出文件 | 心跳/进度行 |

### 6.3 一条最有说服力的证据

Claude Code 的 `TaskOutputTool`——**一个专门用于轮询任务状态的工具——已被标记 DEPRECATED**。`restored-src/src/tools/TaskOutputTool/TaskOutputTool.tsx:173`：

> DEPRECATED: Prefer using the Read tool on the task's output file path instead. Background tasks return their output file path in the tool result, and you receive a `<task-notification>` with the same path when the task completes — Read that file directly.

**"轮询工具"被"完成通知 + 产物文件"取代并弃用**，这是业界实践里最直接的一条表态。

### 6.4 但别急着宣布轮询死刑

同一个文件里，`src/coordinator/coordinatorMode.ts:136` 有一条反例：

> Events arrive as user messages. Merge conflict transitions do NOT arrive — GitHub doesn't webhook `mergeable_state` changes, so **poll** `gh pr view N --json mergeable` if tracking conflict status.

**能推的推，推不了的定向轮询。** 判断标准是**上游有没有事件源**，不是"轮询好不好"。

### 6.5 语言层面的现实：事件只能借用 user 槽位

这是工程落地时绕不过去的一个细节，也是让人觉得"诡异"的地方。

主流 API 里，`system` 不是一个能随便在对话中间插的角色：

| API | system 放在哪 | 能中途插吗 |
|---|---|---|
| Anthropic Messages | 独立参数 `system`，不在 messages 数组 | ❌ |
| OpenAI Responses | 独立参数 `instructions` | ❌ |
| Gemini | 独立参数 `systemInstruction` | ❌ |
| OpenAI Chat Completions | messages 数组里，但各家行为不一致 | ⚠️ 不通用 |

所以想让模型"在对话进行中知道一件新事"，能用的槽位基本只剩三个：`user`、`tool` 结果、`assistant`。

`tool` 结果只在"正好有个工具调用在等返回"时才用得上，不通用；`assistant` 语义反了。

**结论：只能写进 `user` 槽位。** 这就是为什么 Claude Code 和 DSH 都这么做。

Claude Code 的处理方式（`src/coordinator/coordinatorMode.ts:144`）：

> Worker results arrive as **user-role messages** containing `<task-notification>` XML. **They look like user messages but are not.** Distinguish them by the `<task-notification>` opening tag.

连官方都得专门写一句"它长得像用户消息，但它不是"。

实际注入的形状：

```xml
<task-notification>
<task_id>task_123</task_id>
<status>completed</status>
<summary>数据集成完成：成功 9，失败 2</summary>
</task-notification>
```

四个手段消掉诡异感：

1. **XML 标签包裹**——模型一看就知道是结构化事件，不是人话
2. **措辞明确**——不写"我完成了"，写"任务 task_123 完成"
3. **UI 区分渲染**——前端画成灰色卡片/系统消息条
4. **提示词里点名**——告诉模型"看到 `<task-notification>` 说明是系统事件，不要当成用户指令"

若自建 agent 且完全控制 prompt 组装，可以做得更干净（把事件拼在独立段落里），但会失去"多轮对话天然延续"的模型反应习惯。**这是权衡，不是对错。**

---

## 7. 进度反馈：三条通道，各管一段

这一节回答一个常见困惑：

> "轮询子任务明细表能算出进度，但一直轮询就没法跟用户说话；事件投递又反馈不了进度——怎么办？"

### 7.1 先把三件事拆开

"知道进度"其实是三个独立能力，成本差得很远：

| 能力 | 谁需要 | 频率 | 成本 |
|---|---|---|---|
| **查状态** | 前端、agent（按需） | 秒级 | 几乎为 0 |
| **展示进度** | 前端 | 秒级 | 0，不经过模型 |
| **跟用户说进展** | agent | 分钟级/里程碑级 | 每次一次模型调用 |

困惑来自"只有 agent 开口才算告知用户"这个假设。实际上有三条通道。

### 7.2 三通道架构

```text
                任务中心（子任务明细表）
                          │
        ┌─────────────────┼──────────────────┐
        │ ① 秒级            │ ② 分钟级           │ ③ 终态
        ▼                 ▼                  ▼
    前端进度条          里程碑事件           完成事件
   （SSE 直连）        → agent 说一句       → agent 汇总
    0 token            一句人话              一次调用
        │
        └── 用户随时可问："到哪了？"
              agent 查一次 → 答一句（按需，不预播）
```

**通道 ①：进度条，不经过模型**

前端直接订阅任务中心，比如 `GET /integration/{id}/progress`（SSE，或 2 秒轮询）：

```text
[██████░░░░] 6/11 完成 ｜ 正在跑：客户主数据校验 ｜ 预计还需 18 分钟
```

这条通道**永远最新、零 token、不占会话**。

**通道 ②：里程碑事件，经过模型但很少**

只在"值得说一句"的时候发：

- 阶段切换："抽取完了，开始清洗"
- 子任务失败："订单表清洗连续失败 3 次，已跳过"
- 需要决策："字段 X 找不到映射，要人工指定吗"
- 明显卡住："15 分钟没动静了"

一个 1 小时任务，大概发 3~5 条。

**通道 ③：终态事件，只发一次**

完成/失败/取消，带汇总和产物引用。

### 7.3 "事件投递无法反馈进度"是个误解

事件能带进度，关键是**节流**：

| 策略 | 规则 | 适合什么 |
|---|---|---|
| 按时间 | 每 10 分钟最多一条 | 平稳推进 |
| 按变化 | 阶段变了才发 | 阶段清晰 |
| 按异常 | 只有失败/阻塞/要决策才发 | 用户不关心细节 |

**反例**：把每个子任务的完成都做成事件 → 11 个子任务 = 11 次模型调用，比 30 秒轮询 120 次省得有限，而且用户被刷屏。

原则：

> **事件不是"状态采样"，是"值得打断用户的时刻"。**
> 状态采样属于通道 ①，不属于事件流。

这也正好对上 §6.2 里 DSH 的做法：**进度不进事件，进状态行/进度行；事件只在结算时发。**

### 7.4 "一直轮询就没法跟用户说话"——对，但别让 agent 解决

这一条是准确的：**在一个轮次里，agent 要么在跑，要么在说话，不能同时。** 这是轮次模型的本质，改不掉。

正确的应对不是"让轮询不阻塞对话"，而是**把播报这件事从 agent 身上拿掉**：

| 用户想知道 | 由谁答 | 怎么答 |
|---|---|---|
| 现在几成 | 前端进度条 | 直连任务中心，实时刷新 |
| 到哪一步了 | 前端 + 用户主动问 | 用户问 → 新一轮 → agent 查一次答一句 |
| 出问题了吗 | 里程碑事件 | 失败/卡住时唤醒 agent 说一句 |

这样 agent 在"等"的时候是**空闲**的，不占轮次，用户随时能发消息。用户发消息时，任务可能还在跑，agent 查一下当前状态回答即可，**不需要打断任何正在跑的东西**。

> **"等待"和"播报"本来就该分给两个不同的人做。** 让 agent 边等边说，是最贵、最笨的方案。

### 7.5 并行子任务的进度怎么算才不骗人

并行任务有个坑：**完成数除以总数，不等于真实进度。**

举例：11 个并行子任务，其中 1 个要跑 40 分钟，另外 10 个各 2 分钟。

- 干到第 20 分钟，10 个快的都完了
- 显示 10/11 ≈ **91%**
- 然后卡在 91% 二十分钟 → 用户以为死机

三种更诚实的表达：

| 方式 | 长什么样 | 好在哪 | 差在哪 |
|---|---|---|---|
| 加权进度 | 按预估耗时加权算百分比 | 时间维度准 | 得先有预估 |
| 阶段 + 计数 | "清洗阶段 6/11" | 不假装精确 | 颗粒粗 |
| 三态 | "进行中 / 有失败 / 已卡住" | 最诚实 | 信息少 |

**推荐：阶段 + 计数 + 心跳，别给单一百分比。**

```jsonc
{
  "phase": "清洗",
  "done": 6, "total": 11, "failed": 1,
  "last_heartbeat_seconds_ago": 12,
  "eta_seconds": 1080,
  "stalled": false
}
```

因为用户真正想知道的是三件事：

1. **还在动吗？**（心跳）
2. **还要多久？**（ETA）
3. **出问题了吗？**（failed / stalled）

百分比只是这三个问题的粗糙代理。**给不准的百分比，不如不给。**

### 7.6 落到工具接口上

```jsonc
// 提交时把前端要用的地址一起给出来
submit_integration(...)
→ { task_id, eta_seconds, subtask_count,
    progress_url }        // ← 前端拿这个自己去刷

// 模型只在"用户问"或"需要解释"时才调
get_integration_progress(task_id, detail?: "summary" | "full")
→ summary: 一行人话，给模型
→ full:    子任务明细，给"用户想看细节"时
```

注意这里**没有 `wait` 参数，也没有轮询循环**。模型查一次就够，因为：

- 想看实时进度，前端已经看得到
- 想要终态，事件会来
- 用户问，就查一次答完

---

## 8. 凭证生命周期：长任务不能用用户 cookie 跑

### 8.1 问题的提出

如果一个 agent 服务调用业务 API 用的是**用户的 cookie**（转发浏览器会话凭证），那么：

> 用户长时间未操作 → 登录态过期 → cookie 失效 → agent 调不动了？

**是。而且问题比"调不动"更严重：任务还在跑，但用来查询/写入的凭证失效了。**

### 8.2 失败时间轴

```text
10:00  用户点"开始集成"
       agent 用用户 cookie 调业务 API → 提交成功
       cookie 此刻有效 ✓

10:05  用户去开会了，不再操作

10:35  cookie 因"30 分钟无操作"过期

10:40  agent worker 想查进度 → 带过期 cookie → 401
10:45  任务其实在业务系统里跑得好好的（它不关心 cookie）

11:00  任务完成
       worker 想取结果 → 还是 401

11:05  结果拿不回来。用户回来一看："任务状态未知 / 失败了"
```

**最糟的结局：任务成功了，但结果永久丢失，并且用户被告知失败。**

### 8.3 失效不止一种

| 失效原因 | 触发条件 | 心跳能救吗 |
|---|---|---|
| 空闲超时 | 30 分钟没操作 | ✅ 能缓解 |
| **绝对超时** | 登录满 8 小时必失效 | ❌ 不能 |
| 用户主动登出 | 关电脑前点了退出 | ❌ 不能 |
| 多端互踢 | 用户在手机上又登录一次 | ❌ 不能 |
| 服务重启 | 会话存在内存里 | ❌ 不能 |

后四种都救不了。**所以"保活"不是解法，只是拖延。**

### 8.4 更隐蔽的问题：cookie 本来就不该在服务端用

cookie 是给浏览器用的。复制到服务端调接口会遇到：

- **User-Agent 对不上**：浏览器是 Chrome，你的 Python 请求是 `python-requests/2.x`
- **IP 对不上**：用户在办公室，你的服务器在机房
- **CSRF token 缺失**：很多系统对非 GET 请求会校验
- **会话指纹校验**：有些系统绑定设备指纹

结果：**即使 cookie 没过期，也可能被风控拦下来。**

这条路从长期看，不只是"会过期"，而是"本来就不稳"。

### 8.5 根本错误，一句话

> **用户凭证的有效期，必须覆盖使用它的调用链的完整时长。**

如果调用链要跑 1 小时，凭证至少得有 1 小时有效期。做不到，就是设计错误。

由此推出硬规则：

> **任何可能超过凭证有效期的操作，都不能用用户凭证去跑。**

### 8.6 正确做法：凭证只用于"发起"，不用于"执行"

```text
【提交时】用户一定在线，cookie 一定有效
   用户 ──cookie──▶ agent ──▶ 业务系统
                               │
                               ├─ 校验用户身份
                               ├─ 记录：这个任务归 user_123
                               └─ 返回 task_id

【执行时】用服务身份，跟用户登录态无关
   业务系统任务中心 ──▶ 自己跑完 ──▶ 结果落库

【收尾时】agent 用服务身份去取
   agent ──服务账号──▶ 业务系统：给我 task_123 的结果
                        （系统内部知道它归 user_123）
```

**用户身份只在"提交"那一瞬间被使用一次，之后全部解耦。**

这样做还顺带解决了权限问题：业务系统自己知道任务归属谁，你不需要一直扮演那个用户。

### 8.7 四档方案

| 档位 | 做法 | 改动成本 | 效果 |
|---|---|---|---|
| **① 服务账号 + 代表用户** | 申请 API key / client credentials，请求里带 `X-On-Behalf-Of: user_123` | 中（要业务系统配合） | 彻底解决 |
| **② OAuth 令牌交换** | RFC 8693 Token Exchange，用用户 token 换一个代表该用户的短期服务 token | 中高 | 彻底解决，权限最精确 |
| **③ 网关代持会话** | 用户登录时把 refresh token 交给网关，网关负责续期和转发 | 中 | 能缓解，绝对超时仍无解 |
| **④ 心跳保活** | 定时用 cookie 打轻量接口 | 低 | 只缓解空闲超时，可能触风控，**不建议当主方案** |

### 8.8 业务系统一时改不了，怎么过渡

按这个顺序降级：

| 降级 | 做法 | 代价 |
|---|---|---|
| 1 | **把长任务拆短**：只允许在凭证有效期内跑完的任务 | 能力受限 |
| 2 | **人要在线**：前端心跳保活，用户离开就取消任务 | 体验差，但结果不丢 |
| 3 | **结果落业务系统**：agent 只告诉用户"去任务中心看" | agent 拿不到结果 |
| 4 | **接受丢失 + 告警**：记录因凭证过期未回收的次数 | 推动改造时有数据 |

**注意：任何降级方案都不能改变一个事实——任务本身在业务系统里是跑得完的，只是 agent 拿不到结果。**

### 8.9 拿去问业务系统的七件事

1. 会话是**空闲超时**还是**绝对超时**？各多久？
2. 有没有服务账号 / API key / client credentials？
3. 支不支持"代表用户"（On-Behalf-Of）调用？
4. 会话过期后，**已提交的任务会中断还是继续跑**？
5. 任务结果存在哪？能不能用服务身份取？
6. 有没有"用户离线也能完成"的先例（报表导出、批量导入）？
7. 非浏览器客户端（无 UA、无 CSRF）调接口，会被风控拦吗？

**第 6 题最关键**——如果业务系统已有离线任务先例，说明它有现成的服务身份通道，你只是没用上。

---

## 9. 反模式清单

| # | 反模式 | 为什么错 |
|---|---|---|
| 1 | 在 tool 内部 sleep 到任务结束 | 连接必断，沙箱必杀 |
| 2 | 在 description 里写"每 5 秒查一次" | 模型会热轮询（Claude Code 有公开 bug 报告） |
| 3 | 状态查询返回整个任务详情大 JSON | 轮询成本 ×120 |
| 4 | 用 `failed` 表达"还在跑"或"需要补料" | 应该用 `input_required` |
| 5 | 没有 `cancel` | 1 小时任务跑错了只能等它跑完 |
| 6 | 没有幂等键 | agent 的重试比任何客户端都激进 |
| 7 | 只回 `running` 不给心跳/进度 | 模型无法区分"慢"和"卡死"，只能重试 |
| 8 | 用 interrupt 承载长任务 | 悬空中断 / 分叉 / 重放（§4） |
| 9 | 把每个子任务完成都做成事件 | 比轮询还贵，还刷屏（§7.3） |
| 10 | 让 agent 在等的时候播报进度 | 占着轮次说不了话，且最贵（§7.4） |
| 11 | 事件挂在 session 上 | 会话销毁，事件跟着丢（§5.9 坑 2） |
| 12 | 长任务用用户 cookie 跑 | 凭证过期即结果丢失（§8） |

---

## 10. 落地检查清单

### 10.1 等待方式

- [ ] 给每个 tool 显式标注预期时长档位（秒级/十秒级/分钟级/小时级）
- [ ] 超过 1 分钟的操作用"提交 + 句柄"，不做同步 tool
- [ ] 慢操作绝不伪装成同步工具

### 10.2 任务句柄

- [ ] `submit` 返回：`task_id` + 状态 + ETA + 建议查询间隔 + 取消入口
- [ ] `status` 返回：阶段 / 已完成数 / 总数 / 失败数 / 心跳时间 / `stalled`
- [ ] `cancel` 透传到业务侧，不只断 agent 这跳
- [ ] 句柄跨会话可寻址（不绑会话 ID）
- [ ] 提交收幂等键并透传业务侧

### 10.3 事件投递

- [ ] 用**事件注入**，不用 interrupt（除 HITL）
- [ ] 事件在**轮次/步骤边界**投递，不抢占正在跑的轮次
- [ ] 事件带 `task_id` / 发起时间 / 摘要 / 产物引用 / 失效条件
- [ ] 投递幂等（同 task_id 只投一次）
- [ ] 模型已读取则**撤回**未投递事件
- [ ] 一次多条合并成一次投递
- [ ] 设连续唤醒预算上限

### 10.4 进度呈现

- [ ] 进度条由前端**直连任务中心**，不经过模型
- [ ] 里程碑事件按时间/变化/异常三种策略节流
- [ ] 并行任务用"阶段 + 计数 + 心跳"，不给单一百分比
- [ ] 用户主动问进度时，agent 查一次答一句（不预播）

### 10.5 凭证

- [ ] 长任务不用用户 cookie
- [ ] 提交时固化归属，执行与收尾用服务身份
- [ ] 结果交付不依赖用户登录态（预签名 URL / 任务中心）
- [ ] 记录因凭证过期导致的结果未回收次数

### 10.6 存储归属

- [ ] 事件挂在 **user 级** outbox，不挂在 session 级 inbox
- [ ] 会话销毁后未读事件仍可被用户取回
- [ ] 提供"我发起的任务"入口

---

## 11. 证据与基线

### 11.1 本轮基线

| 对象 | 基线 | 形态 | 证据等级 |
|---|---|---|---|
| `langgraph` | `e539ac122`（2026-09-09） | 复用已有克隆 | 【核心】/【核心-文档】 |
| `claude-code-sourcemap` | `a8a678c`（还原自 `@anthropic-ai/claude-code@2.1.88`） | 复用已有克隆 | 【还原源码】 |
| DeepSeek Harness | desktop `0.2.2-rc.1`（asar 内 `runtime.json`） | 直接解析 `app.asar` | 【随包文档】/【源码】 |
| MCP Tasks | `ext-tasks` 2026-07-28 schema | 沿用 engineering.md 附录 | 【一手】 |
| ChatGPT / Deep Research | 产品行为 | 未对码 | 【转述】 |

### 11.2 关键锚点

**LangGraph**

| 位置 | 内容 |
|---|---|
| `libs/langgraph/langgraph/types.py:851-868` | `interrupt()` docstring："enables human-in-the-loop workflows" / "resumes from the start of the node, re-executing all logic" |
| `libs/langgraph/langgraph/types.py:811` | `Command.resume` 支持 "Mapping of interrupt ids to resume values" |
| `libs/langgraph/langgraph/pregel/_loop.py:819-846` | `_pending_interrupts()`：统计未被 resume 的挂起中断 |
| `libs/langgraph/langgraph/pregel/_loop.py:858-880` | `_first()`：`input is None`/`Command` 才算恢复，新输入是全新运行 |
| `libs/langgraph/langgraph/pregel/main.py:1819` | 复制检查点写入 `"source": "fork"` |

**Claude Code（还原源码）**

| 位置 | 内容 |
|---|---|
| `restored-src/src/tasks/LocalShellTask/LocalShellTask.tsx:105-168` | `enqueueShellNotification()`：构造 `<task-notification>` 并入队 |
| `restored-src/src/utils/messageQueueManager.ts:142-166` | `enqueuePendingNotification()` / 优先级 `now/next/later` / `dequeue` 的 between-turn 注释 |
| `restored-src/src/utils/messageQueueManager.ts:423` | 通知模式留在队列中待自动处理 |
| `restored-src/src/coordinator/coordinatorMode.ts:144` | "They look like user messages but are not" |
| `restored-src/src/coordinator/coordinatorMode.ts:168` | "<task-notification> delivered between turns" |
| `restored-src/src/coordinator/coordinatorMode.ts:136` | mergeable_state 无 webhook → 定向轮询 |
| `restored-src/src/tools/TaskOutputTool/TaskOutputTool.tsx:173` | 轮询工具 DEPRECATED |

**DeepSeek Harness（asar 内）**

| 位置 | 内容 |
|---|---|
| `@deepseek-ai/dsh-tool-jobs/README.zh.md` | 完成通知、`inlineOutputBytes`、`maxConsecutiveWakes`、`awaited`、撤回、等待被 steer 打断 |
| `@deepseek-ai/dsh-agent-loop/README.zh.md` | 轮次边界领 next-step + 一条提示词；步骤之间只领 next-step |
| `@deepseek-ai/dsh-tool-schedule/README.zh.md` | 定时任务作为普通 follow-up 消息投递到目标 Session |
| `@deepseek-ai/dsh-tool-jobs/lib/index.js` | `inlineOutputBytes` / `maxConsecutiveWakes` / `awaited` / `steered` / `agent/inbox/claimed` 等符号实测存在 |

### 11.3 已知边界与后续

- 〔推理〕标注的四处（分叉在 UI 的表现、token 量级、上下文错位的影响、fork 后 HEAD 语义）未做运行时实测，属于基于源码语义的推断。
- DSH 只读了随包 README 与关键符号，未通读 `lib/index.js` 的完整投递实现；其 `maxConsecutiveWakes` 的精确计数边界未验证。
- ChatGPT Tasks 的投递行为为转述级，未对码。
- `interrupt` 的多中断恢复顺序在真实异步场景下的行为，建议用最小复现实验验证后再写进团队规范。
