# 调研纪要 B：税务垂直领域的 AI Agent 产品与架构

> 来源：subagent 网络调研（2026-10-11），覆盖国际厂商（TR/Avalara/Vertex/Ryan/四大）与国内厂商（税友/百望/大象慧云/用友/金蝶/航天信息）。
> 证据等级：【一手】官方页面已抓取核实；【转述】二手媒体一致转述；【摘要】搜索摘要级；【未找到】如实标注。

## 一、国际厂商

### 1. Thomson Reuters（ONESOURCE + CoCounsel）

三步演进：
- **2025.3**：CoCounsel Tax 上线，税务研究/文档审查/规划助手，Checkpoint 内容库与事务所文档 "combine in one workspace"，对话式交互，答案可溯源引用（产品页 https://tax.thomsonreuters.com/en/products/cocounsel-tax 【一手】）。
- **2025.11.5**（Synergy 大会）：发布 **ONESOURCE+ —— "AI-powered Intelligent Compliance Network"**（Enterprise Times 报道 https://www.enterprisetimes.co.uk/thomson-reuters-announces-an-ai-powered-intelligent-compliance-network/ 【一手】）。同日发布 agentic AI 三件套：**Ready to Review**（agent 处理源文件+上年申报表→提取→分类→生成「待复核」的 1040 申报表）、CoCounsel Document Analysis、Audit Intelligence Test（官方发布稿 https://www.thomsonreuters.com/en/press-releases/2025/november/thomson-reuters-launches-agentic-ai-solutions-to-transform-tax-audit-and-accounting-workflows 【一手】，CoCounsel 已被 1,300+ 事务所使用）。
- **2026.1**：**ONESOURCE Sales and Use Tax AI**（powered by CoCounsel）——agentic AI 端到端跑间接税合规：数据搬运→智能校验→申报表生成→错误拦截，产出 "signature-ready returns"（产品页 https://tax.thomsonreuters.com/en/products/onesource-sales-and-use-tax-ai 【一手】）。

**人机分工原话**："touchless compliance... without human intervention **until final review and sign-off**"；"manual by exception"；"comprehensive audit trails provide transparency into automated actions"。（Adobe 流程改进 96%，大型企业周期 30 天→11 天。）

**多模块统一的解法**：ONESOURCE+ 是组合层品牌统一 + 数据/内容/工作流网络化，**不是新做独立 AI 工作台 App**。高管访谈：CoCounsel 的 NL 问答 UX 已 "brought into our tools"（嵌入各产品内），计划支持跨整个组合自然语言提问，甚至嵌入第三方系统（Oracle ERP、Icertis）。底座：200+ ERP 合作伙伴、RESTful API、12 个 SAP 认证连接器。

**启示**：TR 选择第三条路——底层用「合规网络」打通数据与工作流，AI 入口嵌入每个既有产品（相当于子系统内副屏），顶层规划跨组合统一入口。没有推倒重建统一工作台；统一入口是渐进长出来的。

### 2. Avalara（对本案最直接对标）

- **2025.9–10**："Agentic Tax and Compliance" 平台，为计税/申报/免税证书/登记/电子发票提供 purpose-built agents（CFO Tech Australia 2025-10-01【转述】）。
- **2026.9.23**（CRUSH 大会）：发布 **Avalara Aviator —— agent hub**（官方新闻 https://newsroom.avalara.com/2026-09-23-Avalara-Ushers-in-New-Era-of-Agentic-Tax-and-Compliance-with-Avalara-Aviator,2 【一手】）；**2026.10.8 宣布 GA**（https://newsroom.avalara.com/2026-10-08-Avalara-Helps-Global-Businesses-Move-Faster-as-Tax-and-Compliance-Complexity-Accelerates 【一手】）。

