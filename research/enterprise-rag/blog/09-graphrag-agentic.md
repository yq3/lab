# 09 | GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

系列写到第九篇，该正面处理两个「话题度远高于使用率」的技术了。GraphRAG 与 Agentic RAG 有三个共同点：都是对朴素 RAG 真实短板的回应；都贵——一个贵在索引成本，一个贵在查询时延与不可预测性；都频繁出现在方案评审里，而生产渗透率远低于 PPT 渗透率。本篇基于 22 仓源码调研档案与四家厂商官方口径，把「什么时候该上、什么时候是过度设计」说清楚，给出一套可以直接抄进评审记录的判断框架。

## 一、先说清楚它们各自补什么洞

向量检索有两个结构性盲区，理解了这两个盲区，就理解了这两项技术为什么存在。

**盲区一：全局性问题。**「这批文档的主要主题是什么」「供应商合同里最常见的风险条款是哪几类」——这类问题没有一段可以直接「相似匹配」的文本。embedding 检索的语义是「找到与 query 相似的 chunk」，而全局问题的答案分散在整个语料里，任何单个 chunk 都只是它的一个碎片。检索器没有东西可命中。

**盲区二：多跳关联。**文档 A 说「项目 X 依赖组件 Y」，文档 B 说「组件 Y 在 3 月发现漏洞」。问「项目 X 有什么风险」需要同时命中 A 和 B，并把它们连起来。单轮向量检索对第二跳的召回是无能为力的——query 里往往根本没有「Y」这个词。

GraphRAG 用「实体图 + 预计算的结构化摘要」正面补第一个洞（顺带部分缓解第二个）；Agentic RAG 用「LLM 自主决定何时检索、检索什么、读完要不要再检索」补第二个洞（顺带部分缓解第一个）。方向不同，成本结构也不同：GraphRAG 的代价主要付在**索引期**，Agentic RAG 的代价主要付在**每一次查询**。

## 二、GraphRAG：两家架构的分野

### 2.1 微软 graphrag：社区检测 + 层级报告

微软官方实现（v3.3.0）是一条重索引管线，标准 workflow 共九步：切块 → LLM 抽图 → Leiden 聚类 → 社区报告 → 嵌入（`microsoft/graphrag@5faaaf4f packages/graphrag/graphrag/index/workflows/factory.py#_standard_workflows`）。关键环节：

- **抽图**：每个 text unit（默认 1200 token / overlap 100）发一次 LLM 调用抽取实体与关系，另加一轮 gleaning 追问（默认 1 次）；同名实体、同边的关系描述还要逐个做 LLM 摘要合并——这是抽图之外的第二类大额调用（`packages/graphrag/graphrag/index/workflows/extract_graph.py#run_workflow`）。
- **社区检测**：hierarchical Leiden，由 Rust 原生扩展 `graspologic_native` 实现，输出多层社区结构，`max_cluster_size=10`（`packages/graphrag/graphrag/graphs/hierarchical_leiden.py#hierarchical_leiden`）。
- **社区报告**：每个社区、每个层级各生成一次 LLM 摘要报告——这是「全局问题的答案」被预计算的地方（`packages/graphrag/graphrag/index/workflows/create_community_reports.py#run_workflow`）。

查询侧四种模式（`packages/graphrag/graphrag/query/structured_search/`）：**local** 把 query 映射到实体、沿图扩邻域，答具体问题；**global** 把社区报告分批跑 map（打分）再 reduce（汇总），是「全局主题问题」的正解，但每问一次就是 1+N 次 LLM 调用；**drift** 是「global 播种 + local 迭代扩散」的混合体，查询成本最高；**basic** 则是纯向量检索——官方自己也保留了向量兜底，这个细节值得注意。

### 2.2 LightRAG：无社区、双层检索

LightRAG（HKUDS）与微软版最核心的架构差异：**没有社区**。全库 grep 不到任何 Leiden/community 实现，README 明示它不依赖社区报告与多跳推理（`HKUDS/LightRAG@4d0afc1bc lightrag/operate.py`、README）。

