# deepagents 框架档案

> 基线：~/develop/opensource/deepagents @ 9e7d62ff6 2026-09-11；版本 deepagents 0.7.13（`libs/deepagents/pyproject.toml`；monorepo 其余包：deepagents-code 0.1.68 / acp 0.0.11 / talon 0.0.8 / evals 0.0.1）

## 1. 定位

deepagents 是 LangChain 官方的「生产就绪 agent harness」：不引入新运行时，而是在 langchain `create_agent()`（其下是 langgraph）之上组装一套面向长程任务的固定中间件栈（planning 式规划已弱化、虚拟文件系统、子代理、摘要压缩、skills、memory、权限、prompt cache），并配 pluggable backends 决定文件与执行落在哪里。它对应 Anthropic「deep agents」理念的可复用 SDK 实现——文件即状态、上下文工程优先、子代理隔离委派、渐进式披露——但当前版本已把 write_todos 规划工具从默认栈移除（见 §5 维度 7）。目标用户是想直接获得 Claude Code 式 agent 能力而不自己搭栈的开发者；同仓 monorepo 另交付终端编码 agent（dcode）、编辑器 ACP 接入（Zed）、实验性消息通道运行时（talon）。定位证据【核心】：`libs/deepagents/deepagents/graph.py#create_deep_agent` 仅做装配后委托 `langchain.agents.create_agent`；`libs/ARCHITECTURE.md`「three layers」明确 harness / agent abstraction / runtime 分层。

## 2. 仓库结构与核心包

monorepo，`libs/` 下各包独立版本（`libs/README.md`）：

| 包 | 路径 | 版本 | 说明 |
|---|---|---|---|
| deepagents（核心 SDK） | `libs/deepagents/` | 0.7.13 | `create_deep_agent` + middleware + backends + profiles |
| deepagents-code | `libs/code/` | 0.1.68 | dcode：终端编码 agent（Textual TUI、远端沙箱、MCP、headless） |
| deepagents-acp | `libs/acp/` | 0.0.11 | Agent Client Protocol server（Zed 等编辑器） |
| deepagents-talon | `libs/talon/` | 0.0.8 | **实验性**（README 自标 alpha）本地运行时 host：whatsapp/telegram/discord 通道适配、cron 调度、历史归档检索 |
| deepagents-evals | `libs/evals/` | 0.0.1 | Harbor 基准集成 + 雷达图脚本 |
| partners | `libs/partners/{daytona,modal,quickjs,runloop,vercel}` | 各自 pyproject | 沙箱/REPL 集成（QuickJS 为 JS REPL 中间件） |

核心包源码布局（`libs/deepagents/deepagents/`，约 2.7 万行）：`graph.py`（978 行，装配入口）、`middleware/`（13 个模块）、`backends/`（10 个模块）、`profiles/`（harness + provider 双注册表）、`_messages_reducer.py` 等。

