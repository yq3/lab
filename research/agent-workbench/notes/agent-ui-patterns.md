# 调研纪要 C：Agent 时代的 UI 形态与交互设计模式

> 来源：subagent 网络调研（2026-10-11）。评估对象：用户设想的「统一工作台——主屏=跨系统工作流进度+数据详情，副屏=agent 对话」。
> 证据等级：【一手】已抓取全文核实；【转述】二手转述；【摘要】搜索摘要级；✅ = agent 已抓取全文。

## 一、逐主题纪要

### 主题 1：副屏/sidecar copilot 模式及其边界

- **《Where should AI sit in your UI?》**（Vitaly Friedman，uxdesign.cc，2025）——AI 放置四类：① 客服悬浮件；② inline overlay；③ **sidecar 侧边面板**（Notion AI、Figma、Microsoft Copilot）；④ 全流程 AI 体验。对 sidecar 判词：已是生产力工具主流，但**挤占屏幕空间、收起后易被忽略，且「只有在输出能方便搬回主工作区时才工作得最好」**——设计假设是「单一主应用上下文」。URL: https://uxdesign.cc/where-should-ai-sit-in-your-ui-1710a258390e 【转述（站点反爬，经搜索摘要核实）】
- **Microsoft 官方 sidecar 文档**：《Enable Copilot capabilities in finance and operations apps》（learn.microsoft.com）明确 Dynamics 365 的 Copilot 是 "sidecar" 形态，跑在主 UI 旁【转述】；Microsoft Design《A simplified system》描述 side panel 为「reasoning、actions、outputs 的捕获入口」+瞬态轻量界面【转述】。
- **《7 AI agent interface architectures beyond the Chatbot》**（AI Accelerator Institute，2026-08-13）——生产团队在交付的 7 种 agent UX 架构（generative UI 到 MCP Apps），证明「聊天窗只是 7 种形态之一」已是共识【转述】。
- **学术批评**：《Software as Content: Dynamic Applications as the Human-Agent Interaction Layer》（arXiv:2603.21334，2026-03-22）✅——聊天式界面三个固有缺陷：**① 结构化数据与线性文本不匹配；② 无约束自然语言输入熵过高；③ 缺乏持久的、可演化的交互状态**；提出 agent 应生成「任务特定的动态应用界面」作为人机交互层。URL: https://arxiv.org/abs/2603.21334 【一手】

**小结**：sidecar copilot 的公认适用边界=单应用内的上下文增强/产物生成；跨应用、多步骤、长时任务流程不在其设计假设内。

### 主题 2：Agent-first / 分屏 agent 工作台

- **《The New Dominant UI Design for AI Agents》**（Andy Walters，Emerge Haus，2025-05-05）✅——**直接命名「split-screen agent UI」**：左约 50% 聊天区 + 右约 50% "dynamic viewer panel"（agent 操作实时视图）。举证 OpenAI Operator、Manus、开源 Open Operator。优势=透明度/信任/可控（"A well-designed split-screen agent UI inspires trust by keeping the user in the loop"）；挑战=agent 既是沟通对象又是监控对象；预言会出现「多步工作流可视化」变体。URL: https://www.emerge.haus/blog/the-new-dominant-ui-design-for-ai-agents 【一手】
- **Manus**：分屏=左侧 agent 思考过程/对话、右侧 "Manus's Computer"（浏览器/文件实时视图）+可并行任务列表【转述】。
- **Devin**（Cognition）：session 视图含 plan editor、terminal、代码编辑器、沙箱浏览器【转述】。
- **GitHub Copilot coding agent**：issue 指派→后台执行→产出 PR；**PR timeline 即进度视图**；2025-07-30 GitHub 官方博客：agent 持续更新 PR 标题和正文提供 at-a-glance 进度；PR 内有 session log 回放、checkpoint【转述】。
- **OpenAI Codex（云端）**：异步任务列表+沙箱面板，交付物是 PR【转述】。
- **ChatGPT Agent 模式**（2025-07 上线）：对话叙事流+内嵌实时浏览器/终端视图，可随时打断，有**「take over（接管）」按钮**直接夺取浏览器/终端控制权【转述】。
- **Claude Code 官方最佳实践**（https://code.claude.com/docs/en/best-practices）✅——四阶段「探索→计划→实现→提交」；plan mode 只读探索；todo list 前置；多实例并行（writer/reviewer 双会话、/batch 扇出）；验证门控（"Give Claude a check it can run"）；checkpoint/rewind。「plan 可视化+进度勾选」的最权威实践来源【一手】。
- **Numerous.ai**：`=AI()` 公式把模型变成表格函数、批量跑整行/列——「应用变成 agent 批处理容器」的实例【转述】。
- **企业级先例**：
  - **SAP Joule Work**（2026-10 SAP Connect）：官方定位「**新的 AI 用户界面**，让员工以自然语言与 SAP 各解决方案交互」；CEO Klein 按 "headless IT" 概念设计未来 ERP 界面；diginomica 2026-04 采访：「真正的企业 AI 价值要求从头重造业务流程，而不是给现有软件叠一层 AI」【转述】。
  - **ServiceNow**：AI Agent Orchestrator（2025-01-30）→ AI Control Tower（Knowledge 2025）→ **Autonomous Workforce + EmployeeWorks**（2026-02-26）：员工从 Teams/Slack/浏览器发起请求，意图转为「受治理的工作流执行」，agent 到边界或需审批时升级人工，全程审计轨迹（itbrief.ca 2026-02-26）✅【转述】。

