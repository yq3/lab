# 维度 13：安全治理（Security Governance）

> 本维度回答：一个 agent 在生产环境运行时，框架在**输入/输出护栏（guardrails）**、**工具权限模型（permission model）**、**代码沙箱（sandbox）**、**审计（audit）**、**PII 脱敏**、**凭据托管（credential management）** 六个层面上各提供了什么正式抽象。17 框架总体呈三层格局：**平台级纵深防御**（Dify、Microsoft agent-framework、AgentScope 双语言、openai-agents、claude-sdk）把权限/沙箱/审查做进核心类型；**切面式治理**（adk-python、crewai、adk-java、spring-ai、spring-ai-alibaba、langchain）靠回调/中间件/钩子留切入位但内容库留给生态或用户；**引擎零安全**（langgraph、langgraph4j、llama_index 纯引擎侧）刻意不做，安全是上层库的事。最值得注意的对比：Claude Code 式「权限模式 + 规则 + 审批」已被 4 家产品化（claude-sdk、agentscope 双语言、MS harness），而「内容安全审查库」只有 Dify 一家内置（moderation）。

## 13.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号）|
|---|---|---|---|
| langchain | ✅ | PII/上下文编辑/三策略沙箱 shell/SSRF 防护四个具体中间件，无统一 guardrail/审计抽象 | libs/langchain_v1/langchain/agents/middleware/pii.py#PIIMiddleware；middleware/_execution.py#DockerExecutionPolicy；core/_security/_ssrf_protection.py#validate_safe_url |
| langgraph | ❌ | 引擎层零安全抽象，仅 checkpoint 静态加密 + 面向闭源平台的 SDK auth/字段加密协议 | libs/checkpoint/.../serde/encrypted.py#EncryptedSerializer；libs/sdk-py/langgraph_sdk/auth/ |
| langgraph4j | ❌ | 全仓 grep guardrail/permission/pii 零命中；工具进程内直执行，无沙箱无审计 | ——（langgraph4j-core 全量检索无命中，已二次复核）|
| langchain4j | ✅ | core 内 Input/OutputGuardrail SPI + 注解挂载 + 独立包三件内置（提示注入正则/审核模型/JSON 提取）+ GraalVM 沙箱；无工具权限 | langchain4j-core/.../guardrail/InputGuardrail.java；langchain4j-guardrails/.../PatternBasedPromptInjectionGuardrail.java |
| deepagents | ✅ | 文件权限三态首匹配 + 路径校验 + 递归删除通配 fail-closed + execute×权限组合显式拒绝；PII/审查需组合 langchain | libs/deepagents/deepagents/middleware/filesystem.py#FilesystemPermission(:387)；filesystem.py:1821-1828#NotImplementedError（二次核验）|
| agent-framework (MS) | ✅ | 纵深四层：内容标签(Integrity×Confidentiality，FIDES 实验特性) + 参数级审批规则 + MCP 专项审批 + Purview 外评(beta) + hyperlight 沙箱 | python/packages/core/agent_framework/security.py#ContentLabel(:157)；_harness/_tool_approval.py#ToolApprovalRule(:86)；packages/purview/.../_middleware.py#PurviewPolicyMiddleware(:24) |
| adk-python | 🟡 | 无内置内容安全/PII 库；治理靠 callback 六切入点（列表化）+ 事件溯源审计轨迹；内容安全走 Model Armor 生态 | src/google/adk/agents/llm_agent.py:488-550（callback 面）；integrations/model_armor/_plugin.py（二次核验存在）|
| adk-java | 🔶 | 无 guardrail 抽象，靠 10 类 callback/Plugin + NamedToolPredicate 黑白名单 + Docker 沙箱 + BigQuery 审计插件 | core/.../tools/NamedToolPredicate.java；codeexecutors/ContainerCodeExecutor.java；plugins/agentanalytics/BigQueryAgentAnalyticsPlugin.java（二次核验存在）|
| openai-agents-python | ✅ | 三层 guardrail（run 输入/输出 + 工具输入/输出三态处置）+ 全工具面审批 + 7 云厂商沙箱子系统 + 加密会话 | src/agents/guardrail.py#InputGuardrail(:72)；tool_guardrails.py:80-116；extensions/sandbox/（7 厂商目录二次核验）|
| claude-agent-sdk-python | ✅ | 三层权限（规则+6 种 permission_mode+can_use_tool 回调可改输入改规则）+ Bash 沙箱配置 + Windows BatBadBut/flag 注入防御 | src/claude_agent_sdk/types.py:25-27#PermissionMode（6 值二次核验）；types.py#PermissionUpdate；subprocess_cli.py#_reject_windows_batch_cli |
| crewai | 🟡 | Task 级 guardrail 三形态 + 11 切入点 hooks + 组件指纹；无 PII/权限/内容安全库，SecurityConfig 多项 TODO | lib/crewai/src/crewai/tasks/llm_guardrail.py#LLMGuardrail(:49)；hooks/dispatch.py#InterceptionPoint(:40)；security/security_config.py |
| dify | ✅ | 输入/输出 moderation（关键词+OpenAI 审查 API）+ SSRF 代理 + 双沙箱（服务容器 + Go landlock/PTY）+ RBAC + 凭据加密与权限策略 | api/core/moderation/input_moderation.py；api/core/helper/provider_encryption.py（二次核验）；dify-agent-runtime/internal/landlock/config.go（二次核验新发现）|
| llama_index | 🔶 | 仅检索后 PII 脱敏处理器（正则/NER）+ agentmesh 集成的密码学信任门控；无 guardrail 框架/沙箱/审计 | llama-index-core/.../postprocessor/pii.py#PIINodePostprocessor(:40)；integrations/agent/llama-index-agent-agentmesh/ |
| agentscope | ✅ | 5 模式权限引擎（确定性求值序 + bypass 免疫 safety ASK + 拒绝自动建议白名单规则）+ 危险路径表 + 8 种沙箱后端 + 资源访问默认拒绝策略；无内容安全/PII | src/agentscope/permission/_engine.py#PermissionEngine(:17)（5 模式二次核验）；tool/_base.py:437#_is_dangerous_path；app/access/_policy.py#DenyAllResourceAccessPolicy |
| agentscope-java | ✅ | 6 步确定性权限链（含 DONT_ASK 降级 DENY）+ @Tool 危险路径元数据 + Unix/Windows 命令白名单校验 + 4 沙箱后端 + DB 分布式沙箱锁 + credential 包 | agentscope-core/.../permission/PermissionEngine.java；tool/coding/UnixCommandValidator.java；agentscope-extensions-jdbc/sandbox/JdbcSandboxExecutionGuard.java |
| spring-ai-alibaba | 🟡 | PIIDetectionHook（检测+脱敏策略）+ 复用 AgentScope runtime 沙箱（browser/fs/mcp）；无统一 guardrail/RBAC/审计 | spring-ai-alibaba-agent-framework/.../agent/hook/pii/PIIDetectionHook.java；spring-ai-alibaba-sandbox/（io.agentscope runtime 1.0.2）|
| spring-ai | 🟡 | SafeGuardAdvisor 敏感词拦截 + 记忆 advisor 防注入转义 + 模板校验模式；无 PII/审计/工具 RBAC/沙箱——**2.0 无 content safety advisor（rg 二次核验零命中）** | spring-ai-client-chat/.../advisor/SafeGuardAdvisor.java；advisors/.../vectorstore/VectorStoreChatMemoryAdvisor（Javadoc 安全注记）|

