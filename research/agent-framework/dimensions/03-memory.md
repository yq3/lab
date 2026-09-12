# 维度 3：记忆（Memory）

> 本维度回答：短期会话记忆用什么结构、什么窗口策略；长期记忆是否区分语义（semantic）/情景（episodic）/程序性（procedural）知识并如何实现；有没有用户画像（user profile）；写入策略（何时写、写什么、谁决定）；遗忘/淘汰机制；检索方式（向量/关键词/图/LLM 路由）；以及记忆抽象与 session 持久化的边界。17 个框架总体格局：**「短期记忆」正在与执行状态合一（checkpoint/AgentState 即会话记忆，独立 Memory 类被淘汰）；「长期记忆」分裂为文件自学习（AGENTS.md 派）、托管服务（Vertex 派）、向量+LLM 打分（LanceDB/Fact 抽取派）三条路线；「遗忘」几乎全线缺位；「用户画像」17 家零实现**。评级沿用各档案；本文件对 4 处证据做源码二次核验（crewai 评分公式/半衰期/合并阈值、agentscope-java 弃用 API、langgraph4j Store 缺失），全部实锤，见表注。

## 3.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | 🟡 | 会话记忆=checkpointer、跨线程=BaseStore 全透传 langgraph；摘要中间件兼作短时管理；长期记忆/画像无抽象（仅 classic 的 ConversationBufferMemory 遗留） | libs/langchain_v1/langchain/agents/factory.py#L847-L850（checkpointer/store 参数）；libs/langchain/langchain_classic/memory/buffer.py#L24【legacy】 |
| langgraph | ✅ | 双层范本：thread 内 checkpoint 短期记忆 + 跨 thread BaseStore 长期记忆（namespace+key 文档、search 语义检索、put(index=) 字段级向量索引） | libs/checkpoint/.../store/base/__init__.py#BaseStore（search :779、put index :856-874）、store/base/embed.py#EmbeddingsLambda |
| langgraph4j | 🔶 | 仅 thread 级 checkpoint（MemorySaver 等 8 后端）；跨线程 Store 无对应物（本次核验 core 无任何 store 文件，实锤缺失） | langgraph4j-core/.../checkpoint/MemorySaver.java；RunnableConfig.java#threadId |
| langchain4j | ✅ | ChatMemory 双窗口实现（MessageWindow 条数/TokenWindow token）+ ChatMemoryStore SPI + ChatMemoryProvider 多会话；无 remove/forget API、无长期记忆（跨会话走 RAG 路线） | langchain4j/src/main/java/dev/langchain4j/memory/chat/{MessageWindow,TokenWindow}ChatMemory.java；langchain4j-core/.../store/memory/chat/ |
| deepagents | ✅（文件式） | MemoryMiddleware 实现 agents.md 规范：AGENTS.md 拼进 system prompt `<agent_memory>`，教模型用 edit_file 自学习写回；跨线程经 CompositeBackend 路由 `/memories/`→StoreBackend(langgraph BaseStore)；DB/向量记忆在 talon 实验包 | libs/deepagents/deepagents/middleware/memory.py#MemoryMiddleware:88（含注入防御提示词 :112-117）；backends/store.py#StoreBackend |
| agent-framework | ✅ | core：AgentSession+SessionStore（FileSessionStore）短期；harness：文件式长期记忆 MemoryStore/MemoryFileStore/MemoryContextProvider（MemoryTopicRecord 话题索引）+ mem0/redis 生态 context provider；无 forget 抽象 | python/packages/core/agent_framework/_sessions.py#SessionStore:1785；_harness/_memory.py#MemoryStore:561/#MemoryContextProvider:976 |
| adk-python | ✅ | BaseMemoryService 两方法族（add_session_to_memory/search_memory）三实现：InMemory、VertexAiRag（托管 RAG 语料）、VertexAiMemoryBank（托管记忆库）；preload_memory_tool/load_memory_tool 工具化注入 | src/google/adk/memory/base_memory_service.py:44、vertex_ai_rag_memory_service.py:167、tools/preload_memory_tool.py |
| adk-java | 🟡 | 接口三方法与 Python 对齐，但实现仅 InMemoryMemoryService + contrib FirestoreMemoryService；无 VertexAiRag/MemoryBank 对应物 | core/.../memory/InMemoryMemoryService.java；contrib/firestore-session-service/.../FirestoreMemoryService.java |
| openai-agents-python | ✅ | Session 极小协议（session_id + get/add/pop/clear 四方法）+ SQLite/OpenAIConversations 核心实现 + 主包 extensions 后端（Redis/Mongo/SQLAlchemy/Dapr/EncryptedSession 加密切面）；长期记忆/画像无 | src/agents/memory/session.py#Session:43；extensions/memory/__init__.py:25-50、encrypt_session.py#EncryptedSession |
| claude-agent-sdk-python | 🟡 | 无 SDK 记忆抽象；CLAUDE.md/auto-memory/子代理 memory(user/project/local) 由 CLI 与 .claude 目录约定承载，SDK 仅 setting_sources 开关与 memoryFiles 回报 | src/claude_agent_sdk/types.py#ClaudeAgentOptions.setting_sources:2218-2228、#AgentDefinition.memory、#ContextUsageResponse.memoryFiles:801 |
| crewai | ✅ | v1.15 统一 Memory：EncodingFlow 写入（批量嵌入+N 路并发 LLM 抽取 scope/类别/重要性+0.85 相似度合并）+ RecallFlow 置信度路由召回 + 复合评分（semantic/recency/importance 加权、30 天半衰期）+ LanceDB 默认存储（本次核验公式与阈值实锤） | lib/crewai/src/crewai/memory/unified_memory.py#Memory:76、encoding_flow.py:75、recall_flow.py:58、types.py#MemoryScoringConfig（recency_half_life_days=30、consolidation_threshold=0.85） |
| dify | ✅（会话级；长期 ❌） | Conversation/Message 全量持久化 + ConversationVariable 工作流会话变量 + 标注回复（相似问命中直接回放答案，score_threshold 可配）；跨会话长期记忆/画像/遗忘无 | api/models/model.py:1124/1463；api/models/workflow.py#ConversationVariable:1521；api/services/annotation_service.py |
| llama_index | ✅ | ChatMemoryBuffer（token_limit）/ChatSummaryMemoryBuffer（超限自动摘要）+ 可组合 memory blocks（Static 静态注入/FactExtraction LLM 事实抽取/Vector 向量检索回注）+ SimpleComposableMemory/VectorMemory + chat_store 持久化 + mem0/bedrock-agentcore 生态 | llama-index-core/.../memory/chat_memory_buffer.py:19、chat_summary_memory_buffer.py:26、memory_blocks/{static,fact,vector}.py |
| agentscope | ✅ | 会话=AgentState.context+summary（随 state 持久化）；长期记忆三中间件：自研 AgenticMemoryMiddleware（memory.md 文件式+frontmatter+清单注入+相关文件检索）/Mem0/ReMe（extras）；无 user profile | src/agentscope/state/_state.py#AgentState；middleware/_longterm_memory/__init__.py、_agentic_memory/_middleware.py:359 |
| agentscope-java | 🟡 | core memory 包整体 @Deprecated(forRemoval, since 2.0.0)（本次核验实锤）；长期记忆走旧 API 的 3 个官方扩展（mem0/bailian/reme）；会话上下文归 AgentState；harness 侧 MemoryConsolidator/FlushManager 维持运转 | agentscope-core/.../memory/Memory.java:34、LongTermMemory.java:70（@Deprecated 核验）；agentscope-extensions-mem/{mem0,bailian,reme}（核验确认引用 LongTermMemory） |
| spring-ai-alibaba | ✅ | 会话=messages key（AppendStrategy）+ checkpoint 10 后端；跨线程 KV Store 5 实现（Memory/FileSystem/Redis/Mongo/Database，namespace+key）；长期画像/遗忘无 | spring-ai-alibaba-graph-core/.../graph/checkpoint/savers/（10 个）、store/stores/ |
| spring-ai | ✅ | ChatMemory 4 方法 + MessageWindowChatMemory 唯一策略 + ChatMemoryRepository 5 官方后端（JDBC/Cassandra/Mongo/Neo4j/Redis）+ 3 类 memory advisor（含 VectorStoreChatMemoryAdvisor 向量长期记忆，带 XML 转义防注入设计）；无画像/遗忘（仅 clear） | spring-ai-model/.../chat/memory/ChatMemory.java、MessageWindowChatMemory.java:107-113；advisors/.../VectorStoreChatMemoryAdvisor |

