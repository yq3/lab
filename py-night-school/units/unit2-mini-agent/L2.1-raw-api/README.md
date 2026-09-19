# L2.1 裸调 LLM API：messages、流式与工具调用协议

> 上一学段收官夜，你的 async 并发 fetcher 三命令全绿：retry 装饰器接住 east 的两次抖动、
> 慢端点超时降级、信号量把并发摁在两路——九课铸的语言零件全部验收。今晚开新学段
> Unit 2：零件不再单练，五个晚课手写一个不用任何框架的 mini-agent；第一晚从最底层
> 开始，裸调 LLM API——五块肌肉的第一块（协议层）。

## 1. 本课目标

Unit 2（无框架手写 mini-agent）的地基课。今晚不用任何 SDK，只用 `httpx` + 标准库 `json`
直连一个 OpenAI 兼容端点，把 agent 框架替你藏掉的三层协议亲手摸一遍。完成后你能：

- 说清一次对话补全的完整解剖：messages 进 → `choices[0].message` 出，`finish_reason` 是分支信号；
- **手撕 SSE 流式解析**：bytes 缓冲、跨块半行重组、`[DONE]` 哨兵——token 是怎么一段段到达的；
- 走完 function calling 两回合时序：`tools` 下行 → `tool_calls` 上行 → `role=tool` 回喂——
  这是 L2.3 ReAct 循环的**单圈原型**；
- 用本课的「本地 mock 端点」让以上全部离线可验收——协议级测试替身（Java 同学：WireMock 的对应物）。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明（发货态＝你 clone 下来、练习未做时的初始状态）：现在跑 pytest，`code/` 讲义区是绿的，`exercises/` 练习区是设计内的红
（TODO 未填）。真实端点演示（`--real`）需要 `.env`，可选、不影响验收。

## 2. 概念讲解

先给全课对照表，再逐小节展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `java.net.http.HttpClient` / OkHttp | `httpx.AsyncClient` | API 几乎同构；httpx 原生 async，返回 awaitable |
| Jackson `ObjectMapper` | 标准库 `json` 模块 | `json.dumps` ≈ `writeValueAsString`，`json.loads` ≈ `readValue`；只有 dict/list，没有强类型 DTO |
| 内部 REST 契约（OpenAPI 文档） | 端点的 API 文档 | 一样是「字段对齐就互通」的契约思维 |
| `System.getenv` | `os.environ` / `os.getenv` | 无类型 dict；`.env` 文件要自己加载（或用 python-dotenv） |

### 2.1 先看全景：框架之下是什么

LangGraph、openai-agents、crewai……所有 Python agent 框架在与模型对话这件事上，
底层都是同一个动作：

```text
你的代码 ──HTTP POST（JSON body）──> {OPENAI_BASE_URL}/chat/completions
       <───── JSON 响应（或 SSE 字节流）──── 端点
```

「OpenAI 兼容端点」的意思就是：这个 URL 契约、请求体字段、响应体字段与 OpenAI 的
`/v1/chat/completions` 一致——GLM / DeepSeek / Qwen / 本地 vLLM 全都实现了它，所以换端点
只是换 `.env` 三变量（夜校的端点中立纪律就建立在这层兼容上）。本课工具层面的 Java 对照
见开头的全课总表，下面只留速成：

httpx 速成（本课只用到这四行）：

```python
async with httpx.AsyncClient(base_url=..., headers={"Authorization": f"Bearer {key}"}) as http:
    response = await http.post("/chat/completions", json=payload)  # json= 自动序列化并设 Content-Type
    response.raise_for_status()
    data = response.json()  # 反序列化为 dict
```

`async with` 管连接池的生死（L1.7 上下文管理器 + L1.8 异步版的合体）；`json=payload`
这一步等价于 OkHttp 的 `RequestBody.create(json, MediaType.parse("application/json"))`。

### 2.2 messages：无状态的对话协议

对话的形态是一个**消息列表**，四种角色：

| role | 谁在说话 | 内容 | Java 类比 |
|---|---|---|---|
| `system` | 你（开发者） | 人设与纪律，永远在第一条 | 配置/指令，不是用户输入 |
| `user` | 终端用户 | 请求正文 | 请求参数 |
| `assistant` | 模型 | 回答正文，或 `tool_calls`（选了工具） | 响应 DTO |
| `tool` | 你的代码 | 某次工具调用的执行结果 | 回调的返回值 |