评级说明：与各档案一致，无冲突；三处二次核验为「确认缺席」（spring-ai ContentSafety、langgraph4j、langgraph）与「确认存在但需加限定」（MS ContentLabel 标注 `@experimental(feature_id=ExperimentalFeature.FIDES)`、adk Model Armor 为 integrations 生态位）。

## 13.2 实现方式深析

### 派系 A：护栏位置学——guardrail 挂在哪、何时执行

**openai-agents：唯一把「执行时机」做成产品特性的**。run 级 `InputGuardrail` 默认 `run_in_parallel=True`，与首轮模型调用 `asyncio.gather` 并发（run.py:1698 `create_task` → :1737 `gather(guardrail_task, model_task)`），tripwire 触发即 `model_task.cancel()`（:1742-1745，受 `should_cancel_parallel_model_task_on_input_guardrail_trip` 配置控制是否取消已并行的模型调用）——用安全检查的延迟换取吞吐而非串行阻塞。工具级再叠一层 `ToolInputGuardrail/ToolOutputGuardrail`，输出三态处置 `allow / reject_content（拒绝但继续，消息回模型）/ raise_exception`（tool_guardrails.py:80-116），且支持 `pre_approval_tool_input_guardrails` 在人工审批**之前**先跑护栏。这是 17 家中粒度最细的护栏网格：run 入口、模型出口、工具入口、工具出口、审批前五处。

