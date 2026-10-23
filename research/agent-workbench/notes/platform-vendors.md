# 调研纪要 A：企业软件平台大厂的跨应用 agent 交付形态

> 来源：subagent 网络调研（2026-10-11），负责厂商：Microsoft / Salesforce / ServiceNow / SAP / Oracle / Workday。
> 证据等级标注沿用本轮约定：【一手】官方页面已抓取核实；【转述】官方页反爬/直连失败，经多个二手来源一致转述；【摘要】仅搜索摘要级。

## 一、逐厂商纪要

### 1. Microsoft —— 混合分层：作业场景内嵌副屏 + 跨应用统一入口 + 治理/运行监控独立工作台

- **M365 Copilot 总览**（官方 Learn 文档，2026-10-01 更新）：https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-overview 【一手】
  - 各 app（Word/Excel/PowerPoint/OneNote/Teams/Outlook）内嵌 Copilot（in-app copilot）；
  - 同时存在独立统一入口 **Microsoft Copilot app**（web/desktop/mobile，由 M365 Copilot Chat 演化而来），作为跨应用 chat + agents + Copilot Search 的统一界面；
  - agents 通过 Copilot Chat 访问；Premium 层有 **Copilot Cowork**："carries out tasks across your Microsoft 365 environment on your behalf"（跨环境代办任务）。
- **Copilot Studio 总览**（2026-09-25 更新）：https://learn.microsoft.com/en-us/microsoft-copilot-studio/fundamentals-what-is-copilot-studio 【一手】——build 侧 studio，运行交付靠渠道："publish them to the channels where your users already work"。
- **Copilot Studio 发布渠道**（2026-09-16）：https://learn.microsoft.com/en-us/microsoft-copilot-studio/publication-fundamentals-publish-channels 【一手】——渠道含 Teams 和 Microsoft Copilot、SharePoint、Demo Website（预建独立网页）、Custom Website、Mobile App 等。agent 即可进副屏（Teams/Copilot），也可有独立页面。
- **Copilot Studio Apps（preview）**（2026-09-25）：https://learn.microsoft.com/en-us/microsoft-copilot-studio/apps-experience/apps-overview 【一手】——**最接近「主屏=应用/数据，副屏=对话」的官方先例**：自然语言生成含数据模型+逻辑+UI 的 app，界面为「左侧对话区 + 右侧交互式 app 预览」。
- **Microsoft Foundry Agent Service**（2026-09-25）：https://learn.microsoft.com/en-us/azure/foundry/agents/overview 【一手】——发布原则："putting your agents where your users already work"；自定义宿主 app 走 Invocations protocol。
- **Dynamics 365**：F&O 各 app 共享内嵌 Copilot 会话 sidecar（ontargit.com 2026-08-31 盘点【转述】）；**agent management（preview）**是跨 F&O 全应用的集中 agent 发现/配置/监控工作区（Microsoft Learn "Agents, Copilot, and AI capabilities in Dynamics 365 apps"，2026-10-02 更新；直接页面 URL 未定位成功，标题+日期可检索【转述】）。
- **HITL**：Copilot Studio Workflows 原话 "Workflows include built-in testing and **human-in-the-loop controls**"；agent flows "can run prompts, call agents, and include **human review steps**"。

**启示**：微软分三层并存——内嵌副屏（单应用上下文）、统一 Copilot app（跨应用任务）、集中工作台（agent 运行监控），而非二选一。

### 2. Salesforce Agentforce —— 混合，但重心是「统一对话入口（Slack）取代在各 Cloud 间跳转」

- **Agentforce 产品页**：https://www.salesforce.com/agentforce/ 【一手】——"supports employees **in the flow of their work**"；集成侧 "MuleSoft API connectors to connect Agents to any system"、Agentforce MCP Support、Agentforce in Slack。
- **Agentforce 360**（Dreamforce 2025，2025-10-13 GA）：官方新闻稿直连 403；采用权威转述【转述】：
  - Investing.com（2025-10-13/14）：Benioff 定位 "Agentforce 360 connects humans, agents and data on one trusted platform"，Agentforce 360 = **digital labor platform**。
  - 行业分析《Salesforce Unveils Agentforce 360: Slack Finally Becomes the Front Door to the Agentic Enterprise》：https://salesforcedevops.net/index.php/2025/10/13/salesforce-unveils-agentforce-360/ 【一手】——**Slack 被定位为 "Agentic OS" / agent 企业的「前门」**：Slack 侧栏直接看客户记录、通知和 agent；传统 Clouds 重组为 Agentforce Sales/Marketing/Service 等 agent 能力。
  - 客户证言（Vercel COO）："We have a goal that **100% of sellers never have to directly enter data in our CRM but only interface via an Agent deployed in Slack**."
