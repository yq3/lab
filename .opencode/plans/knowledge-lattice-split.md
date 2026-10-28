# knowledge-lattice 拆仓方案

> 拟稿：2026-10-28（M1 收官、PR #56 已合 main 之后）。先例：py-night-school 拆仓（2026-09-19）。
> 状态：**已执行完毕**（2026-10-28，执行记录见 §九）。

## 一、背景与目标

- AGENTS.md 约定：每个 App 是 POC，"效果验证通过后，可能拆出去单独建仓继续演进"。
- knowledge-lattice M1 已验收收官（门禁 663 用例双后端全绿、PR #54/#55 合入、#56 同步 main），M2（语义层）尚未开工——正是里程碑边界的拆仓窗口。
- 目标：以与 py-night-school 一致的方式，把 `knowledge-lattice/` 拆为独立仓 `yq3/knowledge-lattice`，**完整提交历史随迁**；lab 侧目录冻结留存并加标注；M2 起的维护一律在新仓。

## 二、先例对照（py-night-school，2026-09-19）

| 维度 | 先例做法 | 本仓沿用 |
|---|---|---|
| 历史迁移 | 完整提交历史随迁（独立仓首条 commit 即原立项 commit，message/作者/日期原样，hash 因路径改写而变——子目录提升为仓根的典型效果） | ✅ 同法 |
| lab 侧目录 | **不删除**，作为"过渡副本"冻结，定格于目录最后一个 commit（`0a228cd`） | ✅ 同法（定格 `93f4426`） |
| lab README | 目录段落加"已拆仓独立演进"引用块：新仓地址 + 定格 commit + "后续维护一律在新仓进行" | ✅ 同格式 |
| 可见性/许可 | public + MIT（LICENSE 系拆仓整理批新加——lab 侧副本无 LICENSE、独立仓有，已实证） | ✅ 同（用户拍板 2026-10-28：public） |
| 默认分支 | 单 `main` | ✅ 建议同（develop 历史已全在 main，无信息损失） |
| 教程/正文自包含 | 拆仓时正文自包含、源码路标指向上游仓库 | ✅ 同原则——断链改指 lab 仓 GitHub 绝对地址 |

## 三、现状盘点

### 3.1 拆迁资产（git tracked，194 文件）

- `src/knowledge_lattice/`（73）、`tests/`（78）、`benchmarks/`（24）、`eval/`（5，corpus/golden/reports）、`scripts/`（3，含 `test_gate.sh`）
- `docs/`（4）：requirements.md / design.md / TEST-CASES.md / known-gaps.md（活文档随仓走）
- `.opencode/workflows/`：`_template.md`（检查点模板，41 行）+ `task-knowledge-lattice-m0a-1 ~ m1-5.md`（9 个，约 4000 行）——**用户指示一并随迁、含提交历史**（kl 任务文件已验证无 lab 内部路径引用；frontmatter `target: knowledge-lattice` 等历史字段原样不改写）
- 根级：README.md、RUNBOOK.md、prototype/index.html、pyproject.toml、uv.lock、.python-version、.gitignore、.env.example
- **不随迁**（未跟踪/忽略）：`.env`（密钥）、`data/`（SQLite 主库/边车/审计月库/对象目录/bench 数据）、`.venv`、`.pytest_cache` 等——工作区 9.2G 均属此类，新仓本身很轻（约 4.1 万行增量 + 前期文档）
- 自包含性已验证：src / pyproject / README 无任何 `develop/lab` 或跨目录相对引用；`.gitignore` / `.env.example` 已完备，克隆即跑

### 3.2 拆仓后会被打断的链接（共 5 处，需改为 lab 仓绝对地址）

| 位置 | 断链 |
|---|---|
| README.md:7 | `../glossary-agent/` |
| README.md:14 | `../research/enterprise-rag/`、`../glossary-agent/` |
| docs/requirements.md:5 | `../../research/enterprise-rag/` |
| docs/requirements.md:19 | `../../glossary-agent/` |
| docs/design.md:6 | `../../research/enterprise-rag/` |

