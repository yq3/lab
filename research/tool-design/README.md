# tool-design — 业务 API 包装为 Agent Tool 的设计实践调研

| | |
|---|---|
| 时间 | 2026-10-28（单会话完成） |
| 形态 | 网络调研（非源码级，同 `agent-workbench/` 轮模式） |
| 背景问题 | Java 分布式微服务业务系统，agent 服务基于 Python、经公司统一 Python MCP 网关接入。业务系统 API 应如何包装 / 整改 / 重写成 tool？业界与 Anthropic / OpenAI 等官方有哪些实践与文章？ |
| 交付 | [report.md](report.md)（设计原则篇，先读这篇）+ [engineering.md](engineering.md)（工程化落地篇：异步任务 + 生产注意点） |

## 方法

1. 第一轮（2026-10-28）：4 轮 WebSearch 定位权威来源（Anthropic engineering、OpenAI 官方指南、AWS ML Blog、社区/厂商实践）。
2. 3 篇全文抓取（WebFetch）：Anthropic《Writing effective tools for agents》、AWS《MCP tool design: Practical approaches and tradeoffs》、philschmid《MCP is Not the Problem, It's your Server》。
3. OpenAI 官方材料两条路径均被挡（PDF 不支持解析、platform.openai.com 403），降级为转述级引用并在 report §6 留痕。
4. 第二轮扩展（同日，应"尽量全面"要求）：4+4+2 路 WebSearch 覆盖 Google / Microsoft / GitHub 官方工程实践 / 学术评测基准（ToolBench、API-Bank、BFCL、TAU-bench、RoTBench 等）/ 框架生态（LangChain、ADK、Neo4j、Cloudflare）；Google 与 Microsoft 官方文档 WebFetch 直连超时，改用 web_reader 全文抓取成功（升为一手）。来源从 14 个扩到 29 个。
5. 第三轮专题（2026-11-01，异步任务 + 工程化落地）：8 路 WebSearch（MCP 长任务、A2A、OpenAI Background、Claude Code 后台任务、幂等、注入防御、上下文经济、生产实践）+ 1 篇一手全文（MCP Tasks 扩展官方文档），交付 engineering.md（新增来源 E1~E10）。
6. 第四轮专题（2026-11-01，回调唤醒 + 挂起恢复）：8 路 WebSearch（deepagents、LangGraph 1.0 durable execution、Temporal、A2A push、OpenAI Agents SDK HITL、ChatGPT Tasks）+ 2 篇一手（gh api 拉 deepagents README、LangGraph 1.0 官方博客全文）+ 1 篇一手附录（gh api 拉 ext-tasks 官方 schema），engineering.md 增 §1.7/§1.8 与来源 E11~E18。
7. 第五轮源码级复核（2026-11-01）：按 AGENTS.md 证据纪律对前三轮网络结论对码——复用 `deepagents@9e7d62ff`、`langgraph@e539ac12` 克隆，新克隆 `modelcontextprotocol/python-sdk@d7845c07`（经 gh-proxy 镜像，remote 已改回官方）；engineering.md 增 §6（四级挂起链路坐实、节点重放语义、SDK 双规范线与形状差异等修正性发现）。
8. 第六轮产品级实证（2026-11-07）：对码四家 harness 的异步任务机制——`claude-code-sourcemap@a8a678c`（通知队列唤醒链路【核心】）、`openai/codex@ee6814bfa4`（cloud-tasks 委派 + unified_exec）、`deepseek-ai/deepseek-harness`（jobs/schedule 包，B 形态教科书【文档级】）、ChatGPT 产品行为；engineering.md 增 §7。结论：四家无一家用挂起执行等长任务，全部是"立即返回句柄 + 状态可查 + 完成通知注入会话"的 B 系实现。

## 证据等级（沿用 agent-workbench 轮定制）

- 【一手】官方原文，已全文抓取并提炼
- 【转述】第三方对官方内容的转述 / 官方内容的二手摘编
- 【摘要】仅搜索引擎结果摘要，未读原文
- 【未找到】检索未命中

## 进度 checklist

- [x] Phase 1 定位与抓取：4 轮检索 + 3 篇一手全文
- [x] Phase 2 原则合并提炼（十条核心原则，report §2）
- [x] Phase 3 重点原文详述（report §3）
- [x] Phase 4 映射到本项目场景（Java 业务系统 + Python MCP 网关，report §4）
- [x] Phase 5 证据等级与复核留痕（report §6）
- [x] Phase 6 二轮扩展（Google/Microsoft/GitHub 官方、学术基准、框架生态，report §1 表 15~29、§3.6~3.10）
- [x] Phase 7 工程化专题：异步任务（MCP Tasks / A2A / OpenAI Background / Claude Code）+ 生产注意点 10 项（engineering.md）
- [x] Phase 8 回调与挂起专题：主动回调四路线 + deepagents/LangGraph interrupt + Temporal durable execution（engineering.md §1.7/§1.8，来源 E11~E18）
- [x] Phase 9 源码级复核：deepagents 挂起链路【核心】、langgraph 恢复重放语义【核心-文档】、python-sdk Tasks 双规范线【核心】（engineering.md §6，含对 §1.3/§1.8 的修正）
- [ ] （可选后续）web_reader 补抓 GitHub 两篇工程博客原文，摘要级 → 一手
- [ ] （可选后续）补读 engineering.md §4 列出的待复核原文（A2A spec 8 态清单、OpenAI Background 保留期细节）
