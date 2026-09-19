# 维度 15：管理平面（Management Plane）

> 本维度回答：框架是否提供**控制台（console/dashboard）**、**配置中心（config center）**、**多租户（multi-tenancy）**、**成本看板（cost observability）**、**应用版本管理（versioning）**——即「运维/治理 agent 的那层 UI 与 API」而不是「跑 agent 的那层」。17 框架只有一个满配玩家：**Dify**（Web 控制台覆盖应用编排/知识库/插件市场/成员 RBAC/计费，tenant_id 贯穿全部业务表，工作流草稿/发布双态版本化）。其余分层清晰：**企业付费控制台**（crewai AMP、langgraph Studio/LangSmith、openai-agents 的 OpenAI 平台、llama_index 的 LlamaCloud）管理面在闭源 SaaS；**本地开发台**（adk web、MS devui、agentscope-java 前端、spring-ai-alibaba admin/studio）管调试不管运营；**纯库无管理面**（langchain、langchain4j、spring-ai、claude-sdk 等）。配置中心是唯一由 Java/中国生态主导的子项：Nacos 注入（spring-ai-alibaba）、YAML Config Agent 热重载（adk-java）、admin/nacos/higress 注册中心（agentscope-java）。成本看板几乎全员缺席——只有 Dify 把 billing 做成模块，开源框架普遍止步于 usage 数据结构。