它的替代方案在查询侧。查询时先用一次 LLM 从 query 抽出**双组关键词**：ll（低层，具体实体名）与 hl（高层，主题概念）；local 模式拿 ll 去实体向量库检索、global 模式拿 hl 去关系向量库检索，hybrid 两路轮询交错（`lightrag/operate.py#_perform_kg_search`、`lightrag/base.py#QueryParam`）。注意 LightRAG 的 "global" 与微软语义完全不同——没有预聚合层，全局感来自关系边描述的跨文档性。默认模式是 **mix**：在 hybrid 之外再并一路「原始 query 对 chunk 向量库的纯向量检索」，KG 上下文与向量 chunk 在同一 token 预算内融合（`operate.py#_perform_kg_search`）。

索引侧的省调用设计有三处结构性差异：免掉整个社区报告阶段；实体描述合并有阈值门控——同名实体描述数 ≥ 8 或总 token 超限才调 LLM 做摘要，否则直接拼接（`lightrag/constants.py#30-36`）；抽取结果缓存跨查询与重建复用。对比微软版「每实体必摘要、每社区每层必报告」，这是调用量的数量级差异。

### 2.3 成本：先算账再谈架构

按默认 1200-token 切块粗算（1MB 英文 ≈ 25 万 token ≈ 208 个 chunk）：**LightRAG 约 210~450 次 LLM 调用/MB**（208 次抽取，gleaning 上限 ×2，加少量阈值触发的合并摘要）；**graphrag 约 500~1500+ 次/MB**（抽取之外还要加上每实体一次的描述摘要、社区数 × 层级数的社区报告——千级文档轻松产生数百社区）。折算成相对成本：graphrag 约为纯向量 RAG 的 3~10 倍，LightRAG 约 2~4 倍。

必须诚实标注：这组数字是调研档案按默认切块的结构推算，**不是官方 benchmark**（两仓仓库内均未见官方数字）。更麻烦的是，graphrag v3.3.0 没有索引前成本预估器——老版本 `--dryrun` 式的估算代码在本版未找到，只有索引结束后的事后统计（token 与美元换算靠 litellm 价格表，`packages/graphrag-llm/graphrag_llm/model_cost_registry/model_cost_registry.py#ModelCostRegistry`）。也就是说，你决定上 graphrag 的那一刻，拿不到任何官方工具告诉你「这批语料要花多少钱」。

### 2.4 增量更新：微软版的隐藏质量债

企业语料会更新，而 graphrag 的 `update` 命令是「delta 重索引 + 表级拼接」：对新增文档跑完整管线，然后实体按 title 合并、关系按 source/target 合并——但**社区只做 id 平移拼接，旧社区原样保留，不会与新文档的实体重新聚类**（`packages/graphrag/graphrag/index/update/communities.py#_update_and_merge_communities`）。后果：图结构演化不会发生，旧社区吸收不了新实体，长期增量后社区边界退化，官方隐含建议是定期全量重建——等于把省下的索引钱以质量债形式欠着。LightRAG 则相反：文档级 append + 内容哈希去重，增量就是日常操作；删除按 doc 重建受影响实体时复用 LLM 抽取缓存、不重新调模型（`lightrag/operate.py#rebuild_knowledge_from_chunks`）。

### 2.5 平台层的真实渗透率

一个有说服力的旁证：号称 RAG 能力最强的开源平台，当前基线上知识图检索恰恰是没做完的。ragflow 的 Go 重写版里 `use_kg` 参数直接 Warn 跳过——`infiniflow/ragflow@deb1235be internal/service/dataset/search.go:324` 原文「use_kg is not yet implemented in Go - skipping KG retrieval」；kotaemon 集成微软 GraphRAG 的通道绑定的是 v0/v1 时代的 parquet 表名与已删除的模块路径，配 graphrag v3.x 预期不可用（基于 import 路径比对的档案判断，未实测）。**GraphRAG 在开源平台层尚处于「宣称多于实现」的阶段**，这本身就是渗透率的注脚。

