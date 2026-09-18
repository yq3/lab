# Unit 3 框架四重奏

> 夜校的主干学段：mini-agent（Unit 2）已经把 agent 的每一层协议亲手摸过一遍，
> 现在把同一道题交给四个开源框架重做——**同题换框架，差异体感最大化**。
> 每课固定收尾「与 mini-agent 对照」：这层抽象替你付掉的代码，在 mini-agent 里是哪几行。

## 本单元的地图：抽象光谱

「四重奏」= 四个**库形态**框架（openai-agents / langgraph / deepagents / adk-python），
外加 dify 这个**平台形态**的半日游（L3.7）。它们不是平行的四个选项，而是铺在一条
「框架替你管多少」的**抽象光谱**上——从最薄到最厚：

```
薄 ←————————————————————————————————————————————→ 厚
openai-agents    langgraph          deepagents      adk-python      dify
(L3.1)           (L3.2–L3.4)        (L3.5)          (L3.6)          (L3.7 平台)
原语层：          图引擎：            harness：        全家桶：         平台：
给你 Agent/       状态图+执行循环     计划/文件系统/    调试器/eval/     画布编排/服务/
handoff/guardrail 你写节点与边        子代理中间件      web 工具链        运维全家桶
你写循环与装配    框架管循环          框架管计划       框架管大部分      几乎全管
```

- 课序 = 沿光谱从薄到厚走一遍：越薄的课你写的越多，越厚的课框架管的越多。
- **langgraph 占三课是刻意的**（L3.2–L3.4）：它是 Java 生产栈 langgraph4j /
  spring-ai-alibaba graph 的同源上游——学它等于预习生产栈语义。
- **为什么是这五个**：两端各取一个极端（openai-agents 最薄原语、dify 最厚平台），
  中间覆盖图引擎、harness、全家桶三种主流形态——学完这条线，新框架只需对位入光谱。
  框架世界远不止这五个（crewai / llama_index / agentscope 等），L3.8 的跳读指南
  教你用同一张光谱给它们归位。

## 学法说明（先读这段）

- **带着 mini-agent 上课**：每个框架课收尾的「与 mini-agent 对照」小节里问自己三问
  ——它的 runner 对应 mini-agent 的哪几行？它的工具注册对应 `@tool` 注册表的哪些
  纪律？它的预算 / 检查点参数对应双终止的哪一半？答不上来就回去翻
  `unit2-mini-agent/milestone/`。
- **离线可验收的底线不变**：L2.3 的本地 mock 端点（协议级测试替身，Java 同学理解为
  WireMock）本学段继续服役——四个框架的模型调用全部指向它，`uv run pytest` 照样零 key
  三态全绿。真实端点是可选加餐（`.env` 三变量 + `--real`）。
- **openai-agents 第一件事是关 trace 外发**：`set_tracing_disabled(True)`——不默认把
  你的会话发去 OpenAI 服务器，这是生产习惯，也是本教程的端点中立纪律。
- **可弃子与必修**：L3.1 / L3.5 / L3.6 时间紧可跳过，langgraph 三连（L3.2–L3.4）不可省；
  L3.7 是平台形态半日游，L3.8 是对照总结课（结业自查表）。

## 同题 demo 契约（四框架共用的「题面」）

统一题目：**报销单审查 agent**——工具是「查预算余额」与「发票校验」两个 mock，输出是
结构化建议单。素材唯一来源 [data/expense/review_mock.json](../../data/expense/review_mock.json)
（CLM-2026-0001~0003 与 Unit 2 明线同源，0004 是本单元新增的发票无效场景单）。

**工具**（`code/mock_tools.py`。「对版」= 共享件跨课字节相同——工具与规则件六课
（L3.1–L3.6）、契约测试五课，改一处同步全部副本；不 import 任何框架）：

| 工具 | 入参 | 返回 |
|---|---|---|
| `check_budget(dept)` | 部门码 | 预算 / 已花 / 剩余（分） |
| `verify_invoice(invoice_id)` | 发票号 | 是否有效 + 人类可读原因 |

**审查规则表**（`code/review_rules.py`，教学约定，先命中先停；真实端点模式下它就是
system 提示里的规则，离线模式下它是替身模型的决策函数——两者同源）：

| # | 条件 | decision | reason |
|---|---|---|---|
| 1 | 明细含非正数金额 | `ESCALATE` | `REJECT:INVALID_AMOUNT`（脏数据转人审） |
| 2 | 任一明细 > 5000 分 | `REJECT` | `REJECT:ITEM_OVER_LIMIT` |
| 3 | 关联发票校验未过 | `REJECT` | `REJECT:INVOICE_INVALID` |
| 4 | 总额 > 部门剩余预算 | `REJECT` | `REJECT:BUDGET_EXCEEDED` |
| 5 | 以上全不中 | `APPROVE` | `PASS` |

