# 税务多系统接入 AI Agent 的作业形态调研（统一工作台设想评估）

> **背景**：公司税务部门 SaaS 时代建了 6+ 系统（计税/所得税/申报/披露/关联交易/税务资产），一条业务流（如国内增值税申报）要跨系统来回切换。进入 agent 时代，拟新建统一「agent 工作台」（主屏=跨系统工作流进度+数据详情，副屏=agent 对话）统筹作业。本轮调研评估该设想是否合理、业界有无更成熟方案。
> **性质**：网络调研（非源码级）。四路并行（subagent）：① 平台大厂跨应用 agent 交付形态；② 税务垂直厂商 AI agent 产品；③ Agent UI 形态与 HCI；④ 跨系统集成/编排架构。关键对标证据（Avalara Aviator、AWS Pizza Bot）由作者二次复核。
> **结论一句话**：设想方向成立（业界全部收敛到「跨系统统一 agent 层」，无人押注子系统副屏），但需三处修正——主屏进度必须是编排引擎事件流的投影、副屏对话之外要有异步审批收件箱、HITL 审批做一等公民；成败关键在前端之下的接入层（MCP 网关）与编排层（durable workflow），而非工作台前端本身。

## 方法与证据等级

- 检索窗口：优先 2025-2026 资料；调研执行日 2026-10-11。
- 四份过程纪要在 [notes/](./notes/)，结论均可溯源到具体 URL。
- 证据等级（区别于源码轮的【核心】/【文档】体系，本轮为网络调研定制）：
  - 【一手】官方页面已抓取全文核实；
  - 【转述】官方页反爬/直连失败，经多个二手来源一致转述（官方新闻稿 403 是常态）；
  - 【摘要】仅搜索结果摘要级（最弱，报告中均单独标注）；
  - 【未找到】如实标注，不臆测。
- 与历史轮的边界：`research/agent-oss/`（开源产品架构）与 `research/agent-persistence/`（持久化）为源码级，本轮不重复；其结论（图编排、审批门、审计等模式）与本轮业界方案相互印证，报告直接引用其存在而不重考。

## 进度 checklist

- [x] 问题定义与四路调研框架
- [x] 路一：平台大厂（Microsoft/Salesforce/ServiceNow/SAP/Oracle/Workday）→ notes/platform-vendors.md
- [x] 路二：税务垂直（TR/Avalara/Vertex/Ryan/KPMG/EY/Deloitte/PwC + 税友/百望/大象慧云/用友/金蝶/航信）→ notes/tax-vendors.md
- [x] 路三：Agent UI 形态与 HCI（sidecar/split-screen/canvas/agent inbox/HITL 六模式）→ notes/agent-ui-patterns.md
- [x] 路四：集成架构（MCP/A2A/browser agent/durable workflow/参考架构/权限审计）→ notes/integration-architecture.md
- [x] 关键证据作者复核（Avalara Aviator 产品页、AWS Pizza Bot 博客）
- [x] 综合报告 report.md

## 目录

```
agent-workbench/
├── README.md                      # 本文件：入口
├── report.md                      # 综合报告（最终交付，先读这篇）
└── notes/                         # 四路过程纪要（含完整来源 URL 清单）
    ├── platform-vendors.md        # 路一：平台大厂
    ├── tax-vendors.md             # 路二：税务垂直
    ├── agent-ui-patterns.md       # 路三：Agent UI 形态
    └── integration-architecture.md# 路四：集成架构
```

## 主要「未找到」清单（研究边界如实记录）

a16z《The Death of the SaaS URL》精确标题原文；Packy McCormick service-as-software 专文；Anthropic《How people use Claude Code》精确标题博客；税务厂商显式「主屏+副屏」双栏工作台产品页；Deloitte agentic 参考架构白皮书；A2A v1.0 官方发布公告原文；「前端先行 vs 编排先行」的权威直接论述；大象慧云/用友/金蝶的税务垂直 agent 工作台。均已给出最接近的可核实替代来源（见各 notes 尾部）。