统一改为 `https://github.com/yq3/lab/tree/<branch>/glossary-agent` 与 `.../research/enterprise-rag` 形式（branch 取 `main`）。

### 3.3 留在 lab 的关联物（不迁）

- `.opencode/workflows/task-pulsepet-m1 ~ m8.md`（8 个）——pulsepet 任务检查点，lab 独有
- `.opencode/README.md`（工作流约定文档）——lab 级资产；模板 `_template.md` 注释引用的"README §4.5/§4.6"在新仓侧悬空（已知、登记不改：约定文档超出本次指示范围，新仓需要时后续补）
- `glossary-agent/`——术语层调研与设计沉淀（kl 的设计输入，但物理属 lab；新仓内以绝对链接回指）
- `research/enterprise-rag/`——22 仓调研（同上）
- lab issue #31~#43（评审与决策变更）——历史留 lab；正文中的绝对 URL 不会断；**新 issue 一律开新仓**

注：`_template.md` 与 9 个 kl 任务检查点为**双份**——随迁新仓（带历史、M2 起新仓继续在此记检查点）+ lab 侧原样冻结留存（模板仍被 pulsepet 流程与 `.opencode/README.md` 引用，不删；kl 文件与 kl 目录冻结同口径）。

## 四、操作步骤

> 全程在临时克隆里做，lab 本仓零风险；filter-repo 不改动 lab 原仓。

1. **前置确认**：lab `develop`/`main` 已同步（✓ 本次 #55/#56 已合入）；本机安装 `git filter-repo`（`brew install git-filter-repo`；当前未安装）。
2. **克隆临时副本**（filter-repo 要求 fresh clone）：
   ```bash
   TMP=/var/folders/9k/4ts9r9n92737zx0fjkqtrnym0000gn/T/opencode/kl-split-$(date +%s)
   git clone --no-local ~/develop/lab "$TMP" && cd "$TMP"
   git checkout main && git branch -D develop develop_opencode   # 新仓单 main（历史已含全部）
   ```
3. **历史改写**（含 workflows 检查点文件的历史随迁——用户指示，先例无此项）：
   ```bash
   git filter-repo \
     --path knowledge-lattice/ \
     --path .opencode/workflows/_template.md \
     --path .opencode/workflows/task-knowledge-lattice-m0a-1.md \
     --path .opencode/workflows/task-knowledge-lattice-m0a-2.md \
     --path .opencode/workflows/task-knowledge-lattice-m0a-3.md \
     --path .opencode/workflows/task-knowledge-lattice-m0b-1.md \
     --path .opencode/workflows/task-knowledge-lattice-m0b-2.md \
     --path .opencode/workflows/task-knowledge-lattice-m0b-3.md \
     --path .opencode/workflows/task-knowledge-lattice-m1-1.md \
     --path .opencode/workflows/task-knowledge-lattice-m1-2.md \
     --path .opencode/workflows/task-knowledge-lattice-m1-3.md \
     --path .opencode/workflows/task-knowledge-lattice-m1-4.md \
     --path .opencode/workflows/task-knowledge-lattice-m1-5.md \
     --path-rename knowledge-lattice/:
   ```
   效果：`knowledge-lattice/` 提升为仓根，10 个 workflows 文件保持 `.opencode/workflows/` 原路径；message/作者/日期原样、hash 变化；无关分支/tag（如 `todo-lite-v*`）自动剪除；仅触及其他文件的 commit 被剪除（如 pulsepet 检查点的 commit 不进新仓）。
   （先例未留操作记录、工具不可考；filter-repo 为社区标准工具，产出与先例效果一致：信息原样、hash 因路径改写而变。）
