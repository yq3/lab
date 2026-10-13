# 08 评测与可观测（Evals & Observability）

> 第八维度：RAG 系统上线前后靠什么守住质量。源码对象：ragas（298b682）、deepeval（2213fac0f）为主，dify（79effdd498）/ ragflow（deb1235be）补平台自带评测视角。证据路径均相对 `~/develop/opensource/<repo>/`，标注【核心】（源码实现）/【示例】/【文档】，查不到标 ❌/⚠️。

## 1. 总表：ragas vs deepeval

| 维度 | ragas | deepeval |
|---|---|---|
| 定位 | RAG 评测**库**（数据集→指标→批量报表） | LLM 应用**单测框架**（pytest 断言门禁 + 评测库） |
| RAG 指标面 | faithfulness / answer_relevancy / context_precision / context_recall / noise_sensitivity / answer_correctness / answer_similarity / factual_correctness / context_entities_recall / 多模态 faithfulness 等（`src/ragas/metrics/__init__.py` 全量导出） | faithfulness / answer_relevancy / contextual_precision / contextual_recall / contextual_relevancy / hallucination + 安全类（bias/toxicity/pii_leakage/misuse/non_advice）+ GEval 自定义指标 + 会话轮次变体（turn_faithfulness 等） |
| 确定性（非 LLM）指标 | BLEU/ROUGE/ChRF/string/DataCompy + **NonLLM context_precision/recall + ID-based 版**【核心】 | exact_match / pattern_match / json_correctness【核心】 |
| 无参考（reference-free） | faithfulness、answer_relevancy、ContextUtilization（=context_precision 无参考版）；context_recall/answer_correctness/noise_sensitivity 均需 reference【核心】 | faithfulness / answer_relevancy / contextual_precision / contextual_relevancy 不需要 expected_output；contextual_recall、hallucination(需 context) 见各文件 `_required_params`【核心】 |
| 合成测试集 | TestsetGenerator：知识图谱（Node=doc/chunk + Relationship）+ transforms（NER/Themes 抽取）+ persona + single/multi_hop 生成器【核心】 | Synthesizer：`generate_goldens_from_docs` / `generate_goldens_from_contexts`，无图谱【核心】 |
| pytest/CI 集成 | ❌ 无 pytest 插件；`evaluate()/aevaluate()`（`src/ragas/evaluation.py`）+ CLI `ragas evals` 跑 experiment 脚本，CI 靠自己写脚本断言 | 原生 pytest11 插件（`pyproject.toml` 注册 `deepeval.plugins.plugin`）+ `assert_test` 断言 + `deepeval test run` CLI；测试结果上传 Confident AI 平台【核心】 |
| red teaming | ❌ | `red_teaming/` 目录只剩 README：**v3.0 起迁出到独立仓 deepteam**（`deepeval/red_teaming/README.md`【核心】）；残留安全指标在 metrics/ 下 |
| 自家 tracing | 无自家系统；导出端：integrations/tracing/（langfuse.py、mlflow.py）+ langsmith/opik/helicone 集成 + langchain callbacks 透传【核心】 | 自带 OTel tracing：`tracing/tracing.py#observe` 装饰器 + `tracing/otel/exporter.py`，依赖 opentelemetry-sdk ^1.24（pyproject.toml）；且能在 trace 上跑 offline_evals（`tracing/offline_evals/`）【核心】 |
| 中文 prompt | 无内置中文模板；`PydanticPrompt.adapt(target_language, llm)` 运行时 LLM 翻译 few-shot examples，instruction 默认不译【核心】 | 英文 templates.json 为主；metrics/README.md 宣称 community 翻译机制（`deepeval translate`），但冻结克隆中 community 目录不存在 ⚠️（宣称 vs 实现存差） |
| license | Apache-2.0 | Apache-2.0 |

一句话定位差异：**ragas 是"评测计算器"（喂批量数据出分数矩阵），deepeval 是"质量门禁"（像 pytest 一样卡 CI）**。deepeval 甚至内置了 ragas 适配器（`deepeval/metrics/ragas.py` 把 ragas 指标包成 deepeval metric 用），说明二者互补而非互斥【核心】。

