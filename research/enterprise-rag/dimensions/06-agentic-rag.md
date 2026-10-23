# 维度六：Agentic RAG —— LLM agent 把检索当工具

> **问题定义**：用户要搭的是「RAG agent/系统」——LLM agent 把「检索知识库」当成一个可自主调用的 tool，自己决定何时检索、检索什么、读完要不要再检索，而不是固定的 retrieve→generate 管线。本维度看 6 个仓库把这种形态做到什么程度。
> **基线**：langgraph e539ac122f / llama_index 7169bcd0d / haystack 05cab58ac / dify 79effdd498 / quivr 67a6c0e9f（Go 重写版）/ kotaemon 9ad3e4e4。
> **证据分级**：【核心】= 产品主代码路径；【示例】= examples/docs 目录；【文档】= 文档站源码。❌=查无实现；⚠️=实现存在但有明确限制。

## 一、总表

| 维度 | langgraph | llama_index | haystack 2.x | dify | quivr V2 | kotaemon |
|---|---|---|---|---|---|---|
| **RAG-as-tool** | 【示例】`create_retriever_tool`（langchain 包）+ `ToolNode`【核心】 | 【核心】`RetrieverTool` / `QueryEngineTool` | 【核心】`PipelineTool`（检索管线→工具，schema 自动生成） | ⚠️ 双轨：旧 Chat App agent 可挂 dataset 工具【核心】；新 agent_v2 节点**明确禁止** dataset 作工具【核心】 | 【核心】MCP 工具化（`search`/`read_record`），给外部 agent 调用 | 【核心】`DocSearchTool`（docsearch） |
| **迭代检索/多跳** | agent 循环天然支持（grade→rewrite→retrieve 循环）【示例】 | `SubQuestionQueryEngine`、`MultiStepQueryEngine`、FLARE【核心】 | Agent `max_agent_steps` 循环 + `state_schema` 跨步状态【核心】 | iteration/loop 节点 + agent 自主循环【核心】 | 委托给外部 agent（MCP 指令里写明 list→search→read 循环） | ReAct 循环 + `DecomposeQuestionPipeline`【核心】 |
| **经典范式（CRAG/self-RAG/adaptive）** | 【示例】三件套 notebook 全有（已归档） | 【示例】CRAG workflow notebook + Router/FLARE【核心】 | ❌ 仓内无范式示例（cookbook 移独立仓） | ❌ 无官方范式模板（question-classifier 节点可手搭 adaptive） | ❌ | ❌（有 rewrite/decompose 优化管线） |
| **编排能力** | StateGraph 状态图 + 条件边 + checkpointer【核心】 | Workflow 事件驱动 + AgentWorkflow 多 agent【核心】 | Pipeline + Agent 组件互相嵌套（agent-as-tool）【核心】 | 可视化 workflow：知识检索↔agent↔iteration↔if-else↔问题分类【核心】 | ❌ 无编排层（纯 API+MCP） | ❌ 单一 UI 流程（simple/ReAct/REWOO 三选一） |
| **成熟度定位** | 框架（图编排引擎，示例教学级） | 框架（agent + 查询引擎双轨，最全） | 框架（工程最扎实的 agent 组件） | 产品（可配置上线） | 基建（检索引擎，evaluation 阶段） | 演示（RAG 技术展示台） |

## 二、逐家源码发现

### 2.1 langgraph：范式策源地，但示例已「归档」

最重要的定位信息：`examples/rag/` 下 9 个 notebook 每个 cell 0 都标注 **"This directory is retained purely for archival purposes and is no longer updated"**（已并入 LangChain 官方文档站）。即这些 CRAG/self-RAG 实现的教学价值仍在，但不再随库演进【示例】。

四类形态（均为 notebook，非可安装模块）：

