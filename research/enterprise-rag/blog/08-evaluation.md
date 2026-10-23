# 上线前后的质量防线：RAG 评测体系从零搭建

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

RAG 系统是概率系统：解析可能丢段落，检索可能召回错 chunk，LLM 可能对着正确的资料编错话。改动一个分块参数、换一个 embedding 模型、调一个 top_k，效果往哪个方向动，没人能拍脑袋知道——唯一可靠的答案是评测。但当我逐源码核对完主流开源 RAG 平台和评测库之后，发现一个普遍的认知错位：**平台自带的那几个页面是「调试器」，不是「评测系统」**；而真正能扛门禁的评测能力，平台一个都没带，得靠 ragas / deepeval 两个库自己拼。

这一篇把四件事讲透：平台自带评测的真实成色、ragas 核心指标的算法解剖（知道它怎么算，才知道分数怎么信）、deepeval 的门禁姿势、以及一套从离线黄金集到在线监控的完整方案。中文场景有一个硬前提也会反复强调：**两库的 judge prompt 全是英文**，直接拿来当中文门禁会翻车。

## 一、平台自带评测都是「调试器」

先看 dify。它的知识库页面有个「命中测试」（hit testing）：`langgenius/dify@79effdd498 api/services/hit_testing_service.py#HitTestingService.retrieve`——单条 query 走检索服务（search_method/top_k/score_threshold/rerank 可调），返回 records 列表（含 segment、score、所属文档），每次测试写一条 DatasetQuery 记录留痕。注意它输出的是什么：**一个 chunk 列表，供人眼判断相关性**。hit-rate、MRR、nDCG 这些 IR 标准指标，全仓 grep 不到实现；批量评测集的服务端实现也没有（web 端只有单条 hit-testing 界面）。这就是「调试器」与「评测系统」的区别：调试器帮你调单次召回，评测系统对数据集出可比的分数序列。

dify 的「标注」功能更容易被误读成评测。`api/services/annotation_service.py#AppAnnotationService` 干的事是：把人工标注的 Q&A 对嵌入向量库，线上按相似度命中就直接返回标注答案（`get_annotation_hit_histories` 可查命中历史）。这是 **one-shot 答案缓存**，一个性能/一致性优化功能——命中数可以当弱信号（后面在线监控会用到），但它不评价任何东西。

ragflow 同级：`infiniflow/ragflow@deb1235be internal/handler/chunk.go#RetrievalTest`（POST /api/v1/datasets/search）返回 chunks + doc_aggs，同样只有人眼判断，无指标计算。ragflow 比别人多做了两件有价值的事：一是**引用机制**（`rag/prompts/citation_prompt.md` 的完整引用 prompt + `internal/agent/component/llm.go#injectCitationPrompt` + `internal/agentic_rag/evidence_registry.go` 的统一编号），让每个事实性断言带 [ID:i] 引用——引用了不存在的 ID 就是幻觉的现成证据，这其实是免费的在线幻觉检测锚点；二是消息级点赞/点踩（`internal/service/chat_session.go#UpdateMessageFeedback`，thumbup bool 落库）——弱信号有了，但 ragflow 没有基于它做任何分析。至于 LLM-as-judge 式的 answer 自动评分：全仓 ❌。

观测侧倒是半成品：dify 的 `api/core/ops/ops_trace_manager.py` 通过插件对接 Langfuse/LangSmith/Opik，`core/ops/entities/trace_entity.py` 埋了 token、延迟、TTFT、检索 span、节点执行 span——**链路有痕，但质量无指标**。所以现实是：平台把「看见」做了，「打分」整体留白。

## 二、ragas 指标算法解剖：知道怎么算，才知道怎么信

ragas（`vibrantlabsai/ragas@298b682`）是 RAG 评测的事实标准库。它的价值不在「给了分数」，而在每个指标的算法都可拆到 prompt 级。这是本篇的技术核心，逐个拆。

