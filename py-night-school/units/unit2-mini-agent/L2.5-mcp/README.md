# L2.5 MCP：工具走出进程

> 昨晚你的 `structured.py` 守住了 agent 的出口：`extract_json` 三层剥壳拆掉模型的花式
> 包裹，`Literal` 值域拦住越界结论，校验失败就带着修复指令回喂、预算耗尽 fail-loud。
> 四块肌肉集齐，只剩工具出不了进程：它们至今焊在你的进程里，别的进程用不上。
> 今晚用官方 `mcp` SDK 把它们搬进独立 server 进程、桥接回 L2.3 的循环
> ——最后一块肌肉（跨进程工具层），五块集齐就进里程碑组装。

## 1. 本课目标

前四课的工具都焊死在 agent 进程里；今晚用官方 `mcp` SDK 把它们搬出去。完成后你能：

- 用 `MCPServer` 写一个 MCP server（财务 mock 工具 ×3：`list_claims` / `get_claim` /
  `preapprove`），经 **stdio 传输**独立进程运行；
- 写 client 三步走：`stdio_client` 拉起子进程 → `initialize` 握手 → `list_tools` 发现 +
  `call_tool` 调用——全程离线可验收（子进程在本地，无网络依赖）；
- 写**桥接层**：MCP 工具的 `input_schema` 原样放进 OpenAI 的 `parameters`（两边都是
  JSON Schema——协议在此接轨），工具执行从进程内调用换成 JSON-RPC 往返——
  **L2.3 的 agent 循环一行不改**；
- 说出 stdio server 的第一条纪律：stdout 是协议通道，日志必须走 stderr（§5 实测）。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）；
测试里有两个 stdio 子进程用例（秒级），慢是真实传输的代价。

SDK 版本说明：夜校锚定官方 python-sdk **2.x**（`mcp>=2.2,<3`）。2.x 把 server 类从
`FastMCP` 改名 `MCPServer`（`from mcp.server.mcpserver import MCPServer`）——你在网上
看到的大量 `FastMCP` 教程是 1.x 时代或独立的 fastmcp 包，思想一致、名字换了，别迷路。

## 2. 概念讲解

先给全课对照表，再逐小节展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `ProcessBuilder` 拉起的服务，管道上跑协议 | server 进程 + stdio 传输 | stdout/stdin 是通道——所以 §5 的坑存在 |
| TCP 建连后的 HELLO / 能力协商 | `initialize` 握手 + 能力协商 | 版本与能力对齐后才准干活 |
| 服务发现 + OpenAPI 契约 | `list_tools` 发现 + JSON Schema | schema 进了协议一等公民 |
| RMI stub（远程方法的本地形状） | MCP client + 桥接回注册表 | 把远程工具还原成本地 registry 形状（§2.4） |

### 2.1 MCP 解决什么：工具的可移植性

前四课的工具住在你的进程里——换一个 agent（或 IDE、或同事的项目）就得重写一遍。
MCP（Model Context Protocol）把「工具」变成**独立进程提供的服务**：

```text
你的 agent 进程                       finance_server.py 子进程
┌────────────────────┐   stdio（JSON-RPC）  ┌─────────────────────┐
│ ClientSession ─────────────────────────▶ MCPServer            │
│  list_tools()  ──── 工具发现（name/描述/schema）───────────────▶ │
│  call_tool()   ──── 工具执行（在 server 进程里跑）──────────────▶ │
│  ◀────────────── 文本/结构化结果 ──────────────────────────────  │
└────────────────────┘                     └─────────────────────┘
```

协议三锚点（server 传输 / 握手协商 / 发现与 schema）的 Java 对照已收进开头的全课总表。

工具的**作者体验**几乎没变：`@server.tool()` 装饰器 + docstring 描述 + 类型标注出
schema（L2.2 的纪律原样成立）；变的只是**运行时位置**——「一次编写，处处挂载」。

### 2.2 server：`MCPServer` 三十行起步

`code/finance_server.py` 的全部骨架：

```python
from mcp.server.mcpserver import MCPServer

server = MCPServer("night-school-finance")

@server.tool()
def preapprove(items_cents: list[int]) -> str:
    """对报销单明细金额（单位分）做规则预审，返回 PASS 或 REJECT:<原因>。"""
    ...  # 与 L2.2 一字不差的规则四态

if __name__ == "__main__":
    server.run("stdio")
```

三个值得点破的细节：

- **类型标注即 schema**：`items_cents: list[int]` 自动生成 `{"type": "array",
  "items": {"type": "integer"}}`——没有 Pydantic 模型也行（SDK 内部替你做），参数
  复杂时依然推荐 L2.2 的「参数模型」纪律；
- **返回值是给模型看的文本**：工具返回 `str`（或可 JSON 化的对象），SDK 装进
  `content` 列表回传——回喂语义与 L2.2 完全一致；
- **`server.run("stdio")` 会「挂起」**：直接跑这个文件它看起来卡住了——那是在等
  client 的 stdin 输入。这不是死机，是服务器在等客户（对照 `socket.accept()` 阻塞）。

### 2.3 client：连接、发现、调用