依赖证据（`libs/deepagents/pyproject.toml`）：`langchain>=1.4.0,<2.0.0`、`langchain-core>=1.6.2`、`langchain-anthropic>=1.7.2`、`langchain-google-genai>=4.4.0`、`langsmith>=0.12.4`、`wcmatch>=11.0`；extras：`aws`（Bedrock prompt cache）/`quickjs`/`video`（PyAV 视频帧）。注意：pyproject **未直接声明 langgraph**，但代码直接 import（`graph.py:26-31` 的 `langgraph.channels.delta.DeltaChannel`、`langgraph.types.Checkpointer` 等）——langgraph 经 langchain 传递依赖，属隐式强耦合。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `create_deep_agent` | `libs/deepagents/deepagents/graph.py:271` | 装配入口：模型/profile 解析→中间件栈组装→委托 langchain `create_agent`，`recursion_limit=9_999` |
| `DeepAgentState` | `libs/deepagents/deepagents/graph.py:73` | AgentState + messages 上挂 `DeltaChannel` 增量 reducer，checkpoint 增长 O(N²)→O(N) |
| `FilesystemMiddleware` | `libs/deepagents/deepagents/middleware/filesystem.py:1681` | 注入 ls/read_file/write_file/edit_file/delete/glob/grep/execute 8 工具 + 权限执行 + 大结果驱逐 |
| `FilesystemPermission` | `libs/deepagents/deepagents/middleware/filesystem.py:387` | allow/deny/interrupt 三态路径规则，声明序首匹配 |
| `BackendProtocol` / `SandboxBackendProtocol` | `libs/deepagents/deepagents/backends/protocol.py:404/870` | 文件存储单协议（9 组 sync+async 操作）；后者加 `execute`/`execute_with_offload` |
| `StateBackend` | `libs/deepagents/deepagents/backends/state.py:38` | 文件存图 state 的 `files` channel（DeltaChannel reducer，thread 内持久） |
| `BaseSandbox` | `libs/deepagents/deepagents/backends/sandbox.py:1411` | 只需实现 `execute`（+上传）即派生全部文件操作的沙箱基类（shell 即文件系统） |
| `CompositeBackend` | `libs/deepagents/deepagents/backends/composite.py:228` | 按路径前缀把虚拟 FS 路由到多 backend（如 `/memories/`→Store） |
| `SubAgentMiddleware` / `SubAgent` / `CompiledSubAgent` | `libs/deepagents/deepagents/middleware/subagents.py:842/66/220` | 子代理包成 `task` 工具；声明式/预编译两类规格 + fork 模式 |
| `GENERAL_PURPOSE_SUBAGENT` | `libs/deepagents/deepagents/middleware/subagents.py:456` | 默认自动注入的 general-purpose 子代理（Claude Code 风格描述） |
| `AsyncSubAgentMiddleware` | `libs/deepagents/deepagents/middleware/async_subagents.py` | 经 langgraph_sdk 连远端 Agent Protocol server 的后台子代理（launch/check/update/cancel/list 工具） |
| `_DeepAgentsSummarizationMiddleware` / `create_summarization_middleware` | `libs/deepagents/deepagents/middleware/summarization.py:523/1757` | 增强版摘要：历史 offload 到文件、非破坏性 state、overflow 兜底重试 |
| `SummarizationToolMiddleware` | `libs/deepagents/deepagents/middleware/summarization.py:1924` | `compact_conversation` 工具，agent/人可主动压缩（与自动层共享 `_summarization_event`） |
| `SkillsMiddleware` | `libs/deepagents/deepagents/middleware/skills.py:766` | Anthropic Agent Skills 规范：SKILL.md 索引进 prompt、全文按需 read_file（渐进披露） |
| `MemoryMiddleware` | `libs/deepagents/deepagents/middleware/memory.py:88` | AGENTS.md 规范记忆注入 system prompt，含注入防御提示词 |
| `RubricMiddleware` | `libs/deepagents/deepagents/middleware/rubric.py` | 「完成度 rubric」自评：无工具调用即结束前由 grader 子代理复审，不满足则注入反馈续跑 |
| `HarnessProfile` / `ProviderProfile` | `libs/deepagents/deepagents/profiles/harness/harness_profiles.py`、`profiles/provider/provider_profiles.py` | 按 provider/model 双注册表调优 harness（prompt 后缀/工具增删/中间件注入），支持 entry-point 插件 |
| `_messages_delta_reducer` | `libs/deepagents/deepagents/_messages_reducer.py:31` | 自 langgraph PR#7729 改造的批量消息增量 reducer（去重/tombstone/全清） |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅（接入面继承 langchain，自研 profile 层） | 任意 langchain provider 经 `init_chat_model` 接入；ProviderProfile 注入归因头/Responses API 默认，HarnessProfile 按模型调栈 | `libs/deepagents/deepagents/_models.py#resolve_model`；`libs/deepagents/deepagents/profiles/provider/_openrouter.py` |
| 2 | 上下文工程 | ✅ | 五层防线：工具结果驱逐→旧 tool-arg 截断→摘要化+历史 offload 到文件→ContextOverflow 兜底 clipping→prompt cache 断点 | `libs/deepagents/deepagents/middleware/summarization.py:262`；`libs/deepagents/deepagents/middleware/filesystem.py:1754` |
| 3 | 记忆 | ✅（文件式） | AGENTS.md 记忆进 system prompt + edit_file 自学习；跨线程靠 StoreBackend 路由；DB/向量记忆在实验包 talon | `libs/deepagents/deepagents/middleware/memory.py#MemoryMiddleware`；`libs/deepagents/deepagents/backends/store.py#StoreBackend` |
| 4 | RAG | 🔶 | 核心无 retriever/vector store/rerank 抽象，检索=grep/glob agentic 路径；talon 实验包有 hybrid 归档检索（Voyage 向量+langgraph BaseStore） | `libs/deepagents/deepagents/backends/protocol.py:499`；`libs/talon/deepagents_talon/history_vectors.py:1` |
| 5 | 工具系统 | ✅ | 8 个内置文件工具+execute+task 走单协议 backend；超时/截断/分页/schema 内建；MCP 不在核心（dcode/talon+langchain MCPAdapter 组合） | `libs/deepagents/deepagents/middleware/filesystem.py:1859`；`libs/deepagents/deepagents/backends/protocol.py:404` |
| 6 | Skill 机制 | ✅ | Anthropic Agent Skills 规范完整实现：frontmatter 索引进 prompt、全文按需 `read_file`（渐进披露）、多源分层、entry-point 插件 | `libs/deepagents/deepagents/middleware/skills.py:735`（SKILLS_SYSTEM_PROMPT 渐进披露四步） |
| 7 | 规划推理 | 🔶 | `write_todos` 已移出默认栈、仅 Codex profile 注入；rubric 自评循环与 structured output 透传是仅有形式 | `libs/deepagents/deepagents/profiles/harness/_openai_codex.py:74`（"SDK no longer provides it by default"）；`libs/deepagents/deepagents/middleware/rubric.py#RubricMiddleware` |
| 8 | 编排 | 🟡（继承 langgraph，版本依赖 langchain>=1.4） | 不提供图 builder，返回 `CompiledStateGraph`；自有贡献=中间件栈装配+子图嵌套+远端 Agent Protocol 委派 | `libs/deepagents/deepagents/graph.py:956`；`libs/deepagents/deepagents/middleware/subagents.py:640` |
| 9 | 多 Agent | ✅ | `task` 工具三类子代理（声明式/预编译/远端异步）+ 默认 GP 子代理 + fork 继承父对话 + 状态白名单回传 | `libs/deepagents/deepagents/middleware/subagents.py:577`（`_build_task_tool`）、`:687` |
| 10 | 持久化 | ✅（checkpoint 继承 langgraph，backend 层自研） | checkpointer/store 参数透传；backends 家族（State/Filesystem/Store/Composite/沙箱×6）+ DeltaChannel 控 checkpoint 膨胀 | `libs/deepagents/deepagents/graph.py:286`；`libs/deepagents/deepagents/backends/state.py:38` |
| 11 | HITL | ✅（引擎继承 langchain HITL，路径谓词合成自研） | `interrupt_on` 透传 + permissions=interrupt 自动合成 when 谓词，防 path="."/glob pattern 绕过；决策集 approve/edit/reject/respond | `libs/deepagents/deepagents/middleware/_fs_interrupt.py:156`；`libs/deepagents/tests/integration_tests/test_hitl.py` |
| 12 | 观测评估 | 🟡 | tracing 继承 LangSmith callback（`ls_integration="deepagents"` 元数据）；全中间件 `TracePolicy` 默认脱敏；evals 独立包（Harbor） | `libs/deepagents/deepagents/graph.py:972`；`libs/deepagents/deepagents/middleware/filesystem.py:1743`；`libs/evals/` |
| 13 | 安全治理 | ✅（权限治理；PII/guardrail 需 langchain 组合） | FilesystemPermission 三态首匹配+路径校验（禁 `..`/`~`）+bulk 结果过滤+递归删除 fail-closed；execute+权限组合显式 NotImplementedError | `libs/deepagents/deepagents/middleware/filesystem.py:423`；`:1821`；`libs/deepagents/deepagents/graph.py:241` |
| 14 | 部署运行时 | 🟡 | 核心纯库；外围包覆盖 ACP server（Zed）/终端 TUI+headless（dcode）/消息通道+cron+后台任务（talon 实验） | `libs/acp/deepagents_acp/server.py`；`libs/talon/deepagents_talon/{channels,cron}/` |
| 15 | 管理平面 | 🔶 | 无 console/tenant/billing；talon 实验包有 authorization/tool_approvals/fleet_import 雏形（自标 alpha、不收安全报告） | `libs/talon/deepagents_talon/authorization.py`；`libs/talon/README.md`（experimental 声明） |

