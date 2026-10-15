# 06 · 让答案可信：引用溯源的三种实现机制

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

前一篇解决了"把最相关的 chunk 送给 LLM"，这一篇解决下一个问题：答案生成之后，用户凭什么相信它？企业知识库答错一个报销比例、一个合同条款，代价不是"不够智能"，而是"不再被使用"。做法业界已经收敛：**让答案的每句话能回溯到来源 chunk**——引用溯源。但"做到引用"和"做到能兜底的引用"之间隔着三种完全不同的实现机制，这篇把 ragflow、kotaemon 的源码和 OpenAI、Anthropic 的 API 原语逐个拆开，最后给自建选择建议。

背景交代同前：ragflow 已重写为 Go，本文 Go 证据取自 `internal/`（基线 `deb1235be`），涉及旧 Python 版时标注历史锚点 `2508c46c8`（纯 Python 最后完整态）。

## 1. 为什么引用不只是个 UI 功能

把引用理解成"前端在答案下面挂一排来源卡片"，是低估了它。引用机制真正的作用是两件事：

**第一，引用是免费的在线幻觉检测锚点。**答案引用的每个 `[ID:n]` 都指向一份真实存在的候选 chunk——如果答案引用了一个不存在的 ID，这本身就是幻觉的直接证据；如果一个断言该引用却无引用，它是可疑信号。ragflow 的引用机制让幻觉**可定位、可人工抽检**（引用了不存在的 ID = 幻觉证据），系统本身不打分，但配合在线抽样可以自动打标（`infiniflow/ragflow@deb1235be` 全仓无 LLM-as-judge 自动评分，用户点赞/点踩只是弱信号落库）。对比评测库的 faithfulness 指标（ragas 的陈述分解 + 逐条 NLI，每次打分两次 LLM 调用），引用锚点是在线、零额外 LLM 成本的幻觉信号——离线评测用 faithfulness，在线监控用引用，两层互补。

**第二，引用是可信度工程的产品化载体。**四家厂商全部把引用做成了 API 原语而非前端装饰：OpenAI 的 annotations 带字符区间（`start_index` / `end_index`）；Anthropic 有专门的 Citations API（响应逐句返回 `cited_text`）；Azure 的 agentic retrieval 返回 source references 加执行过程 activity log——引用连着"为什么检索了这些来源"的过程日志一起给；Google 的 Check Grounding API 更进一步，直接在引用结构上做**在线 groundedness 打分**：claim 级判定（每句一个 claim）、partial entailment 判失败（比 ragas 的宽松蕴含更严格）、引用阈值默认 0.6、平均响应 500ms 以内可挂在线链路。厂商普遍比开源做得更细（字符/片段级），方向一致：**引用在生成时与源文档对齐，而不是检索后拼 URL**。

粒度本身也是信任强度：字符区间 > span 高亮 > 句级 [ID:n] > chunk 级来源列表。下面三种机制，恰好覆盖了这条粒度谱的不同位置。

## 2. 机制一：概率式句级归因（ragflow 的 embedding 兜底）

ragflow 最完整的引用能力是一套**事后归因**算法（`infiniflow/ragflow@deb1235be internal/service/citation.go#InsertCitations`），它不依赖 LLM 配合，任何模型都能用。全参数拆解：

1. **分句**：把答案按标点切句（正则含阿拉伯文标点；代码块保留不切）。
2. **逐句 embed**：每句实时算 embedding，与各候选 chunk 的向量做 cosine。
3. **阈值下降搜索**：初始阈值 `thr=0.63`，每轮取相似度大于 `max×0.99` 的 chunk；一轮没找到就把阈值 ×0.8 递降，最低降到 0.3。
4. **限量插入**：每句至多 4 个 chunk，在句尾机械插入 `[ID:n]`（n 为 chunk 在引用列表中的序号）。
5. **坏引用清洗**：兼容清洗 LLM 自己吐出的畸形引用格式——`(ID:12)`、`【ID:12】`、`(**ID:5**)` 等由 `#badCitationPatterns` 正则族统一处理。

这套参数（0.63 起 / ×0.8 / 降到 0.3 / 每句 4 个）与 Python 旧版 `rag/nlp/search.py:177-267` 的 `insert_citations` 逐项一致（锚点 `2508c46c8` 对拍确认）——是跨重写存活的核心算法之一。两个口径细节：归因用的 chunk 向量是检索阶段带出来的候选集向量（Go 版 `#InsertCitationsWithVectors` 直接接收 `chunkVectors`，不重复 embed）；Python 版调用处（`api/db/services/dialog_service.py:652`）传的是对话级混合权重（默认 tkweight=0.1 / vtweight=0.9）——引用归因与主检索共用同一套权重语义。

