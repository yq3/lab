# L3.5 deepagents：harness 形态（虚拟文件系统 / 子代理 / MemoryMiddleware）

## 1. 本课目标

抽象光谱走到第三站。L3.1 的 SDK 说「我只给你原语，循环自己搭」；L3.2–L3.4 的
langgraph 说「图画出来，我按图跑」；今晚的 deepagents 说「**连图都别画了——
一行 `create_deep_agent`，我把整个工作环境发给你**」。完成后你能：

- 用 `create_deep_agent` 组装报销单审查 agent，并**以请求取证**说清「默认给了
  你什么」：8 个内置工具（文件系统 7 件 + 子代理 `task`）、一个自动追加的
  general-purpose 子代理、9999 的递归预算——以及怎么显式收窄（最小权限）；
- 说清 harness 的三件套机制与源码对应：**虚拟文件系统**（文件不在磁盘，在
  `state["files"]` 这个 channel 里）、**子代理**（声明式 spec 被包装成 `task`
  工具——handoff-as-tool 的 harness 版）、**MemoryMiddleware**（记忆文件在
  请求出栈前注入 system 消息）；
- 让审查底稿落进虚拟文件系统、把发票复核转交给子代理、用 `response_format`
  拿到 Pydantic 实例——离线零 key、确定性剧本，`uv run pytest` 全绿。

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
| Spring Boot starter 自动装配（引入即全开） | `create_deep_agent` 默认全家桶 | Java 人至少知道「约定优于配置」有开关清单；harness 的默认值**直接改模型的工具视野**（§5 坑位） |
| Filter 链 / HandlerInterceptor | `AgentMiddleware` 的 hook 族 | 洋葱包裹同构：`before_agent`（进图前）、`wrap_model_call`（改请求）、`wrap_tool_call`（包工具） |
| `ServletRequestWrapper` 包装请求再放行 | `ModelRequest.override(system_message=...)` | 不改原对象，返回改写后的请求副本——不可变风格的拦截 |
| Maven 依赖传递（只增不减） | `tools` 参数 additive | 传工具只会**追加**，删不掉内置件——要收窄得换件（`FilesystemMiddleware(tools=[...])` 原位替换） |
| 注解 + 反射生成 API 文档 | 函数签名 + docstring 推断工具 schema | langchain 拿类型注解和 docstring 直接生成发给模型的 JSON Schema，零包装代码 |
| WebSocket session（会话在服务端） | `state["files"]` 状态通道 | 无状态协议的补偿：整个「虚拟文件系统」就是 graph state 的一个键 |

### 2.1 harness：替你付掉的是「一整套工作环境」

harness 本义是马具——套在马身上的一整套挽具。放到 agent 语境：**循环你已经有了**
（langgraph 的图引擎，L3.4 精读过 `create_react_agent`），harness 在循环之上再发给你
一个工作台：

- **虚拟文件系统**：`ls / read_file / write_file / edit_file / glob / grep`——模型可以
  读写文件，但文件不在磁盘，在 graph state 里（跨轮次、可 checkpoint、可迁移后端）；
- **子代理**：`task` 工具——把「专门的活交给专门的代理」做成一等机制；
- **计划与记忆**：长任务的 todo 管理、跨会话的 `AGENTS.md` 记忆（本课讲 Memory）。

对照光谱定位一句话：**SDK 卖原语（L3.1），图引擎卖编排（L3.2–L3.4），harness 卖
工作环境（本课），平台卖托管（L3.7 dify）**。L3.6 的 adk 是「harness + 全家桶
工具链」，介于本课与平台之间。deepagents 特别适合「agent 干活」型任务（研究、
编码、审查）——因为它给模型配的是一个可以写写画画的工作台。

### 2.2 中间件模式：Java Filter 链的 Python 版

deepagents 的每个能力（文件系统、子代理、记忆、摘要、HITL）都是一个
`AgentMiddleware`，按声明顺序串成链，包在模型调用的外层。它比 Java Filter 更细：
hook 点分得很清楚——

| hook | 时机 | 本课实例 |
|---|---|---|
| `before_agent` / `abefore_agent` | 进图前，写 state | MemoryMiddleware 把记忆文件读进 `state["memory_contents"]` |
| `wrap_model_call` / `awrap_model_call` | 每次模型调用，可改写请求 | MemoryMiddleware 把记忆拼进 system 消息尾部 |
| `wrap_tool_call` | 每次工具执行，可包一层 | FilesystemMiddleware 在工具层做权限检查 |

