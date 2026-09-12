# AGENTS.md — research/ 调研工作规范

> 本目录是 lab 仓库的**调研专区**：存放调研的过程与结果，每次调研任务建一个子目录（首个案例：`agent-framework/`）。被调研的开源仓库源码**不进本仓库**，统一克隆在 `~/develop/opensource/`。

## 总体模式：两地分离

| 位置 | 角色 | 说明 |
|---|---|---|
| `~/develop/opensource/` | 源码克隆工作区 | 全量克隆被调研仓库，**跨调研任务复用**。克隆规范（镜像加速、remote 改回官方、push 绝不过镜像等）见该目录自己的 AGENTS.md，**克隆前必读** |
| `lab/research/<topic>/` | 调研过程 + 结果 | 进 git、随仓库沉淀；每次任务一个子目录，目录名小写连字符（如 `agent-framework`、`agent-oss`） |

分离的理由：克隆区单个仓库 0.5~1.2G 且是第三方代码，混进 lab 会污染 POC 仓库；分离后同一批克隆可服务多轮调研（如 `dify` 在框架轮已克隆，agent 产品轮可直接复用）。

## 标准流程（四阶段，分批可续）

1. **Phase 0 选型圈定**：用 `gh api` 批量核验候选仓库（canonical 地址有效性 / star / 最近 push / 是否 archived），排除停滞、归档项目；对照历史调研子目录划清边界，避免重复调研。注意仓库会迁移 org / 改名 / 归档，引用地址以 API 实测为准。
2. **Phase 1 逐对象档案**：`profiles/` 每对象一份档案（定位、仓库结构、核心抽象清单、评级总表、证据明细），证据可溯源到 `~/develop/opensource/<repo>/路径#符号`。
3. **Phase 2 横向维度**：`dimensions/` 逐维度做跨对象矩阵分析。维度**按任务定制**（框架轮是 15 维，产品轮不必照搬）。
4. **Phase 3 综合报告**：`report.md` 为最终交付，`README.md` 作入口（研究说明、方法、进度 checklist、目录导航）。

进度用子目录 README 里的 checklist 记录，任务跨会话中断后可续。

## 子目录模板

```
research/<topic>/
├── README.md      # 入口：方法、对象清单、进度 checklist、目录导航
├── report.md      # 综合报告（最终交付，先读这篇）
├── profiles/      # 逐对象档案（过程）
└── dimensions/    # 横向维度分析（过程，可选，看任务形态）
```

## 证据纪律（沿用 agent-framework 轮的约定）

- 所有结论可溯源：`~/develop/opensource/<repo>/路径#符号`；区分三级证据——【核心】核心代码实现 /【示例】examples 或 demo /【文档】文档宣称；查不到标 ❌ 或 ⚠️待确认，不臆测。
- 未本地克隆的对象不纳入源码级结论，只能以「非源码结论」明确标注。
- 网络受限：github.com 网页 / raw 常超时，查仓库元数据 / README / 文件内容优先用 `gh api`（安装位置与用法见仓库根 AGENTS.md）。
- 本目录只放文字结论，不放源码副本、大文件、截图转储。

## 克隆与基线纪律

- 克隆前先查 `~/develop/opensource/` 是否已有，**不要重复克隆**；复用时记录该仓库 HEAD 作为本轮基线。
- **研究进行期间冻结已分析仓库**：不要 `git pull`（避免基线漂移）；确需更新，更新后重记基线。旧报告凭记录的 HEAD 随时 `git checkout <hash>` 复现。
- 通用仓库名可能撞名（opensource 平铺，如 `agent-framework` 这种名字），引用时写全 `owner/repo`，冲突时克隆目录用 `<owner>-<repo>`。
- 磁盘预算：按当轮入选清单**按需克隆**，不要预克隆候选全集。

## 历史调研索引

| 子目录 | 主题 | 时间 | 说明 |
|---|---|---|---|
| `agent-framework/` | 主流 Agent 开发框架多维度对比（17 框架 × 15 维，源码级） | 2026-09 | 方法和评级体系的来源，见其 README.md |