- **CRAG**（`examples/rag/langgraph_crag.ipynb`）：节点 `retrieve → grade_documents（LLM 结构化打分）→ {transform_query(重写) | generate}`，不相关时走 `web_search`（Tavily）兜底。状态是 `GraphState(TypedDict)`: `question/generation/documents` 三字段。
- **self-RAG**（`langgraph_self_rag.ipynb`）：在 CRAG 之上加两级生成自检——`grade_generation_v_documents_and_question` 条件边按「幻觉?/回答相关?」路由回 `transform_query` 或 `useful→END`，共 4 个 pydantic grader（GradeDocuments/GradeHallucinations/GradeAnswer 等）。
- **adaptive RAG**（`langgraph_adaptive_rag.ipynb`）：入口 `route_question` 用结构化输出 `Router(selection: Literal["web_search","vectorstore"])` 做查询路由，再进 CRAG 式纠错环；`_local` 变体用本地模型、`_cohere` 变体用 Cohere reranker。
- **RAG-as-tool**（`langgraph_agentic_rag.ipynb`）：`from langchain.tools.retriever import create_retriever_tool` 把 retriever 包成工具，挂 `langgraph.prebuilt.ToolNode`（现位于 `libs/prebuilt/langgraph/prebuilt/tool_node.py#ToolNode`），agent 决定是否调检索。

框架侧的支撑（【核心】）：`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py#create_react_agent`（支持 `response_format` 结构化输出，可用于 grader）；`libs/checkpoint-postgres` 提供持久化 checkpointer——这是它比其他家强的「可恢复长程编排」能力。检索状态承载方式就是 `StateGraph(GraphState)` 的 TypedDict 字段 + `add_conditional_edges` 的字典路由，简单直接。

### 2.2 llama_index：RAG-as-tool 双层抽象 + agentic 查询引擎「全家桶」

**工具层**（【核心】，llama-index-core 主代码）：
- `llama-index-core/llama_index/core/tools/retriever_tool.py#RetrieverTool`：裸检索工具，返回文档集合（默认描述 "Useful for running a natural language query against a knowledge base and retrieving a set of relevant documents"）。
- `.../tools/query_engine.py#QueryEngineTool`：包整个查询引擎（含合成答案），默认描述 "…get back a natural language response"。两者都实现 `AsyncBaseTool` 接口，带 `ToolMetadata`。

**agent 层**（【核心】）：`llama-index-core/llama_index/core/agent/workflow/` 提供 `FunctionAgent`（函数调用）、`ReActAgent`（`react_agent.py`）、`CodeActAgent`、`multi_agent_workflow.py#AgentWorkflow`（多 agent 编排）。

**「检索→读→再检索」的官方路径**（这个仓库独有的是把迭代检索做成了**可安装的核心模块**而不仅是示例）：
- `core/query_engine/sub_question_query_engine.py#SubQuestionQueryEngine` + `core/question_gen/`：子问题分解，各子问题独立检索后汇总；
- `core/query_engine/multistep_query_engine.py#MultiStepQueryEngine`：`StepDecomposeQueryTransform` 逐步分解，`stop_fn` 判断 query 为 "none" 时早停——真正的迭代检索引擎；
- `core/query_engine/flare/`（`base.py#FLAREInstructQueryEngine`）：FLARE 主动检索（生成中低置信 token 触发检索再续写）；
- `core/query_engine/router_query_engine.py#RouterQueryEngine`：adaptive 路由。

官方文档把这整套称为 agentic strategies（【文档】`docs/src/content/docs/framework/optimizing/agentic_strategies/agentic_strategies.md`：「routing、query transformations 本身就是 agentic 的」+ Data Agents 把 query engine 当工具）。示例证据：`docs/examples/agent/react_agent_with_query_engine.ipynb`（两个 QueryEngineTool：lyft_10k/uber_10k → ReActAgent）、`docs/examples/workflow/corrective_rag_pack.ipynb`（`CorrectiveRAGWorkflow(Workflow)` 事件驱动实现）、`docs/examples/agent/nvidia_sub_question_query_engine.ipynb`、`agents_as_tools.ipynb`、`agent_workflow_research_assistant.ipynb`。

### 2.3 haystack 2.x：RAG-as-tool 工程化最彻底，但范式示例外移

