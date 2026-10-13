# 维度 02：文档解析（Ingestion）层 —— 解析库三强 + 平台接入的源码级深挖

> 调研对象与基线：docling `dd477a9f`（IBM）/ MinerU `b7f3dd0c`（上海AI Lab，实测版本 4.0.12）/ unstructured `e2f22b38`（0.27.26）；参照 ragflow（Go 重写后）、kotaemon `9ad3e4e4`、dify。
> 证据标注：`~/develop/opensource/<repo>/路径#符号`；【核心】= 代码实现，【文档】= README 宣称，❌/⚠️ = 查不到或存疑。
> 本轮最大意外有二：**MinerU 已重构为 4.0「分层档位 + VLM 混合」架构**（`magic_pdf` 时代代码无存，解析栈移入 `mineru/backend|model|parser`，并引入新底层库 docvortex）；**docling 的模型阵容全换代**（布局模型从 DocLayNetYOLO 换成 Heron/Egret 系列，公式走 Granite-Docling VLM，还内置了 MinerU2.5、GLM-OCR 等 VLM 预设）。网上 2025 年前的解析层资料对这两家基本失效。

## 0. 总表

| | docling | MinerU 4.0 | unstructured | ragflow deepdoc（Go） |
|---|---|---|---|---|
| **定位** | 结构化转换器：DoclingDocument 单一中间格式 | 中文 PDF 深度解析（含 VLM 档） | 通用分区器：Element 流 + SaaS 生态 | RAG 平台自研轻量解析（够用就好） |
| **PDF 管线** | preprocess→layout→OCR→layout后处理→table→assemble→读序【核心 standard_pdf_pipeline.py】 | flash/medium/high/xhigh 四档 + txt/ocr 双模【核心 backend/analyze.py】 | fast(pdfminer)/ocr_only(tesseract)/hi_res(YOLOX布局+表格模型，推理在外部包)【核心 strategies.py】 | Go 原生 ONNX：layout.ort→det/rec.ort→tsr.ort + 启发式表格构建【核心 internal/deepdoc】 |
| **布局模型** | docling-layout-heron（默认）/egret-m~xl【核心 stage_model_specs.py:1017-1072】 | PP-DocLayoutV2【核心 model/registry.py:23】 | YOLOX（在 unstructured_inference 包内）⚠️权重细节不在本仓 | 10 类 YOLO（layout.ort）【核心 labels.go#DefaultDLALabels】 |
| **表格** | TableFormer(V1 默认)/TableFormerV2/GraniteVision 三选【核心 pipeline_options.py:151,190】 | SLANet-plus + unet + PP-LCNet 表格分类【核心 registry.py:27-29】 | detectron2 Table Transformer（hi_res + infer_table_structure） | tsr.ort(6类) + Go 启发式构建，输出 HTML【核心 table/*.go】 |
| **公式** | 可选 CodeFormula VLM（granite-docling-258M）【核心 pipeline_options.py:1166】 | PP-FormulaNet-Plus-M（标配）【核心 registry.py:24】 | ❌ 无 | ❌ 自研管线无公式识别 |
| **OCR** | 工厂插件：rapidocr(PaddleOCR系)/tesseract/easyocr/ocrmac/nemotron/kserve_v2【核心 pipeline_options.py:329-767】 | PaddleOCR ch_PP-OCRv6 tiny det + small rec，默认 lang="ch"【核心 registry.py:52-55, ocr/language.py:64】 | 仅 tesseract（ocr_only） | rec.ort + ocr.res 字典 CTC 解码（PaddleOCR 系）【核心 ocr_rec.go】 |
| **VLM 路线** | VlmPipeline：SmolDocling/MinerU2.5/GLM-OCR/Nemotron-Parse 等 10+ 预设【核心 stage_model_specs.py:1106-1646】 | MinerU2.5-Pro-2605-1.2B（vllm/lmdeploy/llama.cpp/mlx/远程）【核心 registry.py:33-39】 | ❌（闭源平台侧有） | 外挂：MonkeyOCR-v2/SOMark 桥【核心 pdf_vision_dispatch.go】 |
| **格式面** | 最宽：PDF/Office/HTML/图片/EPUB/iWork/XML/LaTeX/邮件/CSV/音视频【核心 backend/ 目录】 | PDF/图片分档；Office/HTML/CSV/EPUB/OFD 走 flash；pages/key/mobi/eml ❌【核心 filetypes.py】 | 宽：20+ partitioner【核心 partition/ 目录】 | 16 类【核心 parser_type.go#GetParser】 |
| **输出** | DoclingDocument（texts/tables/pictures+prov bbox+页码；表格 grid/HTML/MD）【示例 kotaemon 消费代码】 | ModelJson→MiddleJson→markdown/content_list/docx/html/latex【核心 render/】 | Element 列表（text_as_html+coordinates）【核心 elements.py:220】 | ParseResult→Go chunker |
| **GPU** | CPU 可跑（ONNX）⚠️无官方硬件表 | basic 0.8GB CPU；standard 2-3GB，vLLM 需 8GB+ VRAM【文档 README.md:456-460】 | CPU 可跑但 hi_res 慢；官方主推 SaaS | onnxruntime CPU/GPU 皆可 |
| **API server** | docling-serve（独立仓，REST /v1/convert/source）【文档 packages/docling-client】 | mineru api_server（FastAPI）+ vlm_server【核心 parser/api_server.py】 | unstructured API（闭源 SaaS/自托管） | ragflow 进程内 |
| **代码 license** | MIT【核心 LICENSE】 | Apache-2.0+附加条款（MAU>1亿或月收>2000万美元需商用授权；在线服务须署名）【核心 LICENSE.md】 | Apache-2.0【核心 LICENSE.md】 | Apache-2.0 |
| **模型权重 license** | ⚠️仓内未注明，HF 卡需上线核实 | ⚠️同左（PP-* 系 Apache，MinerU2.5 需核） | ⚠️推理包与权重不在本仓 | ⚠️InfiniFlow/deepdoc HF 卡未核 |

---

## 1. docling：阶段化流水线 + 插件化模型工厂

### 1.1 管线解剖

主入口 `DocumentConverter`（`docling/document_converter.py`）按格式选 backend + pipeline。PDF 走 `StandardPdfPipeline`（`docling/pipeline/standard_pdf_pipeline.py:586`），这是一条**多线程阶段流水线**，`_create_run_ctx`（:730-802）里的接线顺序是** preprocess(PDF解析)→layout→ocr→layout_postprocess→table→assemble **，之后文档级还有 reading_order、heading_hierarchy，以及可选 enrichment（公式/代码 CodeFormulaVLM、图片分类/描述、图表抽取）（:601-682 的 `_init_models` 逐一实例化）。与老版"每页顺序跑五个模型"不同，现在是各阶段独立线程 + 队列，OCR/layout/table 可批量（`ocr_batch_size`/`layout_batch_size`/`table_batch_size`）。

模型全部经**工厂 + entry_points 插件机制**装配（`docling/models/factories/{layout,ocr,table_structure,picture_description}_factory.py`；`base_factory.py:104` 遍历 entry_points 组），第三方可注册插件类。

### 1.2 模型注册表（本轮换代重点）

- **布局**：`docling/datamodel/stage_model_specs.py:1017-1072` 注册 `docling-project/docling-layout-heron`（默认 `layout_heron_default`）、heron-101、egret-medium/large/xlarge；旧 DocLayNet layout_v2 已弃用、配了会回退 Heron（`datamodel/layout_model_specs.py:76` 注释明说）。
- **表格**：默认 kind `docling_tableformer`（TableFormer V1，docling-ibm-models 包，`pipeline_options.py:151-154`）；`TableFormerV2`（`docling-project/TableFormerV2`，`models/stages/table_structure/table_structure_model_v2.py:41`）与 GraniteVision（`ibm-granite/granite-vision-3.3-2b`，`pipeline_options.py:190`）为可选。
- **OCR**：kind 枚举 auto/rapidocr/tesseract/tesserocr/easyocr/ocrmac/nemotron-ocr/kserve_v2_ocr（`pipeline_options.py:329-767`）。中文要点：rapidocr（RapidOCR，PaddleOCR 系权重）开箱可用；tesseract 走 `utils/ocr_language.py` 的 BCP47 映射（zh-CN/zh-Hans 归一，:13）。
- **公式**：`CodeFormulaVlmModel`，默认 preset `granite_docling`（ibm-granite/granite-docling-258M，`pipeline_options.py:1166,1251`）。
- **VLM 整页路线**：`pipeline/vlm_pipeline.py`（VLM 预测 DocTags → `DoclingDocument.load_from_doctags`，:500,630）。预设清单惊人地广（`stage_model_specs.py:1106-1646`）：SmolDocling-256M、**MinerU2.5-Pro-2604-1.2B**（含 mlx 版，:1380）、**GLM-OCR**（:1512）、Nemotron-Parse-2.0、DeepSeek-OCR、GOT-OCR-2.0、Qwen2.5-VL-3B、Nanonets-OCR2-3B、Dolphin、gemma-3-12b/27b——即 docling 已变成"VLM 解析模型聚合器"。
- 另有 `extraction_vlm_pipeline.py`、`native_pdf_pipeline.py`（纯后端文本、无模型）与 ASR/视频管线。

### 1.3 格式面与输出

backend 目录即格式清单（`docling/backend/`）：PDF 三代后端并存（docling_parse_v4 主力 + managed_pdfium + pypdfium2）、docx/html/pptx/xlsx/epub/image/email/latex/csv/md/odt/json/iwork（pages/numbers/keynote）/xml/asciidoc/afp/mets_gbs/ebcdic/webvtt/boxnote。图片走 `image_backend.py` → OCR 管线。

输出是 **DoclingDocument**（定义在外部包 docling-core>=2.98，本仓 `docling/chunking/__init__.py` 只是 re-export）。字段结构的间接证据【示例】：kotaemon 的 `docling_loader.py:74-107,152-232` 按 `result_dict["texts"/"pictures"/"tables"]` 消费，表格取 `data.grid` 二维格，每个元素带 `prov[0].page_no/bbox/coord_origin`——**bbox 与页码原生保留**；导出器（markdown/html/doctags）在 docling-core。切分模块同样在 docling-core：`HierarchicalChunker`/`HybridChunker`（按文档结构树切块，可配 token 上限）。

部署：CPU 可跑（布局/表格有 ONNX 变体，`stage_model_specs.py:1021` heron-onnx）；服务化是独立仓 **docling-serve**（REST，`packages/docling-client/README.md:3` 证实，ragflow 的 Go 桥调的正是它的 `/v1/convert/source`，见 §4）。license：代码 MIT；**模型权重协议仓内未声明** ⚠️（IBM 系模型历史上多为 CC-BY-NC，采购前必须上 HF 卡核实——这是选型级风险点）。

---

## 2. MinerU 4.0：档位化混合管线（中文场景的事实标准仍是它）

### 2.1 架构与管线

新版把"解析编排"（`mineru/backend/`）、"模型"（`mineru/model/`）、"IO"（`mineru/parser|render|kit`）彻底分层，底层 PDF 读取/分类/Office 转换交给新依赖 **docvortex**（opendatalab 自家文档库，`backend/analyze.py:10` 的 `PDFDocument`、`integrations/docvortex.py`）。

统一入口 `doc_analyze`（`mineru/backend/analyze.py:32`）按后缀分发：PDF→`analysis/pdf/pipeline.py#analyze_pdf`；csv/tsv/epub/html/mhtml/ofd/office→`analysis/*.py`（DocVortex 原生转换，flash 档直出）。PDF 侧两个正交维度：

- **parse_mode**：auto/txt/ocr——`PDFDocument.classify()`（pipeline.py:58）自动判断原生文本还是扫描件；
- **effort 档位**（pipeline.py:29,43-69）：
  - `flash`+txt：纯文本抽取，零模型；
  - `medium`：混合小模型（HybridLocalModelContext）——PP-DocLayoutV2 布局 + PaddleOCR + SLANet-plus 表格 + PP-FormulaNet 公式，行间合并（window.py:234）；
  - `high`：小模型定布局，正文走 VLM `batch_extract_with_layout`（window.py:611），txt 模式下原生表格可回填免 VLM（window.py:453-454 `_split_native_high_table_blocks`）；
  - `xhigh`：VLM 两步 `batch_two_step_extract` + 图像分析（window.py:572,612）。

### 2.2 模型注册表（`mineru/model/registry.py`，【核心】）

- 小模型仓 `MinerU-4_models_torch` / `MinerU-4_models_onnx`：`Layout/PP-DocLayoutV2`、`MFR/pp_formulanet_plus_m`、**`OCR/paddleocr/ch_PP-OCRv6_tiny_det` + `ch_PP-OCRv6_small_rec`（中文主力）**、`seal_PP-OCRv4`（印章）、`Table/slanet-plus.onnx` + `unet.onnx` + `PP-LCNet_x1_0_table_cls`（表格分类→路由 wired/无线表模型，`model/table/cls/`）；
- VLM 仓 `MinerU2.5-Pro-2605-1.2B`（vllm/lmdeploy/mlx）与 GGUF（llama.cpp，:67-77）；
- OCR 语言默认 **lang="ch"**（`model/ocr/language.py:64`），另有 east_slavic/arabic/cyrillic/devanagari 归一——中文是第一公民。

### 2.3 输出与部署

产物两级：`ModelJson`（严格页级模型结果 + producer 元数据 + layout 几何扩展，analyze.py:154-176）→ `postprocess/document.py#model_json_to_middle_json` → **MiddleJson**；渲染层 `mineru/render/` 可出 **markdown / content_list（含 v2）/ docx / html / latex / pdf 预览**；CLI 输出格式枚举 markdown/middle_json/zip（`kit/commands/parse.py:42`）。bbox/阅读序在 MiddleJson 块级保留。

部署档位与硬件（README.md:456-460【文档】）：`basic`（纯小模型）ONNX 约 0.8GB、2GB 内存、**CPU 可跑**；`standard/advanced`（+VLM）ONNX+llama.cpp 约 2GB、CPU 可用（Vulkan 加速）；PyTorch+vLLM/lmdeploy 需 GPU **8GB+ VRAM**。服务化：`mineru/parser/api_server.py`（FastAPI，任务上传/zip 产物）+ `mineru/kit/vlm_server`（vLLM/LMDeploy 独立服务），VLM 可配置远程 `server_url`（registry.py:151）。

License：**Apache-2.0 + 附加条款**——MAU 超 1 亿或月收入超 2000 万美元需单独商用授权；对外在线服务必须显著标注使用了 MinerU（LICENSE.md §1-2【核心】）。对绝大多数企业自建 RAG 无碍，但 SaaS 化产品要注意署名义务。模型权重协议仓内未单独声明 ⚠️（PP-* 系列按 PaddleOCR Apache-2.0 推定，MinerU2.5 权重需上 HF 核实——HF API 在本环境网络不可达，未能在线确认）。

---

## 3. unstructured：partition 分区体系，模型推理外包

- **格式面**：`unstructured/partition/` 一格式一文件——pdf/doc/docx/ppt/pptx/xlsx/csv/tsv/html/image/epub/email/msg/md/org/rst/rtf/odt/xml/json/ndjson/text/audio；`partition/auto.py#partition_auto` 按 FileType 从 `partitioner_loader` 注册表取 partitioner（auto.py:222-293）。
- **PDF 三策略**（`partition/strategies.py`）：`fast`（pdfminer 纯文本，`pdf.py:456 _partition_pdf_with_pdfminer`）；`ocr_only`（pytesseract，pytesseract 缺失则回退 fast，strategies.py:72）；`hi_res`（调 `unstructured_inference` 包做布局+表格，未安装则降级，:58-69）。**模型（YOLOX 布局、detectron2 表格）全部在闭源协作仓 unstructured-inference**——本仓 `unstructured/models/` 只剩空 `__init__.py`，默认 hi_res 模型名从 env `UNSTRUCTURED_HI_RES_MODEL_NAME` 或 inference 包 DEFAULT_MODEL 取（pdf.py:133-139）⚠️权重细节无法在本仓溯源。
- **输出**：Element 列表（`unstructured/documents/elements.py`）——`Table.text_as_html`（:220）保 HTML 表格，`metadata.coordinates`（CoordinatesMetadata，:57-66,167）保 bbox，层级类型 Title/NarrativeText/ListItem 等。
- **中文短板**：OCR 只有 tesseract 一条路（chi_sim），无公式识别，布局标签体系西式——中文扫描件效果不占优。
- **切分**：`unstructured/chunking/title.py#chunk_by_title`——按 Title 元素分段、超长再按 max_characters/overlap 切（:23-110），可经 `add_chunking_strategy` 装饰器直接在 partition 调用里启用（pdf.py:145 附近）。
- License：代码 Apache-2.0；商业模式是 unstructured.io SaaS/自托管 API（`docker/` 目录）。
- **定位变化**：0.2x 版的库本体越来越像"格式适配 + Element 规范层"，深度解析价值在闭源侧。企业自建中文 RAG，它已不是解析主力候选。

---

## 4. ragflow 专节：Go 重写后，解析怎么办了

**结论：Python deepdoc 已删，Go 在 `internal/deepdoc` 原生重建了推理，且新增了一批外部解析器 HTTP 桥。**

- **Go 原生推理**（`internal/deepdoc/native/`，ONNX Runtime cgo）：`dla.go` 加载 `layout.ort`（10 类布局，:60）；`det_core.go:100` 加载 `det.ort`（PaddleOCR 检测）；`ocr_rec.go:119` 加载 `rec.ort` + `ocr.res` 字典做 CTC 解码（PaddleOCR 识别，中文模型系）；`tsr.go:47` 加载 `tsr.ort`（6 类表格结构）。配套会话池/共享权重（session_pool.go、shared_weights_*）。标签契约在 `internal/deepdoc/parser/type/labels.go#DefaultDLALabels`（注释明说与 Python deepdoc 的 dla_cli.py 逐类对齐）。权重来自 HF `InfiniFlow/deepdoc`，经 `ragflow_deps` 镜像打进镜像（Dockerfile_base:14-17【核心】）。
- **解析编排**：格式注册表 `internal/parser/parser/parser_type.go#GetParser`——pptx/ppt/xlsx/xls/csv/docx/doc/pdf/html/markdown/txt/epub/json/email/picture(visual)/audio(aural) 16 类。PDF 解析在 `internal/deepdoc/parser/pdf/`（parser.go 原生文本、parser_ocr.go 扫描件、table/ 目录六件套：layout/coords/cells/construct/annotate/html——模型 + 启发式混合，产出 HTML 表格）。
- **外部解析器桥**（PDF 多后端，`parser/pdf_parser_common.go:49-58 supportedPDFParseMethods`）：`deepdoc`（默认，Go 原生）、`mineru`（调 MinerU API server，`pdf_parser_mineru.go:22-30`，需 mineru_apiserver/MINERU_APISERVER）、**`docling`（调 docling-serve REST `/v1/convert/source`，`pdf_parser_docling.go:65-80`，含 v1/v1alpha 双协议适配）**、`paddleocr`、`somark`、`tcadp`（腾讯云文档解析 API，`tcadp_common.go`）、MonkeyOCR-v2（`internal/ingestion/component/pdf_vision_dispatch.go:214#dispatchMonkeyOCRv2PDF`，按 tenant 的 parser setup/model UUID 分发）。**即 ragflow 的姿态是：自研轻量默认 + 重活外挂，且把 MinerU/docling 都当作可插拔后端。**
- **切分**：`internal/parser/chunk/`——`SplitOperator`（split.go:32：strategy=sentence/length/boundaries，chunkSize 以 **rune 计**，带 overlap），ChunkOptions（options.go:33-48：预处理三开关 + 切分策略 + 合并目标长度 + 最短过滤）。

与三库差异定位：deepdoc 是"YOLO 布局 + PaddleOCR + TSR"的**轻量 ONNX 组合，胜在 Go 原生、无 Python 进程、部署省心**；公式识别缺失、表格复杂度上限低于 MinerU/docling——所以 ragflow 自己也留了外挂通道。

---

## 5. 平台接入对照（kotaemon / dify）

- **kotaemon**：接线文件 `libs/ktem/ktem/index/file/pipelines.py:671-735`——`reader_mode` 下拉：default（`KH_DEFAULT_FILE_EXTRACTORS`，`libs/kotaemon/kotaemon/indices/ingests/files.py:48-64`：pdf=PDFThumbnailReader、docx/pptx/doc/xls/图片=unstructured、html=HtmlReader）/ adobe API / azure-di / **docling** / paddle-struct（PPStructureV3）/ paddle-vl（PaddleOCR-VL）。DoclingReader 实现（`libs/kotaemon/kotaemon/loaders/docling_loader.py:53-209`）：`DocumentConverter.convert → export_to_dict`，图片裁剪 + VLM 生成 caption、表格 grid 转 markdown、正文按页分组——**这是"平台消费 DoclingDocument"的最佳参考实现**【示例】。**MinerU 接入 ❌**（全 libs 无 mineru 匹配，任务假设的"集成 MinerU"在当前基线不成立）。切分：TokenSplitter chunk_size=1024/overlap=256/\n\n（files.py:88-93）。
- **dify**：分发在 `api/core/rag/extractor/extract_processor.py`（extractor 目录，非任务提示的 loader/）：`ETL_TYPE=dify|Unstructured`（`api/configs/feature/__init__.py:1231`），Unstructured 路线走 **UNSTRUCTURED_API_URL/KEY 的外部 API**（:138-178，覆盖 md/doc/msg/eml/ppt/pptx/xml）；dify 自有路线全是轻量抽取——pdf 用 **pypdfium2 纯文本+图片对象，无 OCR 无布局模型**（pdf_extractor.py:102），word 用 python-docx。切分 `api/core/rag/splitter/fixed_text_splitter.py:52`：默认分隔符 `["\n\n", "\n", "。", ". ", " ", ""]`——**内置中文句号，中文友好**，但扫描件 PDF 在默认配置下基本无解。
- **ragflow**：见 §4（自研 + 外挂 MinerU/docling/腾讯）。

**两层分工结论**：解析库侧的"切分"是结构感知的（docling HybridChunker 按文档树、unstructured chunk_by_title 按 Title 元素、MinerU content_list 做天然块边界——它本身不切块）；平台侧的切分是纯文本级的（dify 分隔符递归、ragflow Go 句子+合并、kotaemon token 窗口）。**企业实践的正确姿势：用解析库的结构输出（标题层级/表格/页码）指导平台切分，而不是拿 markdown 后再盲切**——kotaemon 的 DoclingReader 和 ragflow 的 MinerU 桥都在朝这个方向走，dify 目前是反例（解析与切分都最薄）。

---

## 6. 中文企业场景选型小结

1. **默认选择：MinerU 4.0 作为扫描件/复杂 PDF 主力解析服务**。理由：ch_PP-OCRv6 中文 OCR 一等公民、PP-FormulaNet 公式标配、SLANet 表格、high/xhigh 档有 1.2B VLM 兜底；basic 档 0.8GB CPU 可跑（冷启动便宜），吞吐需求上来再上 vLLM + 8GB GPU。部署形态用它自带的 api_server。注意 Apache+附加条款的署名义务。
2. **原生 PDF/Office/HTML：docling（或 docling-serve）**。格式面最宽、DoclingDocument 结构最完整（bbox/页码/阅读序原生），Office/HTML 走原生解析不走 OCR，速度快质量稳。中文扫描件需显式配 rapidocr 引擎（默认 OCR 引擎选择要验证）⚠️。
3. **组合建议（生产拓扑）**：文件入口按类型路由——Office/HTML/原生 PDF→docling-serve；扫描 PDF/图片→MinerU api_server（medium 起步，重要文档 high）；产出统一为结构化块（DoclingDocument/content_list），再进**自研结构感知切分层**（标题边界 + 表格整块 + token 上限），最后入库。ragflow Go 版已经示范了这种"自研轻量 + 外挂重炮"拓扑（internal/parser 的 parse_method 分发就是现成设计参考）。
4. **不推荐**：unstructured 作为中文深度解析主力（OCR 仅 tesseract、无公式、模型在闭源包）；dify 默认管线处理扫描件（pypdfium2 纯文本）。
5. **license 风险动作**：采购前上 HF 逐一核实 docling Heron/Egret、MinerU2.5、InfiniFlow/deepdoc 的权重协议（本环境网络未验，见存疑清单）。

---

## 7. 证据与存疑清单

【核心】关键实现证据（均已正文标注）：docling `pipeline/standard_pdf_pipeline.py:586,730-802`、`datamodel/stage_model_specs.py:1017-1646`、`datamodel/pipeline_options.py:151-767`；MinerU `model/registry.py`、`backend/analyze.py:32`、`backend/analysis/pdf/pipeline.py:29-69`、`backend/analysis/pdf/window.py`、`filetypes.py`、`kit/commands/parse.py:42`；unstructured `partition/strategies.py`、`partition/pdf.py:133-145,456`、`documents/elements.py:220`、`chunking/title.py:23`；ragflow `internal/parser/parser/parser_type.go#GetParser`、`parser/pdf_parser_common.go:49-58`、`parser/pdf_parser_docling.go:41-80`、`parser/pdf_parser_mineru.go:22-38`、`internal/deepdoc/native/{dla,det_core,ocr_rec,tsr}.go`、`internal/parser/chunk/split.go:32`、`internal/ingestion/component/pdf_vision_dispatch.go:69-214`；kotaemon `libs/ktem/ktem/index/file/pipelines.py:671-735`、`libs/kotaemon/kotaemon/indices/ingests/files.py:48-93`、`loaders/docling_loader.py`；dify `api/core/rag/extractor/extract_processor.py:135-178`、`configs/feature/__init__.py:1231`、`splitter/fixed_text_splitter.py:52`。

【文档】：MinerU README.md:119,456-460,1026-1028（硬件表/license）；docling packages/docling-client/README.md（docling-serve）。

❌/⚠️ 存疑：
1. **模型权重 license 全线未落地**：docling/MinerU/ragflow 的 HF 模型卡在本环境网络不可达（huggingface.co 连接重置），仓内均无权重协议声明。IBM 系（Heron/Egret/Granite-Docling）历史上有 CC-BY-NC 先例，商用前必须逐卡核实。
2. kotaemon **无 MinerU 集成**（与任务预期相反）；它选了 PaddleOCR 生态（PPStructureV3/PaddleOCR-VL）作为深度解析备选。
3. unstructured hi_res 的模型细节（YOLOX 版本、表格模型）在闭源协作仓 unstructured-inference，本仓不可溯源 ⚠️。
4. docling 默认 OCR 引擎在无 tesseract 环境下的实际回退行为（auto→rapidocr 还是禁用）未实测，仅确认工厂注册齐全。
5. MinerU `advanced` tier（types.py:137）与 effort `xhigh` 的精确对应关系未逐行核对（README 硬件表把 standard/advanced 并列）。
6. docling TableFormerV2 与 V1 的默认切换时点：代码默认仍是 V1 kind `docling_tableformer`（pipeline_options.py:2152），V2 类已就绪但需显式启用。