概率式归因的优缺点都很鲜明。优点：零 LLM 成本（只有每句一次 embedding 调用）、对 LLM 零要求、坏引用还能兜底清洗。缺点：它本质是**相似度猜测**——"这句话像哪个 chunk"不等于"这句话来自哪个 chunk"，跨句语义（比如总结句）可能错配。所以 ragflow 没把它当唯一机制，而是配了引用指令：`rag/prompts/citation_prompt.md` 是一份完整的生成后补引用 prompt，明确规定了**什么必须引**（数字与统计、时间断言、因果、比较、技术定义、直接归因、预测、有争议的断言八类）、**什么不该引**（常识、过渡句、泛泛的引子、模型自己的综合分析），外加一组技术规则：引用放句尾标点之前、每句至多 4 条、禁止把连续引用合并成区间（`[ID:i-j]` 无法解析回来源）、RTL 语言（阿拉伯语/希伯来语/波斯语）的插入位置规则；由 `internal/agent/component/llm.go#injectCitationPrompt` 注入 system message（另有 `citation_plus.md` 第二版本）。prompt 让 LLM 尽量自觉带引用，embedding 归因兜底补漏——两层配合。

## 3. 机制二：确定性标记提取（有 id 就不要猜）

ragflow 的 agentic 检索管线走了完全不同的路。先说管线背景：ragflow Go 版的 `internal/agentic_rag/` 是一个工具调用型 agent 包（grep / bm25 / locate / web_search 等 40 多个工具文件），LLM 检索时不再是一次性"查询→取回"，而是像用搜索引擎一样逐条调用工具——于是工具输出的每条事实行本就带着 `chunk_id: <id>` 溯源字段。归因因此变成纯确定性操作（`infiniflow/ragflow@deb1235be internal/agentic_rag/citations.go`）：

- `#ExtractCitedChunkIDs`：正则 ``chunk_id:\s*([A-Za-z0-9_-]+)`` 从最终答案里提取全部 chunk_id；
- `#InsertCitationMarkers`：按首次出现顺序给每个 id 编号，机械插入 `[ID:N]` 标记（跳过 `<code>` 块内的文本，避免污染代码）；
- 配套的 `internal/agentic_rag/evidence_registry.go#EvidenceRegistry` 给 chunk 与 web 检索结果**统一编号**（`Stamp` 发号、`Resolve` 反查），保证 [ID:n] 在整条管线里指向一致。

**没有任何相似度猜测**——id 是检索时带进来的，归因是正则。这是三种机制里唯一"零歧义"的：要么引用真实存在的 chunk，要么没有引用，不存在"引错了"这个状态。

值得考古的是：这个机制的直系祖先在 Python 聊天管线里早就存在。锚点版的 `api/db/services/dialog_service.py` 里，`decorate_answer`（:648-663）先用 `CITATION_MARKER_PATTERN`（:381，正则 `\[(?:ID:)?(\d+...)\]`，连阿拉伯-印度数字集都覆盖了）检查 LLM 是否已经吐出 `[N]` / `[ID:N]` 标记——**有就直接正则确定性提取，跳过 embedding 归因**；没有才走机制一的概率兜底。也就是说，"确定性优先、概率兜底"的组合策略至少从 2026-03 的 Python 版就是 ragflow 的既定设计，Go 版的 `internal/agentic_rag/` 只是把确定性那半支泛化成了独立包（外加 EvidenceRegistry 和 40+ 个检索工具）。

## 4. 机制三：LLM 声明 + 程序校验（kotaemon 的 START/END_PHRASE 协议）

kotaemon 的做法介于两者之间：让 LLM **声明**引用位置，但用程序**校验**声明的真实性（`Cinnamon/kotaemon@9ad3e4e4 libs/kotaemon/kotaemon/indices/qa/citation_qa_inline.py`）。它的 prompt 强制 LLM 输出两部分：一个 `CITATION LIST`——每条引用包含 `START_PHRASE` / `END_PHRASE`，**必须是从 CONTEXT 里原样复制的约 6 词短语**；以及答案正文，在断言处标 `【number】` 指向引用序号。

程序侧的校验在 `libs/kotaemon/kotaemon/indices/qa/utils.py#find_start_end_phrase`：拿声明的短语对回源文档**重新定位 span**——定位成功，前端就能做到 span 级高亮；定位失败，说明 LLM 引用了不存在于源文档的文本，这正是幻觉证据。这个设计的妙处在于：LLM 想凭空编造引用，就得先编造一个能通过"原文检索"的短语——校验步骤把"引用"从礼貌性输出变成了可证伪声明。

