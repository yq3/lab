# Agent 开源产品应用架构解剖（18 仓库 → 财务 Agent 参考模式）

> **性质**：应用架构解剖（不是框架能力对比）。为「Java 技术栈 + 财务领域企业级 agent」自研系统提炼参考架构模式，硬约束：① agent 服务独立部署、与业务服务 API 通信；② 图编排工作流；③ 硬性审批/审计/合规。
> **方法**：三阶段——Phase 1 逐仓库解剖档案（`profiles/`，18 份）→ Phase 2 分组横向 + 跨组专题（`dimensions/`，5 份）→ Phase 3 综合报告（`report.md`，pattern catalog / 反模式 / 架构建议）。
> **上游研究**：`research/agent-framework/`（17 框架 × 15 维源码级对比）。本项目构建在这些框架之上的，直接引用其 `profiles/` 结论（交叉引用纪律），精力放在「产品怎么用框架」。
> **提示词留档**：[PROMPT.md](./PROMPT.md)。

## 证据纪律

- 所有结论可溯源：`~/develop/opensource/<仓库>/路径#符号`；四个证据等级——【核心】核心代码实现 /【示例】examples 或 demo /【文档】文档宣称 /【还原源码】仅 claude-code-sourcemap（sourcemap 还原、可能失真）。查不到标 ❌ 或 ⚠️待确认，不臆测。
- 区分「产品宣称」（README marketing）与「代码实现」，前者不作能力证据。
- 研究期间冻结已分析仓库（不 `git pull`），基线以下表 HEAD 为准。

## 分析对象与基线（git HEAD，2026-09-13 记录）

| 组 | 仓库目录 | canonical | 基线 | 状态备注 |
|---|---|---|---|---|
| A 金融/交易 | ai-hedge-fund | virattt/ai-hedge-fund | fc1bf25 (09-03) | |
| A | FinRobot | AI4Finance-Foundation/FinRobot | 6d6ccd3 (09-11) | |
| A | TradingAgents | TauricResearch/TradingAgents | be952b8 (09-07) | |
| A | Vibe-Trading | HKUDS/Vibe-Trading | f84b2977 (09-12) | |
| B BI/数据智能 | DB-GPT | eosphoros-ai/DB-GPT | 04559f9c (09-08) | |
| B | SQLBot | dataease/SQLBot | ba9aa5db (09-11) | 许可 NOASSERTION（DataEase 系惯常 GPLv3+附加），商用注意 |
| B | supersonic | tencentmusic/supersonic | 6919ac50b (09-08) | **维护模式**（release 停 2025-03 v0.9.10，此后 18 个月无发版、仅低频维护提交），只作 ChatBI/语义层参考 |
| B | WrenAI | Canner/WrenAI | be1f9b57 (09-11) | |
| B | DataAgent | spring-ai-alibaba/DataAgent | 3fb7852 (08-19) | 1.0.0-RC 未 GA |
| B | data-formulator | microsoft/data-formulator | 5477f0e2 (08-15) | |
| C 编码 agent | cline | cline/cline | cfe9cadab (09-11) | |
| C | codex | openai/codex | ee6814bfa4 (09-12) | |
| C | gemini-cli | google-gemini/gemini-cli | 9c1b0a610 (09-11) | |
| C | opencode | anomalyco/opencode | 95daf90670 (09-11) | 2026 已迁移 org |
| C | OpenHands | OpenHands/OpenHands | 60877198a (09-12) | 2026 已迁移 org；**当前 HEAD 已清空迁移为 TS 版 Agent Canvas，经典 Python 事件流架构解剖锚定 git 历史 e8249f00a (2026-04-18)** |
| C | claude-code-sourcemap | ChinaSiro/claude-code-sourcemap | a8a678c (03-31) | sourcemap 还原 Claude Code CLI v2.1.88，非官方开源；仅供模式参考 |
| D 研究/浏览器 | gpt-researcher | assafelovic/gpt-researcher | 6f998577 (08-23) | |
| D | browser-use | browser-use/browser-use | 50f205533 (09-09) | |

解剖深度按组：A/B 全 8 维深剖；C 重点解剖权限/审批/上下文管理/会话恢复等横切工程；D 快扫（架构与工具设计）。

## 档案模板（profiles/ 统一格式）

```markdown
# <项目> 解剖档案
> 基线：~/develop/opensource/<目录> @ <hash>；canonical <owner/repo>；状态备注（如有）
## 1. 产品定位与形态（解决什么/目标用户/交互形态 CLI/Web/IDE/服务）
## 2. Agent 执行架构（主循环实现/编排模式/多 agent 分工与通信）
## 3. 技术底座（语言/web 框架/agent 框架选型——交叉引用 agent-framework/profiles）
## 4. 状态与持久化（会话/执行状态/checkpoint/审计/回放/并发）
## 5. HITL 与风控（审批门/危险操作拦截/人工接管/回滚纠错）★重点
## 6. 工具与业务系统集成（工具封装/凭据/权限边界/读写隔离）
## 7. 部署与产品化（形态/多租户/配额成本/可观测性）
## 8. 对本项目的适用性（对照 Java、独立部署+API、图编排、财务合规四条：可借鉴模式→类/模块路径 / 不可迁移点 / 避坑）
```

## 进度 checklist（分批可续）

Phase 1 逐仓库档案（18）：
- [x] A 组：ai-hedge-fund、FinRobot、TradingAgents、Vibe-Trading
- [x] B 组：DB-GPT、SQLBot、supersonic、WrenAI、DataAgent、data-formulator
- [x] C 组：cline、codex、gemini-cli、opencode、OpenHands、claude-code-sourcemap
- [x] D 组：gpt-researcher、browser-use

Phase 2 分组与专题（dimensions/）：
- [x] A 组横向（金融决策/风控拓扑）
- [x] B 组横向（ChatBI/NL2SQL 产品形态）
- [x] C 组横向（harness 横切工程）
- [x] D 组横向（研究/浏览器自动化）
- [x] 跨组专题×4：多 agent 拓扑 / 审批与风控 / 状态与审计 / 工具与系统集成

Phase 3 综合：
- [x] report.md（pattern catalog 三级分类：直接可用 30 / 需改造 10 / 仅参考 8；反模式 14 条；财务 agent 推荐架构含 ASCII 图与分期建议）
- [x] references.md（学术与基准参照系，2026-09-13 gh api 核验）

## 目录

- [report.md](./report.md) —— 综合报告（最终交付）
- [references.md](./references.md) —— 学术与基准参照清单（survey/benchmark）
- [profiles/](./profiles/) —— 18 份解剖档案
- [dimensions/](./dimensions/) —— 4 份分组横向 + 1 份跨组专题