## 2. 核心指标算法解剖

### 2.1 ragas faithfulness：陈述分解 → 逐条 NLI 验证

链路全在 `ragas/src/ragas/metrics/_faithfulness.py`，prompt 原文就内嵌在该文件（不是独立 prompts.py）：

1. **陈述分解** `#StatementGeneratorPrompt`（37 行起）：instruction 原文 "Break down each sentence into one or more fully understandable statements. Ensure that no pronouns are used"——把 answer 打碎成无代词的原子陈述，few-shot 示例为爱因斯坦生平。
2. **逐条验证** `#NLIStatementPrompt`（73 行起）："return verdict as 1 if the statement can be directly inferred based on the context or 0"——LLM 对每条陈述 × 拼接后的 retrieved_contexts 做蕴含判定，输出 statement/reason/verdict 三元组。
3. **计分** `_compute_score`（182 行）：`score = 有依据陈述数 / 总陈述数`；分解不出陈述则返回 NaN。
4. **非 LLM 变体** `#FaithfulnesswithHHEM`（218 行起）：分解仍用 LLM，验证换成 vectara/hallucination_evaluation_model（HHEM）本地 NLI 分类器，省 judge token。

**每次 faithfulness 打分 = 2 次 LLM 调用**（分解 + 批量验证），这是 ragas 评测成本核算的基本单位。

### 2.2 ragas answer_relevancy：反向问题生成 + 向量相似度

`ragas/src/ragas/metrics/_answer_relevance.py#ResponseRelevancy`：让 LLM 从 answer **反向生成问题**（strictness=3，即生成 3 个），与真实 user_input 算 embedding 余弦相似度取均值；若生成侧判 answer 为 noncommittal（敷衍/回避，prompt 38 行），得分直接 ×0。妙处：不需要参考答案即可量化"答非所问/废话"。依赖 `MetricWithEmbeddings`【核心】。

### 2.3 ragas context_precision / context_recall：一个判有用性排位，一个判覆盖

- `metrics/_context_precision.py#LLMContextPrecisionWithReference`：对每个检索到的 context，LLM 用 `#ContextPrecisionPrompt` 判 "was useful in arriving at the given answer"（0/1），然后按排序位置算 **Average Precision**（`_calculate_average_precision`，113 行）——排前面的该有用。无参考版 `#LLMContextPrecisionWithoutReference`（174 行）用 user_input 替代 reference 作判据，别名 ContextUtilization。
- `metrics/_context_recall.py#LLMContextRecall`：把**参考答案**逐句判 "can be attributed to the given context"（`#ContextRecallClassificationPrompt`，45 行起），score = 可归因句 / 总句——衡量检索到了多少答题所需信息。`#NonLLMContextRecall`（165 行）直接算 retrieved_contexts 对 reference_contexts 的覆盖率（token 级），无需 LLM；`#IDBasedContextRecall`（227 行）用文档 ID 集合运算，适合有黄金 chunk 标注的场景。

### 2.4 ragas noise_sensitivity 与数据集抽象

- `metrics/_noise_sensitivity.py#NoiseSensitivity`：需 reference。把 ground truth 答案和（加噪后的）检索结果分别过 faithfulness 链路，测"噪声文档拉低正确答案"的程度，分 relevant/irrelevant 两种噪声模式——评测**检索侧抗噪**而非生成侧。
- 数据集抽象 `src/ragas/dataset_schema.py#SingleTurnSample`：`user_input / retrieved_contexts / reference_contexts / response / reference / rubrics / persona_name / query_style / query_length`（合成时记录风格元数据）；`#MultiTurnSample` 支持多轮；`#EvaluationDataset` 批量装载 + HuggingFace 格式互转。每个 metric 用 `_required_columns` 声明依赖字段，缺列直接报错——**指标可组合、按需选列**是 ragas 数据面最值得抄的设计。

### 2.5 deepeval 的对应实现（三态判定 + 模板外置）