## 15.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号）|
|---|---|---|---|
| langchain | ❌ | 无 console/租户/计费；观测管理面 = 托管 LangSmith（文档宣称，非本仓代码） | ——（libs/langchain_v1 无管理面代码）|
| langgraph | 🟡 | 管理协议开源、实现闭源：SDK 客户端管 threads/assistants/**crons**/store，Studio 控制台在 LangSmith 平台（仓库仅外链 URL）| libs/sdk-py/langgraph_sdk/_async/{threads,assistants,cron,store}.py；libs/cli/langgraph_cli/cli.py（Studio 仅外链，二次核验）|
| langgraph4j | ❌ | 无 console/tenant/billing；最接近的是 SQLiteSaverV2Dashboard 的 thread/tag 查询 API 雏形（test 级）| langgraph4j-sqlite-saver/.../SQLiteSaverV2Dashboard.java#ThreadRecord |
| langchain4j | ❌ | 无任何管理面（A2A 的 tenantId 仅协议字段透传） | langchain4j-agentic-a2a/.../a2a/A2ATenantId.java |
| deepagents | 🔶 | 正式包无管理面；talon 实验包有 authorization/tool_approvals/fleet_import/observability 运行时治理雏形（自标 alpha）| libs/talon/deepagents_talon/authorization.py；libs/talon/README.md |
| agent-framework (MS) | 🟡 | devui 官方包（beta）：本地 playground + OpenAI 兼容端点 + 会话/agent 发现/tracing 页 + React 前端；无多租户 console/billing | python/packages/devui/agent_framework_devui/_cli.py:149#main（二次核验）、_discovery.py、_tracing.py；dotnet Aspire.Hosting.AgentFramework.DevUI |
| adk-python | 🟡 | `adk web` 本地控制台（会话/事件/trace 浏览，内置编译 React 前端 + 内置辅助 agent）；app_name/user_id 多租户命名空间内建；admin/billing 依托 Vertex Agent Engine | cli/adk_web_server.py；cli/browser/（chunk-*.js 编译产物二次核验）；sessions/session.py:43-47 |
| adk-java | 🔶 | dev server REST 面（agents/sessions/artifacts/graph/debug/execution 七 Controller）无内置 UI；YAML Config Agent + ConfigAgentWatcher 热重载（Maven goal 内）；无租户/计费 | dev/.../web/controller/（7 个 Controller）；maven_plugin/.../ConfigAgentWatcher.java + ConfigAgentLoader.java（二次核验）|
| openai-agents-python | ❌ | 无 console/dashboard/租户/计费；trace 数据面默认直连 OpenAI 平台（管理能力外置于 OpenAI 账号体系）| src/agents/tracing/processors.py#_OPENAI_TRACING_INGEST_ENDPOINT |
| claude-agent-sdk-python | ❌ | 无任何管理面；多租户最近的一点是 SessionKey.project_key docstring 建议「tenant id 自行命名空间」 | src/claude_agent_sdk/types.py:1502-1505#SessionKey.project_key |
| crewai | 🟡 | 控制台/SSO/组织/计费全在付费 AMP（enterprise-api yaml 仅契约文档 + PlusAPI/deploy_by_name 客户端，二次核验）；OSS 侧仅 TUI（运行台/断点/记忆浏览）| docs/v1.15.21/enterprise-api.base.yaml；lib/crewai-core/src/crewai_core/plus_api.py:323/:328；lib/cli/src/crewai_cli/{crew_run_tui,checkpoint_tui}.py |
| dify | ✅ | Next.js 控制台全量（apps/datasets/tools/plugins/marketplace/skills/integrations/成员 RBAC/billing）+ tenant_id 贯穿全部业务表 + 工作流与 Skill 双版本化 + DSL 导入导出 | web/app/(commonLayout)/（页面目录二次核验）；api/controllers/console/（admin/billing/workspace 全域）；api/models/workflow.py:259#VERSION_DRAFT |
| llama_index | ❌ | 无 console/租户/计费；商业管理面在 LlamaCloud SaaS（外部，未本地验证） | ——（本仓库零管理面代码）|
| agentscope | 🟡 | 核心 REST 管理 API 完整（session/model/credential/kb/hub/schedule/workspace 17 路由）；Web UI 为示例级（React 管理台在 examples/web_ui，二次核验 frontend/src 存在）；无租户/计费 | src/agentscope/app/_router/（17 个 router）；examples/web_ui/frontend/src/ |
| agentscope-java | ✅ | service 自带 React 管理台 + admin starter（AgentRegistry/CommandPlane 管理命令面）+ scheduler 自托管管理 Web + Studio 对接 + nacos/higress 注册中心；无租户/计费 | agentscope-service/frontend/src/；agentscope-admin-spring-boot-starter/.../registry/AgentRegistry.java + command/CommandPlane.java（二次核验）；service-scheduler/.../web/managed/selfhosted/ |
| spring-ai-alibaba | 🟡 | admin 一站式平台（可视化编排画布 spark-flow + Dify DSL 迁移 22 个 NodeDataConverter + 评估 + MCP 管理 + 账号域，独立构建）+ studio 本地台 + Nacos 四注入器（prompt/model/agents/tools/MCP）；租户/计费深度未验证 ⚠️ | spring-ai-alibaba-admin/.../dsl/adapters/DifyDSLAdapter.java（二次核验）；starter-config-nacos/.../nacos/Nacos{Model,Prompt,Agent,PartnerAgents}Injector.java（二次核验）|
| spring-ai | ❌ | 无 console/dashboard/租户/计费/配置中心；配置走 Boot properties + BOM，观测交 Micrometer 后端呈现 | ——（全仓无对应实现，档案已验证）|

评级说明：与档案一致；无评级冲突。两处二次核验充实：dify web 控制台页面目录（agents/apps/datasets/explore/installed/integrations/marketplace/plugins/skills/snippets/templates/tools）与 spring-ai-alibaba Nacos 注入器全集（Model/Prompt/Agent/PartnerAgents 四 Injector + NacosReactAgentBuilder + NacosOptions）均确认存在。

## 15.2 实现方式深析

### 派系 A：控制台——四档能力光谱