### faithfulness：陈述分解 → NLI 逐条验证

faithfulness 回答「答案里的话有多少能被检索到的资料支撑」。链路全在 `src/ragas/metrics/_faithfulness.py`，prompt 原文就内嵌在这个文件里：

1. **陈述分解**：`#StatementGeneratorPrompt`（34 行起）的 instruction 原文是 "Break down each sentence into one or more fully understandable statements. Ensure that no pronouns are used"——先把 answer 打碎成无代词的原子陈述（few-shot 示例是爱因斯坦生平）。为什么必须消代词？因为「它增长了 3%」这种句子无法脱离指代做蕴含判定。
2. **逐条验证**：`#NLIStatementPrompt`（73 行起）对每条陈述 × 拼接后的检索上下文做 NLI 蕴含判定，instruction 原文 "return verdict as 1 if the statement can be directly inferred based on the context or 0"，输出 statement/reason/verdict 三元组。
3. **计分**：`#_compute_score`（182 行）就是 `有依据陈述数 / 总陈述数`；分解不出陈述返回 NaN。

所以**每次 faithfulness 打分 = 2 次 LLM 调用**（一次分解 + 一批验证），这是 ragas 评测成本核算的基本单位——评测 1000 条样本，光这一个指标就是 2000 次 judge 调用。它还有个省钱变体 `#FaithfulnesswithHHEM`（218 行起）：分解仍用 LLM，验证换成 vectara 的 HHEM 本地 NLI 分类器，judge token 直接省掉。

### answer_relevancy：反向问题生成 + 向量相似

`src/ragas/metrics/_answer_relevance.py#ResponseRelevancy`（64 行）的思路很妙：让 LLM 从 answer **反向生成问题**（默认 strictness=3，生成 3 个），与真实 user_input 算 embedding 余弦相似度取均值。答案答非所问时，从答案反推出的问题会和原问题在向量空间里偏离，于是不需要参考答案就能量化「废话率」。还有一个止损设计：生成侧同时判断 answer 是否 noncommittal（「我不确定」式回避，prompt 在 38 行），判 noncommittal 则得分直接归零。

### context_precision / context_recall：一个管排位，一个管覆盖

- `src/ragas/metrics/_context_precision.py#LLMContextPrecisionWithReference`（82 行）：对每个检索到的 context，LLM 判 "was useful in arriving at the given answer"（0/1），然后按排序位置算 **Average Precision**（`#_calculate_average_precision`，113 行）——有用 chunk 排得越靠前分越高。这正好对齐 RAG 的实际：前几个 chunk 进 prompt 的位置权重更高。无参考版 `#LLMContextPrecisionWithoutReference`（174 行）用 user_input 替代参考答案作判据，别名 ContextUtilization，零标注成本。
- `src/ragas/metrics/_context_recall.py#LLMContextRecall`（88 行）：把**参考答案**逐句判 "can be attributed to the given context"，score = 可归因句 / 总句——衡量「答题所需的信息检索到了多少」，这是唯一能直接反映检索缺口的响应层指标。它有**两个零 LLM 成本变体**值得记住：`#NonLLMContextRecall`（165 行）直接算 retrieved_contexts 对 reference_contexts 的 token 级覆盖率；`#IDBasedContextRecall`（227 行）退化为文档 ID 集合运算——如果你有黄金 chunk 标注，这两个变体在 CI 里跑起来几乎免费。

另外两个值得点名的：`_noise_sensitivity.py#NoiseSensitivity` 测「噪声文档拉低正确答案的程度」（评测检索侧抗噪）；`dataset_schema.py#SingleTurnSample` 的字段抽象（user_input/retrieved_contexts/reference_contexts/response/reference…）配每个 metric 的 `_required_columns` 声明——指标按需选列、缺列直接报错，这个数据面设计是 ragas 最值得抄的工程决策。