**langchain4j：Java 式 SPI + 注解挂载**。`InputGuardrail/OutputGuardrail` 接口在 core（guardrail/ 包），`@InputGuardrails/@OutputGuardrails` 注解挂到 AiServices 声明式接口方法上，`GuardrailExecutor` 统一执行（含 `StreamingToSynchronousChatExecutor` 流式适配）。独立包 langchain4j-guardrails 内置三件：`PatternBasedPromptInjectionGuardrail`（正则提示注入检测）、`MessageModeratorInputGuardrail`（审核模型）、`JsonExtractorOutputGuardrail`——是 Java 系唯一自带「内容检测器」的框架（虽只有三个）。

**crewai：Task 粒度 + 重试语义**。`Task.guardrail(s)` 是任务级校验器（失败重试 3 次，utilities/guardrail.py:123 process_guardrail），另有 `LLMGuardrail`（LiteAgent 驱动的 LLM 裁决）与 `HallucinationGuardrail`（幻觉检测）两个预制品。执行位置在任务产出之后、进入下一任务之前——比 openai-agents 粗两档。

**Dify：应用配置级 moderation，平台唯一**。`InputModeration/OutputModeration`（api/core/moderation/）走应用配置 `sensitive_word_avoidance`，实现两路：keywords 本地关键词 + openai_moderation 调 OpenAI 审查 API（moderation/openai_moderation/ 子目录）。这是 17 家中唯一内置「生产可用的内容审查库」的框架——其余全部要求用户自写检测函数或外接服务。

**adk-python / adk-java：不给护栏给钉子**。无 guardrail 类型，治理范式 = before/after × agent/model/tool 六类 callback（Python 侧 `canonical_*_callbacks` 接受列表可叠加；Java 侧另有 Plugin 单接口 14 钩子 + 全 Sync 变体）。内容安全明确让位生态：`integrations/model_armor/`（Vertex Model Armor 的 _config/_plugin，二次核验仅 plugin 适配层）。Java 版 eval 端点都是 stub（501），更无 safety evaluator。

**MS agent-framework：标签随消息流转（独此一家）**。`security.py` 定义 `ContentLabel = IntegrityLabel(TRUSTED/UNTRUSTED) × ConfidentialityLabel(PUBLIC/PRIVATE/USER_IDENTITY)`（:121/:138/:157，二次核验标注 `@experimental(feature_id=ExperimentalFeature.FIDES)`——ADR-0024 防提示注入的信息流控制模型，实验态）。标签不是拦截器而是消息元数据：中间件可按标签决定哪些内容能进工具调用/哪些输出能外发，把「不可信内容不得触达可信操作」做成类型系统问题。策略执行外置给 Purview（beta 包）：`PurviewPolicyMiddleware(AgentMiddleware)`（_middleware.py:24）与 `PurviewChatPolicyMiddleware(ChatMiddleware)`（:150）对接 Microsoft Purview 合规策略引擎。

### 派系 B：权限模型——谁能调工具、要不要人批

四个框架独立收敛到「Claude Code 式三层结构」：**静态规则（allow/deny/ask）× 权限模式 × 运行时审批回调**。

