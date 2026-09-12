# 维度 5：工具系统与 MCP

> 本维度回答：框架如何定义工具（注册与 Schema 生成）、如何治理执行（校验、超时、重试、沙箱、结果截断、错误回喂 LLM）、以及 MCP（Model Context Protocol）支持做到多深（client/server 双角色、传输层、tool 过滤、elicitation、凭据托管）。总体格局：**17 家全部 ✅**——工具是一等公民没有争议；但「产品级治理深度」差异巨大：openai-agents/agentscope/deepagents/claude-sdk 把超时/截断/沙箱做全，而 langgraph/langgraph4j/spring-ai/llama_index 只做「调用与回填」，超时与截断普遍缺位。MCP 已成标配（16/17 直连或生态可达），但 elicitation 只有 4 家支持。

## 5.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| openai-agents-python | ✅ | strict schema + 工具级超时（2 策略）+ 工具护栏 + 托管工具组 + MCP 三传输/tool_filter/Manager + 7 厂商沙箱 + tool_search 渐进披露 | src/agents/tool.py#function_tool；tool.py#_invoke_function_tool_with_metadata(:2211)；mcp/util.py#ToolFilterStatic；sandbox/ |
| agent-framework | ✅ | @tool schema 推断 + approval_mode 审批 + 调用预算（次数/时长）+ MCP 客户端在 core（审批/体积预算/OTel）+ hosting-mcp 服务端 + hyperlight 沙箱 | python/packages/core/agent_framework/_tools.py#tool(:1231)；_mcp.py#_EncodedSizeBudget(:241)；packages/hosting-mcp/ |
| adk-python | ✅ | Gemini AFC 函数工具 + Toolset 谓词过滤 + MCP 双向（消费+agent 反向成 server）+ OpenAPI/auth 全套 + 7 代码执行器 | tools/function_tool.py#FunctionTool(:93)；mcp_tool/_agent_to_mcp.py#to_mcp_server(:170)；auth/（AuthCredential+CredentialService） |
| adk-java | ✅ | 反射 FunctionTool（@Annotations.Schema）+ requireConfirmation 内置审批 + MCP 三传输消费 + GCP 工具族 + 3 代码执行器；无 auth 包、无通用 OpenAPI | core/.../tools/FunctionTool.java#create；tools/mcp/McpToolset.java(:72/:214)；tools/applicationintegrationtoolset/ |
| langchain | ✅ | BaseTool/@tool/InjectedToolArg 在 core + MCPAdapter（fastmcp，elicitation→interrupt）+ ShellToolMiddleware 三沙箱策略 + 工具选择中间件 | libs/core/langchain_core/tools/base.py#BaseTool；libs/langchain_v1/langchain/mcp/adapter.py#MCPAdapter、elicitation.py；agents/middleware/_execution.py#DockerExecutionPolicy(:267) |
| langgraph | ✅ | ToolNode（Send 并行/错误处理/Command 返回/注入原语）+ ValidationNode 参数校验；schema 定义与 MCP 在另仓 | libs/prebuilt/langgraph/prebuilt/tool_node.py#ToolNode(:622/:821 executor.map)；tool_validator.py#ValidationNode |
| langgraph4j | ✅ | 工具即图节点：LC4jToolService 执行、MCP 客户端可注册进 builder、AgentEx 按工具名分发独立节点 + 逐工具审批；无沙箱/超时/凭据 | langchain4j/langchain4j-core/.../LC4jToolMapBuilder.java#tool(McpClient)(:100)；AgentExecutor.java#executeTool(:113) |
| langchain4j | ✅ | @Tool/@P + ToolSpecification + ToolProvider 动态供工具 + 循环护栏（100 轮/并发执行/幻觉工具名策略）+ 补偿事务 + MCP 三传输（含 websocket）+ GraalVM 沙箱；工具执行无统一 timeout | langchain4j/src/main/java/dev/langchain4j/service/tool/ToolService.java(:133/:386/:774)；langchain4j-mcp/（transport/client/）；code-execution-engines/ |
| deepagents | ✅ | 8 文件工具 + execute + task 走单一 BackendProtocol；超时/截断/分页/schema 内建；MCP 不在核心（langchain MCPAdapter 可组合） | libs/deepagents/deepagents/middleware/filesystem.py:1859-1872（工厂表）；backends/sandbox.py#execute_with_offload(:1464) |
| claude-agent-sdk-python | ✅ | CLI 内置工具集 + 细粒度 allow/deny 规则文法（`Bash(ls:*)`）+ MCP 四种输入形态（stdio/sse/http/**进程内 sdk**）+ SandboxSettings + maxResultSizeChars 截断 | src/claude_agent_sdk/types.py#McpServerConfig(:649)；_internal/sdk_mcp_bridge.py#SdkMcpBridge；__init__.py#create_sdk_mcp_server(:491) |
| crewai | ✅ | BaseTool/@tool + 结构化失败策略（fail/raise/retry/ignore）+ MCP 内置主包（60s 超时+指数退避重试+名单过滤）；普通工具无核心超时 | lib/crewai/src/crewai/tools/base_tool.py#BaseTool(:103)；tool_failure.py#ToolFailurePolicy(:57)；mcp/client.py#MCPClient(:67)；tools/mcp_tool_wrapper.py(:11) |
| dify | ✅ | 六类工具源（builtin/api/mcp/plugin/workflow_as_tool/dataset）+ 独立沙箱服务 + 凭据权限管理；工具超时在 plugin_daemon 协议侧 | api/core/tools/tool_engine.py#ToolEngine；core/mcp/（client+server+auth）；models/credential_permission.py#CredentialPermission |
| llama_index | ✅ | BaseTool/FunctionTool 自动 schema + ObjectRetriever 检索式工具选择 + 工具输出 is_error 容错；MCP 在集成包层；无沙箱/超时/截断 | llama-index-core/llama_index/core/tools/function_tool.py#FunctionTool(:71)；objects/base.py#ObjectRetriever(:25)；integrations/tools/llama-index-tools-mcp/.../client.py#BasicMCPClient(:98) |
| agentscope | ✅ | Toolkit 唯一工具源 + 分组激活 + 中间件洋葱链 + 声明式元数据（read_only/concurrency_safe）+ Bash 120/600s + MCP 三传输 + 8 种 workspace 沙箱 | src/agentscope/tool/_toolkit.py#Toolkit(:66)；tool/_base.py#ToolBase(:99)；workspace/（8 实现） |
| agentscope-java | ✅ | @Tool/@ToolParam 注解 schema + 元工具自管分组 + dangerousFiles 元数据 + 5min 默认超时/重试 + MCP 三传输（含 elicitation）+ 4 沙箱后端 | agentscope-core/.../tool/Toolkit.java(:66)；ToolkitConfig.java(:30)；tool/mcp/McpClientBuilder.java#asyncElicitation |
| spring-ai | ✅ | @Tool→ToolCallback SPI + ToolCallingAdvisor 循环 + 调用预算（40/工具/150 全局）+ 异常转文本回喂 + MCP 双端注解（@McpTool/@McpElicitation）+ ToolSearchTool；无沙箱/超时/截断 | spring-ai-model/.../model/tool/DefaultToolCallingManager.java(:100/:107)；mcp/mcp-annotations/.../McpTool.java；advisors/ |
| spring-ai-alibaba | ✅ | Spring AI ToolCallback 之上加 Async/StateAware/Cancellable+取消令牌 + MCP 三路（直连/Nacos 网关/沙箱内）+ toolerror/toolretry/toolemulator 拦截器 | .../agent/tool/CancellableAsyncToolCallback.java；starter-builtin-nodes/.../McpNode.java；interceptor/{toolerror,toolretry,toolemulator} |

## 5.2 实现方式深析

### A. 注册与 Schema 生成：三种语言惯用形

- **Python inspect/docstring 派**（langchain、langgraph 依赖、agent-framework、adk-python、openai-agents、crewai、llama_index、agentscope）：`@tool`/`@function_tool`/`FunctionTool.from_defaults` 解析函数签名+docstring 生成 JSON Schema。openai-agents 最严格：griffe 解析 + 默认强制 `ensure_strict_json_schema`（OpenAI strict mode），2.0 还加了 `output_type` 双向 schema（`_build_function_tool_output_type`，tool.py:2270 附近）。crewai 走 Pydantic args schema。adk-python 靠 Gemini AFC（Automatic Function Calling）自动执行。
- **Java 反射注解派**：langchain4j `@Tool`/`@P`、spring-ai `@Tool`/`@ToolParam`、adk-java `@Annotations.Schema(name/description/optional)`、agentscope-java `@Tool`/`@ToolParam` + ReflectiveFunctionTool。全都是 Method→ToolSpecification/ToolDefinition 的反射映射，风格高度趋同。
- **TypeDict 直写派**（claude-sdk）：进程内 MCP server 的 `@tool` 装饰器用 TypedDict→JSON Schema 自动推导（__init__.py:338-430），配 jsonschema 运行时校验——因为要跨 JSON-RPC 边界，schema 必须显式可序列化。

### B. 执行治理五件套对比（校验 / 超时 / 重试 / 截断 / 错误回喂）

**参数校验**：langgraph `ValidationNode`（调工具前独立校验参数，tool_validator.py:47）；claude-sdk `create_sdk_mcp_server` jsonschema 校验；openai-agents strict schema + ToolInputGuardrail（`reject_content`/`raise_exception` 三态，tool_guardrails.py:40-116——工具护栏是 17 家独一份）。

**超时**（二次核验后修正档案细节）：
- openai-agents：`timeout_seconds` + `timeout_behavior: Literal["error_as_result","raise_exception"]`（**2 策略而非档案所记 3 策略**）+ 可选 `timeout_error_function` 自定义超时文案；实现为 `asyncio.wait_for` 包工具任务（tool.py:2211 `_invoke_function_tool_with_metadata`，超时后若任务实为异常则优先抛原异常）。
- agentscope：Bash timeout 默认 120s、上限 600s（_builtin/_bash.py:685-699）。agentscope-java：`ToolkitConfig` 内嵌 ExecutionConfig，默认 5 分钟超时、无重试（ToolkitConfig.java:30 javadoc 明示）。
- crewai：仅 MCP 工具有 `MCP_TOOL_EXECUTION_TIMEOUT=60` + 指数退避重试（mcp_tool_wrapper.py:11/:87）；**普通工具无核心超时**（二次核验 tool_usage.py 零命中确认）。
- deepagents：execute 有超时参数 + `max_execute_timeout=3600` 上限 + GLOB_TIMEOUT + 专用线程池并发上限。
- **缺位**：langchain、langgraph、langchain4j（service/tool 包 grep timeout 零命中）、spring-ai（spring-ai-model tool 包零命中）、llama_index、dify（api 侧零命中，超时在 plugin_daemon 协议侧）——五家同为「无统一工具超时」。

**重试**：crewai（MCP 指数退避）、agentscope-java（ExecutionConfig 可配）、langchain4j（节点级 RetryPolicy 经 langgraph4j；工具本身无）、spring-ai-alibaba（toolretry 拦截器）、deepagents talon `_retry_delay`（外部调用侧）。

**结果截断（防 context 爆炸）**——分化最明显：
- deepagents 最体系化：grep 默认 max_count=1000、read 二进制类型识别/行分页/中段截断、大输出 `execute_with_offload` 卸载到文件。
- claude-sdk：`ToolAnnotations.maxResultSizeChars` 经 `_meta` 传给 CLI 作内联阈值（__init__.py#_build_meta）——工具可自报结果体积上限。
- agent-framework：`_EncodedSizeBudget`（_mcp.py:241）**深度遍历 JSON 逐字符计费**（转义按 2-6 字节），超限即抛——这是防 DoS 级实现而非仅防 context 爆炸。
- spring-ai/openai-agents/crewai/langchain：无截断（超长结果直接回喂）。

**错误回喂 LLM**：几乎是共识——openai-agents `failure_error_function`（异常转消息）、spring-ai `ToolExecutionExceptionProcessor`（异常转文本）、langgraph `handle_tool_errors`（默认把异常装进 ToolMessage 回给模型，tool_node.py:383-394）、crewai `ToolFailurePolicy`（fail/raise/retry/ignore 语义 + 失败记录聚合 collect_tool_failures:237，结构化程度最高）、llama_index `ToolOutput.is_error/exception`（types.py:106）、langchain4j `hallucinatedToolNameStrategy`（模型幻觉出不存在的工具名时的策略，:774）。

### C. 执行沙箱：四个梯队

1. **多厂商矩阵**：openai-agents（核心 sandbox/——manifest/挂载物化/快照/rclone 同步/归档限额 + extensions 七厂商 E2B/Daytona/Modal/Runloop/Vercel/Cloudflare/Blaxel + SandboxAgent）；agentscope（workspace 8 实现：Local/bubblewrap/docker/e2b/daytona/k8s/opensandbox/applecontainer，沙箱内经 MCP gateway 执行，workspace 兼任上下文 offloader）。
2. **独立服务**：dify（langgenius/dify-sandbox:0.2.15 独立容器，CodeExecutor POST /v1/sandbox/run；agent_v2 另有 Go PTY 运行时）。
3. **单容器/单引擎**：langchain（ShellToolMiddleware 三策略 Host/CodexSandbox/Docker，_execution.py:92/:191/:267）；adk-python 7 executor / adk-java 3 executor（BuiltIn/Container(docker-java)/VertexAi）；agentscope-java（harness docker + agentrun/daytona/e2b/k8s 扩展 + `JdbcSandboxExecutionGuard` DB 锁防多节点并发同沙箱）；langchain4j（GraalVM `GraalVmPythonExecutionEngine` 显式 `.sandbox(TRUSTED)`+`HostAccess.UNTRUSTED`——JVM 内隔离 + Judge0/ACADS 远程）；spring-ai-alibaba（Docker/LocalCommandline executor）；deepagents（SandboxBackendProtocol 抽象，实现由 backend 决定）。
4. **委派外部**：claude-sdk（SandboxSettings 网络 allowlist/excludedCommands 合并进 CLI --settings，实际沙箱在 CLI 进程侧【文档】）；❌：langgraph、langgraph4j、llama_index、crewai（e2b/daytona 在 crewai-tools 独立包）、spring-ai、agent-framework（hyperlight beta 生态包）。

### D. MCP 支持深度（重点核验项）

**client/server 双角色**：双角色 6 家——adk-python（McpToolset 消费 + `_agent_to_mcp.py#to_mcp_server` 把 agent 变 MCP server，transport 由调用方选 stdio/streamable-http）、agent-framework（core `_mcp.py` 客户端 + packages/hosting-mcp 服务端（alpha））、spring-ai（client Sync/Async ToolCallback + server `@McpTool/@McpPrompt/@McpResource` 注解，webmvc/webflux 双传输 + stateless customizer）、dify（core/mcp/ client+server+auth+session）、agentscope-java（McpClientManager 消费 + harness McpServerRegistrar 注册服务端）、claude-sdk（消费四形态 + 进程内 `sdk` server 本身就是「把 SDK 用户代码变成 CLI 可见的 MCP server」）。纯 client：langchain（MCPAdapter 基于 fastmcp Client/ClientGroup）、openai-agents、crewai、adk-java（无反向暴露——跨语言缺口）、langchain4j、agentscope、llama_index（集成包）、langgraph（另仓 langchain-mcp-adapters）、spring-ai-alibaba（三路消费）。核心零 MCP：deepagents（可组合 langchain MCPAdapter；产品级 OAuth/审批在 dcode/talon 外围）。

**传输层**：stdio+SSE+streamable-http 三件套是 2026 年事实标准（openai-agents mcp/server.py:1888/:2030/:2200、adk-python McpToolset、adk-java、agentscope、agentscope-java、crewai transports/{stdio,sse,http}.py）。特色：**langchain4j 独有 websocket 传输**（client/transport/websocket/WebSocketMcpTransport）+ registryclient + `langchain4j-mcp-docker` 容器化拉起 server + resources-as-tools；**dify 客户端只做 HTTP 系**（streamablehttp_client + sse_client 按 URL 路径协商，api 侧无 stdio——stdio 型 server 在 plugin-daemon 进程侧）；claude-sdk 第四形态 `sdk`（SdkMcpBridge 用 mcp 官方内存 transport 桥接，兼容 mcp 1.x/2.x）+ `claudeai-proxy`（仅出现在 status 输出的只读形态，二次核验 types.py:678-681）。

**tool 过滤**：openai-agents `tool_filter` 双形态——静态 `ToolFilterStatic{allowed_tool_names, blocked_tool_names}` 或动态 callable（含 ToolFilterContext：run_context/agent/server_name，util.py:94-140，可按会话/按 agent 运行时筛）；crewai `allowed_tool_names`；spring-ai `McpToolFilter` + `McpToolsChangedEvent` 热更新（server 端工具列表变更后客户端工具集自动刷新）；adk-python ToolPredicate 谓词按 agent/run 过滤（base_toolset.py:44）；agentscope ToolGroup 分组按 session 激活；langgraph4j AgentEx 按工具名编译成独立分发节点。

**elicitation（MCP server 向客户端请求补充输入，2025 新协议能力）——二次核验矩阵**：
- **langchain：最深度集成**。`mcp/elicitation.py` 把 server 的 `elicitation/create` 请求转成 `langgraph.types.interrupt`（人在环回答），模块 docstring 详述为何自驱循环而非用 SDK 的 run_input_required_driver（LangGraph interrupt 按序匹配、FastMCP 会吞 GraphInterrupt）；显式只答 elicitation，sampling/roots 拒绝。
- **adk-python**：`SessionContext(elicitation_callback=…, sampling_callback=…)`（session_context.py:122-152）传入 ClientSession——回调式，未绑 HITL。
- **agentscope-java**：`McpClientBuilder.asyncElicitation(handler)`（注册后自动启用 client capability，返回 Mono）。
- **spring-ai**：`@McpElicitation` 注解（client 侧处理 server 的 elicitation 请求，方法返回 ElicitResult/Mono——注解式，最 Spring 风格；另有 server 侧 @McpSampling）。
- **不支持（核验为零命中或显式拒绝）**：openai-agents、langchain4j、crewai、dify、llama_index、agentscope(Python)（Java 有 Python 无——跨语言缺口）、adk-java、langgraph4j、spring-ai-alibaba、agent-framework、deepagents(核心)；**claude-sdk 显式拒绝**：SdkMcpBridge 对 server→client 请求（roots/sampling/elicitation）一律回 `method not found`（sdk_mcp_bridge.py:110/:221、types.py:637-641 docstring 自述）。

**凭据托管（auth credential 体系）**：adk-python 独一档——`auth/` 全套（AuthCredential 四模型 Http/OAuth2/ServiceAccount/Inference、exchanger/refresher、`BaseCredentialService` 两种实现 in_memory/session_state、`authenticated_function_tool` 包装器、工具内 `request_credential`（agents/context.py:659））；adk-java **无 auth 包**（仅 ApplicationIntegration 的 GCP Connections 凭据 helper——跨语言最大缺口之一）；dify 平台级（CredentialPermission 表 + credential_permission_service + 工具 OAuth 客户端）；crewai 轻量（`EnvVar` 在工具上声明式声明所需环境变量）；openai-agents 沙箱 providers + ToolContext 携带审批信息；其余（langchain/langgraph/langchain4j/spring-ai/llama_index/agentscope）无凭据抽象。

### E. 工具规模化管理：渐进披露的工具版

openai-agents `tool_search`（tool.py:1613）——工具太多时模型用自然语言搜索按需发现；spring-ai `ToolSearchTool` + `ToolSearchToolCallingAdvisor`（工具清单建向量索引，LRU/TTL 淘汰，工具集指纹变更才重建）；llama_index `ObjectRetriever` 泛型协议（agent/workflow/base_agent.py:105 `tool_retriever` 运行时 aretrieve 动态附加）；langchain `LLMToolSelectorMiddleware`/`ProviderToolSearchMiddleware`/`LLMToolEmulator`；adk-python `before_agent_callback` 谓词。这是「工具面自身也 RAG 化」的共同趋势。

## 5.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | ToolNode：Send 并行分发（:293）、executor.map/asyncio.gather、Command 返回、InjectedState/Store/ToolRuntime、ValidationNode | AgentEx 每工具编译成独立分发节点 + LC4jToolService#execute + `ApprovalNodeAction` 逐工具审批（APPROVAL_RESULT channel） | **机制对齐**：并行执行/动态工具返回/注入语义等价；Java 多预制审批、Python 多 ValidationNode；**两侧同缺**沙箱/超时/截断/凭据 |
| adk-python(2.9) ↔ adk-java(1.9) | AFC FunctionTool + Toolset 谓词 + **MCP 双向**（_agent_to_mcp 反向暴露）+ **通用 OpenAPI 工具 + auth/ 全套凭据** + 7 executor | 反射 FunctionTool + requireConfirmation 内置 + MCP 仅消费三传输 + 仅 GCP ApplicationIntegrationToolset（OpenAPI 专属）+ 无 auth 包 + 3 executor | Python 超出：反向 MCP、通用 OpenAPI、凭据体系、executor 数；Java 独有：`LongRunningFunctionTool`+`SetModelResponseTool`（动态换模型）、审批布尔参数直进 FunctionTool 构造器 |
| agentscope ↔ agentscope-java | Toolkit docstring→schema + ToolGroup + 中间件洋葱链 + Bash 120/600s + MCP（stdio/SSE/streamable-http，`mcp<2.0.0` 钉版本，运行时 header 注入 :260）+ workspace 8 沙箱 | @Tool 注解→schema + ToolGroupManager + **元工具**（reset_equipped_tools 模型自管分组）+ dangerousFiles/dangerousDirectories 元数据直喂权限引擎 + 5min 默认超时 + MCP 三传输 + **asyncElicitation** + docker/agentrun/e2b/k8s 沙箱 | Python 独有：中间件洋葱链、8 种 workspace、header 运行时注入；Java 独有：元工具、危险路径元数据、elicitation、JdbcSandboxExecutionGuard；对齐：分组激活、MCP 三传输、内置文件/编码工具族同构 |

## 5.4 取舍与趋势

1. **「错误回喂」已成共识，「超时/截断」仍是半数缺口**：异常转文本回喂模型（让模型自我纠正）在 7+ 家是默认行为；但统一工具超时仅 openai-agents/agentscope/agentscope-java/crewai(仅 MCP)/deepagents 有，langchain/langgraph/langchain4j/spring-ai/llama_index 五个主流框架同为零——治理深度与框架成熟度不成正比，与「agent 产品化」程度成正比（openai-agents/claude-sdk/agentscope 这批带产品背景的最全）。
2. **MCP 是 16/17 的标配，但分层清晰**：核心内置（langchain/adk 双语/agentscope 双语/openai-agents/crewai/spring-ai/dify/claude-sdk/agent-framework）> 模块级（langchain4j-mcp、spring-ai-alibaba 三路）> 生态包（llama_index、langgraph 另仓）> 无（deepagents 核心）。stdio+SSE+streamable-http 三传输是基线，langchain4j 的 websocket 是孤例，dify 的「HTTP-only api + stdio 归 plugin-daemon」是平台分工式解法。
3. **elicitation 只有 4 家（langchain/adk-python/agentscope-java/spring-ai），且集成深度差三个量级**：langchain 做到 HITL 级（interrupt 人在环回答）、spring-ai 做到注解级、adk-python/agentscope-java 停在回调参数级；claude-sdk 的进程内桥显式拒绝。MCP 客户端能力面（elicitation/sampling/roots）整体还处于早期采纳曲线。
4. **沙箱向「多厂商矩阵 + 独立服务」演进**：openai-agents（7 厂商）与 agentscope（8 workspace）把沙箱做成可插拔后端矩阵；dify 用独立容器服务隔离执行面与控制面；而传统框架（langgraph/spring-ai/llama_index）沙箱缺位，由 langchain 的三策略 ExecutionPolicy 这类「最近补丁」补课。
5. **凭据托管基本是 Google 的私产**：adk-python 的 auth/ 体系（credential service + request_credential + authenticated_function_tool）17 家唯一完整实现，adk-java 甚至都没跟上；dify 用平台数据库（CredentialPermission）解决同一问题——「库框架 vs 平台」在凭据这个点上分野最清楚。
6. **工具面自身的渐进披露兴起**：openai-agents tool_search、spring-ai ToolSearchTool（向量索引 + 指纹缓存）、llama_index ObjectRetriever、langchain 工具选择中间件——当工具数超过 prompt 预算，「工具即语料、按需检索」成为共同解法，与维度 6 的 skill 渐进披露同构。