把常用指标按「输入依赖 × LLM 成本」整理成一张选型表（是否需要参考答案是成本分水岭）：

| 指标 | 需要的输入 | LLM 成本 | 度量的是什么 |
|---|---|---|---|
| faithfulness | answer + contexts | 2 次调用 | 答案有多少被资料支撑（响应层） |
| answer_relevancy | question + answer | 1 次生成 + embedding | 答非所问程度（响应层，无参考） |
| ContextUtilization | question + contexts | 每 context 1 次判定 | 有用 chunk 是否排得靠前（检索排序） |
| LLMContextRecall | 参考答案 | 每句 1 次判定 | 答题所需信息检索到多少（检索覆盖） |
| NonLLM / ID-based recall | reference_contexts 或黄金 chunk ID | **0** | 同上，CI 里近乎免费 |
| answer_correctness | 参考答案 | LLM | 答案与参考的一致性（响应层） |

这张表也解释了评测预算怎么花：上线初期零标注，跑前三个 reference-free 指标；等黄金集攒起来了，便宜的 ID-based recall 先进 CI，贵的 LLM 指标做离线报表。

## 三、deepeval 对照：把评测做成 pytest

一句话定位差异：**ragas 是「评测计算器」（喂批量数据出分数矩阵），deepeval（`confident-ai/deepeval@2213fac0f`）是「质量门禁」（像 pytest 一样卡 CI）**。两者互补而非竞争——deepeval 甚至内置了 ragas 适配器（`deepeval/metrics/ragas.py`，RAGASFaithfulnessMetric 等包装类 + 通用 `#RagasMetric`），把 ragas 指标直接包成 deepeval metric 用。

deepeval 的 faithfulness 实现值得对照着看（`deepeval/metrics/faithfulness/faithfulness.py#FaithfulnessMetric`）：三步链 truths（从检索上下文提取事实）→ claims（从实际输出提取断言）→ verdicts，但判定是 **yes / no / borderline 三态**——比 ragas 的 0/1 二值多了一个模糊带，borderline 态可配 `penalize_ambiguous_claims` 决定是否扣分。判定针对 context 原文而非逐句归因，方法论上比 ragas 粗一档但更省调用。prompt 不内嵌在 Python 里，而是 Jinja2 模板外置（`templates/generate_truths.txt / generate_claims.txt / generate_verdicts.txt`，编译进统一的 templates.json）。两个易踩的坑：hallucination 指标（`metrics/hallucination/hallucination.py`）**方向相反**——分数越高幻觉越多，pass 条件是 `score <= threshold`，且它对比的是给定 context，本意是「给模型一段事实测它胡不胡说」，RAG 场景应该用 faithfulness + retrieval_context；red teaming 在 v3.0 已迁出到独立仓 deepteam（`red_teaming/README.md` 明说），本仓只剩残留安全指标（bias/toxicity/pii_leakage 等，中文安全评测可以拿这三个起步）。

门禁形态是 deepeval 的核心竞争力：pyproject.toml 注册了 **pytest11 插件**，`assert_test` 断言 + threshold 直接写成 pytest 用例，`deepeval test run` 进 CI，测试结果可上传 Confident AI 平台。它还自带 OTel tracing（`tracing/tracing.py#observe` 装饰器 + `tracing/otel/exporter.py`），并且**能在 trace 上自动跑 offline_evals**（`tracing/offline_evals/`）——这俩能力在第六节的在线方案里会用到。