## 5. 维度证据明细

### 维度 1 模型接入
- `resolve_model`（`libs/deepagents/deepagents/_models.py:35`）：字符串经 langchain `init_chat_model(model, **apply_provider_profile(model))` 解析，实例直通——provider 面完全继承 langchain（集成点）。【核心】
- ProviderProfile 注册表（`libs/deepagents/deepagents/profiles/provider/{_nvidia,_openai,_openrouter}.py`）：NVIDIA NIM / OpenRouter 归因头、OpenAI 默认走 Responses API（数据保留指引见 `graph.py:323-333` docstring）。【核心】
- 默认模型 `ChatAnthropic(model_name="claude-sonnet-4-6")`（`graph.py:143-151`），`model=None` 已弃用（0.5.3 起，1.0.0 移除）——收敛到显式传模型。【核心】
- HarnessProfile 内置 5 组：anthropic opus-4-7/sonnet-4-6/haiku-4-5、nvidia nemotron-3-ultra（1848 行 prompt 工程）、openai codex（`profiles/harness/`）。【核心】
- retry/fallback/cache 不在默认栈（langchain 的 ModelRetry/ModelFallback 可经 `middleware=[]` 组合）；流式经 langgraph（`tests/unit_tests/test_deep_agent_streaming.py`）。dcode 另有 `CodeModelRetryMiddleware`、`CostTrackingMiddleware`【外围包】。
- 证据等级：接入机制【核心】+ 继承标注；dcode 部分【示例/外围】。