对照 Java：`before_agent` 像 `preHandle`，`wrap_model_call` 像围着
`chain.doFilter(request)` 的环绕——请求对象不可变，改写靠副本
（`request.override(...)` ≈ `ServletRequestWrapper`）。`create_deep_agent` 的
`middleware=` 参数按 **name 原位替换**默认件（§3 Step 1 的收窄演示靠的就是这条）。

### 2.3 工具包装：这次连包装器都不用写

四个框架课看同一份 `mock_tools.py` 怎么被包装，是 Unit 3 的固定节目：

| 课 | 包装方式 |
|---|---|
| mini-agent（L2.2/L2.3） | 手写注册表 + 手拼 JSON Schema |
| L3.1 openai-agents | `FunctionTool` 显式包装 |
| **L3.5 deepagents（今晚）** | **纯函数直接放进 `tools` 列表**——langchain 从类型注解 + docstring 推断 schema |

`check_budget(dept: str) -> dict` 带着 docstring 直接传入，模型看到的工具描述就来自
docstring。这是 L1.5「装饰器 vs 注解」的续集：langchain 连装饰器都省了——**签名即
schema**。代价是你写工具时注解和 docstring 要认真写（它们是给模型看的 API 文档）。

### 2.4 默认工具族：「默认给了你什么」清单

以本课 demo 的第一个请求取证（`ep.requests[0]["tools"]`），`create_deep_agent`
默认给模型的工具：

```text
ls, read_file, write_file, edit_file, delete, glob, grep   ← 文件系统 7 件（FilesystemMiddleware 注入）
task                                                        ← 子代理转交（SubAgentMiddleware 注入）
check_budget                                                ← 我们传入的自定义工具（additive 追加）
Advice                                                      ← response_format=Advice 生成的结构化收尾工具
```

源码清单（langchain-ai/deepagents@9e7d62ff6，行号在 `#` 路径内）：

- 内置 8 件的工厂清单：`middleware/filesystem.py:1859`（tool_factories）+ `task`
  由 `middleware/subagents.py:832` 装配；
- `execute` 不在其中：它要求 backend 实现 SandboxBackendProtocol，默认的
  `StateBackend` 不满足（`graph.py:637` 默认 `StateBackend()`）；
- **自动追加 general-purpose 子代理**：一个都没声明时也会塞一个进去
  （`middleware/subagents.py:456` 的 `GENERAL_PURPOSE_SUBAGENT`，挂进 `task` 目录）；
- **递归预算默认 9999**（`graph.py:971`）——对照 L2.3 的 `max_turns` 纪律：harness
  默认「不设限」，预算责任回到你手里；
- 0.7.0 起**不再有默认 system 提示**（`BASE_AGENT_PROMPT` 已废弃，`graph.py:124`
  的 `__getattr__` 只留告警）——`system_prompt=None` 时模型收到空 system。

这份清单就是 §5 坑位的全部素材。

## 3. 动手代码

先 `uv sync`。共享模块（advice / mock_tools / review_rules / mock_endpoint）与
`test_contract.py` 和前三课字节相同；本课新增 `demo.py`（契约入口）与四个 Step
演示脚本，产出全部可复现。

### Step 1：harness 跑通离线 demo（15 分钟）

```bash
uv run python code/demo_harness.py
```

```text
== A. 同题 demo：deepagents 五轮剧本 ==
模型实际被调用 5 次：
  R1 工具清单(10): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task', 'check_budget', 'Advice']
  R2 工具清单(8): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'verify_invoice']
  R3 工具清单(8): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'verify_invoice']
  R4 工具清单(10): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task', 'check_budget', 'Advice']
  R5 工具清单(10): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task', 'check_budget', 'Advice']

-- 消息轨迹 --
  user: 请审查报销单 CLM-2026-0004：展会物料采购（发票校验未过），明细 [4200, 800] 分，部门 DEV。
  assistant: [选了工具: task{'description': '复核报销单 CLM-2026-0004 的关联发票 INV-2026-0005', 'subagent_type': 'invoice-specialist'}, check_budget{'dept': 'DEV'}]
       tool: 发票 INV-2026-0005 校验未过：发票已作废（连号重开）。  (id=call_task)
       tool: {"dept": "DEV", "budget_cents": 100000, "spent_cents": 60000, ...  (id=call_budget)
  assistant: [选了工具: write_file{'file_path': '/review/CLM-2026-0004.md', 'content': '# 审查底稿 ...'}]
       tool: Updated file /review/CLM-2026-0004.md  (id=call_write)
  assistant: [选了工具: Advice{'claim_id': 'CLM-2026-0004', 'decision': 'REJECT', ...}]
       tool: Returning structured response: ...  (id=call_advice)

最终 state 键: ['files', 'messages', 'structured_response']
CALL_LOG（工具真实执行）: ['check_budget', 'verify_invoice']
```

