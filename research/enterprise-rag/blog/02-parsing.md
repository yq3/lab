# RAG 的第一道生死线：中文文档解析怎么做

《给 Agent 造知识库：企业级 RAG 搭建手记》第 2 篇。

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

## 一、为什么解析是生死线

企业内部文档的现实，和 RAG 教程里那个干净的 markdown 世界差距很大：合同是盖章后扫描进系统的图片 PDF，红头文件是双栏排版带公章，财务报表是跨页大表，研发文档里躺着公式和 CAD 截图。这些文档进入知识库的第一步是解析——把版面还原成带结构的文本。而表格串列、双栏错序、页眉页脚混进正文、公式变乱码，这些常见解析错误（失败模式属生态通识，未源码级验证）有一个共同点：**一旦进了索引，下游任何环节都无法修复**。切分只能对错误的结构切，检索只能召回错误的内容，重排只能给错误的文本打分。

所以这一层的选型纪律是：**解析质量不达标，后面全部白搭**。我们调研给出的落地验收口径也很朴素——上线前拿 50-100 份真实企业文档（刻意包含扫描件和复杂表格）做解析抽检，看表格、公式、页码的正确率，而不是看 demo 上一份英文论文的渲染效果。

解析层还有一个容易踩的分层误区：解析和切分是两件事。解析库负责「结构还原」（标题层级、表格、页码、阅读序），切分负责「块边界」。本篇聚焦前者，后者下一篇讲——但结尾会说明为什么两者的接口设计决定了你切分的上限。

先给结论：中文场景的双服务拓扑是 **MinerU 4.0 管扫描件和复杂 PDF，docling 管原生 PDF 和 Office/HTML**，ragflow 的 Go 版自己就示范了这套拓扑。下面逐个解剖。

## 二、三强解剖

### 2.1 MinerU 4.0：档位化的中文解析事实标准

MinerU（上海 AI Lab，opendatalab）是中文文档解析的事实标准，但注意：**它已经换代到 4.0，网上大量 magic_pdf 时代的资料过期了**。4.0 把「解析编排」（`mineru/backend/`）、「模型」（`mineru/model/`）、「IO」（`mineru/parser|render|kit`）彻底分层，底层 PDF 读取和 Office 转换交给新依赖 docvortex（`opendatalab/MinerU@b7f3dd0c mineru/backend/analyze.py#doc_analyze`）。

PDF 解析有两个正交维度。第一个是 **parse_mode**：auto/txt/ocr，`PDFDocument.classify()` 自动判断是原生文本 PDF 还是扫描件。第二个是 **effort 档位**（`mineru/backend/analysis/pdf/pipeline.py:43-69`），这是 4.0 的核心设计：

| 档位 | 管线 | 适用 |
|---|---|---|
| flash | 纯文本抽取，零模型 | 原生 PDF、Office/HTML 直转 |
| medium | 小模型混合：布局 + OCR + 表格 + 公式 | 扫描件起步档 |
| high | 小模型定布局，正文走 1.2B VLM | 重要文档 |
| xhigh | VLM 两步抽取 + 图像分析 | 极端复杂版面 |

模型清单（`opendatalab/MinerU@b7f3dd0c mineru/model/registry.py`，全部实锤）：

- **布局**：PP-DocLayoutV2；
- **OCR**：`ch_PP-OCRv6_tiny_det` + `ch_PP-OCRv6_small_rec`——中文主力，且 OCR 语言默认就是 `lang="ch"`（`mineru/model/ocr/language.py:64`），中文是一等公民；
- **表格**：slanet-plus + unet + PP-LCNet 表格分类（先分类路由有线/无线表模型）；
- **公式**：PP-FormulaNet-Plus-M，**标配**不是可选项；
- **印章**：seal_PP-OCRv4——公章场景有专门模型；
- **VLM**：MinerU2.5-Pro-2605-1.2B，支持 vllm/lmdeploy/mlx 部署，也有 GGUF 走 llama.cpp，还能配成远程 `server_url` 让推理独立成服务。