几个对照阅读的细节，能看出两库的气质差异：deepeval 的 contextual_precision（`metrics/contextual_precision/contextual_precision.py`，366-388 行）算的是 weighted cumulative precision，数学上与 ragas 的 Average Precision 同族，但判定全走 LLM；它的 answer_relevancy 不用 embedding，靠 LLM 逐条判「该陈述是否与问题相关」再算占比——比 ragas 的反向生成贵，但判定理由可读（每条 verdict 带 reason，排障时能直接看）。工程细节上，deepeval 的 truths/claims 两步用 `asyncio.gather` 并行，批量评测吞吐占优；judge 调用全部走 schema 约束 JSON 输出，judge 模型可经 `DeepEvalBaseLLM` 换成任意厂商。v3.0 还有个把整指标合并为单次请求的 system_one 模式，源码注释自标 EXPERIMENTAL，生产采用前先自验稳定性。

## 四、评测必须分层：检索层与响应层分开

这是两家厂商口径完全一致、但工程实践中最常被混在一起的纪律：**检索层指标（Recall@k / MRR / hit-rate）与响应层指标（faithfulness / relevancy）必须分开度量**。混在一起的典型症状是：答案变好了不知道是检索变好还是生成变好，回归定位无从下手。

检索层指标没有现成的：ragas 和 dify 都不带 hit-rate/MRR 实现，需要自算——好在有了 ID-based 变体和黄金 chunk 标注后，这就是几十行集合运算。分层方法论可以看 openai-cookbook 的教程（`openai/openai-cookbook@9aad95f examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb`）：检索评估（Hit Rate、MRR）与响应评估（Faithfulness、Relevancy）分离，且原话 "Evaluation should serve as the primary metric"；同仓 `File_Search_Responses.ipynb` 教 Recall@k / Precision@k / MRR / MAP。厂商侧互证：Azure RAG 官方架构指南把评测指标命名为 groundedness / completeness / utilization / relevancy，同样按检索/响应分域。

分层之外还有一个值得抄的严格口径：**Google 的 Check Grounding API**（官方文档，2026-10-15 可访问）。它把 groundedness 做成了在线 API：claim 级打分（每句 = 一个 claim），**partial entailment（部分蕴含）判为失败**——比 ragas 的「有依据陈述占比」更严；支持分 [0,1] 分数带，引用阈值默认 0.6，平均延迟 <500ms 可在线调用。自建 judge prompt 时值得抄这条：模糊的「大体上能推出」不算支撑。判得严一点，比放水对产品质量更有用。

分层的工程红利也别浪费：检索层指标是**调参主力**。改 top_k、score_threshold、混合权重、换 rerank 模型这类高频动作，跑一遍黄金集的 Recall@k / MRR 就够定位方向——ID-based 集合运算是秒级的，不烧一次 LLM；响应层指标每次要付 judge 调用（faithfulness 一条 2 次），留给版本级回归用。两类指标混在一个频率跑，要么调参太慢，要么回归太贵。

## 五、中文硬前提：judge 不懂中文的代价

两个库的 judge prompt 全英文，这是中文场景绕不开的坎。

ragas 没有内置中文模板，官方机制是 `src/ragas/prompt/pydantic_prompt.py#adapt`（357 行）：运行时用 LLM 把 prompt 的 few-shot 示例翻译成目标语言（`prompt.adapt(target_language="chinese", llm=...)`）。注意两点：instruction 默认不翻译，只译示例；翻译质量没有保证——文档示例只演示过印地语，翻译后的 few-shot 是否还成立无人背书。deeveval 这边，`metrics/README.md` 宣称有 community 翻译模板机制（`deepeval translate` CLI），但冻结克隆里 `metric_templates/community/` **目录根本不存在**，只有英文 templates.json——宣称未落地，中文使用仍需换模板或赌 judge LLM 的多语能力。

所以中文场景的上线前校准不是可选项：**抽约 50 条样本做人工双评，先验证 judge 与人的一致性（一致率或 κ），达标后才允许进 CI 当门禁**。这一步没做，后面所有自动化分数都是自欺。校准不过关时的修法按成本递增：先改 judge prompt（把 Google Check Grounding 那条「partial entailment 判失败」的严格口径写进去，通常最有效）；再换更强的 judge 模型；分解-验证类指标（faithfulness）可以考虑先对中文跑 `adapt()` 并人工校对译文。顺带一提，ragas 的 adapt() 翻译产物和 deepeval 的自定义模板，改完都建议进版本库——它们是你评测资产的一部分，不是随手配置。