## 三、四问判断框架

档案给出的判断框架，四个问题按顺序过：

1. **问题分布**：用户是否真有「全局主题 / 多跳关联」类问题，占比是否超过 10~20%？只有点状事实查询（「XX 接口的超时配置是多少」），向量 + rerank 就够，别上。
2. **语料稳定性**：语料是相对稳定的报告库、规范库、案例库，还是频繁改写的 wiki？后者会让 graphrag 的社区退化与成本失控同时发生；LightRAG 对此宽容得多。
3. **预算**：能否接受索引成本 3~10 倍（graphrag）或 2~4 倍（LightRAG）于纯向量？抽取用便宜的非推理模型可以压成本（LightRAG README 明确推荐 Haiku/mini 档）。
4. **运维栈**：愿意运维图数据库吗？LightRAG 的存储矩阵里有 PG 全家桶方案，可以一把梭（`lightrag/kg/__init__.py#STORAGE_IMPLEMENTATIONS`）；graphrag 默认是 parquet + lancedb 的文件形态，企业共享场景要上 cosmos/azure 全家桶。

四问里至少三问「是」，才值得评估微软版（global/drift 的社区报告能力是它独有且不可替代的）；只有一问「是」但想低成本拿到「实体关联增强」，用 LightRAG。

**渐进路径**是本系列的态度：不要把 GraphRAG 当唯一检索层（两者的失败模式不同——向量是全局问题失焦，KG 是实体抽取噪声、冷启动贵——互补而非替代）。两条被源码验证过的渐进路线：

- **LightRAG mix 模式**：一次索引同时产出 KG 与 chunk 向量，查询时 KG 检索失败向量结果仍在场，等于免费获得一路向量兜底。同一套 PG 存储栈，查询侧可逐步放量。
- **kotaemon 的副索引灰度模式**：GraphRAG 作为独立索引类型与普通向量 FileIndex 并列（`Cinnamon/kotaemon@9ad3e4e4 flowsettings.py#356-369`），编排层把 KG 检索器与向量检索器的返回合流进同一上下文。代价是两套索引两份成本，收益是**可灰度、可回退**——落地风险最低。给某类问题开 KG，效果不行就关，主索引毫发无损。

## 四、Agentic RAG：80% 场景，固定管线就是工业默认

### 4.1 为什么固定管线赢面这么大

Agentic RAG 的定义：LLM agent 把「检索知识库」当成可自主调用的工具，自己决定何时检索、检索什么、读完要不要再检索。它牺牲的是三样企业最在意的东西：

- **延迟**：agent 循环每一步都是一次 LLM 决策调用，一次多跳问答轻松到十秒级；固定管线 retrieve→rerank→generate 的延迟是可预算的。
- **成本**：每步决策都在烧 token，且循环次数不可预测。
- **可测试性**：固定管线的回归测试是确定性的（换模型、调参、改切分，跑评测集比分数）；agent 循环行为不确定，第 8 篇讲的评测门禁在 agentic 形态上要难做一个量级。

所以形态判断先行：**问答口径稳定、延迟成本敏感、要可评测——固定管线；多信源混合、问题需多跳分解、需要「读后再检索」、需要 agent 自判信息是否充分——才上 agent 循环。**企业内部知识问答，前者占绝对多数（档案的估计是 80%）。

### 4.2 经典范式的现状：只剩两家，且一家已归档

CRAG（纠错检索：检索后逐文档打分，低分触发重写或兜底）、Self-RAG（生成后自评幻觉与相关性，不过关回炉）、Adaptive RAG（入口分类路由）——这三篇论文范式的「官方实现」现状值得每个方案评审者知道：