```
PDF ─ classify ─▶ txt（原生）/ ocr（扫描）
 │
 ├─ flash    纯文本抽取（零模型）
 ├─ medium   PP-DocLayoutV2 + ch_PP-OCRv6 + SLANet-plus + PP-FormulaNet
 ├─ high     小模型定布局 + 1.2B VLM 抽正文（原生表格可回填免 VLM）
 └─ xhigh    VLM 两步抽取 + 图像分析
        ▼
ModelJson（页级模型结果）→ MiddleJson → markdown / content_list / docx / html / latex
```

硬件门槛友好是它流行的重要原因（README 硬件表，`opendatalab/MinerU@b7f3dd0c README.md`）：basic 档（纯小模型）ONNX 约 0.8GB、2GB 内存、**纯 CPU 可跑**——冷启动便宜；吞吐上来再上 vLLM 加 GPU（需 8GB+ 显存）。服务化用自带的 `mineru/parser/api_server.py`（FastAPI，任务上传 + zip 产物），VLM 可拆成独立的 vlm_server。

产物两级：`ModelJson`（严格页级模型结果，带 producer 元数据）→ `MiddleJson`（bbox 和阅读序在块级保留），渲染层可输出 markdown、content_list、docx、html、latex。**content_list 是给下游程序消费的——它本身就是天然的块边界清单**，这一点在第四节和下一篇会反复用到。

### 2.2 docling：结构输出最完整的转换器

docling（IBM）的定位是「结构化转换器」：输入任意文档，输出一个统一的中间格式 **DoclingDocument**。它的 PDF 管线是多线程阶段流水线（`docling-project/docling@dd477a9f docling/pipeline/standard_pdf_pipeline.py:730-802`）：

```
preprocess（PDF 解析）→ layout（Heron）→ OCR → layout 后处理
      → table（TableFormer）→ assemble → reading_order / heading_hierarchy
      →（可选 enrichment：公式 CodeFormula VLM、图片分类与描述）
      → DoclingDocument
```

与老版「每页顺序跑五个模型」不同，现在各阶段是独立线程加队列，OCR、布局、表格阶段都能配批量（`ocr_batch_size`/`layout_batch_size`/`table_batch_size`），吞吐可以按阶段单独调。PDF 后端三代并存：docling_parse_v4 主力，managed_pdfium 与 pypdfium2 兜底，模型装配走工厂加 entry_points 插件机制，第三方可以注册自己的模型类。

模型阵容在近一年**全换过血**（这也是旧资料失效的重灾区）：

- **布局**：默认 docling-layout-heron（RT-DETR 系），可选 heron-101、egret-medium/large/xlarge；旧 DocLayNet YOLO 已弃用，配了会回退 Heron（`docling/datamodel/stage_model_specs.py:1017-1072`、`datamodel/layout_model_specs.py:76`）；
- **表格**：TableFormer V1 默认、TableFormerV2 与 GraniteVision 可选三选一（`docling/datamodel/pipeline_options.py:151,190`）；
- **OCR**：工厂插件化——rapidocr（PaddleOCR 系，中文可用）/tesseract/easyocr/ocrmac/nemotron/kserve_v2（`pipeline_options.py:329-767`）。中文要点：显式配 rapidocr 引擎（无 tesseract 环境下的默认回退行为档案未实测，部署时先验证）；
- **公式**：CodeFormula VLM，默认 granite-docling-258M（`pipeline_options.py:1166`）；
- **VLM 整页路线**：`docling/pipeline/vlm_pipeline.py` 已内置 **10+ 个第三方 VLM 预设**（`stage_model_specs.py:1106-1646`）：SmolDocling、MinerU2.5-Pro、GLM-OCR、Nemotron-Parse、DeepSeek-OCR、GOT-OCR、Qwen2.5-VL、gemma-3……docling 实际已经变成「VLM 解析模型聚合器」——你想试任何整页 VLM 解析模型，它大概率有现成 preset。

格式面是三者最宽：backend 目录覆盖 PDF（三代后端并存）、docx/pptx/xlsx、HTML、EPUB、图片、邮件、LaTeX、CSV、iWork、XML、音视频等 20 余种，Office/HTML 走原生解析不走 OCR，快且稳。

