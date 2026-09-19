# 维度 1：模型接入（Model Access）

> 本维度回答：框架如何抽象「调一个 LLM」——多供应商接口形态、路由/降级（routing/fallback）是真实实现还是文档宣称、流式接口是否统一、重试在哪一层用什么策略、用量/成本在哪里统计、缓存是 LLM 结果缓存还是语义缓存。17 个框架总体格局：**「统一 provider 接口 + 集成包矩阵」已是绝对主流（约 10 家），注册表/前缀字符串路由是第二选择（5 家），完全不做模型层的只有 langgraph 系与 CLI 外置的 claude-agent-sdk**；真正让人意外的空白是**模型级 fallback/router——17 家中仅 6 家有真实现**，其余要么缺失、要么要求用户用中间件/`@Primary` 自行组合。评级沿用各档案；本文件对 4 处薄弱证据做了源码二次核验（含修正 langgraph4j 档案一处错误生态宣称），标注于 N.1 表注。

## 1.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | ✅ | BaseChatModel 抽象 + init_chat_model 字符串路由 + ModelFallback/ModelRetry 中间件 + BaseCache/RateLimiter，provider 在 15 个 partners 包 | libs/core/langchain_core/language_models/chat_models.py#BaseChatModel；libs/langchain_v1/langchain/chat_models/base.py#init_chat_model；libs/langchain_v1/langchain/agents/middleware/model_fallback.py#ModelFallbackMiddleware |
| langgraph | 🟡 | 刻意不定义任何模型抽象；仅提供节点级 RetryPolicy/TimeoutPolicy/CachePolicy 与 LLM 结果缓存 BaseCache/RedisCache | libs/langgraph/langgraph/types.py#RetryPolicy/#CachePolicy；libs/checkpoint/langgraph/cache/base/__init__.py#BaseCache |
| langgraph4j | 🟡 | core 零模型依赖，官方双集成（langchain4j AgentExecutor / Spring AI ReactAgentBuilder）承载 ChatModel，节点级 RetryPolicy#asHook | langchain4j/langchain4j-agent/.../AgentExecutor.java#chatModel；langgraph4j-core/.../hook/RetryPolicy.java#asHook |
| langchain4j | ✅ | ChatModel/StreamingChatModel 统一接口 + 约 30 个 provider 模块 + provider 级重试（指数退避+jitter）；无模型级 fallback/router | langchain4j-core/src/main/java/dev/langchain4j/model/chat/ChatModel.java#ChatModel；langchain4j-open-ai/.../OpenAiChatModel.java:87（maxRetries=2） |
| deepagents | ✅（继承 langchain 接入面） | resolve_model→init_chat_model 全继承；自有贡献是 ProviderProfile/HarnessProfile 双注册表按模型调 harness；成本追踪在外围包 dcode | libs/deepagents/deepagents/_models.py#resolve_model；libs/code/deepagents_code/cost_tracking.py#CostTrackingMiddleware（本次核验 :2294 实锤） |
| agent-framework | ✅ | BaseChatClient 单协议（get_response/get_streaming_response）+ 10 余官方 provider 包；无内置 router/fallback/retry（本次核验 _clients.py 零命中确认） | python/packages/core/agent_framework/_clients.py#BaseChatClient；python/packages/anthropic/agent_framework_anthropic/{_chat_client,_bedrock_client,_vertex_client,_foundry_client}.py |
| adk-python | ✅ | LLMRegistry 模型名正则注册表 + Gemini/LiteLlm/Anthropic/Gemma/Apigee 原生 adapter + FallbackModel 顺序回退 + Gemini 显式 context cache | src/google/adk/models/registry.py#LLMRegistry；src/google/adk/models/_fallback_model.py#FallbackModel |
| adk-java | ✅ | LlmRegistry 默认仅 3 个正则（gemini/apigee/gemma），Claude 直连 Anthropic SDK 但未进注册表（本次核验确认），广度靠 SpringAI/LangChain4j 双桥 | core/src/main/java/com/google/adk/models/LlmRegistry.java:40-42；contrib/spring-ai/.../SpringAI.java#SpringAI |
| openai-agents-python | ✅ | Model/ModelProvider 协议 + MultiProvider 前缀路由（openai/litellm/any-llm/自定义）+ ModelRetrySettings + prompt_cache_key 管理 | src/agents/models/interface.py#Model；src/agents/models/multi_provider.py#MultiProvider；src/agents/run_internal/prompt_cache_key.py |
| claude-agent-sdk-python | ✅ | 模型执行整体外置捆绑 CLI（仅 Claude 系直连）；SDK 暴露 model/fallback_model/运行时 set_model，cost/usage/rate-limit 由 CLI 结构化回报 | src/claude_agent_sdk/types.py#ClaudeAgentOptions（model/fallback_model）；_internal/query.py#Query.set_model；types.py#ModelUsage |
| crewai | ✅ | LLM 类 `__new__` 工厂：原生 SDK 6 家优先（含各自 max_retries=2）+ LiteLLM 兜底百余模型；completion_cost 计价 + prompt cache 断点标记 + 工具级 SQLite 缓存 | lib/crewai/src/crewai/llm.py#LLM:371、:330 SUPPORTED_NATIVE_PROVIDERS；llms/cache.py#mark_cache_breakpoint（本次核验实锤） |
| dify | ✅ | model_runtime 抽象（graphon 外置库）+ 供应商全插件化（plugin_daemon）+ 错误感知冷却负载均衡（RateLimit 冷却 60s / Auth·Connection 10s）+ 配额结算 | api/core/model_manager.py#_round_robin_invoke；api/core/plugin/impl/model.py |
| llama_index | ✅ | core 统一 LLM 抽象（chat/complete/流式/结构化）+ Settings 全局注入 + 103 个官方 llms 集成包；无统一 usage 对象、无 LLM 级重试（仅限流器） | llama-index-core/llama_index/core/llms/llm.py#LLM；settings.py#Settings；rate_limiter.py#TokenBucketRateLimiter |
| agentscope | ✅ | 11 家 ChatModel + 11 家 formatter + YAML 模型卡目录；ChatModelBase 按各供应商声明的可重试异常重试 3 次；fallback 在 agent 层（ModelConfig.fallback_model） | src/agentscope/model/_base.py#ChatModelBase.__call__（retryable-exceptions）；src/agentscope/agent/_agent.py#_call_model |
| agentscope-java | ✅ | ModelRegistry（命名实例 + ServiceLoader SPI 工厂）+ 5 个官方 provider 扩展 + 可插拔 HTTP/WS 传输层；usage 含 cachedTokens、无 cost、无 router/fallback | agentscope-core/.../model/ModelRegistry.java#resolve；agentscope-core/.../model/ChatUsage.java |
| spring-ai-alibaba | 🟡 | provider 全交 Spring AI ChatClient（DashScope starter 甚至外置）；框架自身只做治理：modelfallback/modelretry 拦截器 + modelcalllimit 钩子 + Nacos 模型注入 | spring-ai-alibaba-agent-framework/.../agent/interceptor/modelfallback；starter-config-nacos/.../NacosModelInjector.java:46-49 |
| spring-ai | ✅ | ChatModel/ChatOptions SPI + 15 个官方 provider 模块 + Flux 流式 + RetryUtils（RetryTemplate，区分 Transient/NonTransient）+ Usage 元数据；无 router/fallback；语义缓存独立模块 | models/（15 模块）；spring-ai-retry#RetryUtils；vector-stores/spring-ai-redis-semantic-cache#SemanticCacheAdvisor（本次核验实锤） |