- **HITL**：官方 human escalation/approval 页面未直接获取【摘要】。

**启示**：Salesforce 不新建「工作流进度工作台」，而是把 **Slack 当统一 agent 工作台**（对话即工作流），agent 经 MuleSoft/MCP 直连各系统。

### 3. ServiceNow —— 混合，与本题最相关：workflow/task list 起家，agent 织入任务流 + 统一审查工作台（AI Workbench）

- **《ServiceNow AI Agents: Build, Operations & Governance Guide》**（ServiceNow 员工发表于官方社区，2026-08-25）：https://www.servicenow.com/community/servicenow-otto-articles/servicenow-ai-agents-build-operations-amp-governance-guide/ta-p/3569932 【一手】
  - **AI Agent Studio**：no-code/low-code 构建 agent；
  - **Otto panel**（原 Now Assist Panel）：用户与 agent 实时交互的聊天侧栏；
  - **AI Control Tower**：跨原生+第三方 agent 的 Discover/Observe/Govern/Secure/Measure（kill switch、MCP server 审批、成本 ROI）；
  - **与 Flow Designer 集成**：agent 工具首选 **Flow Action**（"prefer Flow Designer over scripts — upgrade-safe and auditable"）——**agent 经平台既有 workflow/API 编排跨系统，而非带用户跳系统**；Agentic Playbooks 把 agent 织入传统 playbook 单个任务，人工决策节点与自主步骤混合；Action Fabric 经 MCP 把 flows/approvals/catalog 暴露给外部 agent；
  - **HITL**：工具级 Execution Mode——**Supervised（agent 出计划、人工批准后执行）vs Autonomous**；官方建议首个 agent 用 Supervised 起步、"high-risk, irreversible actions always require human-in-the-loop"。
- **AI Workbench / AI Control Tower 发布**（Knowledge 2025，2025-05-06；Zurich release 2025-09-10 GA 扩展）：官方新闻稿直连 403【转述】——AI Control Tower = "monitor and manage every AI agent, model, and workflow—native or third-party—in one place"；**AI Workbench = 员工在统一界面 review/validate/approve AI 与 agent 输出的工作台**（n2.help、techpartner.news 多源一致）。
- **EmployeeWorks**（2026-02-26，基于 Moveworks）：员工从 Teams/Slack/浏览器发起请求，EmployeeWorks 将意图转为「受治理的工作流执行」（组织架构、审批、授权），agent 到能力边界或需审批时升级给人工，全程审计轨迹（itbrief.ca 报道【转述】）。

**启示**：ServiceNow 是「**跨系统工作流进度为主屏 + 对话为辅**」最强先例——主屏形态是「任务/playbook/审批队列」（AI Workbench），不是六个系统页面拼进一个屏。

### 4. SAP Joule —— 混合：各模块内嵌 Joule 入口 + Joule 作为套件统一 AI 层与 agent 编排器

- **《How SAP Uniquely Delivers AI Agents with Joule》**（官方 news.sap.com，2025-02-13）：https://news.sap.com/2025/02/joule-sap-uniquely-delivers-ai-agents 【一手】
  - Joule 提供 "a **unified user interface across all business functions** and more than 1,300 skills"；"Suite-first" 原则；
  - Joule 从 copilot 升级为 "**an AI orchestrator across all your organization**"，可 "adaptively assemble and orchestrate teams of agents"（含开箱即用与自建 agent）执行跨职能端到端流程；示例：case classification agent → cash collection agent 多 agent 争议解决流程；
  - 自建 agent 走 Joule Studio in SAP Build。
- **TechEd 2024 官方新闻**（2024-10）：https://news.sap.com/2024/10/sap-teched-copilot-joule-collaborative-capabilities-enterprise-ai 【一手】——Joule 目标覆盖 80% 最常用业务任务；collaborative agents 跨 supply chain/finance/HR 跑跨部门流程。
- **Joule Work**（SAP Connect，2026-10）：官方定位为「**新的 AI 用户界面**，让员工以自然语言与 SAP 各解决方案交互」（news.sap.com【摘要】）；CEO Klein 在 diginomica 2026-04 采访中强调「真正的企业 AI 价值要求从头重造业务流程，而不是给现有软件叠一层 AI」【转述】。
- **HITL**：官方审批/接管 UI 的明确表述未找到【未找到】。

**启示**：各 app 留内嵌 Joule 入口（场景内顺手用），跨模块流程交给 Joule 编排的 agent 团队在统一对话层完成——「统一入口」是编排层，不是新工作台。

### 5. Oracle Fusion AI Agent Studio —— agent 原生嵌入各 Fusion 应用内运行