- **claude-agent-sdk**（源头）：CLI 权限规则文法 `Bash(ls:*)` 细到参数模式；`PermissionMode` 六值 `default/acceptEdits/plan/bypassPermissions/dontAsk/auto`（types.py:25-27 二次核验；auto=模型分类器代批）；`can_use_tool` 回调被改写为 `--permission-prompt-tool stdio`（types.py:1896 _configure_can_use_tool），审批时可改写工具输入（updatedInput）**并动态增删权限规则/切模式**（PermissionResultAllow.updatedPermissions 的六种变更 + 四个落盘目的地）。SDK 还复刻了 CLI 规则解析器预判回调遮蔽并告警（CanUseToolShadowedWarning）。
- **agentscope（Python）**：`PermissionEngine` 5 模式各配独立 `_check_<mode>` 方法（_engine.py:87-113 二次核验）；DEFAULT 求值序 = deny 规则 → ask 规则 → 只读快路径 → 工具自检 → allow 规则 → 默认 ASK，其中**bypass 免疫的 safety ASK 不可被 allow 规则覆盖**（:186 _is_safety_ask，如 `rm -rf /`）；EXPLORE 模式显式跳过 allow 规则（只读保证不可让渡）；拒绝时 `PermissionDecision.suggested_rules` 自动生成可加白名单建议（工具的 generate_suggestions hook）——把「审批疲劳」当设计问题处理。
- **agentscope-java**：同 5 模式 + 文档化更细的 6 步链（DENY→ASK→工具自检 bypass-immune→ALLOW→BYPASS 放行→默认 ASK；DONT_ASK 模式把默认 ASK 降级为 DENY 而非放行，PermissionEngine.java:189-198）。权限元数据内嵌 `@Tool` 注解（readOnly/dangerousFiles/dangerousDirectories），shell 侧另有 UnixCommandValidator/WindowsCommandValidator 命令白名单。
- **MS agent-framework harness**：`ToolApprovalRule(tool_name, arguments: dict|None, server_label)`——**参数级匹配**（二次核验：arguments 为 None 匹配该工具全部调用、空 dict 只匹配无参调用），审批决定持久化于会话 `ToolApprovalState`（粘性规则跨轮生效）；MCP 侧独立 `MCPSpecificApproval`（_mcp.py:86）。这是「审批规则可持久化、可参数级收窄」的第三条路线。

**deepagents 走的是路径规则而非工具规则**：`FilesystemPermission(operations, paths, mode)` 三态 allow/deny/interrupt 按声明序首匹配；安全工程亮点在**绕过防御与 fail-closed**——路径必须 `/` 开头、禁 `..`、`~` 显式 NotImplementedError；`_wildcard_delete_overlap` 对 deny 通配与递归 delete 的重叠做 fail-closed 分析（anchor 落在删除子树即阻断）；`FilesystemMiddleware`/`SubAgentMiddleware` 列入不可剥离中间件（profile 剥除即 ValueError）；最硬的一条：**execute 工具 × permissions 组合直接 NotImplementedError**（filesystem.py:1821-1828 二次核验——沙箱后端 + 权限未 scope 到路由即拒绝构造），宁可不可用也不留绕过面。HITL 中断谓词按工具参数语义合成（exact/bulk），堵 `path="."` 与 glob 相对 pattern 的绕过。

**Dify 的权限模型是 RBAC + 凭据两级**：`core/rbac/` + flask_admission 控制台准入门（who 能用哪个应用/知识库）；`CredentialPermission`（models/credential_permission.py:22）+ LB 配置内联合规复检（model_manager.py:450-464）控制哪个模型凭据能被哪类调用使用。

### 派系 C：沙箱与代码执行隔离