表注（二次核验修正）：
1. **langgraph4j 档案宣称「fallback 由 langchain4j 的 FallbackChatModel 等生态件承担」——不成立**。本次在 langchain4j 全仓 `rg -li "fallbackchatmodel|fallback.*chat.*model"` 零命中，`src/main` 内含 "fallback" 的 Java 类均与模型降级无关（ClassInstanceLoader/ParsingUtils 等）。langchain4j 主仓与 langgraph4j 双双没有模型级 fallback，Java 侧此项为共同空白。
2. **agent-framework 档案「无内置 router/fallback/retry」确认**：`python/packages/core/agent_framework/_clients.py` 检索 fallback/retry/router 零命中；openai 包亦无框架级 retry（OpenAI SDK 内部重试不计入）。
3. **adk-java 注册表范围确认**：LlmRegistry.java:40-42 仅 gemini-.* / apigee/.* / gemma-.* 三个正则；`Claude`（models/Claude.java:56，注入 AnthropicClient）确未注册，须手动实例化。
4. claude-agent-sdk 档案遗留 ⚠️ 保留：bedrock/vertex/foundry 仅出现在 types.py:1312-1315 的 `ModelUsage.provider` 注释枚举，SDK 无对应配置字段；CLI 侧如何启用（环境变量）不在本仓库可证范围内。