表注（二次核验，全部实锤）：① crewai 复合评分公式确认于 `lib/crewai/src/crewai/memory/types.py:366-368`（`composite = semantic_n*similarity + recency_n*decay + importance_n*importance`，`decay = 0.5^(age_days/half_life_days)`），`recency_half_life_days` 默认 30（:175-177）、`consolidation_threshold` 默认 0.85（LLM 决定 merge/update/delete，置 1.0 可禁用）、`consolidation_limit=5`；RecallFlow 的 confidence 路由与 `exploration_budget` 确认于 recall_flow.py:53-284。② agentscope-java `Memory.java:34`/`LongTermMemory.java:70` 均 `@Deprecated(forRemoval = true, since = "2.0.0")`；mem0/bailian/reme 三扩展的 `*LongTermMemory` 类确认引用弃用 API。③ langgraph4j core main 下 `find -iname "*store*"` 零文件——BaseStore 等价物确实不存在。④ dify `token_buffer_memory` 见维度 2（属上下文工程而非记忆抽象）。

## 3.2 实现方式深析

### 议题 1：短期会话记忆——结构正在与执行状态合一

按「记忆载体」分三派：

**派系 A：记忆 = 执行状态（checkpoint/AgentState 即会话记忆）**——langgraph（thread 内 BaseCheckpointSaver，消息列表是 checkpoint 的一部分）、langgraph4j（AgentState 快照+MemorySaver(threadId)）、spring-ai-alibaba（messages key + AppendStrategy + saver）、agentscope 双语（AgentState.context 原始消息 + AgentState.summary 压缩摘要，v2 已删除 v1 的 InMemoryMemory 类）、dify（Conversation/Message 数据库表）、openai-agents（Session 四方法协议 + RunState 快照，session_id 承载 thread 语义）、claude sdk（CLI 本地 JSONL 转录即真相源）、deepagents/langchain（透传 langgraph checkpointer）。这一派的优势：会话记忆天然获得断点续跑/时间旅行/跨进程恢复（维度 10 的能力免费复用）；代价：记忆读写与执行持久化耦合，无法独立淘汰。