**统一出口**：每课 `code/demo.py` 暴露 `async run_review(claim_id) -> Advice`（Pydantic
模型：`claim_id / decision / reason / remaining_cents`，金额一律整数分）。

**共用验收**：`code/test_contract.py` 在 L3.1 / L3.2 / L3.4 / L3.5 / L3.6 五课字节相同
（对版纪律：改一处同步五处）——用例读 review_mock.json 的 `expect_*` 字段，附覆盖型
meta 检查（三种 decision、两个部门必须齐），并用 `mock_tools.CALL_LOG` 证明工具被框架
真实执行过。四个框架课（langgraph 由 L3.2 手装图与 L3.4 prebuilt 两种装配代表）全绿的
标准完全一致：**差异只在框架与装配方式，不在题面**。

## 课表

| 课 | 框架 | 一句话 |
|---|---|---|
| [L3.1](./L3.1-openai-agents/README.md) | openai-agents | 极简原语：Agent / handoff-as-tool / guardrail / RunState 的 HITL（先关 trace 外发） |
| [L3.2](./L3.2-langgraph-basics/README.md) | langgraph ① | StateGraph / 状态 schema / 条件边 / subgraph |
| [L3.3](./L3.3-langgraph-checkpoint/README.md) | langgraph ② | checkpoint / interrupt：暂停→杀进程→恢复（HITL 底层） |
| [L3.4](./L3.4-langgraph-fanout/README.md) | langgraph ③ | `Send` 动态扇出；`create_react_agent` 源码导读（对照 mini-agent） |
| [L3.5](./L3.5-deepagents/README.md) | deepagents | harness 形态：虚拟文件系统 / 子代理 / MemoryMiddleware |
| [L3.6](./L3.6-adk-python/README.md) | adk-python | 全家桶：`adk web` 调试器 / eval 工具链 |
| [L3.7](./L3.7-dify-tour/README.md) | dify 半日游 | 本地 compose 跑平台形态，体感「平台 vs 库」分界 |
| [L3.8](./L3.8-comparison/README.md) | 对照总结 | mini-agent vs 四框架：能力-成本-锁定性决策表；跳读指南 |

## 节奏建议（四周，W7–W10）

- 第 1 周：L3.1 + L3.2（两个极端：最薄的原语层 vs 最显式的图引擎）；
- 第 2 周：L3.3 + L3.4（langgraph 深水区：HITL 底层与动态扇出——毕业设计的核心机制）；
- 第 3 周：L3.5 + L3.6（harness 与全家桶：抽象光谱的后两段）；
- 第 4 周：L3.7 + 里程碑 + L3.8（平台体感 + 结业重验产出数据 + 决策表收口——
  带着自己跑出来的数据去上 L3.8，见 milestone「与 L3.8 的分工」）。

每课完成判据与全学段一致：`uv run pytest` / `uv run ruff check .` / `uv run pyright`
三条同时全绿（框架课的练习是**改造题**：在能跑的 demo 上完成指定修改）。

## 里程碑（本学段结业判据）

独立完成 [milestone/](./milestone/README.md)：**四框架同题 demo 全量重验 + 每框架一页
对照笔记 + 自动生成的决策表**。选型工作台会以子进程逐课重跑共用验收脚本（五课的
contract 全绿才算数——L3.1 / L3.2 / L3.4 / L3.5 / L3.6，langgraph 双装配都在内），
并用脚本从五课的依赖清单与代码行数生成决策表数据页——
「能力-成本-锁定性」不再拍脑袋，而是可复现的数字。

## 与前后学段的接口

- 对上游：mini-agent 是决策表的左边一列（已拥有，才知道抽象替你付了什么）；
- 对下游：L3.3 的 checkpoint/interrupt 就是毕业设计「审批暂停→恢复」的直接机制，
  L3.8 的决策表决定 L5 技术选型（ spoiler：毕设用 langgraph）。

## 离毕业又近的一块

本学段结束你将拥有：四框架同题实跑经验（选型不再是听说）、langgraph 三连（毕设执行器
的图引擎）、HITL 暂停恢复的第一手机制（L5.2 审批外化的原型）、决策表（L5.0 技术评审
的依据）。毕业设计需要的「引擎、机制、选型」，这个学段全部到位——剩下的就是把它
组装成一个产品。