**核心卖点 `PipelineTool`**（【核心】`haystack/tools/pipeline_tool.py#PipelineTool`，继承 `ComponentTool`）：把任意 Haystack 检索 Pipeline 包成 LLM 工具，**从 pipeline 输入 socket 自动生成 tool schema**，docstring 里的官方示例就是「embedder+retriever 管线 → document_retriever 工具 → Agent」——这是六家中唯一把「RAG-as-tool」做成自动 schema 生成的一等公民组件。

**Agent 组件**（【核心】`haystack/components/agents/agent.py#Agent`，1252 行，产品级）：tool/toolset 列表、`exit_conditions`（文本或工具名）、`state_schema`（带跨工具调用 merge handler 的共享状态，`state/state.py#State`——多跳检索结果累积的载体）、`max_agent_steps=100`、`tool_concurrency_limit=4`、六个生命周期 hooks（`before_llm/before_tool/after_tool/on_exit/before_run/after_run`，可用于改写/截断工具结果）。

**长循环工程配套**（【核心】）：`haystack/hooks/compaction.py#CompactionHook` + `SlidingWindowCompactor`（上下文达到窗口 70% 时压缩，保留 system+最近任务）——迭代检索轮次多时的刚需；`haystack/tools/searchable_toolset.py#SearchableToolset`（工具目录按语义搜索动态暴露，解决「工具太多塞不下 prompt」）。

**弱项**：`examples/README.md` 明言 examples 已移到独立仓 haystack-cookbook，本仓内 **没有任何 CRAG/self-RAG 官方示例** ❌——范式层要靠用户自己用 Agent+PipelineTool 搭。

### 2.4 dify：产品双轨制，且新架构正在「去 agent-RAG 融合」

dify 有三条 RAG 路径，新旧架构方向相反：

1. **旧 Chat App「Agent」模式**（【核心】`api/core/agent/`）：`base_agent_runner.py` 在初始化时 `DatasetRetrieverTool.get_dataset_tools(...)` 把 dataset 挂为 agent 工具（工具参数就一个 `query`，llm 描述 "Query for the dataset to be used to retrieve the dataset."）；注意 `core/tools/utils/dataset_retriever_tool.py:54` 注释 **"Agent only support SINGLE mode"**（多知识库聚合检索降级为单库）。ReAct 式由 `cot_agent_runner.py`（`CotAgentOutputParser` + `AgentScratchpadUnit`）实现，函数调用式由 `fc_agent_runner.py` 实现。
2. **workflow agent 节点（v1）**（【核心】`api/core/workflow/nodes/agent/`）：节点本身只是壳，策略经 `strategy/plugin.py#PluginAgentStrategy` 从插件仓解析——function-calling/ReAct 等策略实体在 dify-official-plugins 仓，本仓查不到实现 ⚠️。
3. **agent_v2**（【核心】`nodes/agent_v2/`，2026-09 基线新增）：`dify_tools_builder.py#_tool_layer_destination` 对 `ToolProviderType.DATASET_RETRIEVAL` **直接 raise**："dataset-retrieval remains on the knowledge path and is not supported in Agent tool layers." ——产品级架构决策：**新 agent 不让知识库当工具，检索固定走 knowledge-retrieval 节点**，与用户想要的「RAG-as-tool」形态背道而驰。

**编排能力**（【核心】+前端证据）：工作流引擎已外置为 pip 包 `graphon==0.7.0`（`api/pyproject.toml:48`），本仓 `core/workflow/nodes/` 只剩 agent/agent_v2/datasource/human_input/knowledge_index/knowledge_retrieval/trigger_*；完整节点palette看前端 `web/app/components/workflow/nodes/`：`knowledge-retrieval、agent、agent-v2、iteration（迭代）、loop、if-else、question-classifier、parameter-extractor、llm、tool、document-extractor、variable-assigner…`。可组「question-classifier 路由 → knowledge-retrieval → llm → iteration 批量子问题检索」等形态。`knowledge_retrieval/entities.py#KnowledgeRetrievalNodeData` 支持 single/multiple 检索模式、reranking 配置、metadata 过滤（automatic/manual）——检索节点本身可配置性强。