### 主题 3：Generative UI / Canvas 双栏模式

- **Claude Artifacts**（2024-06 首创）与 **ChatGPT Canvas**（2024-10）均「对话+可编辑产物画布」并排（Digital Trends 2024-10 对比文【转述】）。
- **v0**（Vercel）：chat + 实时代码/预览双栏；Vercel AI SDK 官方 Artifacts 模板自述「chat 界面之外的 workspace 式界面」【转述】。
- **Figma Make / Figma Design Agent**（figma.com 博客 2026-05-20）：prompt-to-app + Design/Make 交接，聊天+画布范式最新大型实践【转述】。
- 批评样本：《ChatGPT, Claude, and Gemini still have a critical UI flaw》（xda-developers，2026-06-03）：canvas 类工作区超出基础问答后仍显笨重【转述】。
- **与用户设想的异同**：Canvas/Artifacts 右栏是「agent 生成中的单一产物」；用户设想主屏是「跨系统流程状态+既有业务数据」——更接近 BPM 工作台+agent 监控的混合。两者在合流（generative UI 让 agent 按任务动态生成主屏内容）。

### 主题 4：任务收件箱 / HITL / human takeover 模式

- **BPM 传统**：Camunda **Tasklist**（claim/complete 用户任务，REST API 为构建以人为中心的流程应用设计）；Temporal durable execution + workflow 事件历史视图 + signal【转述】。
- **LangGraph**：`interrupt(value)` 暂停图执行并呈现待决数据，人工输入经 `Command(resume=...)` 恢复，需 checkpointer；LangGraph Studio/Dev UI 可查看中断状态并提交 resume 值【转述】。
- **Microsoft Copilot Studio**：审批经 Power Automate approvals 嵌入；《Monitor overview》（2026-08 更新）提供 agent 级运行监控；配 Purview 审计日志【转述】。
- **AWS Pizza Bot**（aws.amazon.com/blogs/opensource，2026-09-10，Joseph Dolivo & Igor Fil）✅——**当前最完整的「agent 收件箱」设计文本**：Amazon 内部 2000+ 人使用后开源（Apache 2.0）。核心论断："That is babysitting, not collaboration"；**"The interface assumes you are not watching"**；UI=邮件客户端式三队列（All / Unread / **Action-待批准**）；Activity 面板展示主 agent 委派子 agent 的工作及完整 transcript；**审批卡片带 edit 选项（直接修改 agent 的提议而非打回重来）**，批准暂停跨会话跨设备持久；直连 MCP 服务器取工具。URL: https://aws.amazon.com/blogs/opensource/introducing-pizza-bot-an-open-source-inbox-for-ai-agents-that-work-in-the-background/ 【一手，本报告作者已二次复核】
- **客服领域**：Intercom Fin 的 Agent Inbox、Zendesk AI 人机 handover；Sierra AI 反其道不建收件箱、把升级流回客户既有系统【转述】。Cloudflare 开源 agentic-inbox 自托管邮件客户端【转述】。
- **NN/g**：《A Concrete Definition of an AI Agent》（Caleb Sponheim，2026-04-03）✅——agent 四特征（目标/迭代/行动/自主决定下一步）；UX 启示：**可观察性（展示计划、任务清单、进度）、可控性、用用户研究定位「用户在哪失去信任/被迫纠正/放弃」**。《AI Agents as Users》（2026-04-10）：为 agent 这个「用户」设计产品的新视角【转述】。

### 主题 5：观点文章 / SaaS 转型讨论