4. **新仓整理批**（临时仓内一次 commit，对齐先例拆仓批）：
   - 修 §3.2 的 5 处断链（→ lab 绝对地址——先例同法：pns 独立仓 CURRICULUM 指回 lab 调研的链接即 `https://github.com/yq3/lab/tree/main/...` 形式）；
   - 加 **MIT LICENSE**（`Copyright (c) 2026 youqi`——先例拆仓批实证）。
5. **建仓推送**：GitHub 建 `yq3/knowledge-lattice`（**public**）→ `git remote add origin git@github.com:yq3/knowledge-lattice.git && git push -u origin main`。
6. **新仓验证**：fresh clone → `uv sync` → `.env` 按 `.env.example` 配置 → `./scripts/test_gate.sh`（sqlite 臂全绿即证明自包含；pg 臂按 RUNBOOK 起 PG 后复跑）。
7. **lab 侧收尾 PR**（develop_opencode → develop → main，与 #55/#56 同链路）：
   - README.md §knowledge-lattice 段落：保留描述段（顺手把过时版本号刷新为最终态 v0.9.5 / TEST-CASES v1.8 / 门禁 663）+ 加标注块（对齐 py-night-school 格式）：
     > **已拆仓独立演进**（<日期>）：新仓地址 [yq3/knowledge-lattice](https://github.com/yq3/knowledge-lattice)（public、MIT、完整提交历史随迁）。本目录为拆仓时的过渡副本，定格于 lab 提交 `93f4426`；后续维护一律在新仓进行。
   - lab 根 AGENTS.md **不改**（先例未改：pns 条目至今仍指向冻结副本的 AGENTS.md）；
   - 不删 `knowledge-lattice/` 目录本身。
8. **收尾归档**：删除临时克隆；本方案文档标记已执行并回填实际日期/commit。

## 五、风险与对策

| 风险 | 对策 |
|---|---|
| 历史 commit message 里的 `#31`~`#55` 在新仓被 GitHub 解析为不存在的 issue 引用 | 接受不改写（先例同样处理；正文中的绝对 URL 不受影响）。README 拆仓说明中注明"编号 #N 指原 lab 仓 issue" |
| filter-repo 误操作污染 lab 原仓 | 全程用临时克隆；lab 原仓不执行任何改写/force 操作 |
| 运行数据/密钥遗留 | 均未跟踪（.gitignore 已覆盖 .env / data/），filter-repo 只迁 tracked 内容，天然隔离 |
| 拆仓后 lab 冻结副本与后续修复脱节 | 与先例同口径：M2 起缺陷/演进一律新仓，lab 不回写 |
| TC-UI 手动走查（M1 唯一余项）尚未执行 | 不阻塞拆仓（用例清单已入库随迁）；走查在新仓侧执行并回写 TEST-CASES |

## 六、验收清单

- [x] 新仓 `yq3/knowledge-lattice`（public + MIT）单 `main` 分支；首条 commit 为**模板溯源提交**（2026-08-11 opencode 工作流批——模板历史早于 kl 立项，是"模板含历史随迁"的如实结果；kl 立项批紧随其后，日期/信息均原样）
- [x] 新仓含 `.opencode/workflows/_template.md` + 9 个 `task-knowledge-lattice-*.md`（历史随迁，路径不变）
- [x] 新仓 fresh clone 后门禁全绿——实际跑的是**完整双后端双模式门禁**（强于原验收项）：GATE PASS，663 passed / 1 deselected（manual）/ 0 skipped，pg 臂 225 条全实跑（[pg] 参数化 193 + PG 专用 32）
- [x] 新仓内无指向 lab 内部路径的相对链接（§3.2 五处已改绝对地址，全仓 grep 复查为零残留）
- [x] 新仓有 MIT LICENSE；lab README 已加冻结标注（根 AGENTS.md 按先例不动）
- [x] `knowledge-lattice/` 目录原样留存；临时克隆已清理；本方案回填执行记录

## 九、执行记录（2026-10-28）

- **工具**：git-filter-repo 2.47.0（uv tool 安装；brew 不在非交互 PATH）。临时克隆后做过分支收敛操作触发其"新鲜克隆"reflog 检查，以 `--force` 跳过——目标为一次性临时副本，lab 原仓全程零接触。
- **改写**：`--path knowledge-lattice/` + workflows 10 文件枚举 + `--path-rename knowledge-lattice/:`；改写后 95 commits（仅 main 单分支），#56 合并 commit 因双父树过滤后等价被自动剪除（无内容损失）。
- **整理批**：commit `fa55afa`（5 处断链 → `https://github.com/yq3/lab/tree/main/...` 绝对地址 + MIT LICENSE）。
- **新仓**：https://github.com/yq3/knowledge-lattice （public、MIT、单 `main`），HEAD = `fa55afa`。
- **验收**：fresh clone（GitHub SSH）→ `uv sync` → `.env`（本地密钥，不入库）→ `LATTICE_PG_DSN=... scripts/test_gate.sh`：**GATE PASS**——双模式各 663 passed / 1 deselected / 0 skipped（70s/模式），pg 臂 225 条全实跑。
- **lab 收尾**：README §knowledge-lattice 段落刷新最终态（v0.9.5 / TEST-CASES v1.8 / 门禁 663）+ 已拆仓标注块（定格 `93f4426`）；本方案文档随收尾 PR 入库；`knowledge-lattice/` 目录与 `.opencode/workflows/` 全部文件原样留存、未删任何内容。

## 七、决策点（已拍板，2026-10-28）

1. **可见性**：**public**（用户裁定；内部信息顾虑已提示一次，不再重提）
2. **LICENSE**：**MIT**（随 public 对齐先例；`Copyright (c) 2026 youqi`）
3. **拆仓时机**：**现在**（M1 收官点）
4. **新仓名**：`knowledge-lattice`

## 八、与先例的偏差记录（原稿超出先例项，已收回）

原稿曾含 3 处超出 py-night-school 先例的添加，按用户"纯照搬"要求收回，留此记录备查：

1. ~~新仓建议 private~~ → 用户裁定 public（内部信息顾虑已提示，用户接受）；
2. ~~新仓新增根级 AGENTS.md 承接冻结纪律~~ → 先例中 pns 的 AGENTS.md 是拆仓**前**就有的项目宪法、随目录原样搬走，并非拆仓时新增；kl 无自有 AGENTS.md，冻结纪律由 kl README 承载（其中已有"设计冻结纪律不变"声明句），照搬即不新建；
3. ~~修改 lab 根 AGENTS.md 为冻结口径~~ → 先例拆仓时未改 lab AGENTS.md（git 历史实证：pns 条目至今指向冻结副本、未加任何拆仓说明），照搬不改。

保留的两处 kl 特有动作（均非杜撰、有先例或事实依据）：§3.2 断链修复——kl 实际存在 5 处指回 lab 的相对链接，先例同场景同法处理（pns CURRICULUM 指回 lab 调研的链接即改为 `https://github.com/yq3/lab/...` 绝对地址）；lab README 版本号刷新——描述段里 v0.8/v1.4/172 条早已过时，重写标注时顺手改对，属事实性修正。

另有一处**用户指示的先例外扩展**（非自作主张，2026-10-28 指示）：`.opencode/workflows/` 的检查点模板 `_template.md` 与 9 个 `task-knowledge-lattice-*.md` 随仓迁移（含历史）——pns 拆仓无此先例（其无检查点文件）；lab 侧两份资产均不删除（模板仍被 pulsepet 流程引用）。已知悬空引用登记：模板 frontmatter 注释提及的"README §4.5/§4.6"指 lab 的 `.opencode/README.md`，新仓暂无该文档，需要时后续在新仓补约定。