**reasoning 适配**（【核心】）：`nodes/agent/think_tags.py` 专门处理 GLM/DeepSeek 式 `<think>` 标签在工具调用中断流后未闭合的问题（`ThinkStreamState` 逐 chunk 修复，对应 issue #41558）。

### 2.5 quivr V2：反转——不做 agent，把自己做成 agent 的工具

README 开篇即定性：「turns continuous content streams into search and monitoring」的**引擎**，evaluation stage。`grep -ri "openai|anthropic|llm|chat" internal/` **零命中** ❌——Go 重写版完全没有 LLM agent 循环，「agent-first」是 Python 时代（V1）的旧标签。

它的 agentic RAG 姿态是反向的（【核心】`internal/online/mcp.go` + `mcp_catalogue.go`）：`quivr mcp` 子命令把检索能力以 **MCP stdio server** 暴露给任意外部 agent（Claude 等）。工具目录：
- `list_corpora`（列可用语料库）→ `search`（参数：query + corpus_ids + mode: lexical/semantic/hybrid + profile + metadata filter，带完整 JSON Schema）→ `read_record`（取命中记录全文）；
- read/ingest 两个 profile，API key 决定工具可见的 Corpora（服务端鉴权）；
- profile Instructions 直接写给外部 agent 的迭代检索剧本："call list_corpora to learn which Corpora… call search with a question and those corpus_ids, then call read_record on a hit when you need its full context"；
- 命中带精确溯源（record_id/version_id/part_key/字符偏移）。

即：**agent 循环住在客户端，quivr 只提供高质量的检索工具面**。`multimodal-rag/` 目录为空（疑似未拉取的子模块）⚠️。

### 2.6 kotaemon：教科书式「docsearch 工具 + 三种推理模式」

`libs/ktem/ktem/reasoning/` 是 UI 可选的推理层：
- `simple.py`：固定管线（`RewriteQuestionPipeline` 改写 + 检索 + 引用问答），非 agent；
- `react.py#ReactAgentPipeline`：文本 CoT 式 ReAct；其 `DocSearchTool`（name=`docsearch`，args_schema=`DocSearchArgs{query}`）把内部 retriever 列表包成工具，描述里明确教模型「缺私有信息就搜这里，query 越具体越好」；`TOOL_REGISTRY = {Google, Wikipedia, LLM, SearchDoc}`——知识库检索与 Web 搜索、LLM 同级注册；
- `rewoo.py#RewooAgent`：计划-执行分离（先产出 #E1/#E2 变量计划再逐步取证据）；
- `prompt_optimization/`：`DecomposeQuestionPipeline`（子问题分解）+ `RewriteQuestionPipeline`。

**reasoning 适配**（【核心】）：`libs/kotaemon/kotaemon/indices/qa/utils.py#replace_think_tag_with_details` / `strip_think_tag`——把 DeepSeek-R1 式 `<think>...</think>` 渲染成 UI 折叠块或剥离，处理的是**展示层**，不是 agent 循环逻辑。

## 三、经典范式专题：CRAG / Self-RAG / Adaptive 各家实现对比

| 范式 | 核心机制 | langgraph | llama_index | 其余四家 |
|---|---|---|---|---|
| **CRAG**（纠错检索） | 检索后 LLM 逐文档打分；低分→查询重写再检索 / Web 搜索兜底 | 【示例】`langgraph_crag.ipynb`：grade_documents 条件边 + transform_query + Tavily，状态 TypedDict | 【示例】`docs/examples/workflow/corrective_rag_pack.ipynb#CorrectiveRAGWorkflow`（Workflow 事件版，GPT-4 评分 + Tavily） | haystack：❌（可 Agent+PipelineTool 自搭）；dify/kotaemon/quivr ❌ |
| **Self-RAG**（自省生成） | 生成后自评幻觉与相关性，不过关回炉 | 【示例】`langgraph_self_rag.ipynb`：4 个 pydantic grader + `grade_generation_v_documents_and_question` 条件边，含 usefulness/useless 终态 | ❌ 未见官方 self-RAG 示例（FLARE 可视为另一路自省） | 四家 ❌ |
| **Adaptive/Routing**（按问路由） | 入口分类：无需检索/走向量库/走 Web | 【示例】`langgraph_adaptive_rag(_local/_cohere).ipynb`：`Router(Literal)` 结构化输出 | 【核心】`RouterQueryEngine`（选择器路由到子引擎）+【示例】`router_query_engine.ipynb` | dify：question-classifier 节点 + 条件分支可等价手搭（无官方模板）；kotaemon/quivr ❌ |

