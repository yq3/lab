# 统一税务 Agent 工作台设想评估——业界方案调研报告

> 调研时间：2026-10-11 ｜ 性质：网络调研（非源码级）｜ 过程纪要见 [notes/](./notes/)（四路：平台大厂 / 税务垂直 / Agent UI 形态 / 集成架构）
> 证据等级：【一手】官方页面已抓取核实（含作者二次复核）；【转述】官方页反爬/直连失败，经多个二手来源一致转述；【摘要】仅搜索摘要级。【未找到】如实标注，不臆测。

## 0. 结论速览（TL;DR）

调研的原始问题：税务部门 6+ 系统（计税/所得税/申报/披露/关联交易/税务资产）各自独立，业务流（如国内增值税申报）跨系统切换。**在子系统上接 agent 副屏不妥，是否应新建统一工作台（主屏=工作流进度+数据详情，副屏=agent 对话）？**

1. **方向成立**：2025-2026 业界（微软/Salesforce/ServiceNow/SAP/Workday 六大平台厂 + Avalara/TR 等税务厂商）全部收敛到「跨系统统一 agent 层」，**没有一家押注「每个子系统各挂一个 copilot 副屏」作为终态**。副屏模式的公认设计假设是「单一应用上下文」，跨系统流程不在其能力假设内。
2. **但要对设想做三处修正**：
   - **主屏的「工作流进度」必须是编排引擎（durable workflow）事件流的投影，不是前端自造的状态，也不是六个系统页面的拼接**——没有后端编排引擎，主屏无真实数据可显示（业界先例：Temporal UI / LangGraph Studio / UiPath Action Center，后者 2020 年就做出「流程进度+人工审批门户」，早于 LLM agent）；
   - **副屏对话不是唯一人机通道**：长周期税务任务（申报季/关账）要叠加异步「收件箱/通知」模式——AWS 开源 Pizza Bot 的设计原则 "The interface assumes you are not watching" 是当前最清晰的表述【一手】；
   - **审批（HITL）要做一等公民**：税务行业全行业底线是 agent 产出到 "signature-ready / Ready to Review" 为止，**final review + sign-off 永远留给人**；审批门、接管（take over）、审计轨迹是工作台的核心件，不是附属功能。
3. **前端不是成败关键，其下三层才是**：系统接入层（存量 API→MCP 网关化 + OAuth 委托身份 + agent-id 审计）、编排层（确定性流程为主干、agent 为节点、human task 为一等节点）、治理层（审批中心/agent 注册表/审计）。业界证据支持「接入层与编排先行、前端按引擎事件流设计」的生产化顺序；前端可先做 UX 原型验证。
4. **税务特有纪律**：计税等高风险计算用确定性引擎、LLM 只做编排/提取/综合（Avalara 原话【一手】）；browser agent（直接操作现有系统 UI）在真实企业场景成功率不足 5%（Salesforce SCUBA，ICLR 2026），只可作无 API 系统的过渡兜底，不能当主干。

## 1. 背景与问题定义

- **现状**：SaaS 时代烟囱式建设——计税系统、所得税系统、申报系统、披露系统、关联交易系统、税务资产系统各自独立；一条业务流（国内增值税：销项/进项→计税→申报表→申报→缴款→归档）要跨系统来回切换。
- **候选方案**：a) 在每个子系统内嵌 agent 副屏；b) 新建统一「agent 工作台」（主屏=跨系统工作流进度+数据详情，副屏=agent 对话）统筹全流程。
- **调研问题**：设想是否合理？业界有没有更成熟的方案？布局形态有没有先例？前端之下需要什么架构？

## 2. 业界全景

### 2.1 平台大厂：全部收敛到「统一 agent 层」，内嵌副屏只是存量增强

六家路径（证据详见 [notes/platform-vendors.md](./notes/platform-vendors.md)）：