### 维度 2 上下文工程（本框架最强维度）
- **大结果驱逐**：工具结果 >20k tokens、HumanMessage >50k 即写入 `/large_tool_results/{tool_call_id}`，原位替换为 head+tail 预览 + read_file 指引（`middleware/filesystem.py:1754-1757`、`middleware/_message_eviction.py:25 TOO_LARGE_TOOL_MSG`）。【核心】
- **摘要化增强**：`create_summarization_middleware` 默认 trigger=fraction 0.85 / keep=0.10（有 profile 时），无 profile 回退 tokens 170k/messages 6（`middleware/summarization.py:262`）；被逐出的历史完整 offload 到 `/conversation_history/{session_id}.md` 而非丢弃，摘要内嵌回读路径（:1757 docstring 对比 langchain 版「drops evicted messages with no recovery path」）。【核心】
- **非破坏性**：摘要事件存私有 `_summarization_event` 字段，`state["messages"]` 原始日志不动（支持 replay/evals 与 compact 工具共享，:1787-1792）。【核心】
- **预处理链**：旧消息 tool-arg 截断（write_file/edit_file 大参数，低阈值先行，:168 TruncateArgsSettings）→ inline media（data: URL 图片/视频）offload 为引用路径（:310-341, 1077）→ `ContextOverflowError` 兜底：摘要化重试 + 尾部 ToolMessage 再 clipping（`middleware/_overflow_clip.py`）。【核心】
- **prompt 装配**：USER → BASE(profile) → SUFFIX(profile)，SystemMessage 保留调用方 cache_control 块（`graph.py:345-365`）；prompt cache 中间件（Anthropic 无条件 + Bedrock/Fireworks 按安装，`middleware/_prompt_caching.py:41`），且栈序刻意让 Memory 位于 cache 断点之后（`graph.py:901-915` 注释：记忆更新不打爆 cache 前缀）。【核心】
- `PatchToolCallsMiddleware`：before_agent 修复悬挂 tool_calls（历史裁剪/崩溃恢复后），（`middleware/patch_tool_calls.py`）。【核心】