**结构性结论**：三大范式的「官方实现」集中且仅集中在 langgraph 与 llama_index两家，且 langgraph 一侧已整体标注归档——范式教学资源在向 LangChain 文档站迁移；llama_index 把 routing/sub-question/multi-step/FLARE 吸收进 core 查询引擎层，比 notebook 更接近可用件。haystack/dify 没有跟进这些论文范式：haystack 走「通用 agent 组件，范式用户自搭」路线，dify 走「产品节点编排」路线。

## 四、「企业 agentic RAG 底座」选型小结：固定管线 vs agent 循环

**先做形态判断再选底座**：

- **固定管线够用的场景**（问答口径稳定、延迟敏感、成本敏感、可评测）：retrieve→rerank→generate 已是工业默认。dify 的 knowledge-retrieval→llm 节点编排、kotaemon simple、llama_index 普通 QueryEngine 都是此类。agent 循环每一步 LLM 决策都在放大延迟与 token 成本，且行为不确定、回归测试难做——企业知识问答 80% 场景不需要它。
- **需要 agent 循环的场景**：多知识库+Web 混合信源、问题需分解成多跳、需要「读后再检索」、需要 agent 自判信息是否足够（CRAG/self-RAG 动机）。
- **混合形态（务实推荐）**：管线做骨架、局部嵌 agent——例如 dify「question-classifier 分流：简单问题走固定检索，复杂问题进 agent 节点」；或 llama_index「SubQuestionQueryEngine 定向分解 + 外层 FunctionAgent 决定是否调用」。

**底座推荐排序**（面向「企业自建 agentic RAG」）：

1. **haystack 2.x（代码优先、工程严谨）**：`PipelineTool` 自动 schema + Agent 的 state_schema/hooks/exit_conditions/CompactionHook 是六家中唯一把 agentic RAG 所需工程件全部做成核心组件的；代价是范式要自己搭、无现成 CRAG 模板。
2. **llama_index（迭代检索基建最全）**：SubQuestion/MultiStep/FLARE/Router 都是 core 模块，QueryEngineTool 生态成熟，多 agent 有 AgentWorkflow；适合想「少写编排代码、多复用检索策略」的团队。
3. **langgraph（编排控制力最强）**：StateGraph+条件边+Postgres checkpointer 适合「检索状态需要持久化/人工介入/可恢复」的重流程；但 agentic RAG 素材全在归档示例，需要自己重写并承担 LangChain 生态迁移成本。
4. **dify（要产品不要代码）**：可视化编排+权限+可配置上线最完整，但注意其新架构（agent_v2）**明确不支持知识库挂为 agent 工具**，走的是「知识路径与 agent 路径分离」哲学，与「RAG-as-tool」诉求相反；只有旧 Chat App agent 模式保留该能力（且仅 SINGLE 检索）。
5. **quivr V2（当检索后端而非 agent 底座）**：MCP 工具化路线适合「agent 已有（Claude/自研），缺一个带溯源、鉴权、混合检索的语料库服务」的场景；自身无编排无生成。
6. **kotaemon（参考实现库）**：DocSearchTool 的工具描述写法、think 标签处理值得抄，整体是演示级。

## 五、证据与存疑清单

**关键证据（路径#符号）**：

