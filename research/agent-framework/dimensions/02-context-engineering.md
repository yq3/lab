# 维度 2：上下文工程（Context Engineering）

> 本维度回答：发给模型的请求是怎么组装出来的——prompt 模板如何管理与参数化、消息按什么顺序拼装、token 预算用什么计数器与水位线、历史压缩/摘要在什么条件下用什么算法触发、工具结果与多模态内容是否有独立预算、以及是否具备 prompt cache 断点意识（让可缓存前缀稳定）。17 个框架总体格局：**「窗口裁剪」是及格线（人人都有某种形式），「水位比例触发 + 分层防御 + 非破坏性摘要」是当前天花板（deepagents/agentscope/agent-framework 三家），prompt cache 断点意识刚刚兴起（5 家显式实现）**；一个清晰的断层是：harness 类框架（deepagents/agentscope/dcode）把上下文当核心资产经营，库类框架（spring-ai/crewai/dify）多数只给一个开关。本文件对 6 处证据做了源码二次核验，全部实锤（表注见 2.1）。

## 2.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | ✅ | ChatPromptTemplate（模板即 LCEL Runnable）+ dynamic_prompt 动态系统提示 + SummarizationMiddleware 组合触发压缩（无 tokenizer 时 3.3 chars/token 近似） | libs/core/langchain_core/prompts/chat.py#ChatPromptTemplate；libs/langchain_v1/langchain/agents/middleware/summarization.py#SummarizationMiddleware、#TriggerClause |
| langgraph | 🔶 | 仅提供 add_messages reducer（按 id 合并）与 prebuilt prompt/response_format；trim/摘要刻意放 langchain 系另仓；自有贡献是 DeltaChannel 增量快照控 checkpoint 膨胀 | libs/langgraph/langgraph/graph/message.py#add_messages；libs/langgraph/langgraph/channels/delta.py#DeltaChannel |
| langgraph4j | 🟡 | core 定义 ConversationContextPolicy 策略接口 + langchain4j 侧 MessageWindow 按条数窗口实现；SkillInjector 经上下文注入不入 state；无 token 预算/自动摘要（本次核验两文件实锤） | langgraph4j-core/.../agent/ConversationContextPolicy.java#L13；langchain4j/langchain4j-agent/.../MessageWindowConversationContextPolicy.java#L26 |
| langchain4j | ✅ | TokenWindowChatMemory 运行时动态 token 窗口（maxTokensProvider）、SystemMessage 永久保留、驱逐含工具调用的 AiMessage 时连带孤儿 ToolExecutionResultMessage；supervisor 三种上下文策略；RAG 查询压缩/扩展 transformer | langchain4j/src/main/java/dev/langchain4j/memory/chat/TokenWindowChatMemory.java#TokenWindowChatMemory；langchain4j-agentic/.../supervisor/SupervisorPlanner.java#SupervisorContextStrategy |
| deepagents | ✅ | 五层防线：大结果驱逐进虚拟文件系统→旧 tool-arg 截断→摘要化+历史 offload 到 /conversation_history（非破坏性）→ContextOverflow 兜底 clipping→prompt cache 断点栈序 | libs/deepagents/deepagents/middleware/summarization.py:262/:1757、_message_eviction.py、_overflow_clip.py、graph.py:901-915（栈序注释） |
| agent-framework | ✅ | CompactionStrategy 协议一等公民 + TokenizerProtocol/CharacterEstimatorTokenizer + group_messages 把函数调用/结果与 reasoning 成组后再摘要 | python/packages/core/agent_framework/_compaction.py#CompactionStrategy/#group_messages/#_unambiguous_function_call_result_pairs |
| adk-python | ✅ | 事件压缩 EventsCompactionConfig token 阈值触发 + Gemini 原生 content compaction（含函数调用恢复）+ LlmEventSummarizer 摘要器 + 显式 Gemini context cache（本次核验实锤） | apps/compaction.py#_estimate_prompt_token_count；flows/llm_flows/compaction.py；flows/llm_flows/_content_compaction.py:123；flows/llm_flows/context_cache_processor.py#ContextCacheRequestProcessor |
| adk-java | ✅ | Instruction.Static/Provider 动态指令 + Instructions 处理器 {state_var} 替换 + 三种事件压缩器（滑窗/尾部保留/LLM 摘要）+ Fencing 引用块包裹他人上下文（本次核验 summarizer 5 类实锤） | core/.../agents/Instruction.java；core/.../flows/llmflows/Instructions.java；core/.../summarizer/{SlidingWindow,TailRetention}EventCompactor.java、LlmEventSummarizer.java |
| openai-agents-python | ✅ | 动态 instructions（str/Callable/多语言 dict）+ handoff input_filter 裁剪 + SessionSettings 条目截断 + responses.compact 服务端压缩（候选 ≥10 触发）+ context_management 透传；无本地 token 预算 | src/agents/agent.py#instructions；handoffs/__init__.py#HandoffInputFilter；memory/openai_responses_compaction_session.py#OpenAIResponsesCompactionSession |
| claude-agent-sdk-python | ✅ | system_prompt 三形态（str/preset+append/file）+ exclude_dynamic_sections 剥动态段换跨用户 prompt cache 命中 + autocompact（CLI 执行）+ get_context_usage 全量口径分解 | src/claude_agent_sdk/types.py#SystemPromptPreset、#ContextUsageResponse；client.py#ClaudeSDKClient.get_context_usage |
| crewai | ✅ | 布尔级 respect_context_window 超窗摘要/中止 + CONTEXT_WINDOW_USAGE_RATIO=0.85 窗口配比 + provider 无关 prompt cache 断点标记（本次核验实锤）；无消息级 trim 管道 | lib/crewai/src/crewai/agent/core.py:288；lib/crewai/src/crewai/llm.py:329/:1939；llms/cache.py#mark_cache_breakpoint |
| dify | ✅ | 三级 prompt transform（simple/advanced/agent history）+ Jinja2 沙箱渲染 + {{#node.var#}} 变量选择器 + TokenBufferMemory 双限裁剪（max_token_limit 默认 2000 + message_limit，本次核验实锤） | api/core/prompt/；api/core/memory/token_buffer_memory.py:124-232；api/core/workflow/template_rendering.py |
| llama_index | ✅ | 完整模板体系（Prompt/RichPromptTemplate）+ prompt_helper 按上下文窗口预算装配 + 压力式 Memory（FIFO 达 token_limit 按 token_flush_size 弹出交 memory blocks 处理，chat_history_token_ratio=0.7）+ condense 历史压缩 chat engine + agent state 注入 | llama-index-core/.../memory/memory.py#Memory；indices/prompt_helper.py；chat_engine/condense_plus_context.py |
| agentscope | ✅ | 分层压缩：0.6 水位缓冲带提醒→agent 自主压缩工具→0.8 硬阈值结构化五段摘要（自包含摘要 prompt）→失败截断兜底；工具结果 50k token 独立限额、图片 max_image_num=5 先 offload 再替换 HintBlock | src/agentscope/agent/_agent.py#compress_context；agent/_config.py#ContextConfig（trigger 0.8/reserve 0.1/buffer 0.2） |
| agentscope-java | ✅ | harness 层 ConversationCompactor（token/条数双触发、keepTokens 保留区、可指定专用摘要模型、增量叠加历史摘要）+ ToolResultEviction 正交驱逐 + ModelContextWindows 前缀窗口表 | agentscope-harness/.../memory/compaction/{CompactionConfig,ConversationCompactor}.java；model/ModelContextWindows.java |
| spring-ai-alibaba | ✅ | hook+interceptor 策略库：SummarizationHook（TokenCounter 超阈值触发）+ contextediting + returndirect + toolselection + toolcalllimit + Nacos prompt 注入（支持 KMS 加密 dataId） | spring-ai-alibaba-agent-framework/.../agent/hook/summarization/SummarizationHook.java:114；agent/interceptor/contextediting |
| spring-ai | ✅ | StringTemplate 模板（{} 定界、ValidationMode 防注入）+ defaultSystem + 双层裁剪（MessageWindowChatMemory 条数滑窗 + LastMaxTokenSizeContentPurger token 估算保尾部）；无自动摘要（本次核验 purger 实锤） | spring-ai-client-chat/.../advisor/LastMaxTokenSizeContentPurger.java:34；spring-ai-model/.../chat/memory/MessageWindowChatMemory.java:107-113；spring-ai-template-st#StTemplateRenderer |

表注（二次核验，全部实锤）：① langgraph4j `ConversationContextPolicy.java:13`（interface）与 `MessageWindowConversationContextPolicy.java:26`（implements）存在且语义如档案所述；② spring-ai `LastMaxTokenSizeContentPurger.java:34`（TokenCountEstimator + maxTokenSize 构造）存在；③ adk-java summarizer 目录 5 个类（EventCompactor/EventsCompactionConfig/SlidingWindow/TailRetention/LlmEventSummarizer）齐全；④ crewai `llms/cache.py:27 mark_cache_breakpoint` + `CACHE_BREAKPOINT_KEY`（docstring 自述 provider-agnostic prompt-cache breakpoint marker）、`llm.py:329 CONTEXT_WINDOW_USAGE_RATIO=0.85`、`:1939 respect_context_window 分支`；⑤ adk-python `context_cache_processor.py:36` + `gemini_context_cache_manager.py:84`；⑥ dify `token_buffer_memory.py:124` 默认 `max_token_limit=2000`。

## 2.2 实现方式深析

### 议题 1：prompt 模板管理——四种形态

1. **模板即执行单元**：langchain `ChatPromptTemplate` 本身是 LCEL Runnable（可进管道、可序列化），变量用 f-string 风格 `{var}`；配套 `dynamic_prompt`（middleware/types.py:1690）按 state 运行时生成 system prompt。这是「模板」与「组装逻辑」融合最深的做法。
2. **模板引擎外挂**：spring-ai 用 StringTemplate（`StTemplateRenderer`，`{}` 单字符定界、可配），并在 2.0 加 `TemplateRenderer.ValidationMode` 做模板注入防护；dify 用**代码沙箱里的 Jinja2**（CodeExecutorJinja2TemplateRenderer）渲染 workflow 模板，变量引用是图语义的 `{{#node.var#}}` 选择器（经 VariablePool 取值）——平台级模板与图变量系统一体。
3. **指令对象而非模板**：adk 双语用 `Instruction.Static/Provider`（Java）与 `instructions` str/Callable（Python）——系统提示是一等配置字段而非字符串加工流水线；claude sdk 的 system_prompt 三形态（str / preset+append / file）同样把「叠加语义」（append 到 Claude Code 预设之后）做进类型系统。
4. **多语言/本地化模板**：openai-agents 的 instructions 接受 `dict[locale, str]`；crewai 有整个 `translations/` 目录 + i18n 工具（角色扮演提示词多语言化）——两家面向终端产品的框架不约而同做了 i18n。

**消息组装顺序**上各家高度一致：SystemMessage 前置 + 会话历史（按 id 合并或追加 reducer）+ 最新用户输入；差异在「谁持有顺序语义」——langgraph `add_messages`、spring-ai-alibaba `messages` key+AppendStrategy、adk `EventActions.state_delta` 事件溯源，本质都是 reducer/channel 语义（详见维度 10/3）。

### 议题 2：token 预算——计数器与水位线

- **计数器实现三档**：真 tokenizer（spring-ai JTokkit `JTokkitTokenCountEstimator`、agent-framework `TokenizerProtocol` 可插拔 + `CharacterEstimatorTokenizer` 兜底）；模型 API 口径（langchain SummarizationMiddleware 优先用 `usage_metadata` 缩放）；纯近似（langchain 无 tokenizer 时 3.3 chars/token、adk `_estimate_prompt_token_count` 字符估算、agentscope ApproxTokenChunker）。**「不预设 tokenizer 依赖」是 Python 系共识**——避免为每个模型装分词器；Java 系（spring-ai）反而默认真 tokenizer。
- **窗口表来源**：crewai 把上下文窗口常量表内置于 llm.py（mistral 等条目）；agentscope-java `ModelContextWindows` 按最长前缀匹配 qwen3/gpt-4.1 推断窗口供压缩阈值用；agentscope 用模型卡/模型层 context_size——窗口元数据正在变成模型接入层的一部分。
- **水位线（watermark）设计**：agentscope `ContextConfig` 是最完整的比率语义：`trigger_ratio=0.8` 硬压缩触发、`reserve_ratio=0.1` 保留近期、`context_buffer_ratio=0.2` 缓冲带（0.6 起就开始提醒）——三段式水位；deepagents 无 profile 时回退绝对值（tokens 170k / messages 6），有 profile 时用 fraction 0.85/keep 0.10；crewai 一个 `CONTEXT_WINDOW_USAGE_RATIO=0.85` 常量乘窗口。**水位比率 > 绝对条数** 是明确演进方向（见 2.4）。

### 议题 3：历史压缩/摘要——触发、算法与可恢复性

按「触发条件 × 算法 × 是否可恢复」列表：

| 框架 | 触发 | 算法 | 被压缩内容的去向 |
|---|---|---|---|
| deepagents | fraction 0.85（或 170k/6 条兜底） | LLM 摘要 | **offload 到 `/conversation_history/{session_id}.md`，原位替换摘要+回读指引**（非破坏性：原始 messages 留 state，摘要只是请求期投影，存私有 `_summarization_event` 字段） |
| agentscope | 0.8 硬阈值 + 0.6 缓冲带提醒 + agent 自主压缩工具 | **结构化五段摘要**（SummarySchema：task_overview/current_state/important_discoveries/next_steps/context_to_preserve），prompt 明确要求相对时间绝对化、指针全限定（为多次压缩设计的自包含摘要） | 摘要进 `AgentState.summary`；失败回退截断最旧并插 HintBlock |
| agent-framework | compaction 协议（Agent 构造器直收 compaction_strategy） | `group_messages` 先把函数调用/结果、reasoning 消息**成组**（`_unambiguous_function_call_result_pairs`）再摘要——保证工具调用配对完整性 | 由策略实现决定 |
| adk-python | EventsCompactionConfig token 阈值 | 双路：事件压缩（请求处理器，压缩后记 EventCompaction 事件**防重复压缩且可溯源**）+ Gemini 原生 content compaction（含函数调用恢复 :123） | 压缩事件入 session 事件流 |
| adk-java | Compaction 配置驱动 | 三策略切换：滑窗（SlidingWindowEventCompactor）/尾部保留（TailRetention）/LLM 摘要（LlmEventSummarizer） | 事件序列裁剪 |
| openai-agents | 候选条目 ≥10（DEFAULT_COMPACTION_THRESHOLD） | **服务端** `responses.compact`（默认模型 gpt-4.1） | OpenAI 侧会话 |
| claude sdk | autoCompactThreshold（CLI） | CLI autocompact【文档】；SDK 暴露 PreCompact hook（manual/auto trigger + custom_instructions） | CLI 内部 |
| langchain | TriggerClause 可组合（tokens/messages/fraction） | LLM 摘要，无 tokenizer 用近似计数 | **直接改写 state（deepagents 注释自述差异："drops evicted messages with no recovery path"）** |
| spring-ai-alibaba | SummarizationHook token 计数超阈值 | LLM 摘要 hook | 图 state |
| llama_index | ChatMemoryBuffer 超 token_limit；Memory 压力式 FIFO | ChatSummaryMemoryBuffer 自动 LLM 摘要；Memory 达 token_limit 按 token_flush_size 弹出旧消息交 memory blocks（fact 抽取/vector 入库）降级回注 | memory blocks（见维度 3） |
| langchain4j | TokenWindow 动态窗口 | 无摘要——**消息不可分割、放不下整条驱逐**，SystemMessage 永久保留，孤儿 ToolExecutionResultMessage 连带驱逐 | 丢弃（窗口语义） |
| crewai | respect_context_window=True 且超 0.85 窗口 | 摘要或中止（llm.py:1939 分支） | 窗口语义 |
| dify | max_token_limit=2000 + message_limit 双限 | 逐条弹出最旧（TokenBufferMemory.get_history_prompt_messages） | 丢弃（窗口语义） |
| spring-ai | 条数（MessageWindow）或 token（Purger） | 无摘要，滑窗/保尾截断；MessageWindow 淘汰时**向前对齐到 UserMessage** 保持轮次完整 | 丢弃 |
| langgraph4j | 消息条数（MessageWindowConversationContextPolicy） | 窗口语义 | 丢弃 |

三个关键设计分歧：
1. **非破坏性 vs 改写式**：deepagents 把「原始 messages 永远留在 state、摘要只是请求期投影」写成设计原则（summarization.py:1787-1792 自述与 langchain 版差异），代价是 state 体积（用 DeltaChannel 缓解）；langchain SummarizationMiddleware 直接改写。adk-python 用 EventCompaction 事件让压缩本身可溯源可回放——事件溯源平台的天然优势。
2. **成组保护**：agent-framework 的 group_messages 与 langchain4j 的「孤儿工具结果连带驱逐」解决同一问题（工具调用与结果必须配对，否则 API 报错），前者在摘要侧、后者在驱逐侧。
3. **摘要的「自包含性」**：agentscope 的五段结构化摘要 + 「相对时间转绝对、指针全限定、登记后台任务」prompt 工程，是唯一显式为**多次压缩（摘要的摘要）**设计的实现。

### 议题 4：工具结果与多模态的独立预算

这是最能区分「harness 级」与「库级」框架的子项：

- **deepagents**：工具结果 >20k tokens、HumanMessage >50k 即写入 `/large_tool_results/{tool_call_id}`，原位替换为 head+tail 预览 + read_file 指引（_message_eviction.py `TOO_LARGE_TOOL_MSG`）；inline media（data: URL 图片/视频）offload 为引用路径；grep 默认 max_count=1000。
- **agentscope**：`tool_result_limit=50000` token 独立截断（`_split_tool_result_for_compression`）；图片 `max_image_num=5` 超限先 offload 到 workspace 再替换 HintBlock（`_limit_context_images`）——**workspace 兼任上下文二级存储**。
- **agentscope-java**：`ToolResultEvictionConfig` 与摘要压缩**显式正交**（javadoc 明示 orthogonal），两条机制互不干扰。
- **adk-python**：content compaction 处理 Gemini 原生压缩后的函数调用恢复。
- **openai-agents**：`extensions/tool_output_trimmer.py` 只做工具输出裁剪（主包 extensions）。
- 其余（langchain/langgraph4j/spring-ai/crewai/dify/llama_index/spring-ai-alibaba 核心）均无工具结果/媒体独立预算——工具超长结果直接回喂或依赖用户自建。

### 议题 5：prompt cache 断点意识（5 家显式实现）

长会话成本结构下，「哪些前缀必须字节级稳定」成为上下文工程的显式约束：

1. **deepagents 栈序设计**（graph.py:901-915 注释）：中间件栈刻意排成 profile extra → prompt caching → memory——让 AGENTS.md 记忆变更不打爆 Anthropic cache 前缀；SystemMessage 保留调用方 cache_control 块（graph.py:345-365）。
2. **claude sdk `exclude_dynamic_sections`**（types.py:46-57）：剥掉 per-user 动态段（cwd/auto-memory/git status）重注入首条 user message，换取**跨用户** prompt cache 命中——把缓存命中从会话级提升到用户群级。
3. **crewai `mark_cache_breakpoint`**（llms/cache.py:27）：provider 无关的断点标记（消息 dict 加 `cache_breakpoint` 键），executor 在 system 尾 + user 尾打点（:204-206）。
4. **llama_index `CacheControl/CachePoint`**（base/llms/types.py:790/795）：**内容块级** cache_control 标注（Anthropic 式），粒度最细。
5. **openai-agents prompt cache 生命周期**：`prompt_cache_key.py` 管理会话粘性 key + `ModelSettings.prompt_cache_retention/options`。
6. adk-python 的 GeminiContextCacheManager 是另一种物种——**显式内容缓存**（创建/引用/从 session 事件恢复元数据），非隐式前缀缓存。

## 2.3 跨语言对齐

| 对 | 子能力 | Python 侧 | Java 侧 | 对齐度 |
|---|---|---|---|---|
| langgraph ↔ langgraph4j | 消息历史语义 | add_messages reducer（按 id 合并/替换） | channel/reducer 归并不可变 AgentState + RemoveByHash | **已对齐** |
| | 历史裁剪 | prebuilt/生态另仓（langchain trim/SummarizationMiddleware） | MessageWindow 策略 + skill body 上下文注入（不入 state） | **部分**（Java 无 token 级 trim/摘要） |
| | 增量快照 | DeltaChannel + counters_since_delta_snapshot | 无对应物 | **缺失** |
| adk-python(2.9) ↔ adk-java(1.9) | 核心压缩管线 | EventsCompactionConfig token 阈值 + LlmEventSummarizer + content compaction | Instructions/Compaction 处理器 + SlidingWindow/TailRetention/LlmEventSummarizer 三压缩器 | **已对齐**（机制同源，Java 多两种确定性策略，Python 多原生 content compaction） |
| | 动态指令 | instructions str/callable | Instruction.Static/Provider + {state_var} | **已对齐** |
| | Fencing（跨 agent 上下文引用块） | Fencing 处理器 | Fencing.java（ELIDED 引用块） | **已对齐** |
| | 外围处理器 | Python 多 8+：context_cache、nl_planning、tool_call_rearranger、tool_error_handler… | 无 | **部分**（版本差因素） |
| agentscope ↔ agentscope-java | 压缩位置 | **内建于 Agent**（compress_context + ContextConfig 三段水位 + 自主压缩工具 + 图片降级 + 截断兜底） | 外置于 harness（ConversationCompactor + ToolResultEviction） | **部分** |
| | 摘要结构 | 结构化五段 + 自包含摘要 prompt | 增量叠加式摘要 + 可指定专用摘要模型（Java 独有） | **部分**（各有独占细节） |
| | 工具结果/媒体独立预算 | tool_result_limit=50k + max_image_num=5 offload | ToolResultEvictionConfig（正交）；媒体降级未证实（⚠️保留） | **部分** |
| | 水位提醒/自主压缩工具 | 有（0.6 提醒 + CompressContext 工具） | 无 | **缺失** |

## 2.4 取舍与趋势

1. **压缩从「可选工具」变为「默认装配的中间件」，触发条件从条数窗口进化为窗口水位比率**：条数滑窗（spring-ai/MessageWindow、langchain4j、dify、langgraph4j）是 1.0 时代答案；fraction/ratio 水位（deepagents 0.85、agentscope 0.8/0.1/0.2、langchain TriggerClause、crewai 0.85 配比）按模型真实窗口缩放，是 2025-2026 的主流化设计。分层防御（提醒→自主压缩→硬压缩→截断兜底）目前只有 agentscope 一家做全。
2. **非破坏性摘要成为新共识**：deepagents 用私有事件字段保留原始 messages（服务 replay/evals），adk 用 EventCompaction 事件让压缩可溯源——「摘要是有损视图，不该销毁真相」正在取代「摘要即改写历史」（langchain 现版、多数窗口派仍是改写/丢弃式）。
3. **文件系统/workspace 成为上下文的二级存储**：deepagents 把超大工具结果与被压缩历史 offload 进虚拟文件系统并可 read_file 回读；agentscope 把超限图片 offload 到 workspace——「上下文放不下就变成文件，模型自己检索」是 harness 类框架的共同路线，与 RAG 管线式框架形成方法论分野。
4. **prompt cache 断点从参数细节升格为栈序/类型系统约束**：deepagents 用中间件栈序保证记忆变更不打爆缓存前缀、claude sdk 用 exclude_dynamic_sections 换跨用户命中、llama_index 把 cache_control 做成内容块级类型、crewai 提供 provider 无关断点标记——上下文工程的优化目标从「塞得下」扩展到「塞得便宜」。
5. **token 计数普遍近似化、tokenizer 协议化**：为避免每模型 tokenizer 依赖，近似计数（chars/token、字符估算）+ 可插拔 tokenizer 协议（agent-framework）成为 Python 系默认；只有 spring-ai 默认真 tokenizer（JTokkit）。窗口大小元数据则从常量表（crewai）走向模型卡（agentscope）与前缀推断表（agentscope-java）。
6. **服务端压缩外包是平台绑定框架的特权**：openai-agents（responses.compact）、claude sdk（CLI autocompact）、adk-python（Gemini content compaction）把压缩算法本身交给供应商——换来了免费的最优实现，代价是上下文管理能力与后端绑定（本地化/token 级自主性下降）。