对着 §2.4 的清单数一遍：五轮剧本 = R1 主代理转交+查预算 → R2/R3 子代理干活 →
R4 主代理写底稿 → R5 结构化收尾。注意**收尾轮也是一个工具调用**——传
`response_format=Advice` 后，langchain 生成一个 `Advice` 工具，模型调它即
「交表」，`state["structured_response"]` 里就是 Pydantic 实例（L2.4 纪律的
harness 版：出口不再靠 parse 最终文本）。`code/demo.py` 的 `run_review`
把这个五轮剧本封装成契约入口，共用验收照常全绿。

同一脚本 Part B 演示**最小权限收窄**：

```text
== B. 默认工具清单 vs 最小权限收窄 ==
  默认清单(10): ['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task', 'check_budget', 'Advice']
  收窄清单(6): ['ls', 'read_file', 'write_file', 'task', 'check_budget', 'Advice']
```

收窄的写法是往 `middleware=` 传一个自定义 `FilesystemMiddleware(tools=[...])`——
它按 name **原位替换**默认件（注意 `read_file` 必须保留，源码
`middleware/filesystem.py:1800` 有校验）。harness 默认值第一课：**不配置 ≠ 没有**。

### Step 2：虚拟文件系统——state["files"] 工作台（10 分钟）

```bash
uv run python code/demo_fs.py
```

```text
== B. FileData 的真实形态 ==
  /review/CLM-2026-0001.md:
    content 前 60 字: '# 审查底稿 CLM-2026-0001\n- 单据：客户拜访：交通 + 工作餐...'
    encoding: utf-8, created_at: 2026-09-15T14:24:45

== C. invoke 预置文件 + ls 取证 ==
ls 工具回喂（模型看到的目录列表）:
    ['/review/CLM-2026-0001.md', '/review/README.md']
run 结束后从 result 拿回同一份 files: ['/review/CLM-2026-0001.md', '/review/README.md']
磁盘上并没有这些文件——它们只活在 graph state 里（StateBackend 的 docstring：ephemeral）
```

三个关键认识：**文件是 state 的一个 channel**（`FilesystemState.files`，
`middleware/filesystem.py:1192`）；**读写走 langgraph 的 channel 机制**
（`StateBackend._read_files / _send_files_update`，`backends/state.py:81/99`——
不是 `open()`！）；**预置文件就是 invoke 的普通输入**（`files={...}` 进，
`result["files"]` 出，同一条通道）。换成 `FilesystemBackend` 就是真的磁盘、
换成 sandbox 后端就是容器——工具层一行不改（BackendProtocol 的多态）。

### Step 3：子代理——handoff-as-tool 的 harness 版（10 分钟）

```bash
uv run python code/demo_subagent.py
```

```text
== A. task 工具描述里的子代理目录 ==
    - general-purpose: General-purpose agent for researching complex questions, ...
    - invoice-specialist: 发票校验专员：复核关联发票是否有效并报告结论

== C. 隔离性：R3（子代理收尾轮）发给模型的消息 ==
  system: 你是发票校验专员，只负责调用 verify_invoice 工具复核发票，并简短报告校验结论。
  user: 复核报销单 CLM-2026-0002 的关联发票 INV-2026-0002
  —— 子代理的第一条 human 消息就是任务描述本身，主代理的对话历史没有传进来

== D. 主代理的视角：task 工具的回喂 ==
  task 工具回喂: 发票 INV-2026-0002 校验通过：抬头、税号与报销人一致。
```

对照 L3.1 的 handoff-as-tool：openai-agents 里 handoff 是「换人接管对话」；
deepagents 的 `task` 是「派活后收报告」——子代理带着**只有任务描述**的新对话
开局（隔离），干完活把**最后一条非空 AI 消息**作为 ToolMessage 回喂主代理
（`middleware/subagents.py:698`）。声明式 spec 的四个键各司其职：`name` 是
task 找人的 id、`description` 进工具目录给主代理读、`system_prompt` 是子代理
人设、`tools` 圈能力边界（demo 只给发票专员 `verify_invoice`——它的请求里
连 `task` 都没有，不能再转交）。

### Step 4：MemoryMiddleware——请求出栈前的记忆注入（10 分钟）

```bash
uv run python code/demo_memory.py
```