输出是它的王牌：DoclingDocument 里 texts/tables/pictures 每个元素都带 `prov`——bbox 加页码原生保留，表格有 grid/HTML/Markdown 三种形态（消费示例见 `Cinnamon/kotaemon@9ad3e4e4 libs/kotaemon/kotaemon/loaders/docling_loader.py:74-107`）。服务化是独立仓 docling-serve（REST `/v1/convert/source`），代码 MIT，CPU 可跑但官方没给硬件表。

### 2.3 unstructured：格式适配层，不是中文主力

unstructured 是英文生态影响很大的解析分区器，但对中文深度解析要降级预期。三个事实：

1. **推理外包**：hi_res 策略的布局与表格模型推理在独立的 unstructured-inference 包里（2026-10-15 经 gh api 核实为公开仓、Apache-2.0），主仓 `unstructured/models/` 只剩空壳接口，模型与权重细节在主仓不可溯源（`Unstructured-IO/unstructured@e2f22b38 unstructured/partition/pdf.py:133-145`）。0.2x 版的库本体越来越像「格式适配 + Element 规范层」，深度解析的商业重心在其 SaaS 产品线。
2. **中文短板**：OCR 只有 tesseract 一条路（ocr_only 策略），且 pytesseract 缺失时会静默回退 fast 纯文本策略（`unstructured/partition/strategies.py:72`）——依赖装没装，直接决定扫描件到底有没有被 OCR；无公式识别，布局标签体系西式。
3. 输出是 Element 列表：`Table.text_as_html` 保 HTML 表格、`metadata.coordinates` 保 bbox（`unstructured/documents/elements.py:220`），自带 chunk_by_title 切分（`unstructured/chunking/title.py`）。

它的合理位置：轻量格式适配和英文语料，或已深度绑定其 SaaS 生态的团队。中文企业 RAG 的解析主力，不是它。

### 2.4 一张对照表

| | MinerU 4.0 | docling | unstructured |
|---|---|---|---|
| 定位 | 中文 PDF 深度解析（含 VLM 档） | 结构化转换器 | 格式分区器 + SaaS 生态 |
| 布局/表格/公式 | PP-DocLayoutV2 / SLANet / PP-FormulaNet 标配 | Heron / TableFormer 三选 / Granite VLM | YOLOX / Table Transformer / 无 |
| OCR | ch_PP-OCRv6，默认中文 | rapidocr 等 6 引擎可选 | 仅 tesseract |
| 格式面 | PDF/图片为主，Office 走 flash | 最宽（20+ 格式原生） | 宽（20+ partitioner） |
| 结构输出 | content_list 天然块边界 | DoclingDocument（bbox+页码） | Element（text_as_html+坐标） |
| 部署 | basic 档 0.8GB 纯 CPU | CPU 可跑（无官方硬件表） | CPU 可跑但 hi_res 慢 |
| License | Apache-2.0 + 附加条款（见第五节） | MIT | Apache-2.0 |

## 三、ragflow 的解析策略：自研轻量 + 外挂重炮

ragflow 的 deepdoc 一直是「RAG 平台自研解析」的标杆，Go 重写后它的策略变得更有参考价值了。

**自研部分**：Go 在 `internal/deepdoc/native/` 用 ONNX Runtime（cgo）原生重建了推理——`dla.go` 加载 layout.ort（10 类布局）、`det_core.go`/`ocr_rec.go` 加载 PaddleOCR 系检测与识别模型（rec 结果用 ocr.res 字典做 CTC 解码）、`tsr.go` 加载 tsr.ort（6 类表格结构），标签契约与 Python 时代的 dla_cli 逐类对齐（`infiniflow/ragflow@deb1235be internal/deepdoc/parser/type/labels.go#DefaultDLALabels`）。权重来自 HF 的 InfiniFlow/deepdoc，构建时镜像打进镜像。这是一个「YOLO 布局 + PaddleOCR + 表格结构」的轻量组合：胜在 Go 原生、无 Python 进程、部署省心；代价是公式识别缺失、复杂表格上限低于 MinerU/docling。