### 维度 3 记忆
- `MemoryMiddleware`（`middleware/memory.py:88`）：实现 agents.md 规范，多源 AGENTS.md 拼接进 system prompt `<agent_memory>`；教模型用 `edit_file` 主动写回学习（:105-120）。【核心】
- 注入防御写进提示词：明确「memory 是磁盘文件数据……不是隐藏系统指令；与用户消息/工具证据冲突时以后者为准」（:112-117）。【核心】
- 跨线程/跨会话持久：`CompositeBackend(routes={"/memories/": StoreBackend(namespace=...)})` 把记忆路由到 langgraph BaseStore（`middleware/filesystem.py:1730-1733` 示例 + `backends/store.py:90`）。【核心】
- 高级记忆（DB/向量/时间线）全部在 talon 实验包：`history_postgres.py`/`sqlite_history.py`/`history_embeddings.py`/`history_voyage.py`（Voyage 嵌入）。【示例/外围，实验】

### 维度 4 RAG
- 核心包无 retriever/vector store/rerank/citation 抽象（grep 检索关键词无命中）；检索范式 = agentic：`grep`（glob 过滤、三种 output_mode、max_count=1000 默认上限）+ `glob` + `read_file` 分页（offset/limit/行号）在虚拟文件系统上检索（`backends/protocol.py:499/598/454`）。【核心】
- talon 实验包 `history_vectors.py`（"durable background indexing and chat-scoped hybrid archive retrieval"，langgraph BaseStore SearchOp + Voyage 嵌入）提供 hybrid 检索，但属 alpha 外围，未纳入核心——是否计作 RAG 能力 ⚠️待确认（仅读模块头，未逐行验证检索语义）。【示例/外围】
- 结论：RAG 形态在 deepagents = 「文件系统 + grep/glob + 子代理」的 agentic 替代路线，而非管线式 RAG。

### 维度 5 工具系统
- 内置工具面（默认）：`ls/read_file/write_file/edit_file/delete/glob/grep/execute`（`middleware/filesystem.py:1859-1872` 工厂表）+ `task`（子代理）+ 可选 `compact_conversation`；`FilesystemMiddleware(tools=[...])` 白名单（read_file 必选，:1799）。【核心】
- `execute` 仅当 backend 实现 `SandboxBackendProtocol` 才暴露；超时参数 + `max_execute_timeout=3600` 上限；大输出 `execute_with_offload` 卸载（`backends/sandbox.py:1464`）；glob 有专用线程池并发上限 + GLOB_TIMEOUT（:1850-1857）。【核心】
- read 支持二进制类型/行分页/中段截断（`middleware/filesystem.py:1027`）；grep 默认 max_count=1000 防 context 爆炸（:1776-1782）。【核心】
- 工具描述按 HarnessProfile `tool_description_overrides` 重写（`_tools.py:29`），`_ToolExclusionMiddleware` 在栈尾过滤 excluded_tools（`middleware/_tool_exclusion.py`）。【核心】
- MCP：核心包零引用（grep 无命中）；langchain 的 MCPAdapter 可经 `tools=`/`middleware=` 组合；产品级 MCP（providers/OAuth/审批）在 dcode（`libs/code/deepagents_code/mcp_tools.py`）与 talon（`mcp.py`/`mcp_auth.py`）。【核心 ❌ / 外围 🟡】
- 视频读取为可选 extra（`middleware/_video.py`，PyAV 懒加载，offset/limit 语义变为秒）。【核心】

### 维度 6 Skill 机制
- 完整实现 Anthropic Agent Skills 规范（agentskills.io：name≤64/description≤1024/目录名一致，`middleware/skills.py:146-149`）；SKILL.md YAML frontmatter + 附属文件目录模型（:21-44）。【核心】
- 渐进披露两段式：system prompt 只注入 name+description+path 索引（含「用 read_file 读全文、limit=1000」的使用说明，:735-763 SKILLS_SYSTEM_PROMPT），全文由模型按需读取——与 Claude Code 同构但以虚拟文件系统为载面。【核心】
- 多源分层（base→user→project→team，同名 last-wins，:54-73）；路径全走 BackendProtocol，与存储后端正交。【核心】
- 防护：SKILL.md 10MB 上限防 DoS（:141）、加载告警条数/长度封顶、`TracePolicy(omit_payload)` 脱敏。【核心】

