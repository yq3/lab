# L2.3 ReAct 循环：把零件装成 agent

## 1. 本课目标

前三课的零件今晚合体：`messages` 协议 + 工具注册表 + 客户端抽象，装成一个
**真正的 agent 循环**。完成后你能：

- 手写 ReAct 循环（讲义版 `agent.py` 81 行，含文档注释；裸逻辑约 60 行）——注册契约、
  模型选工具、执行回喂、终止、轮数预算，一个不少；
- 用 `typing.Protocol` 定义 `ModelClient`，让「真实端点」与「离线脚本」可互换——
  L1.2 结构化类型的第一次实战兑现，agent 的可测试性由它而来；
- 说清**双终止条件**：软终止（模型不再要工具，概率性）与硬终止（`max_turns` 预算，
  确定性），以及为什么缺硬终止的循环是生产事故；
- （加餐）写朴素上下文管理：字符近似 token 计数 + 保 system、不拆 tool 配对的裁剪。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `while (true) + switch` 状态机 | ReAct while 循环 | 分支判断由模型输出驱动——审计问题从「转移全吗」变「出口谁说了算」（§5） |
| 面向接口编程 + Mockito 造替身 | `ModelClient` Protocol + `ScriptedModel` | 结构化类型不要求 implements，普通类长成形状就算数 |
| 线程池拒绝策略 / 超时兜底 | `max_turns` 轮数预算 | 确定性护栏对冲概率性软终止 |
| 有状态会话（WebSocket session） | messages 全量重发 | 无状态协议：对话状态全在客户端的 list 里 |
| LRU 逐出 / 缓存容量管理 | `trim_messages` 裁剪 | 视图可裁、档案不动；system 与 tool 配对是硬约束 |

### 2.1 ReAct：一个词和一个循环

ReAct = **Rea**soning + **Act**ing：模型「想一步、做一步、看结果、再想」。
落到代码就是一个 while 循环——这也是「agent」与「一次聊天补全」的全部区别：

```text
messages = [system, user]
循环：
    response = 模型(messages, tools)          # ① 请求（无状态：历史全量重发）
    assistant = response.choices[0].message
    messages.append(assistant)                # ② 模型的消息原样入史
    if assistant 没有 tool_calls:
        return assistant.content              # ③ 软终止：模型认为任务完成
    for tool_call in assistant.tool_calls:    # ④ Act：执行全部工具调用
        result = run_tool(name, arguments)    #    L2.2 的注册表分发（错误回喂不抛）
        messages.append({"role": "tool", "tool_call_id": id, "content": result})
```

LangGraph 的 `create_react_agent`、openai-agents 的 `Runner.run`、cookbook 原典的
`run_full_turn`——骨架都是这十行。你在 Unit 3 每个框架课都会回来对照：**这层抽象
替我付掉的代码，就是这十行，加上可观测性、检查点、并发调度**。

对照 Java：这是一个 `while (true) + switch` 的状态机，只不过「分支判断」由模型输出
驱动。Java 人熟悉的状态机审计法在这里要换一个问题：不是「状态转移全吗」，而是
**「循环的出口有几个、每个出口谁说了算」**（§5 坑位的入口）。

### 2.2 `ModelClient` 协议：可测试性的支点

```python
class ModelClient(Protocol):
    async def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict: ...
```

`ReActAgent` 只依赖这个形状，不关心背后是什么。两个实现：

| 实现 | 背后 | 用途 |
|---|---|---|
| `HttpModelClient` | L2.1 的 ChatClient → 真实端点 | 真跑 |
| `ScriptedModel` | 脚本列表（`{"content": ...}` 或 `{"tool_calls": [...]}`） | 离线验收 |

L1.2 讲过：Protocol 是**结构化类型**——`ScriptedModel` 没有 `class ScriptedModel(ModelClient)`
这一行，只要长成协议的形状就算数。对照 Java：这是面向接口编程，但不需要 `implements`，
也不需要 Mockito 造动态代理——一个普通类就是测试替身。**今晚起，agent 的全部行为
都可以离线测试**：想测「模型连续要 5 轮工具」就写 5 条脚本，想测「模型回了废话」
就写一条 content 脚本。竞品课程「必须连真端点才能学」的枷锁，从今晚起不存在。

### 2.3 双终止条件：软终止与硬终止

- **软终止**：`assistant` 没有 `tool_calls` → 模型认为任务完成。它是**概率性的**——
  prompt 写得差、工具结果一直报错、模型「想再多查一单」，它就不来；