```python
params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()                    # ① 握手
        listed = await session.list_tools()           # ② 发现
        result = await session.call_tool("preapprove", arguments={"items_cents": [8800]})
```

三层 `async with` 嵌套各管一段生命周期（L1.7 的纪律）：stdio_client 管子进程与管道，
ClientSession 管协议会话，你管业务。`call_tool` 的 `arguments` 是 **dict**（协议侧已
结构化）——注意与 OpenAI 侧「arguments 是 JSON 字符串」的差异，桥接层正是翻译这
半步的人（§2.4）。

一个类型层细节，躲不开所以就地讲（本课 pyright 全绿的功臣）：MCP SDK 的返回类型是
**联合类型的列表**，不收窄它 pyright 就报错
（TextContent | ImageContent | ...）——只有 TextContent 有 `.text`，直接 `part.text`
会被 pyright 拦下。两种收窄写法你都会遇到：`isinstance(part, TextContent)` 与
`getattr(part, "text", None)`——前者类型安全更足，后者一行流。这不是 MCP 的刁难，
是「协议结果天然多态」的正常代价（Java 里你会写成 `instanceof` 分支或 visitor）。

### 2.4 桥接：协议接轨点为什么这么薄

```python
def mcp_tools_payload(tools: Sequence[Tool]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": tool.name, "description": tool.description or "",
                          "parameters": tool.input_schema}}   # ← 接轨点：同一份 JSON Schema
            for tool in tools]
```

MCP 的 `input_schema` 与 OpenAI 的 `parameters` **都是 JSON Schema**——所以桥接只是
三层 dict 的字段搬运，一个字节不用改。工具执行同理（`run_mcp_tool`）：
拆封 arguments 字符串 → `call_tool(dict)` → 取文本 → `is_error` 翻译成有名异常。
L2.3 的 agent 循环换上这两件后**一行不改**——`demo_agent_mcp.py` 让你逐行对照验证。

一个语义差要记：**MCP 有显式的错误位**（`is_error=True` 时 content 里带错误文本），
OpenAI 协议没有——桥接时把 is_error 翻译成异常或 error JSON，别把失败静默当成功
（ex3 的考点）。

### 2.5 本课的离线验收哲学

MCP 测试有两路，本课两路都用了：

| 路 | 做法 | 速度 | 验收什么 |
|---|---|---|---|
| in-process | 直接 `await server.list_tools()` / `server.call_tool(...)` | 毫秒级 | server 逻辑 |
| stdio 子进程 | 真的拉起 server 进程走完整协议 | 秒级 | 传输 + 握手 + 协议序列化 |

只有 stdio 那一路能抓到「stdout 污染」「握手顺序」「序列化形状」这类协议层事故——
慢，值得（WireMock 的同学对此应有共鸣）。

## 3. 动手代码

先 `uv sync`（依赖只有 `mcp` 一个）。

### Step 1：先跑 server，看它「挂起」（2 分钟）

```bash
uv run python code/finance_server.py
```

它看起来卡住了——`server.run("stdio")` 在等 client。Ctrl+C 退出，进 Step 2 让 client
来敲门。

### Step 2：client 三步走（10 分钟）

```bash
uv run python code/demo_client.py
```

```text
== 连接成功，发现工具 ==
  list_claims: 列出全部报销单（单号、提交人、事由）。
  get_claim: 按单号查询报销单明细（提交人、事由、金额列表，单位分）。
  preapprove: 对报销单明细金额（单位分）做规则预审，返回 PASS 或 REJECT:<原因>。
== input_schema 就是 JSON Schema（与 L2.2 的 parameters 同构） ==
  preapprove.input_schema = {"properties": {"items_cents": {"items": {"type": "integer"}, "title": "Items Cents", "type": "array"}}, "required": ["items_cents"], "type": "object", "title": "preapproveArguments"}
== 调用工具 ==
  list_claims() -> 3 张单: ['CLM-2026-0001', 'CLM-2026-0002', 'CLM-2026-0003']
  get_claim('CLM-2026-0003') -> {"id": "CLM-2026-0003", "submitter": "赵工", "purpose": "打车费冲账（录入了负数）", "items_cents": [-500]}
  preapprove([8800]) -> REJECT:ITEM_OVER_LIMIT
  （工具不在本进程——执行发生在 server 子进程里，结果经 JSON-RPC 回来）
```

`input_schema` 与 L2.2 手写的 `parameters` 长得一模一样不是巧合——§2.4 的接轨点，
眼见为实。

### Step 3：MCP 工具插进 L2.3 的循环（15 分钟）

```bash
uv run python code/demo_agent_mcp.py
```

```text
== ReAct agent × MCP 工具（执行在 server 子进程） ==
  第 1 轮: get_claim -> {"id": "CLM-2026-0001", "submitter": "王工", "purpose": "客户拜访：
  第 2 轮: preapprove -> PASS
最终回答: 预审 PASS：三笔明细合规，合计 7100 分未超总额上限。
```

打开 `demo_agent_mcp.py` 的 `run_agent` 与 L2.3 的 `agent.py` 并排对照：只有两行不同
（契约来自 `mcp_tools_payload`、执行走 `run_mcp_tool`）——**协议分层的红利**：循环
不关心工具住在本进程还是隔壁进程。