**架构与 agent 编队**（产品页 https://www.avalara.com/products/aviator 【一手，本报告作者已二次复核】）：
- **Avi（编排 agent）**："Assigns work to lead agents, proactively flags risks, and keeps humans in control of critical approvals"；
- 专家 agent：**Transactions**（计税+逐行解释+实时核验）、**Returns**（跨数千 jurisdiction 自动准备、对账、申报）、**Research**（基于法定引用的对话式研究）、**Certificates**（免税证书/税号/登记状态实时核验）；
- **"governed autonomy"**："Human-in-the-loop approval gates for all critical tasks"、"Built-in human approval gates ensuring complete filing control"；高风险操作（提交申报、规则覆盖、豁免审批）"require explicit human sign-off"；
- **确定性引擎 vs 生成式分工原话**："Aviator relies on Avalara's proprietary deterministic tax engine. Generative AI is strictly used for orchestration, unstructured document extraction, and statutory synthesis, with 100% of outputs mapped to verified tax laws and confidence-scored before data is presented."（高风险计算不让 LLM 碰）
- **UI 形态**："Aviator launches directly inside the Avalara Portal experience you already use"；"In-app notifications and actions **without switching systems**"；可 "Embed Agentic Tax and Compliance™ directly into your ERP, billing, ecommerce systems, email platforms, and copilots"。规模：540 亿+交易/年、30,000+ jurisdiction、190+ 国家。

**启示**：统一 Agent Hub（编排者+专家群）嵌在统一门户里，业务流程为主屏、对话/通知为辅助层，高责任动作过审批门。

### 3. Vertex

- 无独立 agent hub 产品（截至调研）。2026.4.7 发布 "Vertex Advances AI-Powered Capabilities…"（GlobeNewswire，正文 403【转述】）；2025.10 官方博客："Vertex Cloud brings together global tax content and AI-driven capabilities into **one cohesive platform**"【转述】。
- 2024.6 以约 610 万美元收购 **Ryan 的税务专用 AI（taxability mapping）**（Vertex IR 发布稿 https://ir.vertexinc.com/news-releases/news-release-details/vertex-acquires-artificial-intelligence-tax-capabilities-ryan 【一手】、10-K【一手】）；2025.4 战略投资 Kintsugi。
- **启示**：AI 内嵌单一平台各环节，属「平台内嵌」，暂无统一 agent 入口叙事。

### 4. Ryan

- 技术平台品牌 taxcom；官网称 "AI-powered tax workflows delivering accurate calculations, streamlined filings, and **audit-ready documentation**"【摘要】。
- 核心税务 AI（tax mapping）2024 已卖给 Vertex。2025–2026 **未找到** Ryan 自有独立 tax agent 产品发布【未找到】。

### 5. KPMG

- **Digital Gateway for Tax** 本身就是集中式平台：税务洞察+自研工具+客户数据同一环境（Azure 底座），2024.3 起加 gen AI（Accounting Today 2024-03-22【转述】）；Tax AI Accelerator 给客户沙箱试 AI 用例【转述】。
- **2026.5.19：KPMG × Anthropic 全球联盟，"Digital Gateway Powered by Claude"**——把 **Claude Cowork 和 Managed Agents 直接嵌入 Digital Gateway**，专业人员与客户在平台内实时构建 agentic workflow；税务副主席 Rema Serafi：原来帮客户建 agent「要数周、要在多个工具间切换」，现在「几分钟」（官方发布稿 https://kpmg.com/xx/en/media/press-releases/2026/05/kpmg-and-anthropic-sign-global-alliance-and-launch-digital-gateway-powered-by-claude.html 【一手】）。
- **Claude Cowork 的 UI 形态**：Anthropic 的 "agentic work surface"——人把任务委派给 agent，agent 在共享工作面上处理文件/表格/文档，人随时 check in、拿成品 review（https://claude.com/product/cowork 【一手】）。
- **启示**：**先统一平台、再嵌 agent** 的路径样本。

### 6. EY

- **2025.3.18：EY.ai Agentic Platform（与 NVIDIA 合作）**——首批用于税务：AI agents + 8 万税务专业人员「混合编队」，一年内目标 300 万+税务合规产出、重塑 3,000 万+税务流程；agent 承担数据收集、文档处理等最耗时环节（EY 新闻【转述】）。
- 2025.5：EY.ai for tax（与 IBM watsonx）【转述】。2025.11 TFO 调查：EY 高层判断「未来五年大多数税务申报将大概率由 AI agent 支持」（https://www.ey.com/en_qa/insights/tax/tfo-survey 【一手】）。
- 中国区：安永 METIS.ai 平台 + 财税数字化服务（KPI Copilot 等）【摘要】。
- **形态**：服务公司模式——agent 编入交付流程内部，客户感受到的是服务，不是可购买的工作台产品。