- **langgraph**：三个范式的 notebook 全在 `examples/rag/` 下，但每个 notebook 首个 cell 都标注「This directory is retained purely for archival purposes and is no longer updated」——已整体归档，迁往 LangChain 文档站，不再随库演进（`langchain-ai/langgraph@e539ac122f examples/rag/langgraph_crag.ipynb` 等 9 个）。
- **llama_index**：把 routing、子问题分解、多步检索、FLARE 吸收进了 core 查询引擎层（`run-llama/llama_index@7169bcd0d llama-index-core/llama_index/core/query_engine/sub_question_query_engine.py#SubQuestionQueryEngine`、`multistep_query_engine.py`、`flare/base.py`、`router_query_engine.py`），是唯一把迭代检索做成可安装核心模块而非示例的一家。
- **haystack / dify / quivr / kotaemon**：均无官方范式模板（haystack 的示例已整体迁往独立的 cookbook 仓）。

三大范式集中沉淀在两家框架、其中一家还标了归档——这个事实本身就是工业界的投票结果：**它们是有教学价值的检索策略，不是产品默认形态。**

### 4.3 dify 的反向决策：把知识库从 agent 工具层里拿出来

dify 的新 agent 架构（agent_v2，2026-09 基线）做了一个方向明确的产品决策：`_tool_layer_destination` 对 `ToolProviderType.DATASET_RETRIEVAL` **直接 raise**，错误信息原文「dataset-retrieval remains on the knowledge path and is not supported in Agent tool layers」（`langgenius/dify@79effdd498 api/core/workflow/nodes/agent_v2/dify_tools_builder.py`）。即：新 agent 不让知识库当工具，检索固定走 knowledge-retrieval 节点——「知识路径与 agent 路径分离」。旧 Chat App 的 agent 模式虽然还支持挂 dataset 工具，但注释明写「Agent only support SINGLE mode」，多知识库聚合降级为单库（`api/core/tools/utils/dataset_retriever_tool.py:54`）。

158k star 的 LLM 应用平台在 2026 年做出的架构决策是**收敛**而不是 agentic 化，这与「万物皆 agent」的叙事形成刺眼对照。它的理由值得抄录：企业知识检索要的是稳定、可控、可评测，这些恰恰是 agent 自主性的反面。

### 4.4 quivr 的反转姿态：agent 住客户端，检索做工具服务器

quivr 的 Go 重写版（2026-09 推倒重来，5 周龄、自评 evaluation stage）给了一个反向样本：它完全不做 agent——代码里 grep 不到任何 LLM agent 循环——而是把检索能力做成 **MCP 工具服务器**暴露给任意外部 agent（`The-Vibe-Company/quivr@67a6c0e9f internal/online/mcp.go`）。工具目录是一个三步剧本：`list_corpora`（列可用语料库）→ `search`（query + corpus_ids + lexical/semantic/hybrid 模式 + metadata 过滤）→ `read_record`（取命中记录全文，带 record_id/version_id/part_key/字符偏移的精确溯源）；profile Instructions 直接写给外部 agent：「call list_corpora to learn which Corpora… call search with a question and those corpus_ids, then call read_record on a hit when you need its full context」（`internal/online/mcp_catalogue.go#MCPTools`）。

**agent 循环住在客户端，服务端只提供高质量的检索工具面。**这个姿态恰是本系列主题——「知识库给 agent 供数」——的正解形态：你不需要在知识库服务里再造一个 agent，你的消费者（deepagents、Claude、自研 agent）自己就是 agent；你要做的是把检索、溯源、鉴权做成值得 agent 信赖的工具。第 10 篇的实战设计将完整采用这个形态。

### 4.5 haystack 的工程件：真要自搭 agentic RAG 时抄谁

如果确实需要代码优先的自建 agentic RAG，工程件最全的是 haystack：`PipelineTool` 把任意检索 Pipeline 包成 LLM 工具，并**从 pipeline 输入 socket 自动生成 tool schema**（`deepset-ai/haystack@05cab58ac haystack/tools/pipeline_tool.py#PipelineTool`）；`Agent` 组件有跨工具调用的共享状态（state_schema + merge handler）、退出条件、步数上限（默认 100）、六个生命周期 hooks；`CompactionHook` 在上下文达到窗口 70% 时自动压缩——迭代检索轮次多时的刚需（`haystack/components/agents/agent.py#Agent`、`haystack/hooks/compaction.py#CompactionHook`）。langgraph 的强项则是编排控制力：StateGraph + 条件边 + Postgres checkpointer，适合检索状态需要持久化、可恢复的重流程（`libs/prebuilt/langgraph/prebuilt/tool_node.py#ToolNode`）。