**Dify：唯一的运营级控制台（断崖式领先）**。三个面合一：① Web 控制台 `web/app/(commonLayout)/` 覆盖应用（apps/agents）、知识库（datasets）、工具/插件/市场（tools/plugins/marketplace/installed/explore）、工作区 Skill（skills）、模板（templates）、集成（integrations）、代码片段（snippets）；② 控制台 API `api/controllers/console/` 覆盖 admin、billing（billing.py + compliance.py 合规下载）、workspace（members/rbac/load_balancing_config/model_providers/models/skills/tool_providers/account）、datasets、agent、插件治理、workflow_run_archive 等；③ 开放 API 面 service_api（App Key 鉴权）+ inner_api（插件回调）。配合 cmd+K `/create` 的 LLM 工作流生成器（ROUTER→PLANNER→并行 BUILDERS→POSTPROC），控制台不只是管理面还是构建面。

**agentscope-java：控制平面管理台（企业自托管向）**。service 自带 React 前端（frontend/src 含 api/app/components/features/pages + e2e 测试）；admin starter 把管理做成 Spring 组件——`AgentRegistry`（agent 清单）+ `CommandPlane/AdminCommandRegistry`（管理命令面）+ `AgentInventory`；scheduler 另有自托管 agent 的 Web 管理（web/managed/selfhosted/）。定位证据是 service README 的「unified control plane … govern Agents built with different frameworks」——管理对象不只是自家 agent。无租户/计费/配额。

**adk-python / MS devui：开发台（developer console）**。adk web 内置编译好的 React 前端（cli/browser/ 二次核验为 chunk-*.js 产物），提供会话/事件浏览、trace 查看，并塞了 built_in_agents 辅助 agent 帮你在台内干活；多租户只有 app_name/user_id 命名空间语义，无成员/权限管理。MS devui（beta）同档：`devui` CLI 命令拉起本地 playground + OpenAI 兼容端点 + agent 发现（_discovery.py）+ tracing 页（_tracing.py）+ React 前端，.NET 侧还有 Aspire.Hosting.AgentFramework.DevUI 把台面编进 Aspire 应用模型。两者都是「调试台」语义，无运营功能。

**crewai：管理面 = 付费平台客户端**。OSS 仓库里的管理面证据全是「对接件」：PlusAPI 客户端（deploy_by_name/deploy_by_uuid 二次核验）、`crewai deploy create/list/push/validate/status/logs/remove` CLI、oauth2 login/logout、organization 切换；控制台本体在闭源 AMP（企业 REST 契约仅 docs/v1.15.21/enterprise-api.base.yaml + en/ko 多语言副本——连 API 文档都齐了，就是不实现）。OSS 侧本地界面只有 TUI 三件：运行台（crew_run_tui）、断点浏览（checkpoint_tui）、记忆浏览（memory_tui）。

**langgraph / openai-agents / llama_index：管理面外置于自家 SaaS**。langgraph 最典型——「管理协议开源、实现闭源」：SDK 有完整 threads/assistants/crons/store 客户端（即管理面的 API 形状），但消费这些 API 的生产 server 与 Studio UI 都在 LangSmith 平台；仓库内 Studio 只以外部 URL 出现（cli.py 的 `--li-url` 参数）。openai-agents 默认把 trace 批量外发 `api.openai.com/v1/traces/ingest`——管理台就是 OpenAI 账号后台。

### 派系 B：配置中心——Java/中国生态的主场

- **spring-ai-alibaba：Nacos 四注入器**（二次核验 NacosModelInjector/NacosPromptInjector/NacosAgentInjector/NacosPartnerAgentsInjector + NacosReactAgentBuilder + NacosOptions + NacosContextHolder）：prompt、模型参数（反射替换 ChatClient chatOptions）、agent 定义、partner agents、MCP 网关工具全部可由 Nacos dataId 中心化下发并注入运行中的 agent；支持 `cipher-kms-aes-256-` 前缀加密 dataId。这是 17 家中唯一的「配置中心原生」框架——agent 的定义本身是可远程热更的配置。
- **adk-java：YAML Config Agent + 热重载**：`LlmAgent.fromConfig` + YamlPreprocessor 在 core，maven_plugin 的 ConfigAgentWatcher（二次核验 ConfigAgentWatcher.java/ConfigAgentLoader.java）监听 YAML 变更热重建 agent 树（含回调类名/工具/子 agent，contrib/samples/configagent 七种配置样例）——「无 CLI 的 Java 版低代码调试」。
- **agentscope-java：注册中心三件**——agentscope-extensions-nacos（配置/注册）、higress（网关）、admin starter 的 InMemoryAgentRegistry；调度/渠道/凭证都有对应 REST 管理端点。
- **其余**：无配置中心概念。adk-python/agentscope(Python)/dify 的「配置」是代码或数据库（dify 的应用配置在 DB + DSL 导入导出），langgraph 系靠环境变量与部署配置。