## 六、完整方案：离线黄金集 → CI 门禁 → 在线监控

把前面的积木拼成一套完整防线，三层各自回答一个问题：

**第一层：离线黄金集（上线前）——「这个版本敢不敢上」。** 语料准备用 ragas `TestsetGenerator`（`src/ragas/testset/`）：它先对语料建知识图谱（Node=document/chunk + Relationship，`transforms/default.py#default_transforms` 组装 NER/Themes 抽取、embedding 聚类、连图），再生成 persona（`persona.py#PersonaGenerationPrompt` 先造用户画像再按画像出题），然后从图上生成 single_hop / multi_hop 问答对——多跳问题依赖图上的多节点关系，这是它比「随机抽 chunk 出题」强的地方。数据装载用 `EvaluationDataset`，与 HuggingFace 格式互转，样本上还带 query_style / query_length 元数据（合成时记录，便于按问题风格分层统计）。但合成集只做回归基线：**黄金集必须含人工样本**——合成的中文问题分布、表述方式都和真实用户有距离，人工抽检修正是入库前的必要工序。

指标组合按标注成本递进：零标注先跑 `faithfulness + answer_relevancy + ContextUtilization`（全 reference-free）；有标注后补 `context_recall`（优先 NonLLM / ID-based 变体，零 LLM 成本）和 answer_correctness；检索层自算 Recall@k / MRR（按 chunk ID 对黄金标注做集合运算）。

**第二层：CI 门禁（每次变更）——「这次改动有没有把好的改坏」。** 用 deepeval 的 pytest 形态把黄金集变成回归测试：`assert_test` + threshold 写成用例挂 CI，ragas 指标经 `deepeval/metrics/ragas.py` 适配器包进去。ragas 自身没有 pytest 插件（`evaluate()/aevaluate()` 是库调用 + experiment 脚本），不想引 deepeval 就自己写断言脚本出分数 diff——两条路都通，前者省事后者少一个依赖。

**第三层：在线监控（上线后）——「线上质量在不在漂移」。** 三个抓手：

- **trace**：dify 走原生 ops trace 接 Langfuse（token/延迟/检索 span 已埋好）；自建系统直接用 ragas 的 langfuse/mlflow 导出端（`src/ragas/integrations/tracing/`）或 deepeval 的 OTel `@observe`（后者还能在 trace 上自动跑 offline_evals）。
- **抽样在线评测**：按流量抽 1-5%，对 (query, contexts, answer) 三元组跑 reference-free 指标进看板——faithfulness 和 answer_relevancy 都不需要参考答案，在线可用。抽样率别拍脑袋：reference-free 不等于免费，faithfulness 每条 2 次 judge 调用，按日均问答量和 judge 单价把这笔账算进预算再定百分比。
- **用户弱信号回灌**：dify 的标注命中历史、ragflow 的点赞/点踩，定期人工审一遍回灌评测集；再叠加引用锚点做免费的幻觉自动打标（ragflow 式引用编号下，「无引用的事实断言」和「引用了不存在 ID」都可以自动标出来送人工）。

三层合起来，才配叫「防线」：离线定基线，CI 防回归，在线抓漂移。缺任何一层，另外两层都会慢慢失真——没有 CI 的离线集会过期，没有在线抽样的门禁阈值会脱离真实分布。

## 结语

评测这一篇的方法论内核其实就两句话：平台给的是显微镜（调试器），门禁要自己搭；指标算法要拆开看（prompt 级），分数才可信。ragas 负责把分数算得讲究，deepeval 负责把分数卡得坚决，分层纪律保证回归可定位，50 条人工双评保证中文 judge 不说谎。这套东西搭起来大约是一两周的工程量，但它决定的是你后面每一次「调参、换模型、改分块」敢不敢按下去。