- **「The Death of the SaaS URL」精确标题的 a16z 文章：未找到**【未找到】。最接近的同类论述：Satya Nadella "business applications will collapse / SaaS is dead" 论；Forrester《SaaS As We Know It Is Dead》（2026-02-11）；Bain《The Great Debate: Will Agentic AI Kill SaaS?》（2025-01-23：若 agent 取代 SaaS 业务逻辑层，SaaS 只有在拥有独特数据/工作流时存活）；《SaaS is Losing Its Head》（2026-03-03：agent 成为 UI，「头」没了但后端服务永存）；a16z Show 第 381 期《Is SaaS Dead in a World of AI?》（2026-02）。**共同含义：跨系统的 agent 界面会取代/绕过各 SaaS 自己的 UI，成为新的前端。**
- **service-as-software**：正源 Foundation Capital《The $4.6T Services-as-Software Opportunity》（2025-07）：软件从卖席位变成卖「工作成果」。Packy McCormick 专文：未找到【未找到】。
- **Anthropic《How people use Claude Code》精确标题工程博客：未找到**【未找到】。可核实替代：① Claude Code 官方 best practices ✅；② Anthropic 250K 对话研究（2026-08）：Claude Code 用户在 31 类输出中的 26 类上比 chat/Cowork 用户授予更高自主权；③《Building a C compiler with a team of parallel Claudes》（2026-02-05：16 agent 并行、无人工干预）。

## 二、对用户设想的评价依据汇总

**A. 「主屏=工作流进度+数据详情、副屏=对话」有无先例/名字？**

有先例，但布局方向与设想相反：业界主流是**「左聊天 + 右工作区」的 split-screen agent UI**（Emerge Haus 2025 命名），代表 Manus、OpenAI Operator、ChatGPT Agent、Devin。**核心是「agent 作业现场为主屏、对话为辅屏」**，与用户设想在主从关系判断上完全一致，物理位置镜像属实现细节。企业级同构先例：SAP Joule Work、ServiceNow EmployeeWorks/AI Workbench、GitHub Copilot coding agent（PR timeline 即跨步骤进度视图）。布局无单一公认名称，相关命名散见：split-screen agent UI / agentic workspace / agent workbench / AI control tower / agent inbox。**税务行业专属同类工作台先例：未找到**（可自证的创新点）。

**B. 副屏 copilot 模式的公认局限**

1. 设计假设=单应用上下文，产物「需能方便搬回主工作区」才有效（uxdesign.cc 2025）；
2. 聊天窗三固有缺陷：结构化数据 vs 线性文本不匹配、自由输入熵高、无持久演化状态（arXiv:2603.21334）；
3. 实时聊天假设双方同时在场，对长任务失效——"babysitting, not collaboration"（AWS Pizza Bot 2026）；
4. NN/g：agent 界面必须补足可观察性与可控性，否则用户「失去信任、被迫纠正、放弃」（2026-04）；
5. Microsoft 自己把 Dynamics 的 Copilot 定位为「主 UI 之外」的 sidecar；SAP Klein 明言不能「给现有软件叠一层 AI」。

**C. 长任务的进度与中间产物呈现方式**

① plan/todo 清单勾选（Claude Code、NN/g）；② step timeline + session log 回放 + checkpoint（Copilot coding agent）；③ 实时「作业现场」视图+思考叙事（Manus's Computer、ChatGPT Agent）；④ 产物即进度：PR/diff 预览作为阶段交付物；⑤ 持久化事件历史/工作流图（Temporal、LangGraph Studio）；⑥ 收件箱队列 + Activity 面板 + 审批卡片（Pizza Bot）；⑦ 审计轨迹（ServiceNow、Copilot Studio+Purview）。

**D. human takeover / HITL 的 UI 模式分类（六类）**

1. **事前审批门（approve/reject/edit）**：LangGraph interrupt+resume；Copilot Studio approvals；Pizza Bot 审批卡片（含 edit 直接修改 agent 提议）；
2. **异步任务收件箱**：Camunda Tasklist、Pizza Bot 三队列、Intercom Fin Agent Inbox；
3. **实时接管（takeover）**：ChatGPT Agent 的 take over 按钮；
4. **计划先行审阅（plan-first）**：Claude Code plan mode、Devin plan editor；
5. **升级/转人工（escalation/handover）**：ServiceNow 达边界升级人工、客服 handover；
6. **事后验证（post-hoc review）**：PR diff 评审、对抗性评审子代理、checkpoint 回滚。

**对设想的总体判断**：方向合理且有强先例——跨系统统一工作台正是 SAP/ServiceNow/微软 2025-2026 共同走向（「agent 成为新前端」）；主屏承载流程+数据、对话降为副屏，恰好修正 sidecar copilot 的公认缺陷。需吸收的业界提示：① 副屏对话不应是唯一通道，长周期税务任务应叠加「收件箱/通知」异步模式（"interface assumes you are not watching"）；② 主屏不宜只是静态仪表盘，应支持 generative UI/按任务动态生成详情视图；③ HITL 做一等公民（六类模式，尤其审批+接管+审计）；④ 数据详情可深链回源系统，工作台定位编排/监督层而非重建全部交易 UI（Bain/Forrester 对 SaaS 分层的判断）。

## 三、未找到项

a16z 精确标题《The Death of the SaaS URL》；Packy McCormick service-as-software 专文；Anthropic《How people use Claude Code》精确标题博客；税务行业专属 agent 工作台公开先例。均给出最接近的可核实替代来源。