**外挂部分**：PDF 解析支持七种 parse_method（`internal/parser/pdf_parser_common.go:49-58`）：deepdoc（默认自研）、mineru、docling、paddleocr、somark、tcadp（腾讯云文档解析 API）、monkeyocr。其中 MinerU 桥是 HTTP 形态——调 MinerU 的 API server（`internal/parser/pdf_parser_mineru.go:22-30`，环境变量指定服务地址）；docling 桥调 docling-serve 的 `/v1/convert/source`，还做了 v1/v1alpha 双协议适配（`internal/parser/pdf_parser_docling.go:65-80`）；MonkeyOCR 按租户的 parser 配置分发（`internal/ingestion/component/pdf_vision_dispatch.go`）。

值得知道这段设计有历史：对照 2026-03 的 Python 遗产版（锚点 `2508c46c8`），Python 时代的 PARSERS 分发（`rag/app/naive.py`）就已有 deepdoc/mineru/docling/paddleocr/tcadp/plaintext 六种 parse_method，其中四种外挂桥放在 `deepdoc/parser/` 下——**「自研轻量默认 + 重炮外挂」不是 Go 版新发明，而是被延续并加料的遗产架构**，Go 版新增了 somark 和 monkeyocr。

这个拓扑为什么值得抄？因为它承认了一个现实：轻量自研模型覆盖 80% 的常见文档（省心、无外部依赖），剩下 20% 的硬骨头（扫描件、复杂公式表格）按文档级路由给重型服务，且重型服务是可替换的独立进程——MinerU 出 4.0 你换 MinerU，明天出更强的 VLM 你换 VLM，平台核心不动。

## 四、平台接入的反例：dify 和 kotaemon

不是所有平台都把解析当回事。两个对码出来的反例：

**dify 的默认管线对扫描件无解。** 其自有抽取路线的 PDF 处理用 pypdfium2 抽纯文本和图片对象，无 OCR、无布局模型（`langgenius/dify@79effdd498 api/core/rag/extractor/pdf_extractor.py:102`）；扫描件在默认配置下基本读不出内容。它的 ETL_TYPE 支持 dify 与 Unstructured 两态，后者走 UNSTRUCTURED_API_URL/KEY 的外部 API（`api/core/rag/extractor/extract_processor.py:135-178`）。切分侧倒是有中文友好细节——分隔符列表内置了中文句号 `["\n\n", "\n", "。", ". ", " ", ""]`（`api/core/rag/splitter/fixed_text_splitter.py:52`）——但解析与切分都是五家里最薄的。选 dify 做知识库、语料又以扫描件为主的话，解析层必须自己外挂。

**kotaemon 没有 MinerU 集成（与很多人直觉相反）。** 它的 reader_mode 下拉是 default/adobe API/azure-di/**docling**/paddle-struct/paddle-vl（`Cinnamon/kotaemon@9ad3e4e4 libs/ktem/ktem/index/file/pipelines.py:671-735`），全库无 mineru 匹配——它选了 PaddleOCR 生态当深度解析备选。它的 default 路线同样很薄：pdf 走 PDFThumbnailReader、docx/图片走 unstructured（`libs/kotaemon/kotaemon/indices/ingests/files.py:48-64`），所以深度解析的正路就是 docling。它的 DoclingReader 也是「平台消费 DoclingDocument」的最佳参考实现（`libs/kotaemon/kotaemon/loaders/docling_loader.py:53-209`）：图片裁剪后送 VLM 生成 caption、表格 grid 转 markdown、正文按页分组——想自建接 docling 的，直接抄这个文件。

## 五、生产拓扑建议：按类型路由 + 双服务

综合三强与平台实践，中文企业 RAG 的解析层生产拓扑：