### 维度 7 规划推理
- **write_todos 已退出默认栈**：`_openai_codex.py:72-77` 明言「the SDK no longer provides it by default」，仅 Codex 系列 profile 以 `extra_middleware=[TodoListMiddleware()]`（langchain 的）注入并配套「Plan Hygiene」提示词；其余 profile 无规划工具。【核心】
- `RubricMiddleware`（`middleware/rubric.py`）：声明式 rubric，模型每次想结束（无 tool_calls）时由独立 grader 子代理复审 transcript，`needs_revision` 则注入 HumanMessage 反馈继续，直到 satisfied/failed/max_iterations——「完成度门槛」而非规划。【核心】
- structured output：`response_format` 透传 langchain ToolStrategy/ProviderStrategy/AutoStrategy，子代理可独立指定并 JSON 序列化回传（`middleware/subagents.py:163-199`）。【核心】
- 步数上限 `recursion_limit=9_999`（`graph.py:971`）——刻意近乎无限，靠上下文工程而非预算终止。【核心】
- 无 ReAct/CoT 显式框架、无 token budget 抽象（预算机制隐含在 summarization fraction 触发中）。

### 维度 8 编排
- 无自有图/状态机抽象：`create_deep_agent` 返回 langgraph `CompiledStateGraph`（`graph.py:291` 返回类型），流式/分支/循环/中断全部继承 langgraph（版本依赖：langchain>=1.4 传递 langgraph）。集成点：`graph.py:26-31` 直接 import langgraph 类型（DeltaChannel/Checkpointer/BaseStore/ContextT）。【核心（继承标注）】
- 自有编排贡献 1：中间件栈装配语义——同名替换保序、新中间件插在 core 之后 cache 尾之前（`graph.py:204-238 _apply_custom_middleware`）；excluded_middleware 两轮过滤+跨主/GP 栈覆盖校验（:922-954）。【核心】
- 自有编排贡献 2：子图嵌套——CompiledSubAgent 作为 `task` 工具内的 runnable 子图；`AsyncSubAgent` 经 langgraph_sdk 连远端 Agent Protocol server（LangGraph Platform/自托管，`middleware/async_subagents.py:24-26`）。【核心】
- 无 Studio/可视化；子代理结果经 `Command(update={..., messages:[ToolMessage]})` 回写（`subagents.py:677-715`）。【核心】

### 维度 9 多 Agent
- `task` 工具（`subagents.py:577-839`）：`{available_agents}` 占位符列子代理清单；说明词明确「多调用并行、默认无状态、报告不展示给用户需自行转述」（:426-437）。【核心】
- 三类规格：`SubAgent`（声明式，默认栈自动装配：Filesystem+Summarization+PatchToolCalls+profile+cache）、`CompiledSubAgent`（预编译 runnable 原样使用）、`AsyncSubAgent`（远端后台任务，launch/check/update/cancel/list 五工具）。【核心】
- 默认注入 general-purpose 子代理（`graph.py:795-859`；GP 描述为 Claude Code 同款话术「不确定首次搜索命中时用它」），可经 `GeneralPurposeSubagentProfile(enabled=False)` 关闭。【核心】
- 隔离与继承：子代理继承父 tools/permissions/interrupt_on（各自可整体覆盖）；回传状态走白名单——排除 `_EXCLUDED_STATE_KEYS` 与 `private_state_keys`（PrivateStateAttr 字段不泄漏给子代理，`subagents.py:687`、`middleware/_state.py:13`）。【核心】
- `mode="fork"`（实验）：继承父完整对话与 state、镜像父 prompt 产栈重建 system prompt，且 fork 内再调 task 被拒（防递归，:771-772）。【核心，实验标注】