下一篇聊两个最容易被神化的进阶选项：GraphRAG 和 Agentic RAG。索引成本三倍起跳的知识图谱什么时候值回票价、80% 场景为什么固定管线就够——第 9 篇给出判断框架。

## 参考与出处

源码基线（2026-10 冻结）：`langgenius/dify@79effdd498`、`infiniflow/ragflow@deb1235be`、`vibrantlabsai/ragas@298b682`、`confident-ai/deepeval@2213fac0f`、`openai/openai-cookbook@9aad95f`。正文中的相对路径均相对上述基线。

**ragas**
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/metrics/_faithfulness.py （StatementGeneratorPrompt / NLIStatementPrompt / _compute_score / FaithfulnesswithHHEM）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/metrics/_answer_relevance.py （ResponseRelevancy 与 noncommittal prompt）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/metrics/_context_precision.py （Average Precision 与无参考版）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/metrics/_context_recall.py （LLMContextRecall / NonLLMContextRecall / IDBasedContextRecall）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/metrics/_noise_sensitivity.py （噪声敏感度）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/dataset_schema.py （SingleTurnSample 字段抽象）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/prompt/pydantic_prompt.py （adapt 多语言机制）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/testset/ （TestsetGenerator：graph.py / transforms/default.py / synthesizers / persona.py）
- https://github.com/vibrantlabsai/ragas/blob/298b682/src/ragas/integrations/tracing/langfuse.py （Langfuse 导出端）

**deepeval**
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/metrics/faithfulness/faithfulness.py （FaithfulnessMetric 三态判定）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/metrics/faithfulness/templates/generate_verdicts.txt （judge prompt 模板，另有 generate_truths.txt / generate_claims.txt）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/metrics/ragas.py （内置 ragas 适配器）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/metrics/contextual_precision/contextual_precision.py （weighted cumulative precision）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/metrics/hallucination/hallucination.py （方向相反的幻觉指标）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/pyproject.toml （pytest11 插件注册）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/tracing/tracing.py 与 https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/tracing/otel/exporter.py （OTel tracing）
- https://github.com/confident-ai/deepeval/blob/2213fac0f/deepeval/red_teaming/README.md （red teaming 已迁出至 deepteam）

**dify**
- https://github.com/langgenius/dify/blob/79effdd498/api/services/hit_testing_service.py （hit testing）
- https://github.com/langgenius/dify/blob/79effdd498/api/services/annotation_service.py （标注 = 答案缓存）
- https://github.com/langgenius/dify/blob/79effdd498/api/core/ops/ops_trace_manager.py 与 https://github.com/langgenius/dify/blob/79effdd498/api/core/ops/entities/trace_entity.py （trace 埋点）

**ragflow**
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/chunk.go （RetrievalTest）
- https://github.com/infiniflow/ragflow/blob/deb1235be/rag/prompts/citation_prompt.md （引用 prompt）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/agentic_rag/evidence_registry.go （引用编号注册）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/chat_session.go （消息反馈）

**openai-cookbook**
- https://github.com/openai/openai-cookbook/blob/9aad95f/examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb （检索/响应分层评估）
- https://github.com/openai/openai-cookbook/blob/9aad95f/examples/File_Search_Responses.ipynb （Recall@k / MRR / MAP 教程）

**官方文档（2026-10-15 可访问，非源码级）**
- Google Check Grounding API：https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding
- Azure RAG 设计与评测指南：https://learn.microsoft.com/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建（本篇）
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

下一篇（第 9 篇）讲两个进阶选项的判断框架：GraphRAG 的四问决策（全局问题占比/语料稳定性/预算/图库运维）与 Agentic RAG 的 80% 论证，以及 LightRAG mix 模式怎么从现有向量 RAG 渐进升级。