## 1.2 实现方式深析

### 派系 A：统一 provider 接口 + 集成包矩阵（「接口派」）

langchain、langchain4j、spring-ai、llama_index、agent-framework、dify 六家同构：核心库定义一个最小接口，每个供应商一个独立可裁剪的包/模块，靠标准测试套件约束集成质量。

- **接口形态的差异在「同步/流式是一体还是分体」**：langchain4j 把 `ChatModel` 与 `StreamingChatModel` 拆成两个接口（1.20+ 才补 `chatAsync` @Experimental）；spring-ai 是 `ChatModel.call(Prompt)` + `stream(Prompt)` 双方法同体返回 Reactor `Flux<ChatResponse>`；agent-framework 只有一个 `BaseChatClient`，`get_response`/`get_streaming_response` 同协议双方法；langchain 在 `BaseChatModel` 基类用 `_generate`/`_stream` 模板方法统一；llama_index 的 `LLM` 基类直接给出 chat/complete × sync/async/stream 全套方法族。分体式（langchain4j）换取实现门槛低，一体式（agent-framework）换取中间件只写一份。
- **集成质量治理**：langchain 有独立标准测试包 langchain-tests（`ChatModelUnitTests` 基类，集成包回归用）；dify 把 provider 全部推到 plugin_daemon 进程外（官方模型插件在外部仓库 dify-official-plugins，边界即插件协议）；llama_index 用 103 个集成包的体量换广度，但代价见派系 E——usage 与重试没有核心约定。
- **usage 结构**：langchain `UsageMetadata` 挂在 `AIMessage.usage_metadata` 且 merge 时自动累加；spring-ai `chat/metadata/Usage` + `UsageAccumulator` 跨工具轮累计；agent-framework `UsageDetails`+`add_usage_details` 跨层聚合（_types.py:433）。这一派普遍**只统计 token、不计价**。

### 派系 B：注册表 / 前缀字符串路由派

adk-python、adk-java、agentscope（双语）、openai-agents、crewai、langchain(init_chat_model)。共同点：模型用一个字符串声明，框架在运行时解析到实现。

- **正则注册表**：adk-python `LLMRegistry`（registry.py:62）按模型名正则匹配 BaseLlm 子类，LlmAgent.model 只填字符串；adk-java `LlmRegistry` 同构但默认仅 3 个 pattern（本次核验），广度外包给生态桥（派系 C）；agentscope 双语都用 `ModelRegistry` + `ServiceLoader`/`ModelProvider` SPI（Java 侧还按 ModelCacheKey 缓存实例）。registry 派的实现成本最低，但**默认覆盖面 = 注册的正则数**，兜底能力决定体验。
- **前缀路由**：openai-agents `MultiProvider`（multi_provider.py:62-252）按 `前缀/模型名` 路由——无前缀或 `openai/` 走 OpenAIProvider（Responses 或 ChatCompletions），内建 `litellm/`、`any-llm/` 惰性 fallback，`provider_map` 可注册自定义，`unknown_prefix_mode` 支持把任意 OpenAI 兼容端点透传。这是 17 家中路由语义最完整的实现。
- **工厂方法内路由**：crewai 的 `LLM.__new__`（llm.py:371）是独特变体——构造函数本身做路由：显式 provider → 模型名前缀表 → 命中 `SUPPORTED_NATIVE_PROVIDERS`（6 家原生 SDK）则原生直连，否则懒加载 LiteLLM 兜底。「原生优先拿全参数控制（含各家 max_retries、cache 断点），长尾推 LiteLLM」是介于自研与全代理之间的折中。
- **langchain 的 init_chat_model**（libs/langchain_v1/langchain/chat_models/base.py:195）：按 `provider:model` 字符串路由到集成包，本质是 registry 派在接口派之上的薄壳——两派并不互斥。

### 派系 C：生态桥接派（不自研 provider 面）