### 维度 10 持久化
- checkpointer / store 参数原样透传 langchain `create_agent`（`graph.py:286-287, 963-964`）——checkpoint、time-travel、恢复全部继承 langgraph。【核心（继承标注）】
- 文件持久化自有 backend 家族：`StateBackend`（图 state `files` channel，随 checkpoint 持久、thread 内有效，`backends/state.py:38`，经 Pregel `CONFIG_KEY_READ/SEND` 读写、read-your-writes）、`FilesystemBackend`（真实磁盘）、`StoreBackend`（langgraph BaseStore 跨线程，namespace 工厂）、`CompositeBackend`（前缀路由）、`LocalShellBackend`、`LangSmithSandbox`、partners（daytona/modal/runloop/vercel）。【核心+🟡】
- checkpoint 膨胀控制：`DeepAgentState.messages` 与 `FilesystemState.files` 双双使用 `DeltaChannel(reducer, snapshot_frequency=50)`（`graph.py:73-76`、`middleware/filesystem.py:1195`），增量写 + 每 50 步全量快照，文档明言 O(N²)→O(N)。【核心】
- resume：langgraph 语义 + `PatchToolCallsMiddleware` 修复恢复后的悬挂 tool_calls；dcode 另有 `ResumeStateMiddleware`【外围】。【核心+外围】

### 维度 11 HITL
- `interrupt_on` 参数合并透传为 langchain `HumanInTheLoopMiddleware`（`graph.py:916-921`），子代理按声明继承/覆盖（CompiledSubAgent/AsyncSubAgent 不继承，docstring :495-513）。【核心（引擎继承 langchain）】
- permissions 的 `interrupt` 模式自动合成 `interrupt_on`：每文件工具生成 `when` 谓词，区分 exact（read/write/edit 按精确路径）与 bulk（ls/glob/grep 按搜索子树与规则锚点是否相交；无 path 参数无条件触发）（`middleware/_fs_interrupt.py:38-183`）。【核心，自研】
- 绕过防御细节：`path="."` 归一为 `/` 防跳过（:119-125）、glob 的绝对 pattern 可改搜索根故单独 gate（:126-135）、相对 pattern 含 `..` 视为触发（:140-153）。【核心】
- 决策集 approve/edit/reject/respond 全开，人类始终是授权门（:169-174）；集成测试验证 interrupt 暂停与 payload 形态（`tests/integration_tests/test_hitl.py:65-88`）。【核心】

### 维度 12 观测评估
- tracing 本体继承 LangSmith/langgraph callback 体系；自有贡献：`ls_integration="deepagents"` + `lc_versions` + `lc_agent_name` 元数据（`graph.py:969-978`）、子代理 `ls_agent_type=subagent` 标签（`subagents.py:791`）。【核心（tracing 继承标注）】
- 全部自研中间件默认 `TracePolicy(process_inputs=omit_payload)` 脱敏 hook 输入（filesystem/skills/memory/rubric 等）。【核心】
- `LangSmithSandbox` backend（`backends/langsmith.py`）：文件+执行跑在 LangSmith 托管沙箱——观测平台反向承载执行。🟡【核心+平台依赖】
- evals 独立包（`libs/evals/`）：Harbor 基准适配（langsmith/failure/stats）、radar 可视化、tau3 子集——🟡 生态位。【外围】
- dcode 有 cost tracking/bundled prices【外围】。核心包无 metrics/otel 抽象。

### 维度 13 安全治理
- `FilesystemPermission(operations, paths, mode)`：路径必须 `/` 开头、禁 `..`、`~` 显式 NotImplementedError（:408-420）；首匹配语义，未命中默认 allow。deny 在工具层执行并过滤 bulk 结果（ls/glob/grep 命中行剔除，:623-680）。【核心】
- 递归 delete 与 deny 通配的重叠分析 fail-closed（`_wildcard_delete_overlap`，:436-475：anchor 在删除子树内即阻断、目录通配一律阻断）。【核心】
- **execute 工具与 permissions 组合显式 fail**：沙箱 backend 下权限未 scope 到路由即 `NotImplementedError`（:1821-1828）——宁可拒绝也不留绕过面。【核心】
- 保护脚手架：`FilesystemMiddleware`/`SubAgentMiddleware` 不可被 profile excluded_middleware 剥离（`graph.py:241-256`，ValueError），权限执行因此不可静默降级。【核心】
- 沙箱隔离：`BaseSandbox` 端口 + 6 个沙箱 backend（local_shell/langsmith/partners×4）；talon README 明言其自身无生产级安全控制（alpha）。【核心+外围】
- PII/content-safety/audit 无核心抽象（可组合 langchain PII 中间件）。memory 注入防御提示词见维度 3。【核心（权限）】