**派系 B：独立 ChatMemory 抽象（Java 系主流）**——langchain4j（`ChatMemory` 接口 + `ChatMemoryProvider`（memoryId→ChatMemory 多会话）+ `ChatMemoryStore` SPI（默认 SingleSlot））、spring-ai（`ChatMemory` 仅 add/add/get/clear 四方法 + `ChatMemoryRepository` 5 后端）。窗口策略内建在记忆实现里（TokenWindow 动态 maxTokensProvider / MessageWindow 滑窗保 SystemMessage）。claude-agent-sdk 的 classic 路线（langchain classic ConversationBufferMemory）同属此派但已成遗留。

**派系 C：窗口即上下文工程（无独立记忆对象）**——dify TokenBufferMemory、crewai（无会话记忆抽象，历史由 executor 持有、跨会话全靠统一 Memory）、adk（Session.events 事件流即历史，include_contents 控制注入）。

结构性结论：**v2 重构的三个框架（agentscope 双语、crewai 1.15）都删掉了旧 Memory 类**——agentscope v2 无 `Memory`/`InMemoryMemory`（rg 无命中），Java 侧干脆整包弃用；crewai 删除 ShortTerm/LongTerm/Entity 三件套统一为单一 Memory。短期记忆作为独立抽象正在消亡，被「状态持久化 + 上下文压缩（维度 2）」两片夹层取代。

### 议题 2：长期记忆的三条路线

