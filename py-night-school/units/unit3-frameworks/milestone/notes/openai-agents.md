# 对照笔记：openai-agents（L3.1）

> 抽象光谱第一格：极简原语层。这页写完，决策表的「openai-agents」列就有了
> 你自己的依据。固定小节五个（`tests/test_notes_meta.py` 按结构把关）；
> 问题只是脚手架，回答完删掉问题、留下结论——`TODO(笔记)` 占位符必须全部替换。

## 它替 mini-agent 付掉了什么

对照 L3.1 讲义结尾的「与 mini-agent 对照」表，只挑**替掉你代码行**的条目
（不是能力清单）。至少对上三件：`Runner.run` ≈ `agent.py::run` 的十行循环
（软终止 + `max_turns` 硬预算，`MaxTurnsExceeded` ≈ `AgentBudgetExceeded`）；
`@function_tool` ≈ `tools.py` 手写「Pydantic → JSON Schema → 注册表」三步
（docstring-as-schema）；`output_type=Advice` ≈ `structured.py::ask_structured`
（且实测不多花一轮模型）。

- TODO(笔记)：三行以上清单，每行注「mini-agent 的哪个文件哪些行 → 哪个原语」。

## 它没替你付什么

讲义 §2 反复强调「没有魔法会背着你做事」。至少盘点：mock 端点还得你自己注入
（`OpenAIChatCompletionsModel` + `AsyncOpenAI(base_url=...)`）；messages 协议语义、
工具返回值边界（dict 被 `str()` 成 Python repr 而非 JSON——§2.3 的实测发现）
仍是你自己的纪律；trace 目的地也得你自己管。

- TODO(笔记)：列「没替你付」，每条注一句证据（课次/小节/实测现象）。

## 最惊讶的一个机制

候选（挑一个，注明 L3.1 的小节/Step）：tracing 默认外发 api.openai.com——
只要环境里有 OPENAI_API_KEY，离线验收「看着没事」生产却静默外发（§2.7/Step 2）；
InputGuardrail 默认与第一轮模型调用**并行赛跑**而不是 Filter 式前置（§2.6）；
handoff 在 wire 上就是一个 `transfer_to_<name>` 工具调用、历史原样保留（Step 3）。

- TODO(笔记)：一个机制 + 出处 + 一句「为什么惊讶」。

## 锁定性一句话

往锁定性方向想：极简原语层几乎是「薄包装 + 默认值」，但也有私有词汇
（handoff/guardrail/RunState）与 trace 默认行为。用你自己的话写一句
（会被 summary.py 抓进决策表定稿）。

- TODO(笔记)：一句话，别超一行。

## 什么时候选它

提示方向：已经用 OpenAI 兼容端点、要的只是「循环 + 工具 + 结构化输出」的
最薄装配（tablegen：装配 29 行、lock 51 包——四框架最轻）；想自己保住
循环语义控制权时。反例：需要显式图/checkpoint（L3.3）时它没有。

- TODO(笔记)：两个选它的场景 + 一个不选它的场景，各一句理由。