**最要紧的心智**：端点是无状态的。它不记得上一轮说过什么——每次请求都把**完整历史**
发一遍，「对话」其实活在你客户端的 list 里。Java 人最容易带着 WebSocket session 的直觉
来这里找「连接」：没有连接、没有会话，每次都是一次独立 POST。对照：这更像无状态 REST +
客户端持有全部状态，而不是有状态 RPC。

由此推出本学段最重要的数据结构：`messages: list[dict]`。agent 循环（L2.3）的全部状态
就是这个列表的追加过程。

### 2.3 请求与响应解剖

请求体（`build_payload` 组装的就是它）：

| 字段 | 类型 | 作用 |
|---|---|---|
| `model` | str | 端点上的模型名（`.env` 的 `MODEL_NAME`） |
| `messages` | list[dict] | 完整对话历史（含这一轮的 user） |
| `tools` | list[dict]? | 可选：工具契约列表（§2.5） |
| `stream` | bool? | 可选：true 时响应变成 SSE 字节流（§2.4） |

响应体（非流式）的导航路径是固定的：正文在 `choices[0].message.content`；
`choices` 是数组但聊天场景只用第一个元素。两个高频伴生字段：

- `finish_reason`：模型为什么停笔——**分支信号**，agent 循环靠它/`tool_calls` 判断走哪条路：

  | 值 | 含义 | 循环里怎么处理 |
  |---|---|---|
  | `stop` | 正常说完 | 取 content，结束 |
  | `tool_calls` | 模型要调工具（此时 content 常为 `None`） | 执行工具、回喂、再来一轮 |
  | `length` | 到了 max_tokens 被截断 | 视为异常或续写 |

- `usage`：token 计量（`prompt_tokens` / `completion_tokens` / `total_tokens`）；token＝模型读写文本的计量单元，约 ¼ 个词——计费、截断、上下文预算全按它算，与鉴权 token 无关——今晚
  只需认得这三个字段，成本核算与上下文预算会用到（L2.3 的加餐数据来源）。

`json` 模块三件套（对照 Jackson，一个能打的都没有但全都很轻）：

```python
payload_json = json.dumps(obj, ensure_ascii=False)  # 序列化；ensure_ascii=False 让中文原样输出
obj = json.loads(text)                              # 反序列化 → dict / list / str / int ...
```

注意：`json.loads` 出来的世界里**没有类型**——嵌套结构全是 dict/list，导航全靠
`data["choices"][0]["message"]["content"]` 这样一层层下钻。Java 的 DTO 把这层导航
变成了编译期保证；Python 这层保证要靠 Pydantic（L2.2 起）。

### 2.4 流式输出与 SSE：token 怎么一段段到达

`stream: true` 时，响应不再是「一个 JSON」，而是 `Content-Type: text/event-stream` 的
**字节流**——服务器有一段吐一段。协议叫 SSE（Server-Sent Events），聊天端点只用它的一个子集：

```text
data: {"choices": [{"delta": {"content": "报销单"}}]}     ← 一个事件（一行 data + 空行结尾）
                                                        ← 空行是事件分隔符
data: {"choices": [{"delta": {"content": "通过"}}]}

data: [DONE]                                             ← 结束哨兵，不是 JSON
```

三个必须内化的规则（ex2 的验收点）：

1. **事件以空行（`\n\n`）收尾**——没看到空行，事件就没到齐；
2. **网络字节块的边界不承诺对齐任何东西**——一块里可能有半个事件、一个事件、或三个半；
   一个中文字符的 3 个 UTF-8 字节都可能被劈在两块里。所以解析器必须**缓冲**：
   块进来先追加，凑齐一个完整事件再切出来处理；
3. **bytes 不是 str**——`b"data: ..."` 是字节序列，`json.loads` 吃 str；
   UTF-8 解码（`.decode("utf-8")`）只能在**完整事件**上做，在半截字节上做会
   `UnicodeDecodeError`。对照 Java：`InputStream.read(byte[])` 给你的也是字节缓冲，
   `BufferedReader.readLine()` 之所以能按行给字符串，是因为它内部替你做了同样的缓冲。