- **硬终止**：`for turn in range(1, max_turns + 1)` 跑完 → 抛 `AgentBudgetExceeded`。
  它是**确定性的**——不管模型多执着，第 N 轮一定停。

软终止是模型的自由，硬终止是你的护栏；生产代码两个都要，缺后者的循环在等一场
深夜事故（§5）。预算该设多大？经验值：简单任务 3–5 轮，多工具链 8–10 轮；
宁可小了调大，不要大了调小——token 是真金白银。

### 2.4 加餐：朴素上下文管理

无状态协议的代价：**历史每轮全量重发**（L2.1 §2.2），历史越长请求越贵、越可能
顶破模型的上下文窗口。生产框架的答案是 tokenizer 精确计数 + checkpoint 策略
（langgraph 的 checkpointer，L3.3 会实验它）；本课用「字符近似」把问题讲清楚：

```python
def estimate_chars(messages) -> int:
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
```

裁剪（`context_budget.py` 的 `trim_messages`）只有两条纪律，但都是硬的：

1. **system 永远保留**（index 0 不动）——人设丢了，后续对话全部变形；
2. **不拆 tool 配对**——裁掉一条 `assistant(tool_calls)` 后，它名下的 `tool` 消息成了
   「孤儿」，排在最前面会被端点 400 拒收（协议要求 tool 必须紧跟对应的 tool_calls）。
   所以裁剪永远发生在 index 1，且每次裁完检查排头：是孤儿就连坐裁掉。

另一个工程细节：`trim_messages` **返回新列表，不动原历史**——历史是审计证据
（哪轮调了什么工具、回了什么结果），发给模型的「视图」可以裁，档案不许裁。
这个「视图与档案分离」的想法，L5.3 事件溯源会做成一等公民。

## 3. 动手代码

先 `uv sync`。L2.1 三件套与 L2.2 的 `tools.py` / `finance.py` 原样在 `code/`。

### Step 1：离线跑一个完整 agent（15 分钟）

```bash
uv run python code/demo_agent.py
```

```text
== ReAct agent 离线跑 ==
注册表: ['get_claim', 'preapprove']
user: 请审查报销单 CLM-2026-0003。

== 消息轨迹（7 条，消耗 3 轮） ==
     system: 你是财务预审助手。先用 get_claim 查单据明细，再用 preapprove 预审，最
       user: 请审查报销单 CLM-2026-0003。
  assistant: [选了工具: get_claim]
       tool: {"id": "CLM-2026-0003", "submitter": "赵工", "pu  (id=call_001)
  assistant: [选了工具: preapprove]
       tool: REJECT:INVALID_AMOUNT  (id=call_002)
  assistant: REJECT:INVALID_AMOUNT（报销单含负数金额明细，属脏数据）。

最终回答: REJECT:INVALID_AMOUNT（报销单含负数金额明细，属脏数据）。
```

对着轨迹数一遍 §2.1 的循环：两个工具轮（Act）、最后一个回答轮（Rea 的收束）。
工具是**真实执行**的——`get_claim` 读的是 `data/expense/budget_mock.json`，
`preapprove` 吐的是 L0.1 规则的四态结论；`ScriptedModel` 只负责「替模型做选择」。

### Step 2：预算护栏的实测（10 分钟）

```bash
uv run python code/demo_budget.py
```

```text
== 执念模型 × 5 轮预算 ==
AgentBudgetExceeded: 5 轮预算耗尽（历史 12 条消息仍未收敛）——检查 system 提示是否诱导无限调用，或工具结果是否总在报错。
模型实际被调用: 5 次（预算 5 轮，一次不多）
没有护栏的下场：这个剧本有 100 轮——它真的会跑满 100 轮才停。
```

「执念模型」每轮都换一张单据查、永不回答——把 `max_turns` 改成 100 试试，
你会看着它一单一单查下去：这就是没有硬终止的世界。

### Step 3：讲义区验收 + 读 agent.py（15 分钟）

```bash
uv run pytest code/
```

六个测试覆盖：两轮工具的完整跑通（角色序列、id 配对、工具真实执行）、每轮契约下发
与历史全量重发的取证、预算触发的确定性、剧本耗尽的显式报错、裁剪的两条纪律。

然后逐行读 `code/agent.py`（81 行）——每个概念都能对应到行号：`AgentBudgetExceeded`
（硬终止）、`AgentResult`（结果三件套）、`run` 的 for 循环与两个出口。明天 L2.4 的
结构化输出，就是给这个循环的「出口」再上质量闸。

### Step 4：（可选）真实端点