### 派系 C：多租户——一家实做、两家命名空间、其余 SaaS 侧

- **Dify：实做**。tenant_id 贯穿全部业务表（二次核验 App.tenant_id 解析逻辑 + TenantAccountJoin 模型），工作区成员角色解析（workspace_member_role_resolver.py）、RBAC + flask_admission 控制台准入、按租户的 trace 配置与配额——租户是数据模型的一等公民。
- **adk 双语：命名空间语义**。Session = app_name/user_id/id 三元组，「多租户」= 命名空间隔离，无成员/配额/计费概念。
- **claude-sdk：docstring 级建议**。SessionKey.project_key 注释「Multi-tenant deployments should set this to a tenant ID」——把租户映射留给宿主。
- **langchain4j：协议字段**。A2ATenantId 仅透传，非管理面。
- **crewai / openai-agents / langgraph / MS**：租户管理在付费平台侧（AMP 组织、OpenAI 项目、LangSmith workspaces、Azure 租户）。

### 派系 D：成本看板——从 usage 数据结构到 billing 模块的四级落差

usage 数据（token/成本）几乎家家有（ResultMessage.total_cost_usd、UsageMetrics、ChatUsage、usage_metadata…），但**聚合到管理面**只有 Dify 走完全程：Message.total_price/currency 落库 → 控制台 billing 域（BillingService 调外部计费 API BILLING_API_URL，services/billing_service.py:218 二次核验；社区自托管退化为免费额度 quota_service）+ 合规下载（console/billing/compliance.py ComplianceApi）+ 订阅分层与 Celery 队列联动（PROFESSIONAL/TEAM/SANDBOX）。其余三级落差：crewai 的 UsageMetrics 聚合在库内但无任何 UI；agentscope-java 的 ChatUsage 明确无 cost 计价；多数框架把成本观测推给 tracing 后端（LangSmith/Langfuse/OTel 面板）。「把成本当管理面一等公民」在开源世界基本等于没有。

### 派系 E：应用/Agent 版本管理

- **Dify：双版本化体系**。工作流：草稿单副本（version='draft'）+ 发布版本号单调递增、**不可变**（models/workflow.py:259 VERSION_DRAFT；:753「删除已发布版本不释放版本号」的注释二次核验）；恢复发布快照到草稿（workflow_restore.py）。Skill：SkillDraftFile/SkillVersion（manifest 带 hash 的不可变快照）+ AgentSkillBinding 绑定表。配合 DSL 导入导出（export_dsl/import_app 含依赖检查）构成「应用即代码」的完整版本生命周期。
- **spring-ai-alibaba admin：DSL 方言迁移器**。DifyDSLAdapter/StudioDSLAdapter + 22 个 NodeDataConverter（二次核验 AbstractNodeDataConverter/NodeDataConverter/converter/ToolNodeDataConverter 等）把 Dify DSL 转成自家图并导出代码——不做版本管理，做「版本迁移」（吸收 Dify 存量用户）。
- **crewai：deploy 推平台**。`crewai deploy validate/push` 有版本校验语义（部署规格 CrewDeploymentSpec），但版本存储在 AMP 侧。
- **langgraph：assistants API**。SDK 有 assistants 概念（可版本化的 agent 配置），实现闭源。
- **其余**：版本管理 = git（代码即版本）。