### 7. Deloitte（Zora AI）

- 2025.3 NVIDIA GTC 发布 **Zora AI**，finance/tax 域 agentic 平台（发布稿【一手】：https://www.deloitte.com/us/en/about/press-room/deloitte-unveils-zora-ai-agentic-ai-for-tomorrows-workforce.html）。
- 税务 agent 清单：**Tax Insights（CFO Insights）、Sales and Use Tax Advisor、Autonomous Invoice Management、VAT Advisor**（产品页 https://www.deloitte.com/us/en/services/consulting/services/zora-generative-ai-agent.html 【一手】）。
- 特点：高频交易性工作 "end to end, without manual intervention"；**Trustworthy AI 框架 + human feedback loop + "human-readable reasoning at every step"**；**明确 FAQ 承认 SOX 相关内控不内置**，需并行 Risk & Controls 工作流——罕见的合规坦诚；与 SAP Joule Agents、Oracle Fusion 集成，"not a rip and replace"；"data never leaves your infrastructure"。

### 8. PwC

- 2025.3 发布 **agent OS**（编排框架，专利申请中），宣称已部署 2.5 万个 agent，治理与合规为核心（PwC 直布罗陀透明度报告 2025【一手】）；税务 agent 主要经客户 engagements 交付，**未找到独立税务 agent 产品页**【未找到】。
- 观点文章《AI agents: transforming the tax experience》（2025.3.27）：agent 价值覆盖全税种职能，经 ERP+税务合规工具集成落地【转述】。

## 二、国内厂商

### 9. 税友股份（603171）——国内证据最充分

- 2024：自研「犀友」财税垂直大模型（接通义千问/阿里云）【转述】。
- 2025.3.18 杭州「财税 AIBM 战略」发布会：联合沙利文发白皮书，发布 AI Agent 产品，与华为共建底座（证券时报 https://stcn.com/article/detail/3295750.html 【一手】等）。
- 2025.8.28「财税数智芯 Agent 新纪元」：发布财税行业首个 Agentic 平台「**数智工场**」。产品矩阵 = **「驾驶舱 + 数智会计 + 数智合规顾问」**，宣称幻觉率降至 10% 以下；数智会计把记账人效从 80 套账/月提到 **800 套账/月（10 倍）**、降本约六成；服务 4,000+ 财税机构、46.75 万家企业（观察者网 https://www.guancha.cn/GongSi/2025_08_30_788295.shtml 【一手】、央广网【一手】）。
- 面向集团客户的 **GTS 集团税务共享平台**（办税/管税/筹税）逐步融入 AI；2026.6 亿企赢「Agentic 2.0」从数字员工升级为多智能体「数字组织」（时代周报——单一来源【摘要】，谨慎引用）。
- **启示**：国内最接近「统一工作台」的形态——「驾驶舱（监督主屏）+ 数字员工后台作业 + 合规顾问预警」。

### 10. 百望云

- 「百宝税务智能体助手」：“专属 AI 税务分析师”，结合交易伙伴合规洞察报告做交易信用「CT 扫描」（https://web.baiwang.com/news-details/19.html 【一手】）。
- 形态：**票税数据底座上的单点智能体**，非全流程工作台。启示：发票/交易数据底座是 agent 取数前提。

### 11. 大象慧云

- 背景：航天信息+京东 2016 年发起，发票全生命周期管理+税务信息化。**2025–2026 税务大模型/智能体产品发布：未找到确凿公开资料**【未找到】。

### 12. 用友

- 平台层：YonGPT（2023）→ 2026.1 BIP「本体智能体」（数字孪生+可追溯可控的自主执行）→ 2026.4 **YonClaw 企业超级智能体**【转述】；2026 半年报提及「企业AI工作台、超级智能体、领域智能体」。
- **税务垂直专属 agent 工作台：未找到**——税务能力在「智能财务/业财税一体化」伞下【未找到】。

### 13. 金蝶