langgraph4j、spring-ai-alibaba、adk-java（contrib）。

- langgraph4j core 刻意零模型依赖，官方给 langchain4j 与 Spring AI 两套集成模块（AgentExecutorBuilder#chatModel / DefaultChatService），「用 JVM 生态最厚的两个模型抽象换广度」。
- adk-java 的 contrib/spring-ai、contrib/langchain4j 是 `SpringAI extends BaseLlm`/`LangChain4j extends BaseLlm` 单类桥——相当于把 LiteLlm 的角色交给两个 Java 框架。
- spring-ai-alibaba 更极端：连 DashScope starter 都外置（本仓库仅 `dashscope-sdk-java 2.15.1` 版本管理与 admin 侧消费方），框架本体只做治理件：`interceptor/modelfallback`、`interceptor/modelretry`、`hook/modelcalllimit`、Nacos 下发模型配置反射替换 chatOptions（NacosModelInjector.java:46-49）。**「阿里框架不强绑阿里模型」是可指证的设计决策。**

### 派系 D：模型层留白 / 外置运行时派

langgraph、deepagents、claude-agent-sdk。

- langgraph 只提供**节点级策略对象**：`RetryPolicy`（types.py:418）、`TimeoutPolicy`、`CachePolicy`（key_func+ttl）作用于任意图节点，配合 `BaseCache/RedisCache`（libs/checkpoint/langgraph/cache/）缓存 LLM 调用结果——注意这是**函数级任务缓存**（func API @task 的结果），不是语义缓存；provider 适配完全交给 langchain-core/partners。
- deepagents 在 langchain 之上加的是**模型画像层**而非接入层：`ProviderProfile`（OpenAI 默认走 Responses API、OpenRouter/NVIDIA 归因头）与 `HarnessProfile`（按 opus/sonnet/haiku/codex/nemotron 调整 prompt 后缀与中间件）双注册表，支持 entry-point 插件。成本统计不在核心而在外围 dcode（`CostTrackingMiddleware`，cost_tracking.py:2294，本次核验实锤；另有 `CodeModelRetryMiddleware` model_retry.py:1031）。
- claude-agent-sdk 把整个模型执行面外置进捆绑的 Claude Code CLI 二进制：SDK 侧只有配置面（model/fallback_model/betas→CLI flags）与回报面（`ModelUsage` 含 per-model tokens/缓存/costUSD/contextWindow/provider、`ResultMessage.total_cost_usd`、`RateLimitEvent`）。**计价（USD）由 CLI 算好回报**，是 17 家中「成本计算位置」最远离调用方的一例。

### 横切对比 1：路由 / 降级的真实实现盘点

| 框架 | fallback 真实现 | 位置与机制 |
|---|---|---|
| adk-python | ✅ | `FallbackModel`（_fallback_model.py:207）包装多模型顺序回退，:182 注释明确统一各家 provider 错误归一化后再判定 |
| agentscope (Py) | ✅ | agent 层 `ModelConfig.fallback_model` + `_call_model`（_agent.py:3281）双模型链，每个模型各自 max_retries |
| langchain | ✅ | `ModelFallbackMiddleware`/`ModelRetryMiddleware`（1.x 中间件）+ LCEL `RunnableWithFallbacks`（0.x）双轨 |
| spring-ai-alibaba | ✅ | `interceptor/modelfallback`（拦截器链，非模型类） |
| claude-agent-sdk | ✅ | `fallback_model` 透传 CLI（执行在 CLI，SDK 侧【文档】级） |
| dify | ✅（凭据池级） | `ModelInstance._round_robin_invoke`（model_manager.py:429-478）round-robin 换凭据 + 按错误类型差异化冷却（RateLimit 60s / Auth·Connection 10s），且有控制台 LB 配置管理面——是唯一把「多凭据负载均衡」做成产品功能的 |
| openai-agents | 🟡（半） | MultiProvider 的 litellm/any-llm 是**接入兜底**而非运行时故障切换；无模型链 |
| 其余 10 家 | ❌ | langchain4j/langgraph4j（Java 双双空白，见核验注 1）、agent-framework、spring-ai（要求用户 Spring `@Primary`/自建组合）、crewai、llama_index、agentscope-java、adk-java、langgraph、deepagents 核心（可组合 langchain 中间件但非默认栈） |

