# py-night-school —— Python 夜校

> 白天写 Java，晚上来学 Agent。
> 写给 Java 工程师的 Python Agent 开发晚课：**以 agent 开发为场景学 Python，以 Java 心智模型为桥**——一个学期（标准 16 周）从语言核心学到金融合规毕业设计。

## 为什么需要这个教程

2026 年的 agent 开发生态，Python 侧最火热，但现有教程对 Java 工程师都不友好：

- **Agent 教程默认你会 Python**：HuggingFace Agents Course 前置要求 "Basic knowledge of Python"，微软课程直接上框架代码——Java 工程师卡在第一公里。
- **Python 教程不碰 agent**：「Python for Java Developers」类资源零散且通用（爬虫/脚本案例），学完离 agent 开发还差一半。
- **没有一份教程以 Java 心智模型为桥**：装饰器像注解但不是注解、asyncio 像虚拟线程但语义完全不同、Pydantic 像 bean 但职责更重——这些「似是而非」正是迁移期最大的事故源，值得逐个讲透。

本教程填这个空档。

## 招生对象：适合谁 / 不适合谁

**适合**：
- 主力语言是 Java（或 Kotlin/C# 等同类静态类型 OO 语言），Python 只是略懂；
- 想进入 agent 开发领域，希望「学一门语言」和「学一个领域」一次完成；
- 最好对 Spring 生态有体感——教程里的对照表按 Spring/Maven/JUC 习惯展开。

**不适合**（诚实声明）：
- Python 已熟练的工程师 → 直接去读各框架官方文档更快；
- 零编程基础 → 先补任意 Python 入门课；
- 想学 LLM 原理 / 微调 / Transformer → 见下方「我们不重复造轮子」。

## 教学法四原则

1. **Java 心智桥**：每个语言概念先给「Java 对应物 + 关键差异」对照表，再动手。似是而非之处（`is` vs `==`、协程让出语义、可变默认参数）单独设「Java 人坑位」。
2. **对照组教学法**：Unit 2 先无框架手写一个 ~300 行的 mini-agent；之后每学一个框架都与它对照——「这个框架比我那 300 行多给了什么、少给了什么」。理解抽象的最好方式是先拥有被抽象的东西。
3. **源码路标**：每个框架课附「核心抽象源码导读」，指向真实仓库的具体文件——学框架同时学读生产级 Python 源码。我们不自研玩具框架（这条路线 [hello-agents 第七章](https://github.com/datawhalechina/hello-agents) 已经做得很好），我们深读生产框架。
4. **一题贯穿 + 真实领域毕业设计**：框架课统一用「报销单审查 agent」同一题目换框架重做；毕业设计是金融合规场景的财务 agent（审批外化 / 事件溯源审计 / fail-closed 执行门），不是又一个 chatbot demo。

## 课表

| 单元 | 主题 | 课时 | 里程碑产物 |
|---|---|---|---|
| 0 | 起步：工具链一次到位 | 1 | uv 项目模板（pytest/ruff/pyright 全绿） |
| 1 | Python 语言核心·Java 对照 | 9 | 练习集；能不查资料手写 async 并发 fetcher + retry 装饰器 |
| 2 | 无框架手写 mini-agent | 5 | ~300 行 mini-agent（工具循环+流式+结构化输出+MCP） |
| 3 | 框架四重奏 | 8 | 4 框架同题 demo + 对照笔记 + 决策表 |
| 4 | 开源产品实战 | 3 | 3 个金融产品的跑通与改造 |
| 5 | 毕业设计：财务 agent | 4 | 合规骨架 PoC + Python↔Java 架构映射表 |

完整大纲（含每课时明细、练习机制、节奏建议）：[CURRICULUM.md](./CURRICULUM.md)

## 入学指南

- **环境**：只需安装 [uv](https://docs.astral.sh/uv/)（教程第一课带你配好），每课是独立可运行的 uv 项目。
- **模型端点中立**：任何 OpenAI 兼容端点均可（GLM / DeepSeek / Qwen / OpenAI / 本地 vLLM），不绑定任何云厂商——这是与微软课程（Azure/Foundry）的显著差异。
- **练习即测试**：每课 `exercises/` 提供带 TODO 的练习文件，`uv run pytest` 全绿即完成本课（rustlings 式验收，Java 同学可以理解为 Exercism 模式）。
- **节奏**：标准节奏每周 6–8 小时、约 16 周走完；紧凑节奏 8–10 周。也可以只走主干（见 CURRICULUM「调节旋钮」）。

## 与现有教程的关系（我们不重复造轮子）

本教程立足差异化，通用内容直接指路现有的优秀资源（完整分析见 lab 仓 [research/agent-tutorials/](../research/agent-tutorials/)）：

- LLM / 智能体基础理论 → [hello-agents](https://github.com/datawhalechina/hello-agents)（Datawhale，中文，16 章大部头）
- MCP 协议深入 → [microsoft/mcp-for-beginners](https://github.com/microsoft/mcp-for-beginners)（六语言）
- 微软系框架全景 → [microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners)（18 课）
- smolagents / LlamaIndex 视角 + GAIA 结业挑战 → [HuggingFace Agents Course](https://github.com/huggingface/agents-course)
- 各框架官方课（LangGraph 等）→ LangChain Academy / DeepLearning.AI 短课

**本教程是它们都没有的那一环**：Java 工程师 × 语言桥 × agent × 源码深度 × 金融毕业设计。

## 当前状态与路线图

- [x] 课程大纲设计（CURRICULUM.md）
- [x] 竞品调研与借鉴分析（research/agent-tutorials/landscape.md）
- [x] 逐仓教学解剖（research/agent-tutorials/profiles/ ×8 + report.md 综合报告）
- [ ] Unit 0 / 1 内容与练习
- [ ] Unit 2 mini-agent 全部代码
- [ ] Unit 3 四框架课
- [ ] Unit 4 产品实战课
- [ ] Unit 5 毕业设计与参考实现
- [ ] （远期）在线阅读站 / 英文版 / 社区贡献指南

## 工程说明

- 本教程当前生活在个人实验室仓库（[lab](../)）的 `py-night-school/` 目录，内容成型后拆独立仓库开源（保持目录自包含就是为了随时可拆）。
- 调研档案（竞品扫描、逐仓解剖）在 lab 仓 [research/agent-tutorials/](../research/agent-tutorials/)，是教程的**创作输入而非发布物**——拆仓开源时教程正文自包含、不依赖 lab 内部路径（原则见其 landscape.md §5）。
- 教程中「源码路标」引用的框架仓库按 MIT/Apache 等各自协议归属原作者，我们只做导读链接。
- License：待定（拆仓时确定，倾向 MIT）。