- **AI Agent Studio 发布**（官方新闻稿，2025-03-20）：《Oracle Introduces AI Agent Studio for Fusion Applications》——"a comprehensive platform for creating, extending, deploying, and managing AI agents across the entire Oracle Fusion Applications suite"（oracle.com 直连 403，标题+日期多源确认【转述】）。
- **50+ 新 agents 嵌入 Fusion**（官方新闻稿，2025-10-15，Oracle AI World）：https://www.oracle.com/news/announcement/ai-world-oracle-advances-enterprise-ai-with-new-agents-across-fusion-applications-2025-10-15（403；内容经 ITBrief 转述【转述】：https://itbrief.com.au/story/oracle-embeds-new-ai-agents-in-fusion-cloud-for-smarter-business）——agents "embedded within the company's suite of cloud applications"、"fit seamlessly into existing business workflows"；配套 AI Agent Marketplace（IBM 首批入驻）。
- **终端用户交付层级**（官方博客《Embedding and Deploying AI Agents for End Users in Oracle Fusion》，2026-03-10【转述】）：最深集成走 VB Studio 嵌入或 Smart Actions——agent 可嵌进具体页面/按钮。
- **HITL**：叙事为辅助决策定位（Payables Agent 在审批流程中执行合规与欺诈检查），未见独立审批工作台叙事。

**启示**：Oracle 是六家里最坚持「嵌入各应用、无独立统一 agent 界面」的——前提是 Fusion 本身是一体化套件。对「6+ 系统分裂」型客户恰是反例：系统天然分裂时，纯内嵌会复现切换问题。

### 6. Workday Illuminate —— Sana 作为统一「experience layer」编排全部 agent + Agent System of Record

- **Workday AI Agents 官方页**：https://www.workday.com/en-us/artificial-intelligence/ai-agents.html 【一手】
  - Illuminate agents 矩阵（Agentic HR/Finance/IT/Legal 等）**由 Sana 编排**：Sana 是 "the **central experience layer**"，"From a question to a finished task, in one conversation"；
  - **Agent System of Record**："unites all your agents—even those outside your organization—with your people and money in one system"；
  - **HITL 原话**："all with appropriate **human oversight** and visibility into those agent decisions and actions"；Talent Management Agent "**with a human in the loop on every output**"；需要人的案件 "routes cases that need a human"。
- **Agent Gateway + AI Agent Partner Network**（官方新闻，2025-06-03）【转述】：第三方 agent 经 Agent Gateway 接入 Workday 数据与 Agent System of Record 统一管理。
- 注：Workday 无名为 "Scout" 的 agent【未找到】。

**启示**：与 Salesforce 同路数——统一对话层（Sana）+ agent 注册治理系统。

## 二、横向小结：大厂收敛出的模式

1. **没有一家把「每个子系统各嵌一个孤立 copilot」作为终态。** 2023-2024 第一波普遍是 per-app 内嵌副屏；2025-2026 六家全部收敛到「**统一 agent 层**」：微软 Copilot app、Salesforce→Slack（Agentic OS）、SAP→Joule（统一 UI + orchestrator）、Workday→Sana、ServiceNow→Otto panel + AI Workbench/Control Tower。唯一例外 Oracle（纯嵌入，因 Fusion 套件本就一体化）。
2. **统一层按用途分两种形态**：
   - **日常作业 = 对话统一入口**（Slack/Copilot Chat/Joule/Sana/Otto panel）；
   - **agent 运行监控 + 审批 = 独立工作台**（ServiceNow AI Workbench / AI Control Tower、Dynamics 365 agent management、Copilot Studio Apps preview）——「跨系统工作流进度为主屏」的先例所在：**主屏是 agent 任务/审批队列/运行进度，不是业务系统页面的拼接**。
3. **「主屏=应用/数据、副屏=对话」的正式产品先例**目前只有 preview 级（Copilot Studio Apps）。大厂更常见的折中是「对话层里渲染记录卡片」。
4. **HITL 收敛为三层**：a) 工具/动作级 Supervised/Autonomous 开关（ServiceNow 最明确）；b) 集中审批队列/工作台（AI Workbench、Control Tower 的 Govern、Copilot Studio human review step）；c) 对话内实时确认与接管。
5. **跨系统作业的官方架构高度一致：agent 经 API/connector/MCP/平台 workflow 编排后端系统，用户不跳系统。六家均无「引导用户跳转多个系统」的方案。**

## 三、未找到/受限项

- SAP Joule 官方 human-in-the-loop 审批 UI 表述（未找到）；
- Salesforce「agent 取代 UI 点击」Benioff 确切原话（未找到；有 digital labor platform 定位与 Vercel 引语）；
- ServiceNow AI Workbench / Knowledge 2025 新闻稿一手页面、Oracle 官网页面（反爬 403，多源二手一致确认）；
- Dynamics 365 "Agents, Copilot, and AI capabilities" 文档中心精确 URL（存在、2026-10-02 更新，多路径猜测 404）。
