# 竞品调研与借鉴分析（landscape）

> **目的**：py-night-school（Python 夜校）教程设计前的市场扫描——现有 agent 教程/课程/官方学习资源长什么样、什么值得借鉴、我们补什么空档。
> **方法与约束**：2026-09-14 调研；WebSearch + `gh api`（取 star/元数据/README，规避 github 网页超时）。star 数为当日实值。
> **证据等级**：仓库元数据来自 GitHub API（可靠）；课程结构来自官方 README/文档站摘录（可靠）；「适合谁/体感」判断为分析性结论。

## 1. 竞品总表

| 对象 | star | 语言 | 形态 | 前置要求 | 框架绑定 |
|---|---|---|---|---|---|
| [microsoft/generative-ai-for-beginners](https://github.com/microsoft/generative-ai-for-beginners) | 119.7k | EN（50+ 机翻） | 21 课 | 有编程基础 | Azure/OpenAI 示例为主 |
| [datawhalechina/hello-agents](https://github.com/datawhalechina/hello-agents) | 78.9k | 中文 | 16 章 5 部（书式） | 基础 Python + LLM 概念 | 中立（自研框架 + 主流框架巡礼） |
| [openai/openai-cookbook](https://github.com/openai/openai-cookbook) | 76.0k | EN | 示例集 | Python 熟练 | OpenAI 生态 |
| [microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners) | 74.7k | EN（50+ 机翻） | 18 课 | 会 Python | Microsoft Agent Framework + Foundry |
| [huggingface/agents-course](https://github.com/huggingface/agents-course) | 32.5k | EN（社区翻译） | 4 单元 + bonus | Basic Python | smolagents/LlamaIndex/LangGraph |
| [datawhalechina/self-llm](https://github.com/datawhalechina/self-llm) | 32.2k | 中文 | 部署/微调指南 | Linux 基础 | 模型侧（非 agent 应用侧） |
| [NirDiamant/GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents) | 24.3k | EN | 50+ notebook 模式卡 | Python 熟练 | 中立 |
| [anthropics/courses](https://github.com/anthropics/courses) | 22.8k | EN | 课程集（notebook） | Python 熟练 | Claude 生态 |
| [microsoft/mcp-for-beginners](https://github.com/microsoft/mcp-for-beginners) | 17.2k | EN | MCP 六语言课程 | 有编程基础 | 中立（.NET/Java/TS/JS/Rust/Python） |
| LangChain Academy（[academy.langchain.com](https://academy.langchain.com/) / [langchain-academy](https://github.com/langchain-ai/langchain-academy)） | — | EN | 官方免费课（notebook） | Python 基础 | LangGraph/LangChain |
| DeepLearning.AI 短课（如 [AI Agents in LangGraph](https://www.deeplearning.ai/courses/ai-agents-in-langgraph)） | — | EN | 视频课 | Python 基础 | LangGraph 等 |

另扫描两个维度确认空档：

- **「Python for Java developers」资源**：一本小书《Python for the Busy Java Developer》、Udemy《Go from Java to Python in 100 Steps》、Real Python 若干文章、零散博客路线图——**全部通用向（脚本/爬虫/数据案例），无一以 agent 开发为场景，且无成体系的开源教程形态**。
- **「无框架手写 agent」内容**：Alejandro AO《agents-from-scratch》、dev.to/Medium 教程、HF 官方视频《Intro to Agents – No Frameworks》、Reddit「60 行 agent」帖——证明该教学法有受众，但均为单篇博客/单视频量级，**无「手写 → 四大生产框架 → 真实产品 → 领域毕业设计」的完整后续**。

## 2. 重点对象深析

### 2.1 microsoft/ai-agents-for-beginners（74.7k★，18 课）

- **结构**：00 课程_setup + 18 课。概念-模式驱动：设计模式（tool use/planning/multi-agent/metacognition）、RAG、可信度、生产化、协议（MCP/A2A/NLWeb）、上下文工程、记忆、CUA、部署、本地化、安全。
- **课时形态（值得借鉴）**：每课 = 书面讲义 + 短视频 + `code_samples/` + 延伸链接，四件套齐整；课程总表带视频/延伸两列导航。
- **配套**：Discord 社区、co-op-translator 自动机翻 50+ 语言（附带 sparse-checkout 指引，因为翻译把仓库撑大了——这是多语言的工程代价）。
- **限制（我们的机会）**：代码绑定 Microsoft Agent Framework + Foundry Agent Service（Azure 账号）；假设 Python 已会；概念巡礼型，无领域毕业设计。

### 2.2 huggingface/agents-course（32.5k★，4 单元）

- **结构**：U0 欢迎 → U1 agent 原理 → U2 框架三部曲（smolagents / LlamaIndex / LangGraph 各一个子单元）→ U3 Agentic RAG 用例 → U4 结业项目（GAIA 基准 + 自动评估 + 证书 + 学生 leaderboard）。另有 bonus（function-calling 微调、可观测性、游戏 agent）。
- **值得借鉴**：前置要求明示（"Basic knowledge of Python"）；unit 化 + 结业大项目的课程弧线；贡献指南分级（错字直接 PR、新单元先开 issue 讨论）；引用格式（bibtex）。
- **限制**：英文为主（社区翻译质量参差）；框架三选的广度型路线，无 langgraph4j 谱系的纵深；结业项目是通用基准（GAIA）而非领域系统。

### 2.3 datawhalechina/hello-agents（78.9k★，中文标杆）

- **结构**：16 章 5 部：基础理论（1–3）→ 构建实践（4–7：手写经典范式 / 低代码平台 / 主流框架 / **自研框架 HelloAgents**）→ 高级（8–12：记忆与检索 / 上下文工程 / 协议 / Agentic-RL / 评估）→ 综合案例（13–15：旅行助手 / DeepResearch / 赛博小镇）→ 毕业设计（16）。
- **值得借鉴**：中文原创 + 在线阅读双通道（GitHub Pages + 国内加速）+ PDF 防贩卖水印；内容导航带状态表（✅/施工中）；社区 Extra 章（面试题/FAQ/踩坑）与共创毕业设计；「组队学习」运营模式。
- **定位差异（关键）**：受众「有编程基础 + 基础 Python」的通用学习者；理论部厚重（智能体史/Transformer）；自研玩具框架是它的高潮章——而我们的路线是「深读生产框架源码」；无 Java 桥、无语言迁移内容。
- **协作关系**：我们的 LLM/智能体理论缺口直接指路它的第一部分，不重复写。

### 2.4 microsoft/mcp-for-beginners（17.2k★）

- 六语言（.NET/Java/TS/JS/Rust/Python）MCP 课程，从会话建立到服务编排。**我们的 L2.5（MCP 课）把它列为延伸材料**，课内只做 Python 主线。

### 2.5 官方课程与示例集

- **LangChain Academy**：Intro to LangGraph（6 单元：图/状态/持久化/HITL）与 LangGraph Essentials（13 课）均免费、notebook 驱动——与我们 langgraph 三连课（L3.2–L3.4）互补，列为延伸。
- **DeepLearning.AI**：《AI Agents in LangGraph》先纯 Python 手写 agent 再用 LangGraph 重建——**对照组教学法的先例印证**；我们把它从一节课升级为「一个单元 + 全程对照」。
- **NirDiamant/GenAI_Agents**：50+ 个「一个 agent 模式一张 notebook」——练习题组织方式的参照。
- **anthropics/courses / openai-cookbook**：各生态官方课与示例集，作为延伸阅读池。
- **OpenAI《A Practical Guide to Building Agents》**：设计理念文档，Unit 2/3 的延伸读物。

## 3. 借鉴决策清单（来源 → 采纳形式 → 落点）

| # | 来源 | 借鉴 | 落点 |
|---|---|---|---|
| 1 | MS for-beginners | 课时四件套（讲义+码+延伸+示例目录） | 升级为六段式课时模板（+Java 对照、+坑位）— CURRICULUM §2 |
| 2 | MS for-beginners | 独立的课程 setup 课（00-setup） | L0.1 工具链课 |
| 3 | MS for-beginners | 课程总表导航 | README 课程地图 + CURRICULUM 总览表 |
| 4 | hello-agents | 内容状态表（✅/施工中） | README 路线图 checklist |
| 5 | hello-agents | 中文原创 + 在线阅读双通道 | 中文正文；在线站列入远期路线图 |
| 6 | hello-agents | 社区 Extra 章 / 共创毕业设计 | 远期（社区期） |
| 7 | HF agents-course | 前置要求明示 + 「适合/不适合」 | README 受众声明 |
| 8 | HF agents-course | 结业项目作为课程弧线终点 | Unit 5（但换为领域系统而非通用基准） |
| 9 | HF agents-course | 贡献分级指南 / 引用格式 | 拆仓开源时补 |
| 10 | DLAI 手写→框架 | 对照组教学法 | Unit 2 → Unit 3 全程对照（教学法主轴） |
| 11 | NirDiamant | 一模式一 notebook 的练习粒度 | 每课 exercises 2–5 个小练习 |
| 12 | rustlings / Exercism（练习平台先例） | 练习即测试（TODO+pytest 验收） | CURRICULUM §3 练习机制 |
| 13 | mcp-for-beginners / LangChain Academy | 官方课作延伸 | 各课「源码路标 + 延伸」段 |

**明确不借鉴/暂缓**（有意识的设计取舍）：

- 短视频课（MS 每课配视频）——制作成本高，文本+可运行代码优先，远期再议；
- 自动机翻多语言（co-op-translator）——中文原创期无需求，且机翻质量会稀释 Java 对照表的精确性；
- 证书 + 排行榜（HF 结业机制）——需要平台侧基建，远期；
- 大部头理论部（hello-agents 第一部分）——明确指路，不重复造轮子；
- 自研教学框架（hello-agents 第七章路线）——与「源码路标读生产框架」路线互斥，我们选后者。

## 4. 差异化定位结论

市面空档 = 下列六点的交集，目前无人占据：

1. **受众唯一性**：以「Java 工程师心智模型」为桥的 agent 教程——每课有对照表与坑位，通用 Python-for-Java 资源不含 agent，agent 课程不含语言桥。
2. **对照组教学法**：mini-agent 先行、四框架全程对照的完整路线（现有先例止步于单课）。
3. **源码路标**：生产框架核心抽象源码导读（现有教程只讲 API 用法；读源码能力恰是 Java 工程师转岗后的隐性门槛）。
4. **毕业设计领域化**：金融合规场景（审批外化/事件溯源/fail-closed）——现有结业项目清一色 GAIA/chatbot/RAG。
5. **端点中立**：任一 OpenAI 兼容端点，不绑 Azure/HF/OpenAI（MS 课程绑 Foundry 是显著痛点）。
6. **轻量课时形态**：30 课时 + 练习验收，不与 16 章大部头竞争全面性。

**风险与对策**：

- 头部教程 star 量级巨大（70–120k），但它们的增长由平台品牌（Microsoft/HF/Datawhale）与先发驱动；本教程以「唯一受众定位」取胜而非全面性——差异化越锐利，越不需要拼体量。
- 框架 API 漂移快（调研已知 6 仓一年内形态剧变）：课时采用「概念锚定 + 版本钉死（pyproject 锁版本）+ 源码路标注明基线 commit」三件对策。
- 单人维护带宽：课程按单元独立成段、可中断可续（沿用本仓 research 工作模式）；每个单元发布即完整可用，不追求一次全量。

## 5. 与本仓调研资产的关系

- 教程的「源码路标」「框架取舍论据」「毕业设计架构」源自 `research/agent-framework/`（17 框架×15 维）与 `research/agent-oss/`（18 产品解剖）两轮源码级调研——这是本教程独有的内容生产资料。
- 注意：lab 仓库内的 research 报告是教程的**创作输入**，不是教程的**发布物**；拆仓开源时教程正文需自包含（源码路标直接指向上游仓库），不依赖 lab 内部路径。

## 6. 本地克隆登记（2026-09-14，写入课时前的实地核对用）

> **2026-09-15 补充**：8 仓已完成课时内容级的深度解剖（代表性课时全文精读），逐仓档案见 [profiles/](./profiles/)，横向综合与设计更新见 [report.md](./report.md)——本文件的 README/元数据级分析与档案的课时内容级分析互补。

上表竞品中 8 个仓库已克隆到 `~/develop/opensource/`（克隆规范见该目录 AGENTS.md）。HEAD 为当日克隆基线，引用内容前可 `git -C <repo> log -1` 核对：

| 克隆目录 | owner/repo | HEAD 基线 | 深度 | 占用 | 用途 |
|---|---|---|---|---|---|
| `ai-agents-for-beginners` | microsoft/ai-agents-for-beginners | `25b7985f` 2026-09-10 | 全量·稀疏（排除 translations/） | 148M | 课时模板与结构参照（借鉴 #1–3） |
| `huggingface-agents-course` | huggingface/agents-course | `b3946b1` 2026-09-09 | 全量 | 33M | unit 结构 / 结业弧线 / 贡献指南（借鉴 #7–9） |
| `hello-agents` | datawhalechina/hello-agents | `4f7682c` 2026-09-04 | depth-1 | 341M | 中文标杆：理论部指路对象 + 状态表/运营参照（借鉴 #4–6） |
| `mcp-for-beginners` | microsoft/mcp-for-beginners | `2f43408b` 2026-09-11 | depth-1 | 764M | L2.5 MCP 课的延伸材料 |
| `GenAI_Agents` | NirDiamant/GenAI_Agents | `cd2ee86` 2026-09-08 | 全量 | 332M | 练习粒度与 notebook 组织参照（借鉴 #11） |
| `langchain-academy` | langchain-ai/langchain-academy | `fa15bec` 2026-06-15 | 全量 | 49M | langgraph 三连课（L3.2–L3.4）延伸 |
| `anthropics-courses` | anthropics/courses | `f4dbb13` 2025-11-13 | 全量 | 225M | 延伸阅读池（prompt engineering 课等） |
| `openai-cookbook` | openai/openai-cookbook | `9aad95f` 2026-09-12 | 全量 | 2.0G | 延伸阅读池 + Unit 2 裸调 API 的官方示例参照 |

刻意未克隆（及理由）：`microsoft/generative-ai-for-beginners`（GenAI 通用课，理论缺口已指路 hello-agents，且 50+ 机翻体积大）、`datawhalechina/self-llm`（模型部署/微调侧，与教程应用层定位正交）、`rust-lang/rustlings`（仅借鉴练习机制概念，Rust 项目本体无用）、DeepLearning.AI 课程（视频平台无仓库）。

克隆过程备注（网络实录）：gh-proxy.com 当日全程 403（AGENTS.md 记录的 WAF 临时拦截窗口）；ghfast.top 承接全部克隆，但 >600M 的全量单连接多次断流（early EOF）——mcp-for-beginners 全量在 1GB+ 断流后改 depth-1 成功，hello-agents 同样降级成功，openai-cookbook（2.0G）全量侥幸成功。教训已沉淀到 `~/develop/opensource/AGENTS.md`。