- langgraph【示例】`~/develop/opensource/langgraph/examples/rag/{langgraph_crag,langgraph_self_rag,langgraph_adaptive_rag,langgraph_agentic_rag}.ipynb`（含 `_local`/`_cohere` 变体共 9 个）；【核心】`libs/prebuilt/langgraph/prebuilt/tool_node.py#ToolNode`、`.../chat_agent_executor.py#create_react_agent`、`libs/checkpoint-postgres/`
- llama_index【核心】`llama-index-core/llama_index/core/tools/retriever_tool.py#RetrieverTool`、`.../tools/query_engine.py#QueryEngineTool`、`.../query_engine/{sub_question_query_engine.py#SubQuestionQueryEngine, multistep_query_engine.py#MultiStepQueryEngine, flare/base.py#FLAREInstructQueryEngine, router_query_engine.py}`、`.../agent/workflow/{function_agent,react_agent,multi_agent_workflow}.py`；【示例】`docs/examples/agent/react_agent_with_query_engine.ipynb`、`docs/examples/workflow/corrective_rag_pack.ipynb#CorrectiveRAGWorkflow`；【文档】`docs/src/content/docs/framework/optimizing/agentic_strategies/agentic_strategies.md`
- haystack【核心】`haystack/tools/pipeline_tool.py#PipelineTool`、`haystack/components/agents/agent.py#Agent`、`.../agents/state/state.py#State`、`haystack/hooks/compaction.py#CompactionHook`、`haystack/tools/searchable_toolset.py#SearchableToolset`、`haystack/dataclasses/streaming_chunk.py#reasoning`（releasenotes：add-reasoning-mode-openai-responses、add-agent-context-compaction）
- dify【核心】`api/core/agent/base_agent_runner.py`（dataset 工具挂载）、`api/core/tools/utils/dataset_retriever_tool.py#get_dataset_tools`（"Agent only support SINGLE mode"）、`api/core/workflow/nodes/agent_v2/dify_tools_builder.py#_tool_layer_destination`（dataset 工具显式拒绝）、`api/core/workflow/nodes/agent/think_tags.py`、`api/core/workflow/nodes/knowledge_retrieval/{knowledge_retrieval_node.py#KnowledgeRetrievalNode, entities.py#KnowledgeRetrievalNodeData}`；前端节点清单 `web/app/components/workflow/nodes/`；`api/pyproject.toml:48`（graphon==0.7.0）
- quivr【核心】`internal/online/mcp.go`（`quivr mcp` stdio server）、`internal/online/mcp_catalogue.go#MCPTools`（search 工具 JSON Schema、read/ingest profile Instructions）；README.md（定位=search/monitoring engine，evaluation stage）
- kotaemon【核心】`libs/ktem/ktem/reasoning/react.py#DocSearchTool`+`#ReactAgentPipeline`+`TOOL_REGISTRY`、`.../rewoo.py#RewooAgent`、`.../prompt_optimization/`、`libs/kotaemon/kotaemon/indices/qa/utils.py#replace_think_tag_with_details`

**存疑**：

1. ⚠️ dify workflow agent 节点 v1 的 function-calling/ReAct 策略实现在 dify-official-plugins 独立仓，本仓只有解析协议（`core/agent/strategy/plugin.py`），未验证策略内部是否支持 dataset 工具注入（旧 Chat App 路径已验证支持）。
2. ⚠️ dify 工作流引擎已外置为闭源/独立 pip 包 graphon（0.7.0），iteration/if-else 等节点实现细节在本仓不可见，节点清单以前端目录+node_factory.py import 为证，未读到运行时代码。
3. ⚠️ langgraph `create_retriever_tool` 定义在 langchain 仓（本调研未克隆），langgraph 仓内仅有调用示例；ToolNode 在 `libs/prebuilt`，与 notebook 中 `langgraph.prebuilt` 的旧路径不同（库已重组）。
4. ⚠️ quivr `multimodal-rag/` 为空目录，其多模态 RAG 能力无法核实。
5. ❌ haystack 仓内无任何 CRAG/self-RAG 官方示例（examples 已整体迁往 github.com/deepset-ai/haystack-cookbook，未克隆验证）。
6. ❌ 未在任何仓库发现 self-RAG 的产品级（非 notebook）实现；langgraph 三个范式 notebook 均标注 archived，最新版本在 LangChain 文档站（未在线核验内容一致性）。