```
上传文件 ── 按类型路由 ──▶ Office / HTML / 原生 PDF ──▶ docling-serve（REST /v1/convert/source）
                │
                └────────▶ 扫描 PDF / 图片 / 公式重 ──▶ MinerU api_server（medium 起步，重要文档 high）
                                  （VLM 可再拆独立 vlm_server，或配远程 server_url）
                                        ▼
                  统一结构化块（DoclingDocument / content_list）
                                        ▼
                  自研结构感知切分层（标题边界 + 表格整块 + token 上限）→ 嵌入 → 入索引
```

要点：

1. **路由规则放平台侧**，两个解析服务无状态水平扩：docling-serve 是纯 REST；MinerU 的 api_server 是「任务上传 + zip 产物」的 FastAPI，VLM 可以拆成独立 vlm_server 或配成远程 `server_url`（`opendatalab/MinerU@b7f3dd0c mineru/model/registry.py:151`）——意味着 CPU 小模型池与 GPU VLM 池能分开部署、分开扩容。ragflow 的 parse_method 分发就是现成设计参考；如果你的平台是 dify 这类解析薄的，就在摄取管道前自加一个路由网关。
2. **档位策略**：MinerU medium 起步（小模型混合，CPU 便宜），重要文档升 high（1.2B VLM 兜底）；原生 PDF 千万不要走 OCR——docling/MinerU 的原生解析路径快一个量级且无识别错误。
3. **验收前置**：拿 50-100 份真实文档抽检表格、公式、页码正确率再定档位，不要凭 README 截图决策。
4. 这套双服务拓扑对第 1 篇的架构原则是完美贴合：解析是重活，天然属于异步摄取 worker 池，不该出现在同步链路里。

## 六、License 风险专节

解析层是整个 RAG 栈里 license 陷阱最密集的一层，三条必须知道：

**1. MinerU 的附加条款。** 代码 Apache-2.0 之外加了两条（`opendatalab/MinerU@b7f3dd0c LICENSE.md` §1-2）：MAU 超过 1 亿或月收入超过 2000 万美元需单独商用授权；对外在线服务必须显著标注使用了 MinerU。对绝大多数企业自建内用 RAG 无碍，但基于它做 SaaS 化产品的，署名义务和门槛条款要过法务。

**2. 模型权重 license 全线未核实——这是本次调研最大的遗留风险，如实标注。** docling 的 Heron/Egret/Granite、MinerU 的 MinerU2.5、ragflow 的 InfiniFlow/deepdoc，权重协议在仓库内均无声明，HuggingFace 卡片在调研环境网络不可达未能在线确认。风险点是 IBM 系模型历史上多为 CC-BY-NC（禁商用）先例——**商用采购前必须逐卡上 HF 核实**，PP-OCR 系小模型按 PaddleOCR 的 Apache-2.0 推定相对安全，但 VLM 档的 MinerU2.5 权重没有任何已核实的协议结论。

**3. 混合 license 的传导。** docling 代码 MIT、unstructured 与 unstructured-inference 代码 Apache-2.0 都干净；风险不在代码在权重。企业引入任何解析栈前，把「代码 license + 模型权重 license + 部署依赖（vLLM 等）」三张表分开过一遍。

## 七、结构输出怎么指导下游切分（衔接第 3 篇）

最后回到那个分层误区。调研对码出的两层分工很清晰：

- **解析库侧的切分是结构感知的**：docling 的 HybridChunker 按文档结构树切块（docling-core 包）、MinerU 的 content_list 本身就是天然块边界、unstructured 的 chunk_by_title 按 Title 元素分段；
- **平台侧的切分是纯文本级的**：dify 分隔符递归、ragflow Go 的句子策略加合并、kotaemon 的 token 窗口。

很多团队的做法是「解析出 markdown，再拿 markdown 盲切」——这等于把解析层辛苦还原的结构信息全扔掉再重新猜。正确姿势是**拿结构输出直接指导切分**：标题层级当块边界、表格整块不拆、每块带上页码和章节路径当元数据。这些元数据不只是为了切块质量——第 7 篇会讲到，chunk 里的 doc_id 映射是文档级权限过滤的锚点；第 4 篇会讲到，标题与关键词字段的加权是检索质量的低成本杠杆。dify 是「解析切分都最薄」的反例，kotaemon 的 DoclingReader 和 ragflow 的 MinerU 桥都在朝结构消费的方向走。

