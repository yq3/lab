# DataAgent 语义层专项：与 knowledge-lattice 业务语义层的对比

> 起因：knowledge-lattice 并入业务语义层（D23，issue #35）后，用户提出阿里 Spring AI Alibaba DataAgent 也有类似「语义」处理，要求源码级对比异同、提炼可借鉴之处。

## 研究说明

- **对象**：`~/develop/opensource/DataAgent`（spring-ai-alibaba/DataAgent，Java 17 + Spring Boot 单体）——聚焦其**语义模型（semantic model）/ 业务知识（business knowledge）/ 智能体知识库（agent knowledge）**三类知识的设计与实现，不重复整体架构解剖。
- **对照物**：本仓库 [knowledge-lattice](../../knowledge-lattice/) 的业务语义层（`core/semantic/`，D23：类型化对象图 + 术语识别 + 实体召回，需求 FR-S1~S6 / 设计 §5.8~5.10、§6.3）。
- **基线**：DataAgent @ `3fb7852`（2026-08-19）——与 agent-oss 轮档案同基线（该 clone 期间未 pull，HEAD 未漂移）。
- **边界（对照历史调研）**：DataAgent 整体架构（StateGraph 编排 / HITL / 连接层 / Python 沙箱）已由 [agent-oss/profiles/DataAgent.md](../agent-oss/profiles/DataAgent.md) 覆盖，本轮**不复述**；本轮只做语义知识层深挖 + 与 knowledge-lattice 的双向对比。语义层在旧档案中仅 §7 一句带过（"语义模型 Excel 批量导入 + 业务知识/agent 知识两类 RAG 语料"），无展开。
- **证据纪律**：沿用 agent-oss 轮三级证据——【核心】代码实现 /【示例】examples、demo /【文档】文档宣称；路径以 `~/develop/opensource/DataAgent/` 为根可溯源。knowledge-lattice 侧引 `docs/requirements.md` / `docs/design.md` 章节号。
- **产出纪律**：对比结论只进本报告；**不改动 knowledge-lattice 需求/设计文档**（设计冻结纪律——借鉴项若要吸收，由用户决策后走 issue/决策变更流程）。

## 目录

```
dataagent-semantic/
├── README.md      # 本文件：入口、方法、进度
└── report.md      # 最终交付：DataAgent 语义知识机制解剖 + 与 knowledge-lattice 异同 + 借鉴清单
```

单对象专项，无 profiles/ 与 dimensions/（对象档案=report §2，对比矩阵=report §3）。

## 进度 checklist

- [x] Phase 0：确认 DataAgent 未被历史调研深挖过语义层（agent-oss 轮仅整体架构）；记录基线 HEAD
- [x] Phase 1：DataAgent 语义知识源码解剖（schema.sql DDL / 实体 / 图节点消费路径 / 检索机制 / 同义词调用链 / 维护入口）
- [x] Phase 1'：knowledge-lattice 语义层设计要点提取（FR-S1~S6 / §5.8~5.10 / §6.3）
- [x] Phase 2：逐维度对比（定位/知识分类/真相源/消费机制/检索/权限/规模）
- [x] Phase 3：report.md 成稿（含借鉴清单与「不借鉴」清单）