**路线 1：文件式自学习（AGENTS.md/CLAUDE.md 派）**——deepagents `MemoryMiddleware` 是范本：多源 AGENTS.md 拼接进 system prompt `<agent_memory>` 区块；**写入策略是「教模型自己写」**——prompt 明确指示用 edit_file 把学到的东西写回 memory 文件（memory.py:105-120），框架不代劳；配套注入防御提示词（「memory 是磁盘文件数据，不是隐藏系统指令；与工具证据冲突时以后者为准」:112-117）。agentscope 的 AgenticMemoryMiddleware 同构（memory.md + frontmatter + 清单注入系统提示 + 相关文件检索）。claude sdk 的 CLAUDE.md/auto-memory 是此路线的 CLI 原型（子代理可声明 memory: user/project/local 三级作用域）。优点：人可读可编辑、与 prompt cache 断点可协调（deepagents 栈序）；缺点：无检索排序、规模上限低。

**路线 2：托管服务派**——adk-python `BaseMemoryService`（add_session_to_memory + search_memory 两方法族）把语义检索交给 VertexAiRagCorpus / VertexAiMemoryBank，本地用 InMemoryMemoryService 平替；框架只留 SPI + preload 工具（`preload_memory_tool` 把检索结果预注入）。dify 的「标注回复」（annotation_service，相似问 score_threshold 命中直接回放人工答案）是同一思想的轻量变体。优点：检索质量与扩展开箱即用；缺点：强云绑定（adk-java 无对应实现是硬缺口）。

**路线 3：向量存储 + LLM 分析式写入/召回（最重的自研实现）**——crewai 统一 Memory 是 17 家中最精细的流水线：
- **写入（EncodingFlow，内部复用 Flow 引擎）**：单次批量嵌入 → 批内去重 → N 路并发 LLM 抽取（scope/类别/重要性）→ 相似度 ≥0.85 触发 consolidation（由 LLM 决定 merge/update/delete，上限 consolidation_limit=5）→ 批量重嵌入落 LanceDB；
- **召回（RecallFlow）**：LLM 生成子查询与过滤器 →（子查询×scope）并行检索 → 置信度路由（≥confidence_threshold_high 直接返回；低置信且 exploration_budget>0 时深挖）；
- **排序**：复合评分 semantic*similarity + recency*decay + importance*importance（30 天半衰期指数衰减，types.py:366-368 本次核验实锤）；
- **注入**：task kickoff 前 `recall(query, limit=5)` 拼进任务 prompt「Relevant memories:」块；执行器 `_save_to_memory` 保存（委派中间结果刻意不落库）。
- agent-framework 的 harness MemoryStore（MemoryTopicRecord 话题索引文件）+ mem0/redis context provider、llama_index 的 memory blocks、spring-ai 的 VectorStoreChatMemoryAdvisor 属于此路线的轻量版。

**语义/情景/程序性知识三分法的实现现状**：**没有任何一家提供显式三类型抽象**。最接近的映射：程序性知识（how-to）→ AGENTS.md 派的文件记忆（deepagents 明示教模型记录 working style/preferences）；情景知识（事件）→ checkpoint/session 历史 + crewai 会话写入记忆；语义知识（事实）→ FactExtraction block（llama_index）/crewai LLM 抽取/importance 打分。知识类型学停留在学术分类，工程上被「抽取字段 + 评分权重」吸收。

**用户画像（user profile）：17 家 0 实现**。最接近的替身：adk 的 `user:` state 前缀（命名空间而非画像）、claude 子代理 memory 作用域（user 级）、langgraph Store 的 namespace 约定（`("users", user_id)` 惯例，无画像 schema）。画像作为一等抽象（偏好/画像更新/多用户隔离）整体缺位。

### 议题 3：写入策略——何时写、写什么、谁决定

