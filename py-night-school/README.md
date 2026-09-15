# py-night-school —— Python 夜校

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

## 课程特色

1. **Java 心智桥**：每个概念先给「Java 对应物 + 关键差异」对照表再动手；每个坑按「现象 / 最小复现 / Java 直觉为何失效 / 修复」四段拆解——迁移期最贵的不是不会，而是「似是而非」。
2. **练习即测试**：每课练习是带 TODO 的代码，`uv run pytest` 全绿即过关；hints 渐进提示、答案分离、开放题给 golden answer 诚实降级。八个头部教程解剖的结论是：练习验收是全行业空白——这是我们的核心差异。
3. **对照组教学法**：Unit 2 先手写 ~300 行 mini-agent，之后每个框架课都回来对照「这层抽象替我付掉了什么」，以 OpenAI cookbook 的无框架官方实现为对照原件。
4. **源码路标**：每课延伸给出 `仓库@commit#路径` 精确导读——学框架同时学读生产级 Python 源码（转岗后的隐性门槛）。我们不自研玩具框架，该路线 hello-agents 第七章已做得很好。
5. **双贯穿线 + 金融毕业设计**：明线「报销单审查」从第一课种下、四大框架同题重做；暗线财务 agent 毕业设计每课长一块（审批外化 / 事件溯源 / fail-closed 执行门），结业另产出 Python↔Java 架构映射表。
6. **夜校工程纪律**：中文原创、模型端点中立（任一 OpenAI 兼容 API）、每课独立 uv 项目锁定依赖、图片本地化、克隆即学——竞品的系统性短板（版本漂移、外链失效、绑定云厂）在这里默认不发生。

> 特色 2–6 的方法论出处与证据见 [research/agent-tutorials/report.md](../research/agent-tutorials/report.md)（八仓教学解剖综合报告）。

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

- **环境**：只需安装 [uv](https://docs.astral.sh/uv/)（教程第一课带你配好，macOS / Windows / Linux 均可，平台差异处会对照标注），每课是独立可运行的 uv 项目。
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
- [x] Unit 0 内容与练习（L0.1 工具链 + 明线种子）
- [x] Unit 1 内容与练习（九课 + 里程碑：语言核心·Java 对照，三态验证全过）
- [ ] Unit 2 mini-agent 全部代码
- [ ] Unit 3 四框架课
- [ ] Unit 4 产品实战课
- [ ] Unit 5 毕业设计与参考实现
- [ ] （远期）在线阅读站 / 英文版 / 社区贡献指南

## 工程说明

- 本教程的工作规范（中心思想 / 设计理念 / 硬性纪律 / 写课流程）见 [AGENTS.md](./AGENTS.md)。
- 本教程当前生活在个人实验室仓库（[lab](../)）的 `py-night-school/` 目录，内容成型后拆独立仓库开源（保持目录自包含就是为了随时可拆）。
- 调研档案（竞品扫描、逐仓解剖）在 lab 仓 [research/agent-tutorials/](../research/agent-tutorials/)，是教程的**创作输入而非发布物**——拆仓开源时教程正文自包含、不依赖 lab 内部路径（原则见其 landscape.md §5）。
- 教程中「源码路标」引用的框架仓库按 MIT/Apache 等各自协议归属原作者，我们只做导读链接。
- License：待定（拆仓时确定，倾向 MIT）。