```text
== A. 第一个请求的 system 消息（节选） ==
你是报销单审查助手。

<agent_memory>
/memory/AGENTS.md

# 审查记忆
- 金额一律整数分，报告里禁止出现小数
- 人审清单写到 /review/ 目录，按单号命名

</agent_memory>

== B. hook 时机 ==
  最终 state 键: ['files', 'messages', 'structured_response'] （没有 memory_contents——私有字段被剥离）
  HTML 注释剥离了吗: True
```

机制两步（源码 `middleware/memory.py`）：`before_agent`（279 行）把记忆文件经
backend 下载进 `state["memory_contents"]`（`PrivateStateAttr`，不进最终 state）；
`wrap_model_call`（385 行）把它填进 `MEMORY_SYSTEM_PROMPT` 模板的
`{agent_memory}` 槽、追加到 system 消息尾部——对照 Java：这就是「进图前读数据
（preHandle）、请求出栈前改请求体（doFilter 环绕）」的组合拳。两个细节：记忆
**就是虚拟文件系统里的文件**（Step 2 同一条 channel，存储形态是文件）；HTML
注释在注入前被剥离（作者备注不进 system）。「记忆更新」则反向复用 `edit_file`
工具——模型改文件即改记忆。

### Step 5：讲义区验收 + （可选）真实端点（15 分钟）

```bash
uv run pytest code/
```

九个测试：共用契约两个（四种结论场景全跑通）+ 本课机制七个（五轮结构的主/
子代理分工、底稿落盘、structured_response 类型、task 目录含默认件、子代理隔离、
memory 注入、默认工具清单与收窄）。