## 五、厂商口径互证：三家说的其实是同一句话

- **微软 Azure 架构中心**（RAG 方案设计与评估指南）：标准 RAG 适合**单索引单查**场景，超出这个范围——多步推理、动态选源、运行时分解——才考虑 agentic RAG，即「agent 把检索当按需调用的工具」；其 agentic retrieval 文档同时明言该形态「adds latency… handles query complexity that a single query can't」——能力与代价一体两面（【一手-文档】learn.microsoft.com）。
- **OpenAI**（web search guide）：「agentic search with reasoning models is an approach where the model takes an active role in search — deciding when and what to search, automatically generating refined queries, and ranking results」——模型主动决定搜不搜、搜什么、自己改写排序。注意这是推理模型语境下的定义，且对应的是 Deep Research / File Search 这类产品形态，不是让你在每次企业问答里都跑 agentic 循环。（⚠️ openai.com 的 agentic search 博客本体抓取被 403 挡住，此处以 developers.openai.com 文档为准，档案已标注。）
- **Anthropic**（Effective Context Engineering for AI Agents）：提出 context rot——token 越多 recall 越差，所以 Claude Code 的检索是 just-in-time 的：用 grep/head/tail 定向读，而不是把语料全量加载进上下文；官方口号是「do the simplest thing that works」。这给了「读后再检索」一个更朴素的表述：**定向、按需、小口咀嚼**——不必然需要一个重型的 agent 编排框架。

三家口径与开源侧的源码结论完全同向：agentic 检索是「复杂查询才开的高端档」，不是默认档。

## 六、落地建议

把两件事的建议合成一张决策清单：

| 判断 | 结论 |
|---|---|
| 知识问答为主，口径稳定，延迟/成本/可评测优先 | 固定管线（双路召回 → 融合 → rerank → 生成），第 5 篇配方 |
| 多信源、多跳、需自判信息充分 | agent 循环，且 agent 住客户端、知识库做 MCP 工具服务器（quivr 形态） |
| 折中（多数企业的实际形态） | **管线做骨架、局部嵌 agent**：dify 的 question-classifier 节点分流式——简单问题走固定检索管线，复杂问题才进 agent 节点/循环（编排形态见 `langgenius/dify@79effdd498 web/app/components/workflow/nodes/` 的节点清单）；llama_index 等价做法是 SubQuestionQueryEngine 定向分解 + 外层 FunctionAgent 决定是否调用 |
| 有全局性/多跳问题需求（>10-20% 占比）+ 语料稳定 + 预算充足 | 微软 graphrag（global/drift 不可替代），接受增量不重聚类、定期全量重建的运维模型 |
| 想低成本试「实体关联增强」 | LightRAG mix，一次索引双产出，向量兜底 |
| 任何 GraphRAG 上线 | **先副索引灰度**（kotaemon 模式：两套索引并存、结果合流、可回退），别当唯一检索层 |

一句话收束：**GraphRAG 和 Agentic RAG 都是「问题分布驱动的升级项」，不是「架构先进性指标」。**先问用户的问题长什么样，再决定要不要为它们付出索引成本和查询时延——这在开源源码与四家厂商口径里是少见的高度一致。

## 参考与出处

**开源源码（基线 commit 见文首引用块）**

