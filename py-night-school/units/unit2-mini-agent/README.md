# Unit 2 无框架手写 mini-agent

> 夜校的对照组学段：五个晚课手写一个 ~300 行的 mini-agent，把 agent 框架替你藏掉的
> 每一层协议亲手摸一遍。Unit 3 每个框架课都会回来对照：「这层抽象替我付掉的代码，
> 在 mini-agent 里是哪几行」——对照原件是 OpenAI cookbook 的
> [Orchestrating_agents.ipynb](https://github.com/openai/openai-cookbook/blob/0aaed0f1d/examples/Orchestrating_agents.ipynb)（锚定 0aaed0f1d，与各课路标一致）。

## 学法说明（先读这段）

- **理解抽象的最好方式是先拥有被抽象的东西**：先手写裸 API、手写工具注册表、手写
  ReAct 循环，框架才不再是魔法。本学段全部课程**不用任何 agent 框架**——依赖只有
  `httpx` / `pydantic` / 官方 `mcp` SDK。
- **离线可验收是本学段的工程底线**：每课配「本地 mock 端点」（协议级测试替身，
  Java 同学理解为 WireMock）与「剧本模型」（脚本化回放）——不需要 API key、不需要
  网络，`uv run pytest` 照样三态全绿。真实端点是可选的加餐（`--real` + `.env`）。
- 五课递进即五个零件，**里程碑把它们组装成完整 mini-agent**：裸调 API（血管）→
  工具协议（手）→ ReAct 循环（心脏）→ 结构化输出（质量闸）→ MCP（跨进程关节）。
- 本学段起**坑位密度上升**：字符串套娃坑、签名漂移坑、终止条件外包坑、Markdown
  围栏坑、stdout 串台坑——五个命名化失败模式都是生产事故的原型，名字要记住。

## 课表

| 课 | 主题 | 一句话 |
|---|---|---|
| [L2.1](./L2.1-raw-api/README.md) | 裸调 LLM API | messages 协议、手撕 SSE 流式、工具调用两回合——框架之下的三层协议 |
| [L2.2](./L2.2-tool-protocol/README.md) | 工具协议 | Pydantic → JSON Schema → 注册表：契约从类型生成，不是手抄 |
| [L2.3](./L2.3-react-loop/README.md) | ReAct 循环 | agent = 模型 + 工具循环；双终止与预算护栏（+上下文管理加餐） |
| [L2.4](./L2.4-structured-output/README.md) | 结构化输出 | 解析、校验、回喂重试——LLM 不是序列化层，契约靠自己剥 |
| [L2.5](./L2.5-mcp/README.md) | MCP | 工具走出进程：官方 SDK 写 server + client 消费 + 桥接回 agent |

## 里程碑（本学段结业判据）

独立完成 [milestone/](./milestone/README.md)：**mini-agent**（裸逻辑 249 行，ast 口径）——
多工具 + 流式 + 结构化输出 + MCP server，离线验收十一路全绿。它就是 Unit 3 的
全程对照组：决策表的左边一列，从今晚起有了实体。

## 节奏建议（两周）

- 第 1 周：L2.1 + L2.2（协议层：动手多、概念新，mock 端点要跑熟）；
- 第 2 周：L2.3 + L2.4 + L2.5 + 里程碑（循环与组装：前两课的零件在这里合体）。

每课完成判据与全学段一致：`uv run pytest` / `uv run ruff check .` / `uv run pyright`
三条同时全绿。真端点 `.env` 任意时点配好即可（`.env.example` 三变量，任一 OpenAI 兼容端点）。

## 与 Unit 3 的接口（出发前对表）

从下一学段起，每次学框架先回来对三问：它的 runner 对应 mini-agent 的哪几行？
它的工具注册对应 `@tool` 注册表的哪些纪律？它的预算/检查点参数对应双终止的哪一半？
带着 mini-agent 去上课——它是你衡量一切抽象的尺。

## 离毕业又近的一块

本学段结束你将拥有：协议层直连能力（毕设执行器的对外接口）、工具注册表（L5.1 工具
白名单的雏形）、双终止循环（成本护栏的直系祖先）、结构化决策单（Plan JSON 的 schema
预演）、MCP server（毕设工具层的部署形态）。毕业设计的骨架，在这个学段全部现形。