| 厂商 | 统一层形态 | 跨系统怎么干 | 值得抄的点 |
|---|---|---|---|
| Microsoft | 各 app 内嵌 Copilot + 独立 **Copilot app**（跨应用 chat+agents）+ 集中 agent 管理工作台 | agent 经 connectors/MCP 编排，"putting your agents where your users already work" | **Copilot Studio Apps（preview）**：「左侧对话+右侧交互式应用预览」——与设想最接近的官方先例【一手】 |
| Salesforce | **Slack = "Agentic OS"**，agent 前门 | MuleSoft/MCP 直连各 Cloud，用户不再进各 Cloud | 最激进叙事：Vercel 目标「100% 卖家只经 Slack 里的 agent 界面工作，不直接进 CRM」【转述】 |
| ServiceNow | Otto panel（对话侧栏）+ **AI Workbench（统一审查/审批工作台）**+ AI Control Tower（治理） | agent 工具首选平台 Flow Action——**agent 经既有 workflow/API 编排跨系统，而非带用户跳系统**【一手】 | **与设想最同构**：Supervised/Autonomous 工具级开关；「高风险不可逆动作必须 HITL」官方原则 |
| SAP | 各模块内嵌 Joule + **Joule = 套件统一 AI 层与 agent 编排器**；2026-10 推 Joule Work「新的 AI 用户界面」 | Joule 编排 agent 团队跑跨职能流程（1300+ skills） | CEO Klein：「真正的企业 AI 价值要求从头重造业务流程，而不是给现有软件叠一层 AI」【转述】 |
| Oracle | **无统一层**，50+ agents 嵌入各 Fusion 应用 | Fusion 本身是一体化套件 | 反例参照：系统天然分裂时，纯内嵌会复现切换问题 |
| Workday | **Sana = "central experience layer"** 编排全部 agent + Agent System of Record | Agent Gateway 接第三方 agent 统一治理 | "human in the loop on every output"（Talent Agent）【一手】 |

**收敛规律**：① 2023-24 第一波 per-app 副屏 → 2025-26 全部加「统一 agent 层」；② 统一层分两种用途——**日常作业=对话统一入口，agent 运行监控+审批=独立工作台**（进度主屏的先例在后者）；③ 六家跨系统方案全部是「agent 经 API/connector/MCP 编排后端，用户不跳系统」，无一带用户跳转的方案。

### 2.2 税务垂直：三种解法，全行业人机分工底线一致

（证据详见 [notes/tax-vendors.md](./notes/tax-vendors.md)）

| 模式 | 代表 | 做法 |
|---|---|---|
| **平台网络化 + AI 嵌入各产品** | Thomson Reuters | ONESOURCE+「智能合规网络」打通数据/工作流；CoCounsel UX 嵌入每个产品；统一 NL 入口是路线图而非现品 |
| **统一 Agent Hub 嵌入门户** | **Avalara Aviator**（2026-09 发布、10-08 GA）、航天信息金税智能体、税友数智工场 | 编排 agent（Avi）+ 按域专家 agent（Transactions/Returns/Research/Certificates）；hub 长在统一门户里 |
| **先有统一平台，再嵌 agent** | KPMG Digital Gateway × Claude Cowork（2026-05）；EY 编入 8 万人交付流程 | 统一平台承载人+agent 协同工作面 |

**与设想最直接的对标——Avalara Aviator**【一手，已二次复核】：
- agent 编队：Avi（编排，分派工作+预警+"keeps humans in control of critical approvals"）+ 四个领域专家 agent；
- UI：**"launches directly inside the Avalara Portal experience you already use" + "In-app notifications and actions without switching systems"**——统一门户为主屏、对话/通知为辅助层；
- 人机边界："Human-in-the-loop approval gates for all critical tasks"；提交申报/规则覆盖/豁免审批 "require explicit human sign-off"；
- 计算纪律："**Aviator relies on Avalara's proprietary deterministic tax engine. Generative AI is strictly used for orchestration, unstructured document extraction, and statutory synthesis**, with 100% of outputs mapped to verified tax laws and confidence-scored"。

**国内**：税友「数智工场」（2025-08）=「驾驶舱（监督主屏）+ 数智会计（后台数字员工，记账人效 10 倍）+ 合规顾问」；航天信息「金税智能体」（2026-08）= 三层大模型架构 + 贯通开票/记账/申报/报销/风控的场景 agent 群 + 智能体平台承载。国内形态与 Avalara 同构：**主屏是监督驾驶舱/流程，agent 在后台作业**。

**注意**：没有任何税务厂商公开过「主屏=流程进度+数据详情、副屏=对话」这种显式双栏工作台的产品页或截图【未找到】——该具体形态与行业方向一致但**略超前**，属于可自证的设计决策，不是照抄现成产品。

### 2.3 Agent UI 形态学：设想的布局有名字、有先例、有已知坑

（证据详见 [notes/agent-ui-patterns.md](./notes/agent-ui-patterns.md)）