```bash
uv run python code/demo_agent.py --real
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。）

`HttpModelClient` 上场，循环一行不改——这就是协议抽象的回报。模型自己决定
调几张单、按什么顺序；预算 6 轮兜底。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区；实现需要的顶部 import 可以补（骨架只预置了
given 部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_agent_loop.py` | 循环核心：原样入史、id 配对、未知工具回喂不抛 |
| ex2 | `exercises/ex2_budget.py` | 硬预算：恰好 max_turns 轮触发异常、异常带轮数 |
| ex3 | `exercises/ex3_trim.py` | 上下文裁剪：system 保留、孤儿 tool 连坐、不动原件 |

三题的骨架都是自包含的迷你版（脚本模型、迷你注册表随题给定）——把你对循环的理解
写进 TODO，而不是抄讲义。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：终止条件外包坑（把 while 的出口交给模型）

这是本课的命名化失败模式——Java 人写循环的第一课是「审计出口」，agent 循环会让
你把这一课全部还回去。

- **现象**：agent「跑不动了」——日志显示循环还在转，账单在涨，最后一轮工具结果是
  `{"error": "unknown_tool: get_claims"}`（模型拼错了工具名），下一轮模型换个拼法
  继续错，永不收敛。或者更隐蔽的：system 提示写了「把所有单据都查一遍」，
  工具列表有 200 张单，模型就真的一张一张查。
- **最小复现**（`demo_budget.py` 就是它）：

  ```python
  while True:  # 没有预算的循环
      response = await client.complete(messages, tools)
      message = response["choices"][0]["message"]
      messages.append(message)
      if not message.get("tool_calls"):
          return message["content"]   # 唯一出口：模型说了算
      ...  # 执行回喂，继续循环
  ```

  模型的剧本有 100 轮工具调用——这个循环就真的跑 100 轮（每轮都是真金白银的 token）。
- **Java 直觉为何失效**：Java 人审计 `while` 会问「出口全吗、条件会收敛吗」——但
  `while (true)` + `if (模型说停) return` 在 Java 里会被 code review 打回来，在 agent
  代码里却看起来**完全正常**，因为「条件」藏在一次网络调用的返回值里，静态看不见。
  更深的差异：传统循环的终止条件是**你写的逻辑**（可推理、可单测），agent 的软终止是
  **概率性信号**（受 prompt、工具结果、温度影响）——不可静态审计的东西不能当唯一护栏。
- **修复与纪律**：双终止——`for turn in range(1, max_turns + 1)` 让预算成为结构的一部分
  （而不是循环外掐秒表）；预算耗尽抛**有名异常**（`AgentBudgetExceeded`），让上层决定
  重试、降级还是报警（L1.7 异常分层的复习）；异常信息里带轮数与历史长度——
  值班同学第一眼就要知道烧了几轮。langgraph 的 `recursion_limit`、openai-agents 的
  `max_turns` 是同一条纪律的框架化（延伸路标）。

## 6. 延伸

- openai/openai-cookbook@0aaed0f1d#examples/Orchestrating_agents.ipynb —— **对照原件**，
  今晚必读「Executing Routines」一节：官方 `run_full_turn` 与我们的 `run` 并排读，
  逐行找对应（它用 `tools_map` 分发、我们用注册表；它没有预算——你会带着 §5 的
  眼光发现原典也留着这个坑）。Unit 3 的对照问题从今晚开始积累。
- langchain-ai/langgraph@f6d95abbe#libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py ——
  `create_react_agent` 的本体（已搬进独立的 prebuilt 包）：搜工具节点装配——
  它是把今晚 81 行的循环包进 StateGraph 的产物（L3.4 会精读，先混个眼熟）。
- typing.Protocol 官方文档（结构化类型的权威定义）：
  https://docs.python.org/3/library/typing.html#typing.Protocol
- 《Fluent Python》第 2 版第 13 章（Protocol 的进阶：runtime_checkable 与静态检查的边界）。
- 各框架的预算参数对照：openai-agents 的 `RunConfig.max_turns`、langgraph 的
  `config.recursion_limit`——文档搜这两个关键词，看框架如何命名同一条纪律。

## 离毕业又近的一块

毕业设计 L5.1 的执行器就是这个循环加审批外化（跑一步、停下来等人、再继续）；
L5.4 的 fail-closed 检查链相当于给每一轮 `run_tool` 的结果再加一道纯函数闸；
今晚的 `AgentBudgetExceeded` 是 L5 成本护栏（`usage` 累计超额即停）的直系祖先。
mini-agent 的第三块肌肉（循环骨架）今晚完工——它已经能干活了，明晚教它「把结论
交成带 schema 的正式文件」。