组装侧还有一层：每个事件的正文在 `choices[0].delta.content`（流式叫 delta，增量），
拼起来才是完整回答；首个事件常只有 `{"role": "assistant"}` 没有 content，末尾常有只有
`finish_reason` 的事件——取值都要防空（`.get("content")`）。

### 2.5 工具调用协议：两回合时序

function calling 不是「端点执行你的函数」——端点**只会做一件事：告诉你它想调哪个函数、
参数是什么**。执行永远在你的进程里。完整时序两回合：

```text
第 1 回合请求:  messages + tools（工具契约：名字 + 描述 + 参数 JSON Schema）
第 1 回合响应:  choices[0].message.tool_calls = [
                  {"id": "call_001", "function": {"name": "preapprove",
                   "arguments": "{\"items_cents\": [8800]}"   ← 注意：字符串！§5 陷阱
                  }}]
                finish_reason = "tool_calls"，content = None
你的代码:      执行 preapprove(**json.loads(arguments))，把 assistant 消息原样追加进历史，
                再追加 {"role": "tool", "tool_call_id": "call_001", "content": "<结果>"}
第 2 回合请求:  messages（此时比第 1 回合多了 assistant + tool 两条）
第 2 回合响应:  基于工具结果的最终回答（finish_reason = "stop"）
```

三个纪律：assistant 的 tool_calls 消息**原样入史**（它是历史的一部分，裁剪会破坏对应关系）；
`tool_call_id` 必须一一回带（串位或缺失会被端点 400 拒收）；一条 assistant 消息可以
并行携带多个 tool_calls（每个都要各自回喂）。

工具契约里的 `parameters` 是一份 **JSON Schema**（描述参数形状的 JSON：类型、必填、
元素类型）。今晚手写它，L2.2 用 Pydantic 模型自动生成它——那时你会明白为什么
「Pydantic 是 agent 世界的血管」。

Java 对照：这是「把方法签名序列化成契约，让外部决策者选择并回叫」——最接近的直觉是
反射 `Method` + 白名单注册表，只不过决策者是模型、调用走 HTTP 往返。

### 2.6 本课工程法：mock 端点 + 双模式演示

「裸调 API」的麻烦是：验收不能依赖真实端点（要 key、要网络、输出不确定——竞品课程
的通病）。本课的答案分两层：

- **`code/mock_endpoint.py`**：在 `127.0.0.1` 起一个真的 HTTP 服务（JDK 内置
  `com.sun.net.httpserver.HttpServer` 的对应物：标准库 `http.server`），按脚本回放响应、
  记录收到的请求。给定基础设施，不要改——它让 client 面对的是**真实的 HTTP 状态码、
  JSON 结构、SSE 字节流**；
- **双模式演示**：每个 demo 默认离线跑（起 mock）；`--real` 才读 `.env` 打真实端点。
  验收测试全部离线确定；真端点是体感课。

这套「协议级测试替身」的手感，就是你以后在 Java 侧用 WireMock / MockWebServer 的手感。

## 3. 动手代码

先 `uv sync`，然后按 Step 走。所有输出为 mock 模式实测（离线、可复现）。

### Step 0：端点配置（真端点模式才需要）

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

（Windows PowerShell：`copy .env.example .env`；今晚离线跑可以不做这步。）

`code/env_loader.py` 把 `.env` 三变量灌进 `os.environ`（十行解析：注释跳过、行内
` #` 注释剥掉、`setdefault` 保证真实环境变量优先）。讲义区验收：

```bash
uv run pytest code/test_client.py
```

### Step 1：非流式一问一答——看 messages 进、看 choices 出

```bash
uv run python code/demo_chat.py
```

```text
== 端点收到了什么（请求体骨架） ==
  model: mock-model  stream: False
  messages: 2 条
    - system: 你是财务预审助手，结论只用 PASS…
    - user: 预审报销单 CLM-2026-000…
== 我们拿到了什么（响应骨架） ==
  message.content: 报销单 CLM-2026-0001 预审通过：三笔明细均合规，合计 7100 分未超总额上限。
  finish_reason:   stop
  usage:           {'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20}
```

请求骨架是 mock 端点**如实记录**再打印的——你在 Java 里抓包看到的 payload 就是它。