```bash
uv run python code/demo_harness.py --real
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。）
组装一行不改，模型自己决定轮次——`Advice` 工具仍然兜底结构化收尾。

## 4. 练习（本课过关点）

改造题：在能跑的 demo 上完成指定修改。规则：**单变量编辑约束**——只改标注的
TODO 区与所需的顶部 import；卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 改造点 |
|---|---|---|
| ex1 | `exercises/ex1_custom_tool.py` | 加自定义工具 `lookup_policy`（政策话术 mock）并注册——命中记日志、未命中回错误行 |
| ex2 | `exercises/ex2_budget_subagent.py` | 声明「预算专员」子代理（SubAgent 四键），把 check_budget 转交出去 |
| ex3 | `exercises/ex3_write_dossier.py` | 审查底稿落盘的编排与取回：write_file 轮参数组装 + 从 state 取正文 |

每题两个验收测试（共六个）：断言都基于**执行取证**（POLICY_LOG / 请求工具清单 /
ToolMessage 回喂 / state 文件），剧本自说自话骗不过去。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：harness 默认值坑（「我没配置就没有」的反直觉）

这是本课的命名化失败模式——Spring 自动装配的直觉在这里会反着咬你一口。

- **现象**：你想做一个「只查预算、只交建议单」的审查 agent，写了三行：
  `create_deep_agent(model, tools=[check_budget], response_format=Advice)`。上线
  后审计同事问：这个 agent 为什么**能读写文件、还能派子代理**？日志里模型偶尔
  真的调了 `glob`、`grep`（它是被工具描述吸引的）——你的「小 agent」其实拎着
  一整个工具箱上岗。
- **最小复现**（Step 1 的取证就是它）：打印第一个请求的 `tools` 列表——你没配置
  任何文件系统，模型照样看见 `ls / read_file / write_file / edit_file / delete /
  glob / grep / task` 八件内置工具，外加一个你没声明的 `general-purpose` 子代理；
  你也没配置预算，但递归上限默认是 9999（`graph.py:971`），烧 token 上不封顶。
- **Java 直觉为何失效**：Spring 老兵的肌肉记忆是「没引 starter 就没自动装配、
  没加 `@EnableXxx` 就没那套 Bean」——**配置驱动，缺省即无**。deepagents 正相反：
  **缺省即全有**（`tools` 参数 additive、general-purpose 自动追加、中间件默认
  装满，全是 `create_deep_agent` 的默认参数，源码见 §2.4 清单）。更微妙的是这
  里的「装配」不是给你的代码用的，是给**模型**用的——多一个工具就是多一份
  模型选错工具的概率面，安全边界从「进程能调什么」变成了「模型会调什么」。
- **修复与纪律**：把「默认给了什么」当部署清单审计——第一件事永远是打印请求里
  的工具列表（`ep.requests[0]["tools"]`，本课 demo 的标准动作）；要收窄就显式
  换件：`middleware=[FilesystemMiddleware(backend=StateBackend(),
  tools=["ls", "read_file", "write_file"])]` 按 name 原位替换默认件（`read_file`
  必须保留，源码有校验）；预算显式给——`agent.ainvoke(..., config=
  {"recursion_limit": 25})` 覆盖 9999 默认（L2.3 双终止纪律在 harness 时代照样
  成立）；更细的管控用 `permissions`（allow/deny/interrupt 规则表）或
  `interrupt_on`（HITL，L3.3 的机制在工具层的应用）。

## 6. 延伸

- langchain-ai/deepagents@9e7d62ff6#libs/deepagents/deepagents/graph.py ——
  `create_deep_agent` 本体（271 行起）：默认中间件栈的装配顺序（Filesystem →
  SubAgent → Summarization → … → Memory → HITL）、`backend` 默认 StateBackend
  （637 行）、递归预算 9999（971 行）。今晚「默认给了你什么」的每一句都能在这
  200 行里找到出处。
- langchain-ai/deepagents@9e7d62ff6#libs/deepagents/deepagents/middleware/subagents.py ——
  SubAgent TypedDict（66 行起）、`_build_task_tool`（577 行起）：子代理如何被
  编译成 `task` 工具、目录怎么拼、回喂怎么取最后一条非空 AI 消息（698 行）。
- langchain-ai/deepagents@9e7d62ff6#libs/deepagents/deepagents/backends/state.py ——
  StateBackend：虚拟文件系统的读写全部走 langgraph channel（`_read_files` 81 行、
  `_send_files_update` 99 行），「文件 = state 键」的最终证据。
- langchain-ai/deepagents@9e7d62ff6#libs/deepagents/deepagents/middleware/memory.py ——
  MemoryMiddleware 全文 417 行：`before_agent`（279 行）下载进 state、
  `wrap_model_call`（385 行）注入 `<agent_memory>`、HTML 注释剥离。值得整读——
  这是「中间件模式」最小最完整的一个样本。
- langchain-ai/deepagents@9e7d62ff6#libs/deepagents/deepagents/middleware/filesystem.py ——
  内置工具族工厂（1859 行起）与 `tools=` 收窄参数（1758 行，`read_file` 必含
  校验 1800 行）。全文 3654 行（wc -l 口径），还包括大结果落盘、消息驱逐等
  生产件——跳读目录即可。
- 官方文档：https://docs.langchain.com/oss/python/deepagents/overview ——注意
  版本差异：网上老教程（0.0.x/0.1.x 时代）手工装 `middleware=[FilesystemMiddleware(),
  SubagentMiddleware(...)]`、backend 传工厂的写法在 0.7 已废弃（源码里有显式报错
  「Backend factories were removed in deepagents 0.7」）；`BASE_AGENT_PROMPT`
  也于 0.7.0 废弃——本课锁定 deepagents==0.7.13，一切以 9e7d62ff6 源码为准。

### 与 mini-agent 对照

deepagents 替你付掉的，是 mini-agent **完全没有的一整层工作环境**：虚拟文件系统
（mini-agent 里审查底稿只能拼在消息里，这里是可 `ls`/`read_file` 的文件）、
子代理（mini-agent 的「转交」要自己再造循环，这里是 `task` 一个工具）、记忆
（mini-agent 的上下文管理只有字符裁剪，这里是有存储形态的文件）。而 **agent
循环本体一点没少也没换**——deepagents 的引擎就是 langgraph（L3.2 的图 + L3.4
的 `create_react_agent`），harness 是图引擎之上的一叠中间件。反过来，mini-agent
教你的东西在这里全部兑现：CALL_LOG 照样证明工具真实执行（test_contract 四课
同款）、L2.4 的结构化出口变成了 `Advice` 工具、L2.3 的预算纪律变成了「覆盖
9999 默认值」的自觉。**你付掉的抽象税**：对中间件栈顺序的理解成本 + §5 的
默认值审计成本——工具越全的 harness，越要会收窄。

## 离毕业又近的一块

毕业设计的执行器已定 langgraph（L3.8 决策表的前哨），今晚补上最后一块环境认知：
L5.1 的「计划驱动路由」可以用 harness 的子代理机制做执行分工；L5.2 审批外化的
「暂停→恢复」在 deepagents 里有 `interrupt_on`/`permissions` 的现成钩子；L5.3
事件溯源最想要的「agent 工作留痕」，虚拟文件系统给了最便宜的雏形（审查底稿
天然是审计证据）。至此四重奏只剩最后一对：L3.6 的 adk 全家桶与 L3.7 的平台
半日游——看过 harness 之后，「全家桶与平台多给了什么、多收了什么锁定性」
你会问得更准。