结论：**fallback 的主流实现位置不在模型抽象层，而在 agent 层（agentscope/langchain 中间件）或平台层（dify）**——模型接口保持纯粹、降级是编排语义，是多数框架的隐性共识。

### 横切对比 2：重试在哪一层、什么策略

| 层 | 框架与机制 |
|---|---|
| provider 类内 | langchain4j `OpenAiChatModel.maxRetries=2` 走 core `RetryUtils`（指数退避+jitter）；crewai openai/anthropic completion 默认 `max_retries=2`；agentscope `ChatModelBase.__call__` 按**各供应商声明的 `_get_retryable_exceptions()`** 重试默认 3 次、固定 `retry_delay`（且 CancelledError 转 INTERRUPTED 响应而非异常）；openai-agents `ModelSettings.retry: ModelRetrySettings`（含退避，_openai_retry.py） |
| SDK/模板层 | spring-ai `RetryUtils`（spring RetryTemplate，区分 `TransientAiException`/`NonTransientAiException`——显式异常分类是独一份） |
| 图节点层 | langgraph `RetryPolicy`（任意节点）；langgraph4j `RetryPolicy#asHook`（maxAttempts 默认 3、可配 retryOn）——重试只是又一个 hook |
| agent 循环层 | langchain `ModelRetryMiddleware`；dcode `CodeModelRetryMiddleware`（外围） |
| 无 | agent-framework（用户经 ChatMiddleware 自建）、adk-java（models/ 下无 retry 实现）、llama_index（core 无 LLM 重试，只有 `TokenBucket/SlidingWindow` **限流器**——限流≠重试）、adk-python（靠 provider SDK 自身） |

值得注意的分化：**Python 系倾向 provider 层声明式重试，Java 系倾向节点/拦截器层组装式重试**；agentscope 的「供应商声明可重试异常类型」是把重试语义正确地绑定到错误分类的最认真实现。

### 横切对比 3：用量统计与成本计算位置

- **token 结构统一、计价分裂**：usage 对象人人有（langchain UsageMetadata 自动累加 / openai-agents `Usage` 含 cached/cache_write/reasoning 细分最全 / agentscope ChatUsage 含 cachedTokens / adk `LlmResponse.usage_metadata` / spring-ai Usage+RateLimit / dify LLMUsage），但**换算成钱的只有 4 家**：claude CLI（total_cost_usd 回报）、dify（`total_price/currency` 落 Message 表 + QuotaManagedModelInstance 配额结算）、crewai（`completion_cost`，llm.py:373）、dcode CostTrackingMiddleware（bundled prices）。llama_index 甚至连统一 usage 对象都没有（各集成从 raw 透传，openai 集成 base.py:691 自行取 raw_response.usage）。
- agentscope-java 的 ChatUsage 无 cost、adk 双语无 cost——「计价是平台/产品职能，不是库职能」的边界感普遍存在。

### 横切对比 4：缓存的三个物种

1. **LLM 结果缓存（精确匹配）**：langchain `BaseCache/InMemoryCache`（caches.py:32，进阶实现在 community）；langgraph `BaseCache/RedisCache`（配合节点 CachePolicy，key_func+ttl）；crewai 工具级 SQLite 缓存（`agents/cache/cache_handler.py:10`，Crew.cache=True）。
2. **语义缓存（相似度命中）**：17 家只有 spring-ai 有官方模块——`vector-stores/spring-ai-redis-semantic-cache` 的 `SemanticCacheAdvisor`（Redis 相似度命中直接返回，本次核验主类存在）。dify 档案明确「LLM 语义缓存 ❌ 未见表级实现」。
3. **prompt cache（供应商前缀缓存）**：不是缓存响应而是缓存请求前缀——openai-agents `prompt_cache_key.py` + `ModelSettings.prompt_cache_retention/options` 做会话粘性管理；crewai `mark_cache_breakpoint`（llms/cache.py:27，provider 无关的断点标记，system 尾+user 尾）；llama_index `CacheControl/CachePoint` 内容块级标注；adk-python `GeminiContextCacheManager` + `ContextCacheRequestProcessor`（从 session 事件恢复 cache 元数据，显式内容缓存）；deepagents `_prompt_caching.py`（Anthropic 无条件 + Bedrock/Fireworks 按安装）。**prompt cache 已从「供应商私有参数」升级为框架显式管理对象**（栈序设计见维度 2）。

