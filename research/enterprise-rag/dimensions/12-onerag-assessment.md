# 12. OneRAG 快速评估（用户指定的补充对象）

> 背景：用户提出 OneRAG（notadev-iamaura/OneRAG）与需求「高度重合」，做针对性快速源码考察。
> 基线：`notadev-iamaura/OneRAG@dc1c9bd`（2026-09-29，depth-1 克隆于 2026-10-16）。韩国个人项目（README 主文韩语），126⭐/40 fork，MIT，Python 3.11+，2026-01 创建。304 py 文件 / 约 9.9 万行 app 代码 + React 19 前端（frontend/src 238 文件）。
> 证据等级：本篇为快速考察（非全维度深挖），路径相对克隆根。

## 结论：参考价值高，采用价值低（中文场景）

形态上它几乎就是本轮 report 推荐的「自建薄服务」的一个已写成的版本（韩语向）：FastAPI + Dense/BM25 混合检索 + RRF 融合 + reranker + MCP + 前端 + 审计事件 + OpenAI 兼容 API，工程质量（2100+ tests、CI、importlinter、DI 容器、YAML 分层配置）远超一般个人项目。

## 与需求的匹配对照

| 能力 | 实现 | 证据 | 判定 |
|---|---|---|---|
| MCP server | FastMCP 内置包装（`app/modules/core/tools/server.py`，工具如 search_weaviate，DI 单例） | 【核心】 | ✅ deepagents 可连 |
| 混合检索 | Dense+BM25 → **RRF（k=60，注释引通用值 60）** | `app/modules/core/retrieval/bm25_engine/hybrid_merger.py` | ✅ 与本轮/厂商结论一致的标准配方 |
| BM25 分词 | kiwipiepy（韩语形态素）+ 用户词典/停用词/同义词管理；**tokenizer 无中文分支**（grep zh/chinese/language 零命中），pyproject extras 仅 kiwipiepy | `bm25_engine/tokenizer.py`、`pyproject.toml` | ❌ 中文文档 BM25 路基本不可用 |
| 文档解析 | pypdf + python-docx（原生文本级）；ingestion 是 connectors/factory/service（sitemap 等） | `pyproject.toml: pypdf>=5, python-docx==1.1.0`、`app/modules/ingestion/` | ❌ 扫描件/复杂表格无解（对照 dim02 生死线结论） |
| Reranker | 4 种：local（本地推理）/cohere/vertex_ranking/jev_decision | `app/modules/core/retrieval/rerankers/` | ✅ 形态全 |
| 查询扩展/self-RAG/路由/缓存/PII 脱敏 | `app/config/features/*.yaml`（query_expansion/self_rag/routing/cache/privacy） | 【文档】配置面 | ✅ 管线完整 |
| 审计 | append-only SQLite(WAL) 运维审计（文档删除等破坏性操作）；**非查询审计**；设计注释明说「曾多租户(company_id) 后简化单租户」 | `app/api/audit_event_store.py` | ⚠️ 仅运维级 |
| 用户体系/文档级 ACL | 无 User/login 模型（grep class User/login_required 零命中；bm25/user_dictionary 是分词词典非用户系统） | 【核心】 | ❌ 与 dim07 五平台同病 |
| 前端 | React 19（上传/聊天/管理），支持 LANG=zh 界面语言 | `frontend/src`、README | ✅（界面中文化≠分词中文化） |

## 定位建议

1. **不当采用**：中文 BM25 缺分词 + 解析深度不足 + 无权限体系，对「中文企业知识库」三个硬伤（前两个致命）。
2. **当骨架参考（推荐）**：自建薄服务时的同路人样本——modules 分层（core/ingestion）、`config/features/` YAML 分层、FastMCP ToolServer 包装方式、audit_event_store 的零依赖 append-only 设计、hybrid_merger 的 RRF 实现均可直接借鉴。
3. **fork 改造的账**：需换分词（kiwipiepy→jieba）、换解析（pypdf→MinerU/docling 桥）、补用户与 ACL——三项都是伤筋动骨的主干改动，加之单人项目 bus factor=1，改造成本接近重写，不推荐。

## 与主报告结论的关系

不改变 report 的任何结论；反而佐证 §4「路线 C/自建」判断：连 126⭐ 的同形态项目也绕不开「解析深度、中文分词、文档权限」这三块硬骨头——它们正是开源生态的系统性缺口（dim02/dim03/dim07）。