### Step 2：流式——SSE 手撕的实测台

```bash
uv run python code/demo_stream.py
```

```text
== async for 逐段消费（SSE data 事件 → delta.content） ==
  第  1 段到达: '报销单 '
  第  2 段到达: 'CLM-2026-0003 '
  第  3 段到达: '预审拒绝：'
  第  4 段到达: 'REJECT:'
  第  5 段到达: 'INVALID_AMOUNT'
  第  6 段到达: '（存在负数金额）。'
拼装结果: 报销单 CLM-2026-0003 预审拒绝：REJECT:INVALID_AMOUNT（存在负数金额）。
共 6 段，耗时 14.5ms——首段到达即可开始渲染，不必等全文
```

消费端是 `async for delta in client.stream(messages)`——L1.9 异步生成器的生产端今天
真的用上了。解析端 `SSEDecoder`（`code/client.py`）是本课的硬核，值得逐行读：

```python
def feed(self, chunk: bytes) -> list[str]:
    self._buffer += chunk                       # ① 追加：半行半事件都先攒着
    payloads: list[str] = []
    while True:
        index = self._buffer.find(b"\n\n")      # ② 找空行：事件收尾标志
        if index == -1:
            break                               # 没有完整事件了，等下一块
        block, self._buffer = self._buffer[:index], self._buffer[index + 2 :]  # ③ 切出完整块
        ...                                     # ④ 提取 data: 行、剥可选空格、整块 UTF-8 解码
        payloads.append(...)
    return payloads
```

> **IDE 侧（PyCharm，一次配置全学段复用）**：File → Open 打开本课目录、解释器选 uv 建的 `.venv`（L0.1 Step 7 那套）——此后五课的 demo 都是右键 Run/Debug。进阶：在 `SSEDecoder.feed` 的 `find(b"\n\n")` 与切块两行打断点、Debug 跑 `demo_stream.py`，Watch `_buffer` 从半截 JSON 逐块长出——跨块半行重组从推断变成亲见。

跨块重组的验收在 `code/test_client.py::test_sse_decoder_reassembles_events_split_across_chunks`
——事件的 JSON 被切在两块中间，第一块喂进去返回空列表（事件未到齐），第二块到了才吐出两个事件。

### Step 3：工具调用两回合——完整时序

```bash
uv run python code/demo_tool_call.py
```

```text
== 第 1 回合：把工具契约随请求发给端点 ==
  finish_reason = tool_calls  content = None
== 本地执行工具并回喂（role=tool） ==
  preapprove({'items_cents': [8800]}) -> REJECT:ITEM_OVER_LIMIT
== 第 2 回合：带着工具结果再请求 ==
  最终回答: 报销单 CLM-2026-0002 预审拒绝：REJECT:ITEM_OVER_LIMIT（单笔 8800 分超过上限 5000 分）。
== 两回合后的完整消息轨迹 ==
     system: 你是财务预审助手：必须先调用 preapprove 工具，再…
       user: 预审报销单 CLM-2026-0002，明细：8800（单位…
  assistant: [选了工具: preapprove]
       tool: REJECT:ITEM_OVER_LIMIT  (tool_call_id=call_001)
  assistant: 报销单 CLM-2026-0002 预审拒绝：REJECT:…
```

五条消息的轨迹就是 §2.5 时序图的实体。明细金额与仓库共享素材 `data/expense/budget_mock.json`
对应（CLM-2026-0002 的 items 就是 [8800]）；本课为聚焦协议将规则内联复刻，规则的事实源仍是
L0.1 的 `budget.py`——L2.2 起工具改从 data/ 实时读取。把「user → assistant(tool_calls) → tool →
assistant(stop)」这个形状记住——L2.3 的循环就是把这两回合跑成 `while`。

### Step 4：（可选）真实端点一次

配好 `.env` 后给任意 demo 加 `--real`（如 `uv run python code/demo_chat.py --real`）。
输出依端点与模型而异——这正是验收不依赖真实端点的原因。

### Step 5：对照官方 SDK（openai-python——OpenAI 官方 Python SDK；明晚的 L2.2 之前值得花五分钟）