| 梯队 | 框架 | 形态 |
|---|---|---|
| 子系统级 | openai-agents | `src/agents/sandbox/` 核心子系统（manifest/挂载物化/快照/rclone 同步/归档限额/_mount_security 审计）+ `extensions/sandbox/` 七云厂商（二次核验目录：blaxel/cloudflare/daytona/e2b/modal/runloop/vercel）；ShellTool 网络域 allowlist |
| 多后端矩阵 | agentscope(Python) | workspace 8 后端：local/bubblewrap/docker/e2b/daytona/k8s/opensandbox/applecontainer，沙箱内经 MCP gateway 执行 |
| 多后端矩阵 | adk-python | 7 种 code executor：built_in/container/gke/unsafe_local/vertex_ai/agent_engine_sandbox + timeout_seconds；`unsafe_local_code_executor` 以命名显式警示 |
| 容器级 | adk-java / spring-ai-alibaba / dify(Code 节点) | docker-java 起容器（减 capability）/ 复用 io.agentscope runtime 沙箱 / 独立 dify-sandbox 容器服务（compose 镜像 langgenius/dify-sandbox:0.2.15 二次核验）|
| 双沙箱 | dify(agent_v2) | 另有 Go 写的 `dify-agent-runtime`：PTY 沙箱 + **Linux landlock**（internal/landlock/config.go，二次核验新发现）+ sanitize-pty 命令（cmd/sanitize-pty/main.go）——内核级文件/网络 confinement，比容器更轻 |
| JVM 内隔离 | langchain4j | GraalVM polyglot `.sandbox(TRUSTED)` + `HostAccess.UNTRUSTED`（进程内语言级隔离，非容器）|
| 三策略 | langchain | ShellToolMiddleware 的 Host/Codex/Docker 三 ExecutionPolicy |
| 微虚拟机 | agent-framework(MS) | hyperlight（beta 包，.NET 侧另有 Hyperlight 项目）——轻量 VM 级隔离 |
| 无 | langgraph / langgraph4j / llama_index / crewai 核心 / spring-ai / openai-agents 之外的多数 | 工具进程内直执行 |

### 派系 D：审计、PII、凭据托管

**审计**：正式「审计抽象」只有两家半——adk-java 的 `BigQueryAgentAnalyticsPlugin`（agent 调用落 BigQuery+GCS，二次核验插件 + E2E 测试齐全）；Dify 的运行审计（workflow_runs/节点执行落库）+ 闭源企业审计导出（api/enterprise/ 🟡）；adk-python 借事件溯源（EventActions.state_delta 一切变更即事件）获得天然审计轨迹但无独立 audit log API。crewai 的 `Fingerprint`（组件身份指纹 + 审计元数据）是供应链审计思路但 SecurityConfig 的 Authentication/Scoping/Impersonation 全 TODO。其余框架审计 = 观测 trace 的副产品。

**PII**：langchain `PIIMiddleware`（RedactionRule 正则规则、出错 PIIDetectionError fail-closed）+ `ContextEditingMiddleware`（对话后遗忘式擦除）是最完整的一对；spring-ai-alibaba `PIIDetectionHook`（PIIDetectors/PIIType/RedactionStrategy/PIIMatch）Java 侧对位；llama_index 只有检索后 `PIINodePostprocessor`（含 NER 变体）；langgraph4j、adk 双语、agentscope 双语、openai-agents、claude-sdk、crewai、dify、MS 均无（MS 依赖 Purview、dify 依赖闭源企业版）。

**凭据托管**：adk-python 是唯一的完整体系——`auth/` 包：AuthCredentialTypes（ApiKey/Http/OAuth2/ServiceAccount，auth_credential.py 二次核验 HttpAuth/OAuth2Auth/ServiceAccountCredential 三类模型）+ exchanger/refresher + `BaseCredentialService`（in_memory/session_state 两实现）+ `authenticated_function_tool`；OpenAPI 工具可声明 auth 后由凭据服务注入。Dify 是平台式：模型/工具凭据 AES 加密落库（api/core/helper/provider_encryption.py + encrypter.py 二次核验）+ CredentialPermission 权限策略 + 工具 OAuth 客户端（models/tools.py）。crewai 走 Fernet 加密登录 token（crewai-core/token_manager.py）+ 工具 EnvVar 声明式凭据。langchain4j / langgraph / langgraph4j / spring-ai 无凭据抽象（环境变量自理）。MS 的凭据在其 MCP/Foundry 生态包内，core 无统一抽象。