- graphrag 索引 workflow 顺序：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag/graphrag/index/workflows/factory.py （`#_standard_workflows`）
- graphrag 抽图：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag/graphrag/index/workflows/extract_graph.py
- graphrag Leiden 社区检测：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag/graphrag/graphs/hierarchical_leiden.py
- graphrag 社区报告：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag/graphrag/index/workflows/create_community_reports.py
- graphrag 增量社区只拼接不重聚类：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag/graphrag/index/update/communities.py （`#_update_and_merge_communities`）
- graphrag 成本统计（litellm 价格表）：https://github.com/microsoft/graphrag/blob/5faaaf4f/packages/graphrag-llm/graphrag_llm/model_cost_registry/model_cost_registry.py
- LightRAG 双层检索与 mix 模式：https://github.com/HKUDS/LightRAG/blob/4d0afc1bc/lightrag/operate.py （`#_perform_kg_search`）、https://github.com/HKUDS/LightRAG/blob/4d0afc1bc/lightrag/base.py （`#QueryParam`）
- LightRAG 阈值门控常量：https://github.com/HKUDS/LightRAG/blob/4d0afc1bc/lightrag/constants.py
- LightRAG 存储实现清单（PG 全家桶）：https://github.com/HKUDS/LightRAG/blob/4d0afc1bc/lightrag/kg/__init__.py （`#STORAGE_IMPLEMENTATIONS`）
- LightRAG 删除按缓存重建：https://github.com/HKUDS/LightRAG/blob/4d0afc1bc/lightrag/operate.py （`#rebuild_knowledge_from_chunks`）
- kotaemon 副索引灰度模式：https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/flowsettings.py
- ragflow use_kg 未实现（Warn 跳过）：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/dataset/search.go
- langgraph 归档的范式示例：https://github.com/langchain-ai/langgraph/blob/e539ac122f/examples/rag/langgraph_crag.ipynb （同目录 9 个 notebook 均标注 archival）
- langgraph ToolNode：https://github.com/langchain-ai/langgraph/blob/e539ac122f/libs/prebuilt/langgraph/prebuilt/tool_node.py
- llama_index 迭代检索进 core：https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/query_engine/sub_question_query_engine.py （同目录 `multistep_query_engine.py`、`flare/base.py`、`router_query_engine.py`）
- haystack PipelineTool：https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/tools/pipeline_tool.py
- haystack Agent 与 CompactionHook：https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/components/agents/agent.py 、https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/hooks/compaction.py
- dify agent_v2 拒绝 dataset 工具：https://github.com/langgenius/dify/blob/79effdd498/api/core/workflow/nodes/agent_v2/dify_tools_builder.py
- dify 旧 agent 单库限制：https://github.com/langgenius/dify/blob/79effdd498/api/core/tools/utils/dataset_retriever_tool.py
- quivr MCP 工具服务器与剧本：https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/online/mcp.go 、https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/online/mcp_catalogue.go

**官方文档（2026-10-15 当日可访问）**

- 微软 Azure 架构中心 RAG 方案设计指南（标准 RAG vs agentic RAG 口径）：https://learn.microsoft.com/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide
- Azure AI Search agentic retrieval 概览（延迟代价表述）：https://learn.microsoft.com/azure/search/agentic-retrieval-overview
- OpenAI web search guide（agentic search 定义）：https://developers.openai.com/api/docs/guides/tools-web-search
- Anthropic Effective Context Engineering for AI Agents（context rot / just-in-time 检索）：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

**证据等级说明**：开源部分为源码级（档案【核心】标注）；微软/Anthropic 为官方文档一手引文；OpenAI agentic search 博客本体未取到（403），以 developers.openai.com 文档为准；graphrag/LightRAG 的每 MB 调用数为档案按默认切块的粗算，非官方数字；kotaemon 微软 GraphRAG 通道「配 v3.x 预期不可用」为 import 路径比对推断，未实测。

---

### 系列目录：《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计（本篇）
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

**下一篇预告**：系列的收官篇把前九篇的结论收拢成一份完整的实施蓝图——用 FastAPI + SQLite/LanceDB + TEI + MinerU/docling 自建一个轻量知识库服务，以 MCP 工具的形态接进 deepagents，含架构图、数据模型草案与 MVP 验收口径。