产品形态上（`libs/ktem/ktem/reasoning/simple.py`）给了三档开关：`off`（关）/ `inline`（内联引用）/ `paraphrase`（paraphrase 模式走 `libs/ktem/ktem/utils/visualize_cited.py#CreateCitationVizPipeline` 的引用可视化管线）。相比机制二，它不要求管线里有结构化的 chunk_id（普通 chat 管线即可用）；相比机制一，它有程序校验而不是纯相似度。代价是 prompt 更长、LLM 输出 token 更多，且协议遵从度依赖模型能力。

三种机制放到一张表上：

| | 机制一：概率式归因 | 机制二：确定性提取 | 机制三：声明+校验 |
|---|---|---|---|
| 代表 | ragflow chat 路径 | ragflow agentic 路径 | kotaemon |
| 归因依据 | 句向量 × chunk 向量相似度 | 工具输出自带的 chunk_id | LLM 输出的原文短语 |
| 程序校验 | 无（相似度即依据） | 无需（id 即事实） | 有（短语回定位） |
| 粒度 | 句级 [ID:n] | 行级 [ID:N] | span 级高亮 |
| 对 LLM 的要求 | 零要求 | 按格式带溯源字段 | 遵守 START/END_PHRASE 协议 |
| 额外成本 | 每句一次 embedding | 零 | prompt 与输出变长 |
| 失败模式 | 相似但非来源 → 错配 | 工具不带 id 则失效 | 协议跑偏 → 定位失败（可检出） |

## 5. 厂商对照：引用做成 API 原语长什么样

- **OpenAI annotations**：内联引用作为消息级结构化字段——每个 annotation 带**字符区间**（`start_index` / `end_index`）与 `file_id` / `filename`，前端直接切字符串渲染高亮，不需要任何回定位逻辑。Deep Research 的内联引用同样带字符区间。这是粒度天花板：字符级、生成时对齐、零后处理。
- **Claude Citations API**：请求级支持——`documents` 参数直接传 text / PDF content block，回答时逐句返回 `cited_text` 及其引用的文档片段；可把用户 prompt 本身放进 document 要求带引用回答，可与 web search / Google Search 组合引用网页。官方可靠性提醒值得抄进自建的失败模式清单：上下文必须包含**完整**源文档（否则引用失败或漂移）；streaming 下 citation 事件可能跨 chunk 分裂；引用断言只覆盖到其前缀文本（后面的 token 不受约束）。
- **纯 prompt 引用（llama_index CitationQueryEngine）**：把检索节点再切成 512 token / overlap 20 的引用子块编号（`run-llama/llama_index@7169bcd0d llama-index-core/llama_index/core/query_engine/citation_query_engine.py`，`DEFAULT_CITATION_CHUNK_SIZE=512`），prompt 令 LLM 按 `[N]` 引用。问题在**没有程序校验**：归因粒度完全取决于 LLM 自觉，引用错位、漏引都无法发现——只适合 demo，生产别用。
- **dify 是平台下限**：chunk 级引用——检索结果作为 `retrieval_resource`（segment 列表 + score）随消息返回，前端展示来源文档/段落，**无句级归因机制**（`langgenius/dify@79effdd498 api/core/rag/retrieval/dataset_retrieval.py` 全文无 sentence-level citation）。用户能知道"答案大致来自这几段"，但无法知道"哪句来自哪段"——对内部知识库的容错场景（答错可以接受人工复核）或许够用，对合规敏感场景不够。
- haystack core 没有内置 citation 组件——引用被划为应用层职责，框架不表态。

## 6. 自建怎么选

三种机制对应三种管线形态，决策树很短：

1. **管线里有确定性 id 可用吗？**（agentic 检索、工具输出带 chunk_id、结构化检索记录）→ 有，机制二优先：零歧义、零额外模型成本。ragflow agentic 管线是现成样板。
2. **普通 chat 管线**（LLM 直接对着检索结果生成）→ 机制一做兜底（embedding 句级归因，任何 LLM 通用），或机制三做协议式（有 span 高亮需求、模型协议遵从度可靠时）。两家也可以叠：prompt 引用指令（哪些必须引/不该引）+ 坏引用清洗 + embedding 补漏，即 ragflow 的完整形态。
3. **组合公式一句话：确定性优先、概率兜底。**ragflow 双机制就是答案——同一份代码里，agentic 路径走确定性提取、chat 路径走"LLM 自觉 + 概率归因"，EvidenceRegistry 保证两种来源的编号体系一致。