## 15.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | 🟡 管理协议开源（threads/assistants/crons/store SDK）+ Studio/LangSmith 闭源台 | ❌ 无（SQLiteSaverV2Dashboard 雏形） | Python 侧「API 形状在、UI 在平台」；Java 侧连管理 API 形状都没有——跨语言对齐在本维度为零，证明管理面从来不是 langgraph4j 的移植目标 |
| adk-python(2.9) ↔ adk-java(1.9) | 🟡 adk web 本地台（内置 React 前端 + built_in agents 辅助）+ 多租户命名空间 | 🔶 dev REST 七 Controller 无 UI（⚠️ 是否有外部配套前端未证实）+ YAML Config Agent 热重载 | **UI 有无是硬差异**（Python 内置编译前端，Java 无静态资源）；Java 独有的「配置中心式」通道（ConfigAgentWatcher 热重建 agent 树）部分补偿无 UI；两家云端管理面都外推 Vertex Agent Engine |
| agentscope(Python) ↔ agentscope-java | 🟡 17 路由 REST 管理 API（核心级）+ web_ui 示例台 | ✅ service React 管理台（核心级）+ admin starter（AgentRegistry/CommandPlane）+ scheduler 自托管 Web + nacos/higress 注册中心 | **Java 反超 Python** 的维度：Python 把管理 API 做成核心、UI 留在 examples；Java 把管理台做进核心 service 模块并配注册中心生态。对齐项：两家都没有租户/计费；Python 的 hub（MCP/技能市场）管理在 Java 侧由 skills 仓库扩展（git/mysql/pg）承担 |

## 15.4 取舍与趋势

1. **「运营级管理面」与「开源框架」几乎是互斥集**：17 家中只有 Dify（低代码平台）与 agentscope-java（企业控制平面）把控制台做进开源仓库；crewai、langgraph、openai-agents、llama_index、MS 的管理面全在商业侧。框架厂商普遍把「谁看日志、谁管版本、谁付账单」视为 SaaS 护城河而非框架职责——选择开源框架基本等于选择自建或外购管理面。
2. **配置中心是「框架 vs 平台」的隐形分水岭，且被中国 Java 生态垄断**：Nacos 注入（spring-ai-alibaba）、YAML Config Agent 热重载（adk-java）、nacos/higress 注册（agentscope-java）三家全是 Java + 中国生态；Python 系框架的「配置」要么是代码、要么是平台数据库。原因结构性：Spring/Nacos 企业栈里「运行时改配置不重启」是既定运维契约，agent 定义自然被当成配置的一种。
3. **多租户的诚实分级**：只有 Dify 做了数据模型级租户（tenant_id + RBAC + 配额）；adk 的三元组命名空间和 claude-sdk 的 docstring 建议是「留了格子没建房子」；其余全部把租户推给部署侧。对多租户 SaaS 选型，这个差异比任何架构图都硬。
4. **成本看板是全行业一致的留白**：usage 结构人人有、成本聚合无人做——Dify billing 调的还是外部计费 API（社区版退化为免费额度），crewai 止步 UsageMetrics、agentscope-java 连计价都没有。成本可见性的现实路径是 tracing 后端（LangSmith/Langfuse/OTel + Grafana），框架自己不做也不打算做。
5. **版本管理的两极：数据库双态 vs git**：Dify 把「草稿可变/发布不可变/版本号不回收」做进数据库（应用即数据的必然选择），langgraph assistants 在平台侧提供等价物；代码框架一致地回答「版本 = git」。spring-ai-alibaba 的 DifyDSLAdapter（22 个节点转换器）代表第三条路——不做版本、做跨平台迁移，把存量 Dify 应用当获客入口，是管理平面竞争里罕见的进攻性设计。
6. **「管理 API 先行、UI 后置/外置」成为可移植策略**：langgraph（SDK 客户端全开源、server/UI 闭源）与 agentscope(Python)（核心 17 路由 REST、UI 留 examples）都把管理面拆成协议与皮肤两层——协议留在开源侧保证生态可编程，皮肤的商业价值留给平台。这解释了为什么 langgraph4j 连管理 API 都没有：没有平台计划的移植不需要协议层。