- faithfulness：`deepeval/metrics/faithfulness/faithfulness.py#FaithfulnessMetric`，三步链 truths（从 retrieval_context 提取事实）→ claims（从 actual_output 提取断言）→ verdicts（yes/**no/borderline** 三态判定）。与 ragas 的差异：①判定针对 context 原文而非逐句归因；②borderline 态可配 `penalize_ambiguous_claims`；③异步版 truths/claims 用 `asyncio.gather` 并行。prompt 原文在 `metrics/faithfulness/templates/generate_truths.txt / generate_claims.txt / generate_verdicts.txt`（Jinja2 模板，`.txt` 源文件编译进 `deepeval/templates/metrics/templates.json` 统一 bundle，resolver 在 `deepeval/templates/resolver.py`）【核心】。
- answer_relevancy：`metrics/answer_relevancy/answer_relevancy.py`——分解 statements → 逐条判 relevant to input → 占比计分（不用 embedding，纯 LLM 判定，比 ragas 贵但可解释）。
- contextual_precision：`metrics/contextual_precision/contextual_precision.py`——LLM 逐条判 retrieval_context 节点相关性后算 **weighted cumulative precision**（366-388 行），数学上与 ragas AP 同族。
- hallucination：`metrics/hallucination/hallucination.py#HallucinationMetric`——注意**方向相反**：score 越高幻觉越多，threshold 判断是 `score <= threshold` 才 pass；且它对比的是 `context`（给定事实），设计意图是"给模型一段事实测它胡说不胡说"，不完全等于 RAG 场景（RAG 场景用 faithfulness + retrieval_context）。
- LLM 调用方式：所有 judge 调用走 schema 约束 JSON（`generate_with_schema_and_extract`），模型侧 `DeepEvalBaseLLM` 可换任意厂商；v3.0 新增 system_one eval mode（整指标合并为单次请求，见 faithfulness.py 内 `SystemOneEvalSpec`）【核心】。

### 2.6 合成测试集生成

- ragas（演进为知识图谱方案）：`src/ragas/testset/`。`graph.py` 定义 Node（document/chunk 两型）+ Relationship；`transforms/default.py#default_transforms` 组装默认流水线（NERExtractor/ThemesExtractor 抽实体主题 → embeddings 聚类 → relationship builder 连图）；`synthesizers/single_hop/` 与 `multi_hop/`（`abstract.py` 定义抽象查询模式、`specific.py` 具体化）从图上选节点生成问答对；`persona.py#PersonaGenerationPrompt` 先造用户画像再按画像出题。入口 `synthesizers/generate.py#TestsetGenerator`，`with_langchain()/with_llamaindex()` 两种构造。**多跳问题依赖图上的多节点关系，这是它比"随机抽 chunk 出题"强的地方**【核心】。
- deepeval：`deepeval/synthesizer/synthesizer.py#Synthesizer`——`generate_goldens_from_docs`（从文档生成 goldens）/ `generate_goldens_from_contexts`，带 chunking、跨文件 context 合并、cosine 相似度去重。轻量，无图结构【核心】。

## 3. 平台自带评测能力

### 3.1 dify：hit testing 是"召回调试器"，标注是"线上答案缓存"，都不是评测

- **hit testing（召回测试）**：`dify/api/services/hit_testing_service.py#HitTestingService.retrieve`——单条 query 走 `RetrievalService.retrieve`（search_method/top_k/score_threshold/rerank 可调），返回 records（含 segment、score、所属文档），每次测试写 `DatasetQuery` 表（source=HIT_TESTING）留痕。控制器在 `api/controllers/console/datasets/hit_testing.py`（管理台）与 `controllers/service_api/dataset/hit_testing.py`（开放 API，可脚本化）。**只有人眼判断相关性，无 IR 指标（hit-rate/MRR/nDCG 全仓 ❌）、无批量评测集**【核心】。
- **标注（annotation reply）**：`api/services/annotation_service.py#AppAnnotationService`——这不是质量评测，是 one-shot 答案缓存：`enable_app_annotation` 起 celery 任务把人工标注 Q&A 对嵌入向量库，线上按 `score_threshold` 相似度命中即直接返回标注答案；`get_annotation_hit_histories` 可查命中历史（命中数可当弱信号）。支持批量导入导出（`batch_import_app_annotations`）【核心】。
- **可观测**：`api/core/ops/ops_trace_manager.py` 通过插件对接 Langfuse/LangSmith/Opik（`from dify_trace_langfuse import ...`，232-255 行）；`core/ops/entities/trace_entity.py` 定义 token（prompt/completion/total）、latency、TTFT、`DATASET_RETRIEVAL_TRACE`、`NODE_EXECUTION_TRACE`（elapsed_time）、`MESSAGE_TRACE`（provider_response_latency）——**检索有 span 可见但无"命中率/相关率"这类质量埋点**，质量指标要靠接 Langfuse 后在观测侧对 trace 跑离线评测【核心】。

### 3.2 ragflow：引用是"可信度工程"，反馈是弱信号，无自动评分

- **引用机制**：`rag/prompts/citation_prompt.md`（生成后补 [ID:i] 引用的完整英文 prompt：哪些必须引——数字/时间/因果/对比，哪些不引——常识/过渡句，含 RTL 语言规则）；Go 侧 `internal/agent/component/llm.go#injectCitationPrompt`（1117 行，把引用指令 append 进 system message）+ `internal/agentic_rag/evidence_registry.go#EvidenceRegistry`（给 chunk/web 结果统一编号，`Stamp`/`Resolve`）。另有 `citation_plus.md` 第二版本。**引用能让幻觉可定位、可人工抽检（引用了不存在的 ID = 幻觉证据），但系统本身不给分**【核心】。
- **检索测试**：`internal/handler/chunk.go#RetrievalTest`（POST /api/v1/datasets/search），question + kb 参数返回 chunks + doc_aggs，与 dify hit testing 同级，无指标计算【核心】。
- **用户反馈**：`internal/service/chat_session.go#UpdateMessageFeedback`（路由 `PUT chats/:chat_id/.../feedback`，body 为 `thumbup: bool`）——消息级点赞/点踩落库，可回灌为评测样本，但 ragflow 未做任何基于它的分析【核心】。
- **answer 质量自评**：❌ 全仓未发现 LLM-as-judge 式自动评分代码。

## 4. 「上线前后评测体系」推荐（最小可行组合)

1. **离线评测集（上线前门禁）**：
   - 语料准备：ragas `TestsetGenerator`（知识图谱 + persona + multi_hop）生成候选问答对，**人工抽检修正后入库**（合成集只做回归基线，黄金集必须含人工样本，中文尤其如此）。
   - 指标组合：无参考先跑 ragas `faithfulness + answer_relevancy + ContextUtilization`（零标注成本）；有标注后补 `context_recall`（NonLLM/ID-based 版零 LLM 成本）+ `answer_correctness`。检索侧再加自建 hit-rate/MRR（ragas/dify 都不自带，需按 DatasetQuery/chunk ID 自算）。
   - 中文注意：ragas prompt 全英文，先对每个指标跑 `prompt.adapt(target_language="chinese", llm=...)` 并人工校对翻译，且用 ~50 条人工双评验证 judge-人一致性（κ 或一致率）后才可作为门禁。
2. **CI 集成（变更防护）**：用 deepeval 的 pytest 断言形态（`assert_test` + threshold）把黄金集变成回归测试挂 CI；ragas 指标可直接经 `deepeval/metrics/ragas.py` 适配器包进去，或用 `ragas evaluate` 脚本出报表 diff。
3. **在线监控（上线后）**：
   - trace 侧：dify 走原生 ops trace 接 Langfuse（token/延迟/检索 span 已埋好）；自建系统直接复用 ragas 的 langfuse/mlflow 集成或 deepeval 的 OTel `@observe`（后者还能在 trace 上自动跑 offline_evals）。
   - 质量侧：**抽样在线评测**（按流量抽 1-5% 对 (q, contexts, answer) 跑 reference-free 指标入看板）+ 用户弱信号（dify 标注命中/ragflow thumbup）定期回灌评测集。
   - 引用侧：ragflow 式引用编号既提升可信度，又给在线幻觉检测提供了免费锚点（无引用断言/引用错位可自动打标）。
4. **安全评测**：中文安全场景用 deepeval 现成 bias/toxicity/pii_leakage 指标起步，系统化 red teaming 需另接 deepteam 仓（v3.0 已从 deepeval 剥离）。

## 5. 证据与存疑清单

**核心证据（均已读源码）**
- ragas：`src/ragas/metrics/_faithfulness.py#Faithfulness/#NLIStatementPrompt/#FaithfulnesswithHHEM`；`_answer_relevance.py#ResponseRelevancy`；`_context_precision.py#LLMContextPrecisionWithReference/#LLMContextPrecisionWithoutReference`；`_context_recall.py#LLMContextRecall/#NonLLMContextRecall/#IDBasedContextRecall`；`_noise_sensitivity.py#NoiseSensitivity`；`src/ragas/dataset_schema.py#SingleTurnSample/#EvaluationDataset`；`src/ragas/testset/{graph.py,transforms/default.py,synthesizers/generate.py#TestsetGenerator,persona.py}`；`src/ragas/prompt/pydantic_prompt.py#adapt`；`src/ragas/evaluation.py#aevaluate`；`src/ragas/integrations/tracing/{langfuse.py,mlflow.py}`。
- deepeval：`deepeval/metrics/faithfulness/faithfulness.py#FaithfulnessMetric` 及 `templates/*.txt`；`metrics/contextual_precision/contextual_precision.py`；`metrics/hallucination/hallucination.py`；`metrics/ragas.py`；`deepeval/test_case/llm_test_case.py#SingleTurnParams`；`deepeval/synthesizer/synthesizer.py#Synthesizer`；`deepeval/tracing/tracing.py#observe` + `tracing/otel/exporter.py`；`pyproject.toml`（pytest11 插件注册、OTel 依赖）。
- dify：`api/services/hit_testing_service.py#HitTestingService.retrieve`；`api/services/annotation_service.py#AppAnnotationService`；`api/core/ops/ops_trace_manager.py` + `core/ops/entities/trace_entity.py`。
- ragflow：`rag/prompts/citation_prompt.md`；`internal/agent/component/llm.go#injectCitationPrompt`；`internal/agentic_rag/evidence_registry.go`；`internal/handler/chunk.go#RetrievalTest`；`internal/service/chat_session.go#UpdateMessageFeedback`。

**存疑清单**
- ⚠️ deepeval 社区多语言模板：`deepeval/metrics/README.md` 宣称 community 翻译 + `deepeval translate` CLI，但冻结克隆（2213fac0f）内 `metric_templates/community/` 目录不存在，仅英文 `templates.json`——宣称未落地或未随包发布，中文使用仍需换模板或靠 judge LLM 多语能力。
- ⚠️ ragas 中文适配质量：`adapt()` 是通用 LLM 翻译机制，文档示例仅演示印地语，翻译后的 few-shot 质量无人保证；faithfulness 类分解-验证链在中文上的判定漂移无官方 issue 佐证（本轮未爬 GitHub issues，不下结论）。
- ⚠️ deepeval v3.0 的 system_one / jev_eval 模式标 EXPERIMENTAL（faithfulness.py 注释自述），生产采用需自验稳定性。
- ❌ dify/ragflow 均无 hit-rate/MRR/nDCG 类 IR 指标实现；dify 无批量评测（batch evaluation）服务端实现（web 端仅有 hit-testing 界面）；ragflow 无 answer 自动评分。
- ❌ ragas 无 pytest 插件、无自家 tracing 后端（均为集成导出模式），CI 门禁需自写断言脚本。
- ⚠️ deepeval red teaming：README 与 `red_teaming/README.md` 明确 v3.0 起迁移到 confident-ai/deepteam 独立仓，本克隆未含其源码，red teaming 能力细节未做源码级核验。