## 1.3 跨语言对齐

| 对 | 子能力 | Python 侧 | Java 侧 | 对齐度 |
|---|---|---|---|---|
| langgraph ↔ langgraph4j | 模型抽象 | 两侧都不做（生态承载），性质相同 | 同 | **对等** |
| | 节点级重试 | `RetryPolicy`（types.py:418，指数退避可配） | `RetryPolicy#asHook`（maxAttempts=3） | **已对齐**（机制不同：参数对象 vs hook） |
| | LLM 结果缓存 | `BaseCache`/`RedisCache` + `CachePolicy`（key_func+ttl） | 无对应物 | **缺失** |
| adk-python(2.9) ↔ adk-java(1.9) | 注册表 | LLMRegistry 多 adapter（gemini/google/lite_llm/anthropic/gemma/apigee + labs openai） | LlmRegistry 仅 3 正则；Claude 手动实例化（核验确认） | **部分** |
| | fallback | `FallbackModel` 错误归一化顺序回退 | 无 | **缺失** |
| | 广度策略 | LiteLlm 代理百余模型 | SpringAI/LangChain4j 双桥（Java 独有取法） | **部分**（等价广度、不同载体） |
| | 显式 prompt/内容缓存 | GeminiContextCacheManager + ContextCacheRequestProcessor | 无 | **缺失** |
| agentscope ↔ agentscope-java | provider 数 | 11 家（含 deepseek/moonshot/volcengine/xai/openai_response）+ embedding/tts 域 | 5 家扩展 + starter；无 embedding/tts | **部分** |
| | 重试 | ChatModelBase 按供应商声明异常重试 3 次 | 无框架级重试 | **缺失** |
| | fallback | agent 层 ModelConfig.fallback_model | Registry 只解析不路由 | **缺失** |
| | 传输层 | 各 provider 自带 client | 可插拔 `model/transport/`（JDK/OkHttp+代理+WebSocket）——Java 工程化加分 | Java 局部超出 |

注：版本差是 adk 对齐表的重要噪音（Python 2.9 vs Java 1.9，Python 领先一个大版本），「缺失」可能含版本因素而非平台定位差。

## 1.4 取舍与趋势

1. **接口收敛、路由缺席**：「一个统一协议 + N 个集成包」已成标准答案（6+ 家同构），但模型级 fallback/router 只有 6/17 家有真实现，且位置分散（模型包装器/agent 中间件/拦截器/平台凭据池四种形态各一家）——**多数框架把降级视为编排问题而非接入问题**，留白给中间件生态。
2. **重试下沉到 provider、上浮到节点，唯独不在框架核心**：provider 类内声明式重试（langchain4j/crewai/agentscope）与图节点 RetryPolicy（langgraph 系）是两种成熟范式；agent-framework、adk-java、llama_index 的核心层完全不管重试，是接入面「薄核心」哲学的直接代价。
3. **prompt cache 进入框架管辖范围**：openai-agents 的 cache key 生命周期管理、crewai 的 provider 无关断点标记、deepagents 的栈序设计、adk 的 Gemini 显式内容缓存、llama_index 的块级 CacheControl——五家不约而同把供应商前缀缓存从「透传参数」升格为「框架编排对象」，驱动因素是长 agent 会话的成本结构（详见维度 2 的栈序分析）。
4. **成本计价是平台职能而非库职能**：token usage 人人有、USD 计价只有 CLI/平台/产品化外围做（claude CLI、dify、crewai、dcode）；库框架普遍止步于 token——企业自建成本核算仍需自拼价目表。
5. **语义缓存全军覆没于一家**：只有 spring-ai 有官方语义缓存模块（Redis 相似度命中）。在人人讲 RAG 的 17 家里，LLM 响应级语义缓存反而无人跟进——命中正确性风险（相似≠同义）可能高于收益是隐性共识。
6. **Java 侧模型接入靠「桥」不靠「量」**：langgraph4j 双集成、adk-java 双桥、spring-ai-alibaba 全托管给 Spring AI——JVM 生态把 provider 广度问题外包给 langchain4j/Spring AI 两个枢纽，与 Python 侧「每家自带 15-103 个集成包」形成生态结构差异。