延伸段第三条路标是 openai-python 自己的 SSE 解码器。带着今晚的手撕经验去读：
同样的「find 分隔符 + 缓冲 + 解码」形状，生产级的实现。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区；实现需要的顶部 import 可以补（骨架只预置了
given 部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_messages.py` | messages 组装 + 响应导航（含 content=None 归一化） |
| ex2 | `exercises/ex2_sse_parser.py` | 手撕 SSE（硬核题：半个中文字符、半个 JSON 事件的跨块重组） |
| ex3 | `exercises/ex3_tool_roundtrip.py` | 工具回合组装：arguments 解析、并行 tool_calls、id 一一回带 |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：字符串套娃（arguments 是 JSON 字符串）

这是本课的命名化失败模式——以后说「字符串套娃」我们秒懂。它是 function calling 的
头号事故源，ex3 亲手拆的就是它。

- **现象**：`TypeError: string indices must be integers, not 'str'`——你写下
  `arguments["items_cents"]`，炸在导航第一层。
- **最小复现**：

  ```python
  tool_call = response["choices"][0]["message"]["tool_calls"][0]
  arguments = tool_call["function"]["arguments"]
  print(arguments)          # 打出来是 {"items_cents": [8800]}——长得就是 dict！
  arguments["items_cents"]  # TypeError: string indices must be integers
  ```

- **Java 直觉为何失效**：Jackson 反序列化时，嵌套对象天然变成 `Map` / DTO，你几乎
  从不遇到「一个 JSON 字段的值是 JSON 字符串」。而协议设计上 arguments 是**流式友好的
  字符串**（端点可以边生成边拼字符，不必维护半成品对象），于是 JSON 里套了一个 JSON。
  Python 侧再加一刀：`print` 一个 str 和 print 一个 dict 几乎无法区分，且 dict 导航
  没有编译期检查——`str` 印出来像 `dict`，就是你 Java 直觉翻车的准确位置。
  （Java 里最接近的体感：`JsonNode` 明明是 `TextNode`，你却按 `ObjectNode` 用。）
- **修复与纪律**：`arguments = json.loads(tool_call["function"]["arguments"])`——先拆封
  再用，一行解决。生产纪律（L2.2 起生效）：拆封后立刻 `model_validate` 成 Pydantic 模型，
  「解析 + 校验 + 类型收敛」一步到位；校验失败在入口拦下，脏参数进不了你的业务函数。

## 6. 延伸

- OpenAI Chat Completions API 参考（字段级权威定义，兼容端点都以它为准）：
  https://platform.openai.com/docs/api-reference/chat
- MDN：Using server-sent events（SSE 协议完整规则：`data:`/`event:`/`id:` 行、重连）：
  https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- openai/openai-python@d7c41efee#src/openai/_streaming.py —— 官方 SDK 的流式解码器（`SSEDecoder`
  类）：与你今晚手写的实现并排读，「find 分隔符 + 缓冲 + 解码」的形状一模一样——
  读完你就确信框架没有魔法。
- openai/openai-python@f348ec87b#src/openai/types/shared/function_definition.py —— SDK 里工具
  契约的类型定义：`name` / `description` / `parameters`（JSON Schema）三件套的静态化。
- openai/openai-cookbook@0aaed0f1d#examples/Orchestrating_agents.ipynb —— 本学段的
  **对照原件**：官方的「无框架手写 agent」名篇（`run_full_turn` 循环 + `tools_map` 分发）。
  L2.3 写循环时直接对照它，Unit 3 每个框架课也会回来问：这层抽象替我付掉的代码在对照原件里是哪几行。
- httpx 官方文档（Async API / 流式响应）：
  https://www.python-httpx.org/async/ 
- theskumar/python-dotenv@a00cb2eed —— 生产里 `.env` 加载的事实标准库（本课手写了它的十行子集）：
  https://github.com/theskumar/python-dotenv/tree/a00cb2eed

## 离毕业又近的一块

今晚你摸到的三层协议（messages / SSE / 工具调用）是毕业设计执行层的**全部外部接口**：
L5 的执行器把它们包上重试与预算（Unit 1 里程碑的零件），流式是审批推送（L5.2 SSE）的
机制本体，「历史在客户端」是事件溯源（L5.3）的第一推动。mini-agent（本学段里程碑）
的第一块肌肉（协议层）今晚长出，明晚是第二块：工具注册表。
