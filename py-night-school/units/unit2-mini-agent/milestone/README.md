# Unit 2 里程碑：mini-agent（学段结业项目）

> 任务书 + 验收。没有逐节讲义——到这里，讲义是多余的：**零件全在前五课，
> 拼装是你的事**。这个项目是 Unit 3 的全程对照组：每个框架课都会回来问
> 「这层抽象替我付掉的代码，在 mini-agent 里是哪几行」。

## 你要造的东西

一个无框架 mini-agent：给定一张报销单，自己查明细、自己预审、最后交出**带 schema 的
结构化决策**。五块肌肉一个不少：

```text
client.py       L2.1  HTTP + SSE 流式解析（给定）
tools.py        L2.2  Pydantic → JSON Schema → 注册表 → 分发（给定）
agent.py        L2.3  ReAct 循环 + 双终止 + 执行器接缝（T1：你写）
structured.py   L2.4  解析 + 校验 + 回喂重试（T2：你写其中修复循环）
mcp_bridge.py   L2.5  MCP 工具桥接（T3：你写）
```

行数口径（诚实计数，可复现——用 ast 定位模块/类/函数各级 docstring 的行区间后，
数非空、非 # 注释、不在区间内的行）：核心五模块裸逻辑 **249 行**；含文档注释 454 行；里程碑全部 Python（含给定件、演示入口与 hints，不含 tests）887 行。
CURRICULUM 说的「~300 行」指第一口径的量级：
一个下午能从头读完的体量，这就是「不神秘」的量化证明。

对照原件：openai/openai-cookbook@0aaed0f1d#examples/Orchestrating_agents.ipynb
的 `run_full_turn` 循环——写完后去读它，你会认出每一个零件。

## 任务（三个 TODO，全在标注文件里；实现所需的顶部 import 可以补）

### T1 agent.py：循环 + 接缝（L2.3 复刻 + 一个新设计）

补全 `ReActAgent.run()`：双终止（软：模型不选工具；硬：`max_turns` 预算）、
assistant 原样入史、tool_calls 逐个执行回喂（id 配对）。

新设计只有一处：**执行器接缝** `execute: ToolExecutor | None`——
None 时走本地注册表（`self._default_execute`），注入时全走它。`main.py --mcp`
模式靠这个接缝把工具执行整体搬到 MCP server，**循环一行不改**。

### T2 structured.py：修复循环（L2.4 复刻）

补全 `ask_structured()`：模型产出**先入史再校验**（好坏都入，审计留底）；
`extract_json` + `model_validate` 一个 `except` 接两种伤；失败回喂
`feedback_message(exc)`；`attempts` 耗尽抛 `StructuredOutputError`（带次数）。
给定函数（`extract_json` / `feedback_message` / `PreapprovalDecision`）直接用，别重写。

### T3 mcp_bridge.py：桥接两件（L2.5 复刻）

补全 `mcp_tools_payload()`（input_schema 原样透传成 parameters）与
`run_mcp_tool()`（拆封 arguments → call_tool → 取文本 → is_error 抛 `McpToolError`）。
验收会真的拉起 `mcp_server.py` 子进程走完整协议——写得对不对，协议会告诉你。

## 实现提示

- 卡住先想 10 分钟，再看三级渐进提示（每次只看一级）：

  ```bash
  cd units/unit2-mini-agent/milestone
  uv run python -c "from hints import hint; print(hint('t1', 1))"
  ```

- 手动看效果（填完对应 TODO 后）：

  ```bash
  uv run python main.py
  uv run python main.py --mcp
  uv run python main.py --real
  ```

  前两个离线全链路（剧本模型 + 本地/MCP 工具 + 结构化决策）；`--real` 需先配 `.env`
  （`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`），模型自己决定调用顺序，预算 6 轮兜底。

> **IDE 侧**：`--mcp` 这类参数在 PyCharm 里不是敲命令行——Run → Edit Configurations → Parameters 填 `--mcp`（IDEA 的 Program arguments 对应物）；Debug 跑 `main.py` 在 T1 的 `run()` 断点自查。T3 侧沿用 L2.5 的结论：client 侧断点有效，server 子进程内不命中。

## 验收（全部绿 = Unit 2 结业）

`tests/test_mini_agent.py`（不要改）十一路取证：

| 测试 | 断什么 |
|---|---|
| `test_given_*` ×3 | 给定模块基线：SSE 跨块重组 / 注册表分发 / 三层剥壳（发货态就必须绿） |
| `test_t1_full_run_local_tools` | 查单→预审→回答三轮；角色序列与 id 配对；工具真实执行（结果来自 data/） |
| `test_t1_budget_exceeded` | 执念模型恰好 4 轮触发 `AgentBudgetExceeded`，一次不多 |
| `test_t1_executor_seam` | 注入执行器拿到原始 arguments 字符串；回喂内容来自接缝 |
| `test_t2_structured_repairs` | 围栏+值域错单 → 修复指令 → 合法决策；历史五条角色序列 |
| `test_t2_structured_exhausted` | 恰好 attempts 次后 `StructuredOutputError` |
| `test_t3_payload_passthrough` | input_schema 逐字节透传；description None 归一 |
| `test_t3_stdio_roundtrip` | 真子进程协议：预审四态 + 未知工具 `McpToolError` |
| `test_end_to_end_offline_decision` | 循环 × 工具 × 结构化合体：CLM-2026-0002 → `REJECT:ITEM_OVER_LIMIT`（与 data 的 expect 字段一致） |

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

三条同时全绿，回到 [unit2-mini-agent/README.md](../README.md) 打卡里程碑，然后进 Unit 3——
从此每个框架课都带着它对照。

## 目录

```text
milestone/
├── README.md            # 本任务书
├── agent.py             # T1：ReAct 循环（TODO 在 run()）
├── structured.py        # T2：结构化输出（TODO 在 ask_structured()；解析/模型给定）
├── mcp_bridge.py        # T3：MCP 桥接（两个 TODO）
├── client.py / tools.py / finance.py / model.py / mcp_server.py / env_loader.py  # 给定件（不要改）
├── main.py              # 三模式演示入口（不要改）
├── hints.py             # 三级渐进提示（t1/t2/t3）
├── tests/test_mini_agent.py  # 验收（不要改）
└── solution/            # 参考答案（完成前别看）
```

## 离毕业又近的一块

毕业设计与 mini-agent 的对应关系，从今晚起逐课对表：L5.1 的静态图 = 这 249 行的
拓扑化；L5.2 的审批外化 = 在「选工具」与「执行」之间插一个人工节点；L5.3 的事件溯源 =
`messages` 列表升级为 append-only 事件表；L5.4 的 fail-closed 门 = `run_tool` 出口
再加一条纯函数检查链。你在 Unit 3 每学一个框架，就回来问一次：**它替我付掉的
是哪几行、收走的控制权是哪一个接缝**——问满八次，决策表（L3.8）就自己长出来了。