- 2025.5.21 苍穹 AI 峰会：苍穹 Agent 平台 2.0 + 五大 AI 智能体【转述】；星瀚 V7.0 内嵌苍穹 AI 平台、100+ AI 场景；税务方向 = 「业财税一体化 AI 财务云 + AI 合规预警引擎（事后补救→事前预防）」（金蝶官网 2025-11-21【转述】）。
- **独立税务 agent 工作台：未找到**【未找到】。

### 14. 航天信息（600271）

- 2025.11：AI 财税四大新品（爱信诺智税/云税/微税/易账）【转述】。
- **2026.8.5 发布「金税智能体」**：基于自研爱信诺·信诺大模型，**贯通开票、记账、申报、报销、风控全场景**；三层架构 = 通用模型 + 财税专业模型 + 轻量化场景模型；票据/凭证/商品编码识别准确率 99.9%；由 Aisino 智能体平台承载多个财税 agent（新浪财经 2026-08-05【转述】）。
- **启示**：收敛为「垂直大模型三层架构 + 覆盖全链条的场景 agent 群 + 一个智能体平台承载」，与 Avalara 的「编排者+专家群」同构。

## 三、横向小结：税务垂直收敛出的形态

### A. 「多模块平台 + agent」的三种解法（无一押注「每模块挂副屏」）

| 模式 | 代表 | 做法 |
|---|---|---|
| 平台网络化 + AI 嵌入各产品 + 顶层规划统一 NL 入口 | Thomson Reuters | ONESOURCE+ 打通数据/内容/工作流；CoCounsel UX 嵌入每个产品；路线图跨组合自然语言提问 |
| 统一 Agent Hub 嵌入门户 | **Avalara Aviator**（最纯粹）、航天信息金税智能体、税友数智工场 | 编排 agent + 按领域专家 agent；hub 长在既有门户/平台里，"without switching systems" |
| 先有统一交付平台，再把 agent 嵌进去 | KPMG Digital Gateway × Claude Cowork、EY（服务内嵌） | 统一平台承载人+agent 协同工作面 |

### B. 人机分工的收敛边界

- **agent 主导**：取数/数据搬运与映射、计税与校验比对、申报表生成到 "signature-ready"、证书/登记监控、政策研究与问答（带引用）；
- **人保留**：**final review + sign-off 是全行业一致的底线**（TR 原话；Avalara approval gates；Zora human feedback loop；税友人机协同）；
- **HITL UI 形态**：审批门+复核队列（TR 产品名 "Ready to Review" 本身就是 UI 隐喻——agent 产物一律落进「待复核」态）、"manual by exception"、审计轨迹、引用溯源、人类可读推理链、置信度分。

### C. 「主屏=流程/数据、副屏=对话」的先例

**未找到任何税务产品公开页面明确以「双屏/双栏」措辞并给出截图**【未找到】。最接近的三个形态证据：
1. **Avalara Aviator**：统一门户为主屏，agent 以对话+in-app 通知/动作嵌入；
2. **KPMG Digital Gateway + Claude Cowork**：任务委派+共享产物工作面；
3. **税友数智工场「驾驶舱」**：监督驾驶舱+后台数字员工。

结论：该形态与行业方向**一致且略超前**——可视为把 Avalara 的「hub 嵌门户」与 Cowork 的「工作面+对话」合并成显式双屏工作台；这是设计决策而非照抄现成产品。

### D. 税务场景的特殊要求（厂商反复强调）

1. **确定性优先**：Avalara 明确「计税用确定性引擎、gen AI 只做编排/提取/综合」；航信三层模型同理；
2. **审计留痕与可解释**：TR audit trails；Avalara audit-defensible；Zora "human-readable reasoning at every step" + SOX 内控需另行设计；
3. **审批门治理**（governed autonomy / approval gates）；
4. **多税种多 jurisdiction**：按域分设专家 agent（而非全能 agent）；
5. **ERP/发票集成是前提**：TR 200+ ERP 连接器；国内厂商全部以发票底座（航信/百望）或 ERP（用友/金蝶）为取数地基；
6. **数据主权**：Zora "data never leaves your infrastructure"、KPMG 私有沙箱。

## 四、未找到项（如实标注）

Ryan 自有 tax agent 产品；大象慧云 2025-2026 税务大模型/智能体发布；用友/金蝶税务垂直专属 agent 工作台；任何税务厂商「主屏+副屏」双栏布局的明确截图描述。