### Step 4：讲义区验收（10 分钟）

```bash
uv run pytest code/
```

六路取证：in-process 注册与四态、桥接 payload 形状、stdio 往返的 get_claim、
`run_mcp_tool` 的错误分流。其中 stdio 用例各拉起一个真实 server 子进程。

### Step 5：stdout 串台坑实测（§5 的预备铃，5 分钟）

```bash
uv run python code/demo_stdio_pollution.py
```

看 client 侧刷出的 `Failed to parse JSONRPC message from server`——那是垃圾帧进通道
的现场证据，§5 逐帧分析。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区；实现需要的顶部 import 可以补（骨架只预置了
given 部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_mcp_server.py` | 写 server：get_claim 工具（stdio 子进程真协议验收） |
| ex2 | `exercises/ex2_bridge.py` | 桥接 payload：input_schema 原样透传成 parameters |
| ex3 | `exercises/ex3_mcp_client.py` | client 执行：拆封 arguments、is_error 分流 |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：stdout 串台坑（把日志打进协议通道）

这是本课的命名化失败模式——MCP stdio server 的第一坑，几乎人人踩。

- **现象**：client 侧日志刷 `Failed to parse JSONRPC message from server`，内容是
  `Invalid JSON: ... input_value='调试: 收到 [1200]'`；会话时好时坏。
- **最小复现**（`code/demo_stdio_pollution.py` 实测，2026-09 / mcp 2.2.0）：

  ```python
  @server.tool()
  def preapprove(items_cents: list[int]) -> str:
      """预审。"""
      print(f"调试: 收到 {items_cents}")   # ← stdout 是 JSON-RPC 协议通道！
      return "PASS"
  ```

  实测证据（client 的 stderr）：

  ```text
  Failed to parse JSONRPC message from server
    Invalid JSON: expected value at line 1 column 1 [type=json_invalid,
    input_value='server starting up...', input_type=str]
  ```

- **Java 直觉为何失效**：Tomcat 里 `System.out.println` 无伤大雅——stdout 不是任何
  协议的载体，日志框架随便往里写。但 stdio 传输的 server 里，**stdout 每个字节都是
  协议帧**：print 出去的「调试日志」在 client 看来是一段该按 JSON-RPC 解析的坏帧。
  这是「进程即服务、管道即线路」的心智差——Java 老手其实在 `ProcessBuilder` 管道
  场景见过它，只是没往「我的日志语句」上联想。
- **修复与纪律**：server 进程里一切日志走 **stderr**——`print(..., file=sys.stderr)`
  或直接用 `logging`（默认 handler 就是 stderr）。实测里 client 对坏帧「跳过并报错」
  侥幸存活，但那是这一版 client 的宽容，不是协议的许可：垃圾帧赶上握手期、或对端
  换一个更严格的实现（IDE、其他 SDK 版本），会话直接打崩；而且每次污染都在日志里
  制造一条解析错误——可观测性先被毁掉。别赌宽容，走 stderr。

## 6. 延伸

- MCP 官方规范（协议原文：传输、生命周期、工具/资源/提示词原语）：
  https://modelcontextprotocol.io/specification 
- modelcontextprotocol/python-sdk@65c614e48#src/mcp/server/mcpserver/server.py —— 官方 SDK
  的 server 实现本体（1.x 时代叫 FastMCP，2.x 改名 MCPServer——这个路径名是改名前的
  活化石）；`@server.tool()` 装饰器怎么从签名生成 schema，答案在这个目录里。
- modelcontextprotocol/python-sdk@65c614e48#src/mcp/server/mcpserver/tools/base.py ——
  Tool 对象与 `input_schema` 的生成逻辑：L2.2「Pydantic → JSON Schema」的同族实现。
- modelcontextprotocol/python-sdk@9972c21aa#src/mcp/client/session.py —— client 会话
  本体：initialize 握手、list_tools、call_tool 的请求/响应序列化全在这里。
- microsoft/mcp-for-beginners@2f43408b7 —— MCP 协议深入课（六语言实现，
  https://github.com/microsoft/mcp-for-beginners/tree/2f43408b7 ）：夜校只讲 agent 视角
  必需的一层，传输变体（SSE/streamable HTTP）、资源与提示词原语、部署形态去这里续。
- 《Fluent Python》第 2 版第 13 章（Protocol）+ 本课的联合类型收窄实践：
  `isinstance` 收窄在协议多态结果上的应用。

## 离毕业又近的一块

毕业设计的工具层就是今晚的形状：L5.1 的「取数 → 分析 → 建议单」工具集以 MCP
server 形态部署，agent 进程只持 client——工具的授权、审计、版本管理全部落在 server
侧（L5.3 事件溯源的「工具调用一等事件」由此好记）。mini-agent 的最后一块肌肉
（跨进程工具层）今晚到位——五块肌肉集齐，明天进 [milestone/](../milestone/README.md)
把它们组装成 ~300 行的完整 mini-agent：Unit 3 全程对照组，此刻起它有名字、有身板。