| 框架 | 写入时机 | 写什么 | 决定者 |
|---|---|---|---|
| crewai | 每次任务执行后 `_save_to_memory` | agent 最终输出与中间结论（委派中间结果不落库） | 框架自动 + LLM 抽取字段 |
| deepagents | 无自动写入 | 模型认为值得记的学习 | **模型自主**（edit_file 写回，框架只给提示词） |
| llama_index FactExtraction block | Memory 压力 flush 时（token_flush_size） | 从被弹出旧消息抽取的事实 | 框架触发 + LLM 抽取 |
| agentscope Agentic | 中间件时机 | memory.md 增量 | 模型自主（文件编辑） |
| agent-framework harness | MemoryFlushMiddleware/Consolidator | 话题索引更新 | 框架（harness 生命周期） |
| adk-python | 显式 `add_session_to_memory` 调用 | 整个 session 事件 | **开发者显式调用**（无自动触发） |
| langgraph BaseStore | 工具/节点内 put() | 任意文档（index= 声明索引字段） | 开发者/模型（经 InjectedStore 工具） |
| dify | 会话自动持久化；标注人工录入 | Message 全量 / 人工标注对 | 框架/人工 |
| claude sdk | CLI auto-memory 时机【文档】 | CLAUDE.md 类文件 | CLI |

分化明显：**「LLM 分析式写入」（crewai/llama_index）与「模型自主写入」（AGENTS.md 派）是两种新兴哲学**——前者框架控制质量（打分/合并/去重），后者把记忆当 agent 的自然行为；传统「全量自动存」（session 持久化）则退守为短期记忆职责。

### 议题 4：遗忘/淘汰——几乎全线缺位

显式 forget API 盘点：langchain4j ChatMemory **无 remove/forget/clear API**（档案 grep 零命中）；spring-ai 仅 `clear(conversationId)` 全清；crewai 无 forget API、仅 CLI `reset-memories` 清库；agent-framework 档案明示「未见 forget/淘汰策略抽象」。实际存在的三类替代物：
1. **评分衰减**（不删除、只是排不进前列）：crewai recency 半衰期 30 天；
2. **合并去重**：crewai consolidation（LLM 决定 merge/update/delete——最接近真遗忘的机制）、agentscope-java MemoryConsolidator；
3. **窗口驱逐**：所有 TokenWindow/MessageWindow（短期侧）与 adk 事件压缩。
即：**长期记忆的「遗忘」目前只能靠合并降权，无法按策略删除**（如 GDPR 式按用户删除、按主题过期），企业合规场景需要自行在存储层实现。

### 议题 5：检索方式

- **向量检索**：langgraph BaseStore.search（put(index=) 字段级向量索引 + EmbeddingsLambda 适配任意 embed 函数）、crewai LanceDB（后台自动 compact）、spring-ai VectorStoreChatMemoryAdvisor、llama_index VectorMemoryBlock、adk VertexAiRag。
- **LLM 路由式检索**：crewai RecallFlow（LLM 生成子查询 + 置信度决定是否深挖，exploration_budget 限额）——检索本身被建模为一个小 agent 循环。
- **文件/关键词式**：deepagents grep/glob over /memories/（agentic 检索）、agentscope AgenticMemory 相关文件检索、claude CLI（文件系统即记忆库）。
- **相似度匹配回放**：dify 标注回复（score_threshold）。
- **图检索**：无一家在记忆维度使用图（spring-ai 有 Neo4j memory repository 但只是会话存储载体，非图查询）。

### 议题 6：记忆与 session 持久化的边界

普遍清晰的三层分界（以最典型的 langgraph/adk/agentscope 为准）：
1. **会话恢复层**（SessionStore/SessionService/checkpointer）：保证崩溃后继续跑——存的是执行状态（含未完成工具调用、HITL 挂起点），见各档案维度 10/11；
2. **短期记忆层**：当前对话的消息历史，多为第 1 层的子集（checkpoint 内 messages / AgentState.context / Session.events）；
3. **长期记忆层**（BaseStore/MemoryService/Memory 中间件）：跨会话、跨 thread，按语义检索注入。

边界设计最干净的是 agent-framework（AgentSession/SessionStore 管恢复，MemoryContextProvider/HistoryProvider 是**注入接口**而非存储接口）与 openai-agents（Session 是纯历史容器，RunState 才是执行快照，两者正交）。最模糊的是 claude sdk（本地 JSONL 同时是执行转录与记忆来源）与 dify（Message 表兼任一切，长期记忆干脆缺席）。

## 3.3 跨语言对齐

