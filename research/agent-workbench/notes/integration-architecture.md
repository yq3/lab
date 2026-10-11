# 调研纪要 D：跨多系统的 Agent 集成与编排架构

> 来源：subagent 网络调研（2026-10-11）。主题：前端形态之下，agent 与 6 个既有税务系统如何接起来（MCP / A2A / browser agent / durable workflow / 参考架构 / 权限审计）。
> 证据等级：【一手】官方页面已抓取核实；【转述】二手一致转述；【摘要】搜索摘要级。

## 一、逐主题纪要

### 主题 1：MCP 企业落地——「存量 API → MCP」成主流打法，网关化是治理答案

- **Microsoft Azure API Management 已把「REST API 一键暴露为 MCP server」产品化**（GA，Build 2025 推出，文档更新至 2026-04-28）：在 APIM AI 网关里把已纳管 REST API 的若干操作选为 MCP tools，对外提供 MCP 端点；可在 MCP server 上挂 APIM 策略做限流、认证，官方示例用 policy 记录调用方 `agent-id` 做 trace（审计）；还支持代理企业内已存在的外部 MCP server 统一收口。来源：https://learn.microsoft.com/en-us/azure/api-management/export-rest-mcp-server 【一手】；Azure API Center 建企业私有 MCP 注册表（Arinco，2025-08）【转述】。
- **Cloudflare**：2025-04-07 业界首个 remote MCP server；Agents SDK 内置 `McpAgent` 与 OAuth provider 库；企业参考架构强调「集中网关管理 + anycast 网络」【转述】。
- **Higress / 阿里云**（国内路线）：2025-04-25 发布 MCP Marketplace，核心卖点「存量 API 跨入 MCP 时代」；MCP 服务管理模块提供 **OpenAPI→MCP 自动转换、DB→MCP**，可建私有 MCP 市场（官方市场 mcp.higress.ai）【转述】。
- **开源网关层收敛**：[agentgateway](https://github.com/agentgateway/agentgateway)（Solo.io/Lyft 系）——同时处理 MCP 与 A2A 流量的代理，「微服务时代的 API gateway 之于 agent 时代的等价物」；[mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry)（Apache 2.0，可跑在 EKS/Docker 的企业级 MCP server+agent 控制平面）；Solo.io「Agentic Mesh」概念【转述】。
- **架构讨论**：Xenoss——MCP 网关「本质是为 agent 通信模式重新设计的 API 网关」（认证、访问策略、调用日志、路由）【转述】。

**「MCP 聚合层 = 事实上的 agent 后端」**：趋势上是。商业云厂商（APIM）、国内开源（Higress）、中立开源（agentgateway）三条路线殊途同归，agent 的工具调用、身份、限流、审计收敛到这一层，与 2015 年代 API gateway 之于微服务的角色同构。

### 主题 2：A2A 协议——agent 间协作开放标准，与 MCP 互补

- Google 2025-04-09 官宣，50+ 合作伙伴（Atlassian、Box、Salesforce、SAP、ServiceNow 等）：https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/ 【一手】。JSON-RPC 2.0 / HTTP / SSE 标准 Web 技术。
- **治理归属**：捐给 Linux Foundation；2025-12-09 成立 **Agentic AI Foundation (AAIF)**，A2A 与 MCP 首次置于同一中立治理伞下【转述】；IBM ACP 与 A2A 汇流【转述】。
- **协议核心**（https://a2a-protocol.org/latest/ 【一手】）：**Agent Card**（能力发现）+ **Task 生命周期**（`submitted → working → input-required → completed`）——`input-required` 原生支持「子 agent 中途要求人工/上游输入」，对审批流有用。v1.0 语义已在规范/迁移指南中，**官方 v1.0 发布公告原文未找到**（存疑标注）。
- **与本题关系**：MCP 解决 agent↔工具/系统，A2A 解决 agent↔agent。「每个税务系统一个专职 agent」可独立部署、被发现（Agent Card）、被编排（Task 生命周期），而非把 6 个系统的逻辑塞进单体 agent。Azure 已采纳 A2A（2025-05 起）。

### 主题 3：浏览器操作型 agent——消费级进步快，企业级（强审计场景）仍不成熟

- **产品**：OpenAI Operator（2025-01-23）→ ChatGPT agent；Anthropic computer use（2024-10，安全研究者即警告「未经测试的 AI 安全领域」）；Claude in Chrome（2025-08-26 research preview，已开放含 Enterprise 的付费计划）——但 2026-07 报出恶意扩展可借其执行特权 AI 动作的漏洞【转述】；Manus（每任务一个云 VM/E2B 沙箱 + multi-agent 规划/执行循环 + Browser Use 库；企业合规被独立评估为「需要额外控制」的未成熟项）；国内：字节扣子空间（2025-04 内测，自主操作浏览器+MCP 生态）、豆包电脑版、Coze 开源（2025-07-28）【转述】。
- **成熟度硬数据**：
  - OSWorld：2026-03 最好 computer-use agent 约 82% 成功率【转述】；**OSWorld 2.0**（arXiv 2026-06-28）把任务升级为 250+ 步长程工作流——长程能力才是企业场景真实门槛【转述】；
  - **Salesforce SCUBA**（ICLR 2026）：OSWorld 类基准表现良好的开源模型，放到真实企业安全场景任务上**成功率不足 5%**——benchmark 成绩与企业可用性存在数量级差距【转述】；
  - IBM Generalist Agent（AAAI 2026）：企业生产部署 computer-use agent 需人工监督配套【转述】。
- **RPA 厂商的 agentic 转型给出行业答案：API 优先、UI 自动化兜底**。UiPath 2025-10 新 AI automation suite（预构建 agentic 方案+编排）；Automation Anywhere agentic orchestration=「协调 agent、业务工具、遗留数据库与人工，跨企业系统」；两家都在从屏幕抓取转向「API 能力 + AI 特性 + 云原生」【转述】。
- **审计共识**：可辩护的 agent 审计日志必须**不可变、绑定身份、可重放**（immutable / identity-bound / replayable，Keito 2026-04-06）【转述】。browser agent 的操作粒度是「截图+点击坐标」，满足该标准比 API 调用日志难得多。

### 主题 4：Durable workflow 引擎——「工作流为主干、agent 为节点」是收敛模式

- **Temporal**：官方定位 durable agentic workflows——状态可靠、支持 HITL、跨服务集成；核心机制 **Event History**（每步记录为事件），Web UI 提供 Timeline 视图【转述】。
- **LangGraph（Platform）**：graph 编排 + checkpoint 持久化 + `interrupt()`/恢复实现 HITL + time travel 重放 + Dev UI/Studio 线程检查；LangChain 官方对比：Temporal 是优秀运行时持久层，但 agent 开发还需更多；有两者叠用实践（LangGraph 推理图 + Temporal 持久化外壳）【转述】。
- **Camunda 8**（官网已深读）：三段光谱——全确定性（规则直通）/ 混合（**「规则用 BPMN，判断用 agent」**）/ 全动态；口号 "Agents automate tasks, orchestration automates the process"；**human task 与 AI agent 同为流程模型一等节点**；对 MCP、A2A 框架中立。来源：https://camunda.com/agentic-orchestration/ 【一手】。
- **Inngest**：durable execution 已成 agent 可靠性的标准编程模型【转述】。**Dify / Coze**：低代码可视化 agent workflow，适合快速 POC，治理深度弱于上述引擎【转述】。
- **关键先例**：**UiPath Action Center**（2020-11 GA，早于 LLM agent）——unattended 机器人挂起长流程、生成人工 Action（审批/校验/异常处理），人在门户处理后流程自动恢复。这就是「主屏=流程进度+待办审批」的前 LLM 时代原型；UiPath Maestro（2025）升级为 agent+robot+human 的长流程编排层【转述】。

### 主题 5：企业 agent 平台参考架构——接入层标准组件趋于一致

- **AWS Prescriptive Guidance「Agentic AI architecture in the enterprise」**（已深读）：三层——应用层（含**非 GenAI 业务系统**，明确定位「可暴露其功能为 agent 可调用的 tools」）/ agents 层（发现、A2A 通信与编排、记忆）/ 核心服务：**model access**（模型网关+护栏+成本）、**tools**（工具发现+安全执行+按角色/上下文授权）、**knowledge bases**（向量/图存储+RBAC）；observability、security、discoverability 跨层贯穿。来源：https://docs.aws.amazon.com/prescriptive-guidance/latest/govern-architect-agentic-ai/enterprise-architecture.html 【一手】。
- **Microsoft**：Copilot Studio（低代码）+ Azure AI Foundry Agent Service（专业代码）+ 统一 Agent Framework，MCP connector 原生接入，租户级治理【转述】。
- **Google Cloud**：Agentspace（2025-08 GA）→ 2025 年底整合为 Gemini Enterprise Agent Platform【转述】。
- **Salesforce**：架构师站点「The Agentic Enterprise」定义独立 **Agentic Layer**；Agentforce 接第三方系统靠 **MCP + MuleSoft**，并以此攻击 Sierra「自建 API 连接器维护成本高」——头部厂商已把「MCP/iPaaS 连接层」当竞争差异点【一手（架构师站）/转述（对比页）】。
- **咨询公司**：Accenture AI Refinery（2025-01，与 NVIDIA）【转述】；**Deloitte 专门 agentic 参考架构白皮书：未找到**【未找到】。

### 主题 6：权限与审计——OAuth 2.1 + 代理身份（OBO）+ 不可变操作日志

- **MCP 官方授权规范**：MCP client 即 OAuth 2.1 client，代表资源所有者发起请求，强制 PKCE（modelcontextprotocol.io/specification）【一手】。
- **On-behalf-of 委托**：Microsoft 官方教程演示生产级 MCP server 用 Azure AD OAuth 2.1 + **OBO flow** 调 Graph——「agent 拿着用户委托令牌行动，身份链路可审计」（DevBlogs 2026-02-26）【转述】；Stytch agent-to-agent OAuth + MCP 实现指南【转述】。
- **非人类身份（NHI）治理**：Auth0 指出 agent 常以 OAuth client 身份代表人类行动，传统静态身份框架不适配动态 agent 生命周期；CSA Labs 称当前处于「NHI 治理真空」（2026-05）【转述】。
- **落地抓手**：APIM MCP policy 里直接 trace `agent-id`；审计标准「immutable / identity-bound / replayable」。

## 二、横向小结：跨系统集成架构的收敛模式

2025-2026 业界对「agent 接 N 个既有系统」收敛出同一张分层图（自下而上）：

1. **系统接入层**：遗留系统/SaaS 能力经 **API 网关 → MCP 网关** 暴露为 tools（APIM「REST API→MCP server」、Higress「OpenAPI→MCP」、agentgateway）。UI 自动化（RPA/browser agent）退居「无 API 系统的兜底连接器」。
2. **连接治理层**：MCP registry（私有注册表/marketplace）+ agent registry（A2A Agent Card）+ OAuth 2.1/OBO 身份委托 + 网关策略（限流、agent-id 审计）。
3. **编排层（durable workflow 引擎）**：确定性业务主干（申报流程步骤、法定时点、校验规则）+ agent 作为非确定性节点 + human task 一等节点。Temporal / LangGraph / Camunda / UiPath Maestro 是成熟度不同的载体。
4. **前端消费层**：统一工作台 = 编排引擎状态的投影（进度主屏 = event history/checkpoint 的可视化；副屏对话 = agent thread；审批页 = HITL interrupt/Action Center 的恢复入口）。

两个协议各就各位：**MCP 管 agent↔系统（工具），A2A 管 agent↔agent（协作）**，同归 Linux Foundation AAIF 中立治理——协议风险快速下降。

## 三、重点问题回答

### A. 「API/MCP 编排」vs「browser agent 直接操作 UI」

| 维度 | API/MCP 路线 | browser agent 路线 |
|---|---|---|
| 企业成熟度 | 高：云厂商产品化 GA、OAuth 2.1 标准化、网关治理组件齐全 | 低-中：消费级进步快（OSWorld 最优 ~82%），企业真实场景 <5%（SCUBA）、250+ 步长程仍是硬门槛 |
| 审计合规 | 调用日志、身份委托（OBO）、策略管控成熟 | 操作粒度截图+点击，「不可变/身份绑定/可重放」标准难满足；已有安全事件 |
| 业界策略 | 主路线；Salesforce/微软把 MCP 连接层当竞争力 | 兜底路线；UiPath/AA 明确 API-first、UI 自动化只留给无 API 遗留系统 |
| 适用场景 | 强流程、强审计（如税务申报）、写操作 | 只读探查、无 API 系统过渡、人在场的辅助操作 |

**结论**：税务申报这类强审计、法定流程场景，证据一边倒支持 **API/MCP 为主干**；browser agent 最多作个别无 API 系统的过渡连接器，且应限定人在监督下使用。

### B. 统一工作台与编排引擎的关系：进度主屏本质是 workflow 引擎的可视化投影

是，且先例充分：Temporal Web UI Timeline、LangGraph Studio/Dev UI、**UiPath Action Center（2020 GA，早于 LLM agent）**。关键架构含义：**主屏的「进度」数据必须来自 durable 引擎的事件流——没有编排引擎，主屏无真实数据可显示**；副屏对话与主屏进度的联动点在 HITL interrupt（agent 需审批时，进度条停住、对话与审批卡片同时出现）。

### C. agent 接入层的标准组件（多家收敛）

1. MCP/API 网关（存量 API→MCP tools、限流、策略）；
2. 连接器/工具目录（iPaaS / API Center；工具按角色/上下文授权）；
3. 注册表（MCP server registry + agent registry/A2A Agent Card）；
4. 身份与授权（OAuth 2.1 + PKCE + OBO 委托链：用户→agent→工具；NHI 治理）；
5. 模型接入网关（LLM gateway：统一访问、护栏、成本核算）；
6. 审计/观测（immutable/identity-bound/replayable 操作日志）；
7. HITL 审批中心（interrupt→人工 action→恢复，Action Center 模式）；
8. 知识库组件（带 RBAC 的 RAG，税务场景的法规/口径知识）。

### D. 对「先建统一工作台前端」的架构建议

**未找到权威来源直接论述「前端 vs 后端编排谁先」**（如实标注）。间接证据高度一致：所有参考架构把端用户应用放最上层，编排+工具+治理是核心层；UiPath/Camunda 产品史是先有编排引擎、后有人类任务门户；前端核心价值（进度可视化、审批入口）技术上依赖引擎的 event history 与 interrupt 机制。

**推导的演进路径**：① 先做接入层（6 系统经网关 MCP 化，OAuth/OBO 身份与审计随网关落地——最难、复用价值最高的资产）；② 选 durable 编排引擎做申报流程主干（agent 为节点、human task 为节点），进度数据自然产生；③ 统一工作台前端按「引擎事件流」设计而非自造进度模型。前端可先行做 UX 设计原型，但**生产化顺序以后端编排选型为前置依赖**，否则进度主屏只能靠前端伪造状态，后续推倒重来。

## 四、未找到项

Deloitte 专门的 agentic 参考架构白皮书；A2A v1.0 官方发布公告原文（v1.0 语义已在规范/迁移指南中）；「前端先行 vs 编排先行」的权威直接论述（仅有间接架构证据）。