- **名字**：业界叫 **split-screen agent UI**（Emerge Haus 2025 命名【一手】）：约 50% 对话区 + 50% "dynamic viewer panel"（agent 作业现场实时视图）。代表：Manus、OpenAI Operator、ChatGPT Agent、Devin。物理布局与设想镜像（业界多左对话右工作区），但**主从关系判断一致：agent 作业现场为主屏、对话为辅屏**——这是实现细节，不影响设想成立。
- **副屏 copilot 的公认局限**（= 为什么不该在子系统挂副屏）：① 设计假设单应用上下文，产物「需能方便搬回主工作区」才有效；② 聊天窗三固有缺陷——结构化数据 vs 线性文本不匹配、自由输入熵高、无持久演化状态（arXiv:2603.21334【一手】）；③ 实时聊天假设双方同时在场，对长任务是 "babysitting, not collaboration"（AWS Pizza Bot【一手】）。
- **长任务进度的呈现谱系**（工作台主屏的弹药库）：plan/todo 勾选（Claude Code 官方最佳实践【一手】）→ step timeline + session log 回放 + checkpoint（GitHub Copilot coding agent 的 PR timeline）→ 实时作业现场视图（Manus's Computer）→ **产物即进度**（PR/diff 预览作为阶段交付物）→ 事件历史/工作流图（Temporal/LangGraph）→ **收件箱队列 + Activity 面板 + 审批卡片**（Pizza Bot）→ 审计轨迹。
- **HITL 六模式**（税务工作台的必备件清单）：① 事前审批门（approve/reject/**edit**——直接修改 agent 提议而非打回）；② 异步任务收件箱；③ 实时接管（take over 按钮）；④ 计划先行审阅（plan-first，执行前人审计划）；⑤ 升级/转人工；⑥ 事后验证（diff 评审 + checkpoint 回滚）。
- **宏观趋势佐证**：「agent 界面取代各 SaaS 自己的 UI 成为新前端」已是 Forrester/Bain/a16z/SAP CEO 的共同判断（"SaaS is losing its head"——头没了，后端服务永存）。设想的统一工作台正是这个方向在企业内部落地的形态。

### 2.4 集成架构：工作台之下要有的三层 + 标准组件

（证据详见 [notes/integration-architecture.md](./notes/integration-architecture.md)）

业界对「agent 接 N 个既有系统」收敛出的分层图：

```
┌─────────────────────────────────────────────────────────────┐
│ ④ 前端消费层：统一工作台 = 编排引擎状态的投影                    │
│    主屏=流程事件流+数据详情(深链回源系统)+待办/审批队列            │
│    副屏=agent thread；通知=IM/邮件；审批卡=HITL interrupt 入口   │
├─────────────────────────────────────────────────────────────┤
│ ③ 编排层：durable workflow 引擎（Camunda「规则用流程、判断用    │
│    agent」；Temporal/LangGraph/UiPath Maestro）               │
│    确定性流程主干 + agent 节点 + human task 一等节点            │
├─────────────────────────────────────────────────────────────┤
│ ② 连接治理层：MCP registry + agent registry(A2A Agent Card)   │
│    + OAuth 2.1/OBO 身份委托链 + 网关策略(agent-id 审计/限流)    │
├─────────────────────────────────────────────────────────────┤
│ ① 系统接入层：6 个系统的存量 API → MCP 网关暴露为 tools         │
│    (Azure APIM「REST API→MCP server」/ Higress / agentgateway)│
│    无 API 系统用 RPA/browser agent 兜底(限人在场监督)           │
└─────────────────────────────────────────────────────────────┘
```

**路线判断**（强审计场景的证据一边倒）：
- **API/MCP 编排为主干**：企业成熟度高（云厂商已产品化 GA）、审计合规成熟（调用日志+身份委托+策略）；
- **browser agent 不当主干**：OSWorld 类基准最优 ~82%，但真实企业场景 <5%（Salesforce SCUBA，ICLR 2026）；操作粒度是截图+点击坐标，难满足「不可变/身份绑定/可重放」的审计标准；UiPath/Automation Anywhere 的 agentic 转型都是 **API-first、UI 自动化只留给无 API 遗留系统**；
- **进度主屏 = workflow 引擎可视化投影**：Temporal UI（event history Timeline）、LangGraph Studio（checkpoint+interrupt 恢复）、UiPath Action Center（2020 年的前 LLM 原型）都是先例。**主副屏的联动点 = HITL interrupt：agent 需要审批时进度条停住、对话与审批卡片同时出现。**

## 3. 对设想的逐点评估

### 3.1 成立的部分（业界强证据支持）

1. **否定「子系统各挂副屏」**：六大平台厂 + 税务厂商无一押注；副屏的公认设计假设（单应用上下文）与跨系统流程冲突；Oracle 的纯内嵌路线恰恰建立在 Fusion 套件一体化的前提上，与「6 系统分裂」现状相反。
2. **统一工作台统筹全流程**：ServiceNow（AI Workbench）、SAP（Joule Work「新的 AI 用户界面」）、Avalara（Aviator hub 嵌入门户）都在做同构的事。
3. **主从关系（作业现场为主、对话为辅）**：split-screen agent UI 的核心判断与此一致；对话降为副屏恰好修正聊天窗的三固有缺陷。
4. **工作台显示「工作流进度+数据详情」**：ServiceNow AI Workbench、UiPath Action Center、Copilot coding agent PR timeline 验证了这种主屏的信息架构。

### 3.2 需要修正/补强的部分

1. **主屏数据来源**：进度必须来自编排引擎事件流。若先做前端、后端无引擎，进度只能伪造——业界无此做法（无权威论述直接比较先后，但所有参考架构把编排/工具/治理作为核心层，前端为投影；详见 notes D §三D）。
2. **主屏内容边界**：是「流程状态 + 汇聚视图 + 待办/审批队列」，**不是六个系统交易界面的重建**。数据详情深链回源系统（工作台=编排/监督层），否则项目范围失控；generative UI 趋势（Copilot Studio Apps、MCP Apps）支持「按任务动态生成详情视图」而非静态拼页面。
3. **通道多元化**：副屏对话之外必须有异步收件箱/通知（申报季人不可能盯着对话流）；"The interface assumes you are not watching" 是当前最好的设计原则表述【一手】。
4. **HITL 一等公民**：审批门（含 edit 选项）、接管按钮、plan-first（执行前人审计划）、事后 diff 评审 + 回滚、全程审计轨迹。税务全行业底线：final review + sign-off 留给人（TR 原话 "without human intervention until final review and sign-off"【一手】）。
5. **计算纪律**：计税/校验等高风险计算走确定性引擎，LLM 只做编排/文档提取/综合/解释（Avalara 模式）；输出映射到法规依据并打置信度。
6. **agent 组织**：编排 agent + 按域专家 agent（增值税/所得税/转让定价…），而非一个全能 agent（Avalara、航信、A2A Agent Card 发现机制同构）。

## 4. 建议的目标形态与演进路线

### 4.1 目标形态（一句话）

**新建统一「税务 agent 工作台」作为编排/监督层：主屏=编排引擎驱动的流程进度 + 数据汇聚视图（深链回源系统）+ 待办/审批队列；副屏=agent 对话；另配异步通知与审批收件箱；其下以 MCP 网关接入 6 系统、durable workflow 做流程主干、确定性引擎做计税、全程身份委托与审计。**

### 4.2 演进路线（按业界证据推导）

| 阶段 | 做什么 | 业界依据 |
|---|---|---|
| **P1 接入层**（最难、复用价值最高） | 6 系统存量 API 经网关 MCP 化（APIM/Higress/agentgateway 模式）；OAuth 2.1 + OBO 身份委托链（用户→agent→工具）；agent-id 审计随网关落地。无 API 系统先列兜底清单 | APIM「REST API→MCP server」GA；MCP 授权规范；UiPath API-first |
| **P2 试点流** | 选国内增值税一条端到端流上 durable 编排引擎：确定性步骤（法定时点/校验规则）+ agent 节点（取数/映射/生成草表）+ human task 节点（复核/签核/提交）。agent 从 **Supervised 起步**（出计划、人批准后执行） | ServiceNow「首个 agent 用 Supervised 起步」「高风险不可逆必须 HITL」【一手】；Camunda 三段光谱 |
| **P3 工作台前端生产化** | 主屏渲染引擎事件流（进度/耗时/卡点）+ 数据详情（深链）+ 待办审批队列；副屏挂 agent thread；审批卡复用 interrupt（带 edit）；叠加 IM 通知 | Action Center / Temporal UI / LangGraph Studio 先例；Pizza Bot 收件箱；Copilot Studio Apps 双栏 |
| **P4 横向扩展** | 扩税种/场景 → 编排 agent + 专家 agent 编队；agent 经 A2A/Agent Card 纳入注册表统一治理；建立 agent 目录与 kill switch（AI Control Tower 同构） | Avalara Aviator 编队；A2A Agent Card；ServiceNow Control Tower |

前端可先做 UX 原型（信息架构/双屏布局/审批交互的可用性验证），但生产化顺序以 P1/P2 为前置依赖。

### 4.3 需要同步建设的治理件

审批中心（interrupt→人工 action→恢复）、agent 注册表与 kill switch、审计日志（不可变/身份绑定/可重放）、模型网关（成本/护栏）、带 RBAC 的税务法规知识库（RAG，供 Research 类 agent 引用溯源）。

## 5. 风险与开放问题

1. **SOX/内控不会随 agent 自动内置**——Deloitte Zora 明确 FAQ 承认需并行 Risk & Controls 工作流【一手】；立项时就要把控制点设计进流程模型（human task 节点即控制点）。
2. **组织与归属**：统一工作台天然是跨 6 个系统建设方的公共资产，需要先解决所有权/维护权/需求优先级治理，否则会重演烟囱（六大厂靠平台组织收敛，甲方可参考「平台团队+领域团队」结构）。
3. **NHI/agent 身份治理仍是行业真空期**（CSA Labs 2026-05）——网关层身份委托要早做，后期补很痛。
4. **无 API 的存量系统**：RPA/browser agent 兜底的成功率与审计合规都差（SCUBA <5%），应作为推动源系统补 API 的过渡手段，并限定人在场监督。
5. **对话窗口的形态惯性**：团队容易把工作台做成「聊天为主+挂个仪表盘」。业界证据（arXiv:2603.21334、Pizza Bot）反复指出这是错误重心——主屏的流程/数据/审批才是主体。
6. **开放问题**：a) 税务行业无公开的显式双栏 agent 工作台成品（形态略超前，需自己做 UX 验证）；b) 「前端 vs 编排谁先」无权威直接论述（本报告结论为间接证据推导，已在 notes D 标注）；c) 国内厂商公开资料以发布会转述为主【转述/摘要】，源码级/文档级细节不足。

## 6. 来源精选（均含在 notes 四份纪要内，此处列最关键 10 项）

1. Avalara Aviator 产品页（agent hub / governed autonomy / 确定性引擎分工）— https://www.avalara.com/products/aviator 【一手】
2. ServiceNow《AI Agents: Build, Operations & Governance Guide》（Otto panel / AI Workbench / Supervised-Autonomous / Flow Action）— https://www.servicenow.com/community/servicenow-otto-articles/servicenow-ai-agents-build-operations-amp-governance-guide/ta-p/3569932 【一手】
3. AWS《Introducing Pizza Bot》（agent 收件箱；"The interface assumes you are not watching"）— https://aws.amazon.com/blogs/opensource/introducing-pizza-bot-an-open-source-inbox-for-ai-agents-that-work-in-the-background/ 【一手】
4. Emerge Haus《The New Dominant UI Design for AI Agents》（split-screen agent UI 命名）— https://www.emerge.haus/blog/the-new-dominant-ui-design-for-ai-agents 【一手】
5. SAP《How SAP Uniquely Delivers AI Agents with Joule》（统一 UI + agent 编排器）— https://news.sap.com/2025/02/joule-sap-uniquely-delivers-ai-agents 【一手】
6. Microsoft Learn：Copilot Studio Apps（preview）— https://learn.microsoft.com/en-us/microsoft-copilot-studio/apps-experience/apps-overview 【一手】
7. AWS Prescriptive Guidance《Agentic AI architecture in the enterprise》— https://docs.aws.amazon.com/prescriptive-guidance/latest/govern-architect-agentic-ai/enterprise-architecture.html 【一手】
8. Microsoft Learn《Expose REST API as MCP server》（存量 API→MCP + agent-id 审计）— https://learn.microsoft.com/en-us/azure/api-management/export-rest-mcp-server 【一手】
9. arXiv:2603.21334《Software as Content: Dynamic Applications as the Human-Agent Interaction Layer》（聊天窗三固有缺陷）— https://arxiv.org/abs/2603.21334 【一手】
10. Thomson Reuters agentic AI 发布稿（"Ready to Review" / final review and sign-off）— https://www.thomsonreuters.com/en/press-releases/2025/november/thomson-reuters-launches-agentic-ai-solutions-to-transform-tax-audit-and-accounting-workflows 【一手】

其余（Salesforce Agentforce 360/Slack 前门、Workday Sana、Oracle AI Agent Studio、KPMG×Anthropic、Deloitte Zora、税友数智工场、航信金税智能体、Temporal/LangGraph/Camunda、UiPath Action Center、SCUBA/OSWorld 2.0、MCP 授权规范、A2A 协议等）见各 notes 的来源清单。