## 13.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | ❌ 引擎零安全（仅 EncryptedSerializer + 平台 SDK auth 协议） | ❌ 全仓零命中 | **完全对齐的缺席**：两家都把安全留给上层（langchain 中间件 / langgraph4j 无上层）。Python 侧至少有 SDK 侧 auth/encryption 类型为闭源平台预留，Java 侧连这层都没有 |
| adk-python(2.9) ↔ adk-java(1.9) | 🟡 callback 六切入点列表化 + Model Armor 生态 + 7 code executor + MCP stdio 白名单开关 + api_server DNS-rebinding 防护 | 🔶 10 类 callback/Plugin + NamedToolPredicate 工具集黑白名单 + Docker 沙箱 + BigQuery 审计插件 | **auth 框架 Python 独有**（Java 无 auth 包，仅 AppIntegration 内 GCP Connections helper）；**审计 Java 独有**（BigQuery 插件正式化，Python 反而无对应物只有事件溯源）；工具过滤：Python 用 ToolPredicate 谓词 + toolset 回调，Java 用 NamedToolPredicate 名单——语义相近粒度不同。注意版本差（2.9 vs 1.9）可能放大部分缺口 |
| agentscope(Python v2.0.8) ↔ agentscope-java(v2.0.2+) | ✅ 5 模式 PermissionEngine + 危险路径常量表 + app 层 ResourceAccessPolicy(DenyAll 默认) + 8 沙箱后端 + credential 模块 | ✅ 同 5 模式 6 步显式链 + @Tool 危险路径注解 + Unix/Windows 命令校验器 + 4 沙箱后端 + JdbcSandboxExecutionGuard + credential 包 | **本维度对齐度最高的跨语言对**（语义同构）。Python 多：资源访问策略层、沙箱后端数（8:4）、拒绝建议生成（suggested_rules 自动白名单建议）；Java 多：DONT_ASK→DENY 降级语义显式化、DB 分布式沙箱执行锁（多节点并发防重入）、Windows 命令校验器 |

## 13.4 取舍与趋势

1. **「权限引擎」正在从 CLI 产品下沉为框架原语**：claude-agent-sdk（CLI 移植）、agentscope 双语言（5 模式 + bypass 免疫 + 规则建议）、MS harness（参数级审批规则 + 决定持久化）四家在一年内独立收敛到「规则 × 模式 × 审批回调」三层结构，且都把「审批决定可持久化/可收窄」当一等语义（RunState always_approve、ToolApprovalState、PermissionUpdate 六种变更）——服务端多用户场景要求审批状态跨请求存活，这是 CLI 时代没有的约束。
2. **内容安全审查没有一家开源框架想做**：17 家中只有 Dify 内置 moderation（平台属性使然），MS 把它外推给 Purview、Google 外推给 Model Armor、openai-agents 留空给 OpenAI moderation API——内容审查的合规/运营成本太高，框架层只提供「挂检测器的钉子」（guardrail 函数位、callback、hook），检测器本身是平台生意。
3. **guardrail 的差异化在执行时机与处置语义，不在有没有**：openai-agents 的「与模型调用 gather 并发 + tripwire 取消模型任务」和工具输出三态处置（reject_content 继续而非中断），langchain4j 的流式护栏适配（StreamingToSynchronousChatExecutor），MS 的「标签随消息流转」三种设计分别押注延迟、流式、信息流控制——比「提供 before/after 钩子」的共识层更有信息量。
4. **沙箱分化为三个强度梯队且互不收敛**：云厂商沙箱矩阵（openai-agents 7 厂商、agentscope 8 后端）面向 SaaS 化执行；容器/微 VM（dify Go landlock、MS hyperlight、adk-java docker-java）面向自托管密度；JVM 内隔离（langchain4j GraalVM）面向无容器权限的企业环境。openai-agents 是唯一把沙箱做成带 manifest/快照/网络策略/挂载安全的**完整子系统**而非「一个 executor 接口」的框架。
5. **fail-closed 正在成为 harness 类框架的显性卖点**：deepagents（execute×权限 NotImplementedError、保护中间件不可剥离、递归删除通配阻断）、agentscope（EXPLORE 跳过 allow 保只读、bypass 免疫）、langchain（PIIDetectionError）都把「不确定时拒绝而非放行」写进构造期校验——与早期框架「默认放行 + 文档警告」（adk 的 unsafe_local_code_executor 命名式警告）形成代际差。
6. **凭据托管是生态分层的清晰指标**：adk-python（OAuth2 流程全家桶）> Dify（加密存储 + 权限策略）> crewai（Fernet token）> 其余零抽象——凡是有「平台」野心的都做了凭据体系，纯库框架一致地留给环境变量；唯一例外是 MS，凭据在 Foundry 生态而非 core，与其「app-owned + Azure 托管」的分层哲学一致。