三个工程注意：**引用编号要全管线一致**（ragflow EvidenceRegistry 的 Stamp/Resolve 就是干这个的，否则前端 [3] 和后端 chunk 对不上）；**引用要落库**（引用关系随消息存储，既是审计证据，也是后续回灌评测的原料——第 8 篇展开）；**token 预算一句带过**——引用机制本身开销不大：注入一段引用指令（ragflow）、输出 START/END_PHRASE 拉长答案（kotaemon）都是小头，"每句至多 4 条 / 约 6 词短语"这类限制同时也是输出预算的护栏；真正的大钱在第 5 篇的检索与重排，别在引用层过度工程。

再往深一层，引用数据应该接进在线质量监控形成闭环：按流量抽样一部分会话，对（问题，检索结果，答案，引用关系）四元组做自动检查——引用了不存在的 ID、该引用处无引用、引用与断言内容对不上（用机制一的相似度思路反向验证），都自动打标进看板；配合用户点赞/点踩这类弱信号定期回灌评测集，就是一套不依赖人工抽检的在线幻觉监控。ragflow 的引用机制天然支持这种玩法，dify 式 chunk 级"来源卡片"则撑不起来——这也是机制选型时容易漏算的长期价值。

最后留一个判断：如果只能做一件事，做**机制一的最小版**（分句 + 与候选 chunk 的向量相似度 + 句尾插 [ID:n]）——五十行代码，就能让答案从"一段文字"变成"一组可验证断言"，在线幻觉监控的地基就有了；将来升级到机制二或机制三，这套地基也照样通用。

## 参考与出处

开源源码（基线 commit 均为 2026-10 冻结）：

- ragflow 概率式句级归因：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/citation.go （`#InsertCitations`：0.63 起阈值 / ×0.8 递降 / 0.3 下限 / 每句 4 chunk；`#badCitationPatterns` 坏引用清洗）
- ragflow 引用 prompt 与注入：https://github.com/infiniflow/ragflow/blob/deb1235be/rag/prompts/citation_prompt.md 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/agent/component/llm.go （`#injectCitationPrompt`）
- ragflow 确定性标记提取：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/agentic_rag/citations.go （`#ExtractCitedChunkIDs` / `#InsertCitationMarkers`）、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/agentic_rag/evidence_registry.go （`#EvidenceRegistry`）
- ragflow 历史锚点（纯 Python 最后完整态 2508c46c8）：https://github.com/infiniflow/ragflow/blob/2508c46c8/rag/nlp/search.py （:177-267 `insert_citations`，参数与 Go 逐项一致）、https://github.com/infiniflow/ragflow/blob/2508c46c8/api/db/services/dialog_service.py （:381 `CITATION_MARKER_PATTERN`、:648-663 `decorate_answer` 确定性优先跳过 embedding 归因）
- kotaemon 内联引用协议：https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/indices/qa/citation_qa_inline.py （`DEFAULT_QA_CITATION_PROMPT`、START/END_PHRASE）、https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/indices/qa/utils.py （`#find_start_end_phrase`）、https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/reasoning/simple.py （off/inline/paraphrase 三模式）、https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/utils/visualize_cited.py （`#CreateCitationVizPipeline`）
- llama_index 纯 prompt 引用：https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/query_engine/citation_query_engine.py （`DEFAULT_CITATION_CHUNK_SIZE=512` / overlap 20）
- dify chunk 级引用：https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/retrieval/dataset_retrieval.py （retrieval_resource 返回）

官方文档与厂商原语：

- Anthropic Citations API（documents 参数、cited_text、可靠性提醒）：https://docs.claude.com/en/docs/build-with-claude/citations
- Anthropic Contextual Retrieval（引用与 grounding 的方法学背景）：https://www.anthropic.com/news/contextual-retrieval
- OpenAI File Search 与 annotations（start_index/end_index 字符区间）：https://developers.openai.com/api/docs/guides/tools-file-search 、https://developers.openai.com/api/docs/guides/retrieval
- ragas faithfulness（对照：离线幻觉指标的两步 LLM 链路）：https://github.com/vibrantlabsai/ragas

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》全 10 篇：

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制（本篇）
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

答案可信了，下一个问题是"谁有权看到这个答案背后的文档"——下一篇聊聊企业级 RAG 最大的必答题：五个开源平台的文档级权限全军覆没的实证，以及自研 ACL 与托管服务各自可抄的模式。