具体怎么设计切分层（token 上限、父子块、递归策略与领域模板的取舍），是下一篇的主角。

## 参考与出处

源码基线（2026-10 冻结，正文引用均为行内 `owner/repo@commit 路径` 格式）：

- opendatalab/MinerU @ b7f3dd0c — https://github.com/opendatalab/MinerU/blob/b7f3dd0c/mineru/model/registry.py （模型注册表：PP-DocLayoutV2/ch_PP-OCRv6/SLANet/PP-FormulaNet/seal/MinerU2.5-1.2B）；…/mineru/backend/analyze.py （统一入口与 docvortex）；…/mineru/backend/analysis/pdf/pipeline.py （parse_mode 与 effort 档位）；…/mineru/backend/analysis/pdf/window.py （high/xhigh 的 VLM 批抽取）；…/mineru/model/ocr/language.py （默认 lang="ch"）；…/mineru/parser/api_server.py （FastAPI 服务化）；…/README.md （硬件档位表）；…/LICENSE.md （附加条款）
- docling-project/docling @ dd477a9f — https://github.com/docling-project/docling/blob/dd477a9f/docling/pipeline/standard_pdf_pipeline.py （阶段流水线接线）；…/docling/datamodel/stage_model_specs.py （Heron 默认 + VLM 预设清单）；…/docling/datamodel/pipeline_options.py （TableFormer 三选/OCR 工厂/CodeFormula）；…/docling/pipeline/vlm_pipeline.py （VLM 整页路线）
- Unstructured-IO/unstructured @ e2f22b38 — https://github.com/Unstructured-IO/unstructured/blob/e2f22b38/unstructured/partition/strategies.py （三策略）；…/unstructured/partition/pdf.py （推理外包与降级链）；…/unstructured/documents/elements.py （Element 结构）；…/unstructured/chunking/title.py （chunk_by_title）
- infiniflow/ragflow @ deb1235be — https://github.com/infiniflow/ragflow/blob/deb1235be/internal/deepdoc/native/dla.go （layout.ort）及同目录 det_core.go/ocr_rec.go/tsr.go （Go 原生 ONNX 推理）；…/internal/parser/pdf_parser_common.go#supportedPDFParseMethods （七种 parse_method）；…/internal/parser/pdf_parser_mineru.go （MinerU HTTP 桥）；…/internal/parser/pdf_parser_docling.go （docling-serve 桥）；…/internal/ingestion/component/pdf_vision_dispatch.go （视觉模型分发）
- langgenius/dify @ 79effdd498 — https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/extractor/pdf_extractor.py （pypdfium2 纯文本）；…/api/core/rag/extractor/extract_processor.py （ETL 分发）；…/api/core/rag/splitter/fixed_text_splitter.py （分隔符与中文句号）
- Cinnamon/kotaemon @ 9ad3e4e4 — https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/index/file/pipelines.py （reader_mode 清单，无 MinerU）；…/libs/kotaemon/kotaemon/loaders/docling_loader.py （DoclingDocument 消费参考实现）；…/libs/kotaemon/kotaemon/indices/ingests/files.py （默认抽取器与切分参数）

关联仓库与官方资源（2026-10-15 经 gh api 核实可访问）：

- docling-serve（MIT，Docling 的 API 服务化）：https://github.com/docling-project/docling-serve
- unstructured-inference（Apache-2.0，hi_res 推理所在独立仓）：https://github.com/Unstructured-IO/unstructured-inference

标注：模型权重 license 未核实项、docling 默认 OCR 回退行为未实测项，均如实标注于正文；常见解析失败模式举例为生态通识，未源码级验证。

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》：

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做（本篇）
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

下一篇预告：解析产出的是结构化块清单，接下来要回答「块切多大、怎么切、存进哪个引擎」——中文 BM25 的引擎分野（qdrant 服务端分词为什么坑）、平台 schema 的两流派、以及父子块与字段级权重这些切分配合检索的联动设计，都在第 3 篇。