| 对 | 子能力 | Python 侧 | Java 侧 | 对齐度 |
|---|---|---|---|---|
| langgraph ↔ langgraph4j | 短期（checkpoint） | BaseCheckpointSaver + InMemory/Sqlite/Postgres | BaseCheckpointSaver SPI + 8 外部 saver（Java 后端更多） | **已对齐（Java 广度超出）** |
| | 长期（跨线程 Store） | BaseStore：namespace+key、search 语义检索、字段级向量索引 | 无任何对应物（核验：core 无 store 文件） | **缺失**——Python 灵魂能力之一在 Java 缺位 |
| adk-python(2.9) ↔ adk-java(1.9) | MemoryService 接口 | add_session_to_memory + search_memory 两方法族 | sessionToMemory/searchMemory 三方法（语义同构） | **已对齐（接口层）** |
| | 实现 | InMemory + VertexAiRag + VertexAiMemoryBank（3） | InMemory + contrib Firestore（1+1，无 RAG 记忆库） | **部分**（云记忆库缺失，含版本差因素） |
| | 记忆工具化 | preload_memory_tool/load_memory_tool | LoadMemoryTool/LoadArtifactsTool 思路存在 | **已对齐（思路）** |
| agentscope ↔ agentscope-java | 短期会话 | AgentState.context+summary（v2 删除 Memory 类） | AgentState 同构；core memory 包整包弃用 | **已对齐** |
| | 长期记忆中间件 | `middleware/_longterm_memory/` **正式非弃用**：Agentic（自研文件式）/Mem0/ReMe | 3 扩展（mem0/bailian/reme）挂在 @Deprecated(forRemoval) 的 LongTermMemory 上；bailian 为 Java 独有后端 | **部分且倒挂**：Java 有实现无未来（API 将移除），Python 有正式抽象；Java 需迁移才能延续 |
| | 记忆运维 | —（无对应物） | harness MemoryConsolidator/FlushManager/BackgroundTasks + SessionTree/TranscriptWriter | Java 局部超出 |

## 3.4 取舍与趋势

1. **短期记忆抽象正在消亡，与执行状态合一**：agentscope v2 删 Memory 类、Java 侧整包弃用、crewai 删三件套、langchain 仅在 classic 保留——「会话记忆」被 checkpointer/AgentState/Session 吸收，独立 ChatMemory 只在 Java 库系（langchain4j/spring-ai）作为低门槛入门抽象存续。这实质是把「记住了什么」的定义权从记忆模块移交给上下文压缩层（维度 2）。
2. **长期记忆三分天下，且与商业模型强相关**：文件自学习派（deepagents/agentscope/claude——harness 与 CLI 产品，人可审计优先）、托管服务派（adk——云平台导流优先）、向量+LLM 分析派（crewai/llama_index/spring-ai advisor——库框架，可控性优先）。选型时这比功能清单更能预测长期演进方向。
3. **写入策略从「自动全存」转向「LLM 分析式/模型自主式」**：crewai 的打分-合并流水线、llama_index 的事实抽取、deepagents 的「教模型写文件」是三种新范式；纯粹自动保存（session 持久化）退守短期层。写入质量治理（去重、consolidation、重要性打分）成为长期记忆的核心成本所在。
4. **遗忘是全行业空白**：无一家有策略化 forget（按用户/主题/时效删除）；半衰期降权 + LLM 决定合并是仅有的近似物。随着记忆系统走向生产（多用户合规场景），这是下一个必争之地。
5. **用户画像零实现、知识类型学无人落地**：语义/情景/程序性三分法没有任何显式抽象承接，用户画像无一家做（最多有 user 命名空间）；框架层的记忆抽象停在「文档+向量+评分」，画像与知识分类被留给应用层——这与其他维度（fallback、guardrail）「框架留白给编排层」的取向一致。
6. **记忆检索出现「agentic 化」迹象**：crewai RecallFlow 把检索建模为 LLM 生成子查询 + 置信度深挖的小循环、deepagents 用 grep/glob 让模型在记忆文件系统里自主检索——与 RAG 管线式「一次检索一次注入」形成路线之争；后者（向量单发）仍是多数，前者在 harness 类框架中扩张。