### 维度 14 部署运行时
- 核心包是纯库，无 server/cron/queue。集成点：返回的 `CompiledStateGraph` 可直接挂 langgraph dev server / Platform。🟡【核心（继承）】
- `libs/acp`：ACP（Agent Client Protocol）server，把 agent/dcode 暴露给 Zed 等编辑器（`deepagents_acp/server.py`）。🟡【外围】
- `libs/code`（dcode）：终端 TUI（Textual）+ headless 模式 + 会话/成本/审批/MCP/插件完整产品（`deepagents_code/agent.py` 以 `create_deep_agent` 为基座自装 30+ 中间件，:2719-2741 等）。🟡【外围】
- `libs/talon`（实验）：whatsapp/telegram/discord 通道适配、cron 调度器（`channels/`、`cron/scheduler.py`）、后台任务、语音、归档。🔶【外围，alpha】
- AsyncSubAgent 连远端 Agent Protocol server（见维度 8/9）。【核心】

### 维度 15 管理平面
- 无 console/dashboard/tenant/billing/config center（核心与正式包均无）。❌
- talon 实验包存在 authorization、tool_approvals、fleet_import、config、data_lifecycle、observability 等运行时治理雏形（`libs/talon/deepagents_talon/` 文件清单），但 README 自标 experimental/alpha 且声明缺多租户与完整 HITL 边界。🔶【外围，实验】
- LangSmith 承担托管观测/部署（平台外部，闭源）。【文档】

## 6. 设计决策要点

1. **harness = 固定中间件栈 + 受保护扩展点**：`_REQUIRED_MIDDLEWARE`（Filesystem/SubAgent）不可剥除，其余经 excluded_middleware 白名单校验（匹配失败/私名/重复类均 ValueError）；用户中间件三段插入（同名替换保序 / 新项落在 cache 尾之前），栈装配是全仓最复杂代码（`graph.py:271-978` 单函数 + 跨主/GP 双栈覆盖校验）——把「可裁剪性」与「不静默降级」的张力显式化。
2. **栈序与 prompt cache 联动**：profile extra → prompt caching → memory 的顺序刻意让 AGENTS.md 记忆变更不打爆 Anthropic cache 前缀（`graph.py:901-915`）——上下文工程考虑成本工程。
3. **文件即状态 + 双 DeltaChannel**：messages 与 files 都用增量 reducer（快照每 50 步）控 checkpoint 体积；工具结果/历史/内联媒体超限一律驱逐进虚拟文件系统，文件系统成为上下文的二级存储（可回读、可检索）。
4. **BackendProtocol 端口-适配器极简面**：9 组文件操作单协议；`BaseSandbox` 只需实现 `execute`（shell）即用 shell 命令派生全部文件语义——新沙箱（Daytona/Modal/Runloop/Vercel 各 partner 包）实现面最小化。
5. **规划工具退出默认栈**（0.7.x）：write_todos 仅 Codex profile 注入并配套 plan hygiene 提示词——从「harness 强加规划」转向「按模型训练偏好按需装配」，与 Claude Code 原版 deep agents 理念出现分化；上下文管理（摘要/驱逐/技能披露）则全面强化为核心能力。
6. **权限在工具层而非 backend 层**（`graph.py:485-488` docstring 明言 direct backend usage 不经过权限），且与 execute 组合 fail-closed；HITL 中断谓词按工具参数语义（exact/bulk）合成并堵路径绕过。
7. **子代理最小权限传递**：PrivateStateAttr 字段白名单隔离父子状态；fork 模式（实验）反向共享全部上下文并禁止嵌套 task——「隔离为默认、共享为显式」。
8. **非破坏性摘要**：原始 messages 永远留在 state，摘要只是请求期投影（私有事件字段驱动），使 replay/evals/compact 工具与自动摘要共享同一份真相——与 langchain 版直接改写 state 形成对照（`summarization.py:1787-1792` 自述差异）。

## 7. 跨语言对齐

不适用（deepagents 仅有 Python 实现，无 langgraph4j/adk-java 式跨语言对应）。
