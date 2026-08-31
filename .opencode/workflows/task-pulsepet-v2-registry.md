---
taskId: task-pulsepet-v2-registry
target: pulse-pet
coderTaskId: ses_fb4a38acbffe8DIUpdfhu5OaxQ
testerTaskId: ses_fb4285e8affew32RWWjQ8BbMK8
committerTaskId: ses_fb41f11dfffeUtUJ7USmT974Mx
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: db8dc714afcb34425f91601960f49d6668d29a0a
reviewedSha: db8dc714afcb34425f91601960f49d6668d29a0a
filesChanged: ["src-tauri/src/agents.rs(新增)", "src-tauri/src/http_server.rs", "src-tauri/src/integrations/mod.rs", "src-tauri/src/lib.rs", "src/lib/agents.ts(新增)", "src/lib/agents.test.ts(新增)", "src/lib/token-stats.ts", "src/lib/bubble-queue.ts", "src/lib/pet-menu.ts", "src/lib/integrations.ts", "src/lib/agent-adapter.ts", "src/panel/TokenStats.tsx", "src/panel/Settings.tsx", "src/lib/token-stats.test.ts", "src/lib/token-chart.test.ts", "docs/v2/agent-registry.md", "AGENTS.md"]
endReason: null
createdAt: 2026-08-29T10:19:44+08:00
updatedAt: 2026-08-29T13:18:32+08:00
---

# task-pulsepet-v2-registry: PulsePet agent registry 收敛 P1+P2（Rust + 前端注册表，行为零变化）

## 任务原文

实施 `pulse-pet/docs/v2/agent-registry.md`（2026-08-28 定稿，已过评审轮 + 测试覆盖核定）中的收敛方案 **P1 + P2 两阶段**（P3 N 源化与 degraded 口径 A′ 另立检查点任务，不在本任务范围）：

**P1：Rust `agents.rs` 注册表（§8.1，行为零变化，~400 行净变动，多为删分支）**
- 新增 `src-tauri/src/agents.rs`：`AgentSpec` / `IntegrationSpec` / `StatsSource` + `static AGENTS`（两家）+ `find(id)`；自测：find 已知 id 命中、未知 id → None、AGENTS id 唯一、无 id 叫 `"task"`；
- 改造点：`http_server.rs:41` 白名单删除改查表（:287 校验 / :968 测试遍历）；`lib.rs:109` idle 分流 match 两臂 → find + spec.stats 分发（注入式签名冻结不变，:570-722 闭包注入单测免改）；`lib.rs:202/:210` cc_dispatch 字面量 → spec.id；`lib.rs:295/:311/:359` 接线组 → `agents::register_states(&app)`（窗口创建循环之前，:730-748 时序钉子改盯 register_states，issue #9 铁律不变）；`integrations/mod.rs` ID_* 常量迁移、status_for 拆两函数走 status_probe 指针、vec![两行] → 遍历 AGENTS、install/uninstall 守卫与分发 → find + 函数指针 + install_hint 字段；tempdir 注入单测免改；
- 新钉 5 枚（§8.7.2 P1）：agents.rs 自测 ×3、status_for 未知 id 明确 Err（消静默错误①）、时序钉子改写。

**P2：前端 `src/lib/agents.ts` 注册表（§8.2，~150 行）**
- 新增 `AGENTS` 表 + helpers（`shortOf` / `badgeOf` / `hasCostOf` / `descKeyOf`）+ `IntegrationId` 派生类型；
- 改造点：`token-stats.ts` 删 AGENT_* 常量与 switch（引用点仅 4 文件）；`TokenStats.tsx:83-87` agentBadgeOf → badgeOf 查表 + 未知 id 显原名（消静默错误②）+ "codex"→非"oc"钉子；`agentLabel` / cost 两处（:485/:520）→ hasCostOf；`Settings.tsx:565` nameKey 三元 → descKeyOf；
- 双端互钉（§6.3）：agents.rs 测试 `include_str!("../../src/lib/agents.ts")` 断言两端 id + short 集合一致；
- 新钉 2 枚（§8.7.2 P2）：badgeOf 未知 id 显原名、include_str 互钉。

**验收标准**：
- `cargo test` 全绿：基线 346 passed + 3 ignored（+ 新钉 5 枚）；`cargo build` 零警告；
- `npm test` 全绿：基线 442（+ 新钉 2 枚）；`npx tsc --noEmit` / `npm run build` 全绿；
- 行为零变化：integrations_status / token_stats_query / 气泡徽标 / doctor 输出与改前一致（既有网回归证明）；
- dev 冒烟：设置页两张接入卡 doctor / 安装 / 卸载与改前一致（§8.1）；
- 每阶段独立 commit、可单独回滚；commit 后补完整 `npm run tauri build`（流程口径，见遗留事项 F）。

**约束**：
- 明确不做（§6.7）：不激活 AgentAdapter、不动 HTTP 协议/DB schema/气泡菜单状态机、不接 codex、不动 killswitch 粒度、不引新依赖；
- 分支：切到既有 `develop_opencode` 并**立即快进同步最新 develop**（2026-08-29 实测落后 6 个提交、停 b2c91e3，无分叉可 ff），commit 格式 `[task-pulsepet-v2-registry] R<n>`，commit 前再次确认已同步 origin/develop；
- 工作区他人未提交改动（V2-OPEN-ITEMS.md §十四落档、.opencode/* 修订、blog / images/ 未跟踪文件）**不属于本任务，禁止 stage / commit / 修改**；
- 文档联动（§8.4）：`agent-registry.md` 回写实施记录随阶段进行。

## 需求确认

- [x] 用户已确认（2026-08-29 10:29，五项裁定如下，status → implementing）
- 确认结果：
  1. 范围节奏：**P1+P2 连做**，P3 另立检查点任务；
  2. dev 冒烟：coder 在 P2 完成后跑**一次** `npm run tauri dev` 基础冒烟（启动、设置页两张接入卡 doctor/安装/卸载、Token 页、气泡）；每 commit 后补完整 `npm run tauri build`（流程口径 F）；不另设强制人工目验节点（双通过后交付确认即用户自然目验点）；
  3. 遗留事项 A（manual 冒烟测试参考 SQL 旧口径）**并入 P1 顺手修**；B（TokenStats.tsx:521 过时注释）**并入 P2 顺手清**；
  4. 工作区未提交改动（V2-OPEN-ITEMS.md §十四落档、.opencode/* 修订、blog / images/ 未跟踪）**保持原样，coder 只 stage 自己的文件**；⚠️ 用户特别指示：**coder 切到 develop_opencode 后必须立即同步最新 develop**（develop_opencode 停在 b2c91e3，落后 develop 6 个提交，可快进，实测 2026-08-29 10:29）；
  5. V2-OPEN-ITEMS §十四（跨天会话归属）**继续排队、本轮不动**；顺序定为 **registry P3 完成后再实施 §十四**。

## 遗留事项（跨任务移交）

扫描 `.opencode/workflows/` 全部 15 个历史检查点（status 均 approved），未了结事项分类：

**本任务并入（2026-08-29 用户确认，处理完毕后回写勾选并注来源）**：
- [x] **A.（来源 task-pulsepet-v2-m5 R2 tester 2026-08-27，用户 2026-08-29 确认并入 P1）TEST_BUG real_db_reconciliation_manual**：src-tauri manual 冒烟测试（ignored）参考 SQL 仍 DESIGN §4.1 旧口径，未随 M5 `GROUP BY day,agent,model_id`+mock 过滤更新——随 P1 顺手修；→ **✅ 已清偿，无需新增改动（2026-08-29 编排者核验）**：coder 发现该 TEST_BUG 已在 M6 R1 commit `8973813` 顺手修毕，现行 SQL 即 `GROUP BY day, agent, model_id` + mock 过滤（token_stats.rs:2053-2068，注释含"v2-m5 移交 TEST_BUG，M6 顺手修"字样），本人 grep 复核属实；
- [x] **B.（来源 task-pulsepet-v2-m5 committer 终审 P3-3，用户 2026-08-29 确认并入 P2）TokenStats.tsx:521 symmetricToggle 注释「模型/agent 共用」过时**（R2 后仅模型用）——随 P2 顺手清（一行注释）。→ **✅ 已清偿，无需新增改动（2026-08-29 编排者核验）**：coder 发现在 polish 轮 commit `8a054e0` 已修正，现行注释（TokenStats.tsx:537-538）为"模型筛选用——v2-m5 R2 后 agent 维度已改为恒全集展示，不再消费本函数"，措辞准确，本人 grep 复核属实。

**流程口径（必传 coder，非待办）**：
- **F.（来源 task-pulsepet-v2-polish 2026-08-28 用户三次抓漏后确立）**：coder 每次代码 commit 后必须补完整 `npm run tauri build` 且产物时间戳晚于提交时间。

**继续移交（去向已注明，不并入本任务）**：
- 实机/硬件类：多屏与 Windows 实机验证批次（v1-m6/m8、v2-m1/v2-m4/v2-m5 多处汇总；含 TC-M5 实机缺口 4 项待用户人工配合）；
- 用户反馈类：v2-m2 实机目验 7 项、v0.1.3 收尾目视验收、Release publish 决定（待用户指示）；
- 打磨轮去向：v2-m5 committer P3-1（transcript.rs 注释重复）/P3-2（assert_ne TZ 假设）/P3-4（TranscriptCache 锁内解析观察项——P1 动 register_states 时留意但不强改）、v2-m6 P3-①②④、v2-polish 终审 P3×5（global.css/V2-OPEN-ITEMS 措辞等）；
- 记录类：INC-20260827-1033 留档至 2026-09-03（未到期）、V2-OPEN-ITEMS §十四（独立排队任务，2026-08-29 落档）；
- v1 后移项：TC-DONE-01~09、限流豁免 /health（v2 心跳引入时）。

**本任务新移交（2026-08-29 R1 双通过后确立，去向=registry P3 检查点任务 kickoff 清单，来源=committer 终审观察项）**：
- [ ] **① P3 文档**：agent-registry.md 全局状态标记刷新——标题行状态栏/§1 结论/§6 标题/§8.0 附表仍称"未启动/待指令"，与 §8.1/§8.2"已实施"记录矛盾（P3 kickoff 时统一刷新为"P1/P2 已实施、P3 进行中"）；
- [ ] **② P3 代码**：TokenStats `agentBadgeOf` 内联查表改为 `specOf` 单次查表（`text: badgeOf(s.agent)`），使 P2 钉 1 直接覆盖消费点（Tester 观察②，风险低非必改，顺带消除钉子盲区）；
- [ ] **③ P3 注释**：lib.rs:106 注释"§6.1 决策 4"引用无对应编号项（§6.1 仅三个编号决策）——改为"§6.1 注入式签名冻结"；
- [ ] **④ P3 收尾**：V2-OPEN-ITEMS.md §13 交叉引用与闭环记录回写（本任务因该文件有用户未提交改动而推迟——P3 kickoff 前确认用户已处理工作区改动）；
- [ ] **⑤ 流程沉淀**：后续轮次流程口径 F 的构建产物时间戳建议以 `stat` 输出形式落档（Tester 观察①），供双构建留痕复核。

## 轮次记录

- R1（进行中，2026-08-29）：Coder 首次调用被取消（vision 越界权限卡死，用户中断）；经 opencode.db 恢复会话 task_id=`ses_fb4a38acbffe8DIUpdfhu5OaxQ`。中断前实际进度（11:16 git 实测）：**P1/P2 两 commit 已落 develop_opencode**（`604fb6d` P1 Rust agents.rs 注册表 / `db8dc71` P2 前端 agents.ts 注册表+双端互钉），工作区纪律完好（用户未提交改动未被触碰）；卡点=P2 后 tauri dev 冒烟——截图存 `/tmp/pulsepet-smoke-1.png`（工作区外），委托 Vision 分析触发越界权限申请卡死。用户指示：**续接 Coder 继续，vision 调用必须先确保图片拷入当前工作区**。
- R1: **Coder 完成（2026-08-29 11:30 报告）**。P1 commit `604fb6d`（5 文件 +538/−203：agents.rs 新增 235 行 AgentSpec/IntegrationSpec/StatsSource/AGENTS/find/register_states + 自测 4 枚；http_server 白名单改查表；integrations status_for 拆两函数+未知 id Err+遍历 AGENTS+install/uninstall 指针化+install_hint；lib.rs idle 分流查表+签名冻结+register_states 收敛+时序钉子双断言加严；agent-registry.md §8.1 回写）。P2 commit `db8dc71`（14 文件 +209/−48：agents.ts 新增 64 行 AGENTS 表+helpers+AgentId 派生；agents.test.ts 新增 5 例；token-stats.ts 删常量与 switch；bubble-queue/pet-menu 两个盘点外消费方一并迁 shortOf；IntegrationId 表派生；agent-adapter 装饰性标注；TokenStats badgeOf 查表+未知显原名+cost hasCostOf；Settings descKeyOf+兜底；agents.rs 增 include_str 双端互钉；文档回写+AGENTS.md 加指南句）。**自测证据**：cargo test 352 passed+0 failed+3 ignored（基线 346+3i）/ cargo build 0 警告 / npm test 447 passed·32 文件（基线 442）/ tsc --noEmit OK / npm run build OK / 流程口径 F 两 commit 后 tauri build 产物时间戳均晚于提交（P1 10:58:49→10:59:22/43；P2 11:06:08→11:06:51/07:12）/ dev 冒烟：启动干净无 panic、面板唤起、Token 页 4 KPI+柱图+会话列表正常且无 degraded 横幅、设置页两卡 doctor 正常（opencode 已安装·事件正常；CC 未安装·node 已就绪，needs_node_probe 路径实证）、右键菜单/气泡未目验已如实记录（测试网覆盖，建议用户交付时自然目验）。**偏差 7 点**（详见 coder 报告）：install/uninstall 经薄适配函数挂表（内层+tempdir 单测零改动）、node 探测计时日志移至分发层（doctor 输出逐字节一致）、register_states 放 HTTP server 启动前（强于设计下限，时序钉双断言）、短名消费方多 2 文件、A/B 顺手修经核实已在历史提交清偿无需重复、2 处定点 #[allow(dead_code)] 有先例注释、register_states mock 测试走泛型内层+Wry 薄壳。**编排者核验（11:31 git/grep 实测）**：HEAD=db8dc714afcb34425f91601960f49d6668d29a0a 属实；工作区仅剩用户未提交改动（V2-OPEN-ITEMS.md/images/）；A 项 manual SQL 确为 GROUP BY day,agent,model_id+mock 过滤（token_stats.rs:2053-2068，注释注明 M6 顺手修）；B 项 TokenStats.tsx:537-538 注释确为准确措辞（polish 轮已修）。status → testing。
- R1: **Tester PASS（2026-08-29 12:50 报告，testedSha=db8dc71…与 HEAD 一致）**：既有网全部亲测（cargo 352+0+3i / npm 447·32 文件 / tsc / cargo build 0 警告 / npm run build 全过）；注入式签名冻结硬约束核实（lib.rs diff 全部 hunk 不含 idle 闭包注入单测区，tempdir 内层签名零改动、20 枚全免改通过）；新钉 7 枚逐枚核对真实在跑且断言与目的相符；两处静默错误修复实证（status_for 未知 id→Err / badgeOf 未知→原名）；行为零变化读码逐项等价（白名单/idle 两臂含未知臂日志原文/doctor 输出逐字段溯源一致/token_stats.rs 两 commit 未触碰/前端消费点等价）；Coder 7 点偏差全部裁定可接受（③ register_states 先于 server 启动裁定"正确且必要"）；commit 卫生无混入。非阻断观察 3 项：①P1 中间构建产物被 P2 构建覆盖，以 Coder 报告为准（建议以后 stat 落档）；②TokenStats.tsx agentBadgeOf 内联查表而非调 badgeOf（行为恒等，钉子守的是 helpers 非消费点，P3/P4 可顺手统一 specOf 单次查表）；③右键菜单/气泡留待交付时用户自然目验。详见"最新验证意见原文"。status → 待 committer。
- R1: **Committer APPROVED（2026-08-29 13:00 报告，reviewedSha=db8dc71…=testedSha=HEAD）**：独立读码复核（未采信 Tester 结论）——方案忠实度四原则逐条通过、§6.7 零越界（codex 拒绝钉原样保留）、行为零变化代码级复核成立（白名单全输入域等价/idle 两臂与未知臂日志逐字节一致/status_for 拆分逐字段同源/install 守卫文案逐字不变/前端消费点等价，两处有意行为变更仅发生在静默错误修复路径=任务要求本身）；Tester 3 观察项处置：①接受留档（后续 stat 落档）②接受留档移交 P3/P4（风险低：消费点无 "oc" 硬编码+互钉把守）③接受留档；文档回写准确（附 1 项 P3 观察：agent-registry.md 全局状态标记仍称"未启动"与 §8.1/§8.2 矛盾——建议 P3 kickoff 时统一刷新）；commit 拆分干净（备忘：P1-only revert 需先撤互钉测试，实际回滚场景为全撤或撤 P2，无碍）；遗留风险扫描无 P1/P2 级问题（互钉格式约束响亮失败可接受）。**问题清单：无 P0/P1/P2；需求边界问题：无**。观察/备忘 5 项全非阻断：①P3 文档状态标记刷新 ②P3 badgeOf→specOf 统一 ③P3 lib.rs:106 注释引用编号修正（"§6.1 决策 4"无对应项）④后续流程 stat 落档 ⑤交付目验。**放行**。详见"最新验证意见原文"。status → approved。
- R1: **交付启动（2026-08-29 13:08 用户确认"交付"）**：遗留事项小节回写完毕（清偿 A/B；新移交 ①~⑤ 去 P3 kickoff 清单）；指示 Coder 续接执行：同步 origin/develop → 推送 develop_opencode → 开 PR（base=develop）→ Committer gh pr review → Coder 写 evidence manifest 进 PR description → 汇报合入请求。不自动合入。
- R1: **交付完成（2026-08-29 13:16）**：①Coder 同步核验 origin/develop 无新提交（b8cf83d）→ push 成功（`b2c91e3..db8dc71` → origin/develop_opencode，SSH 认证通过）→ **PR #22 开立**（base=develop，head=develop_opencode）；②Committer 正式评审：`gh pr review --approve` 被 GitHub 平台拒绝（"Can not approve your own pull request"——PR 作者与 gh 登录同为 yq3，无法绕过），改走 `--comment` 评论式留痕成功（state=COMMENTED，结论文案完整，注明平台规则）；③Coder 补写 Evidence Manifest JSON 进 PR description（`gh pr edit` 成功，原概述保留，JSON 数值与实施记录核对一致）。**PR #22：https://github.com/yq3/lab/pull/22 —— OPEN + MERGEABLE，待用户合入指令；未 merge、未动 develop/main。** 本任务流程终态（status=approved 沿历史惯例保持，遗留事项新移交 ①~⑤ 由 registry P3 任务承接）。
- R1: **合入闭环（2026-08-29 13:18 用户指令"先合入一下"）**：`gh pr merge 22 --merge`（沿 PR #21 decd3de 双亲合并惯例，保留 P1/P2 独立 commit）→ **state=MERGED，mergeCommit=`4857f81f913e21380ffaf4981681350605b4fc44`（13:17:34）**；本地 develop 已 ff 同步至 4857f81，P1/P2 commit 在主线历史完整可见；develop_opencode 分支保留（工作流常驻分支）。**任务全闭环。**

## 最新验证意见原文

### R1 Committer 报告（2026-08-29 13:00，逐字收录）

审查完成。我已完成：检查点与设计文档通读、两个 commit 的全量 diff 逐文件读码、当前 HEAD 关键区域实读（lib.rs run 时序/注入测试区/order_nails、integrations status_for/probe_status/spawn_status、http_server 校验与测试）、残留引用 grep（ID_*/AGENT_WHITELIST/agentShortName/AGENT_*）、IntegrationId 消费点核查。以下是独立结论（未采信 Tester 结论，逐项自证）。

---

## 审查报告：task-pulsepet-v2-registry R1（P1+P2）

### 判定

**reviewVerdict: APPROVED**

（HEAD `db8dc71…` = testedSha 一致；工作区用户未提交改动零触碰，git status 前后一致，仅存 .opencode/*、V2-OPEN-ITEMS.md、blog、images/ 等用户原有改动。）

---

### 逐项审查结论

#### 1. 方案忠实度（§6.1/§6.2/§6.3/§8.1/§8.2/§6.7）— 通过

- **四原则逐条核对**：
  - *行为零变化*：见第 2 项独立复核，成立。
  - *单一事实源*：Rust 侧 id/short/stats/install/uninstall/status_probe/needs_node_probe/install_hint/register_state 全部收敛进 `AgentSpec`；前端 id/short/labelKey/descKey/hasCost 收敛进 `AGENTS` 表；`ID_*` 常量迁移后 grep 确认无残留散落定义。
  - *贴现有风格*：静态数组 + 函数指针 + enum dispatch，无 trait object/泛型/运行时注册；`#[cfg(test)]` tempdir 注入模式保留。与定稿一致。
  - *分阶段可回滚*：见第 5 项。
- **§6.7 明确不做清单逐项核验**：AgentAdapter 仅加 5 行装饰性标注注释（未 import 进主链路、未激活）；HTTP 协议/DB schema/气泡状态机零触碰（diff 无相关文件）；未接 codex（`state_unknown_agent_returns_400` 与 lib.rs:636 "codex" 拒绝钉原样保留，符合 §6.6 P3-4 预期）；killswitch 未动；Cargo.toml/package.json 均不在改动清单，零新依赖。**无越界。**
- **§8.1/§8.2 文件级计划落实**：14 处必改点的收敛映射全部落实且无遗漏（#1 白名单查表 / #2+#13 idle 查表+register_states / #4 拆两函数+未知 id Err / #5 遍历 AGENTS / #6 指针化+install_hint / #7-#10 前端查表+兜底 / #12 测试面改写 / #14 文档回写）。

#### 2. 行为零变化承诺的代码级复核（独立读码）— 通过

- **http_server 白名单**：`find(&agent).is_none()` vs `!AGENT_WHITELIST.contains()`——AGENTS 恰含原两 id，全输入域等价（含空串/typo）。✓
- **idle 分流两臂**：`OpenencodeDb` 臂 = 原 "opencode" 臂逐行等价（`spec.id` 恒为 "opencode"，SQL 汇报 + apply_event + emit_bubble 字面量同值）；`CcTranscript` 臂 = 原 cc 臂（cc_dispatch 单派发）；未知 id 提前 return，日志原文 `(agent={agent}, unknown)` 与原 `other` 臂逐字节一致。`StatsSource::None` 臂当前无构造点（死分支，P4 预留，`#[allow]` 有据）。✓
- **cc_dispatch 闭包**：`cc_cache` 直持 Arc → `app.state::<Arc<Mutex<TranscriptCache>>>()` 取值；`cc_id` = find("claude-code").id 恒等于原字面量。语义等价的前提是 manage 先于 server start——已由新时序钉双断言 + 实测代码顺序（lib.rs:321 register_states < :334 http_server::start < :425 窗口循环）保证。✓
- **integrations status_for 拆分**：`status_opencode`/`status_cc` 逐字段溯源与原 if/else 两分支一致（id/config_path/hook_file/node_available/last_event_at/message/error 全部同源同值；opencode 的 node 恒 None、CC 的 Some(node) 恒等）。node 探测耗时仅从 CC 日志行片段移为独立 plog 行——IntegrationStatus 输出逐字节不变，日志形态差异无消费方解析，偏差②裁定成立。`integrations_status` 遍历 AGENTS 序 = 注册表序 = 原两行序。✓
- **install/uninstall**：守卫错误文案逐字不变；函数指针目标函数与原 match 两臂逐行等价（`install_oc` = `install_opencode(&opencode_dir()).map(|_| ())`）；`install_hint` 仅 CC true。✓
- **前端消费点**：`shortOf` 与原 `agentShortName` 全输入等价（task 特例 + 原名兜底）；`hasCostOf` 在 wire 值域 {opencode, claude-code} 内与原比较恒等（未知输入差于"更安全"方向且不可达）；Settings `descKeyOf`+原名兜底在两卡值域内恒等。**两处有意行为变更仅发生在静默错误路径**（status_for 未知 id→Err、badgeOf 未知→原名），正是任务要求的修复，非偏差。✓
- **token_stats.rs**：两 commit 均未触碰（stat 证实不在文件清单），构造性保证。✓

#### 3. Tester 3 项观察项处置建议

| # | 观察项 | 我的建议 |
|---|---|---|
| ① | P1 中间 tauri build 产物被 P2 覆盖 | **接受留档**。属流程口径 F 的证据链问题，非代码问题；P2 产物 mtime 11:06:51 > 提交 11:06:08 已实物复核，P1 以 Coder 报告为准。建议后续轮次按 Tester 建议用 `stat` 输出落档双份时间戳。 |
| ② | TokenStats `agentBadgeOf` 内联查表而非调 `badgeOf`（钉子守 helpers 非消费点） | **本轮接受留档，移交 P3/P4 顺手统一**。风险级别评估：**低**——当前消费点不存在任何 "oc" 硬编码（静默错误已事实上消除）；表漂移由 include_str 互钉把守；钉子+代码注释双重记录不变量。回归路径需要未来某人在消费点主动重新引入 `else→"oc"`，且届时该文件正是 P3/P4 改造对象（届时统一为 `specOf` 单次查表即可让钉子直接覆盖）。非阻断。 |
| ③ | 右键菜单/气泡未目验 | **接受留档**。与用户裁定"不另设强制人工目验节点"一致；既有网覆盖（bubble-queue.test.ts:330 兜底钉、agentsWithRows 等）实测通过，交付时用户自然目验。 |

#### 4. 文档回写质量 — 通过（附 1 项 P3 观察）

- §8.1/§8.2 实施记录：数据与实测一致（351/352、447/32、基线漂移说明、三处/四处微调均如实记录且与 diff 吻合）；AGENTS.md 指南句准确（互钉 id/short、一行注册+三件套+i18n、勿散落分支——与 §6.6 目标态一致）。
- **观察项（P3，非阻断）**：设计文档全局状态标记已滞后——第 3 行状态栏、§1 结论"未启动"、§6 标题"实施未启动"、§8 标题"未启动——均仍称"未启动/待指令"，与 §8.1/§8.2"已实施"形成文档内部矛盾。本轮验收标准只要求分阶段实施记录回写（已做），全局状态标记建议在 **P3 检查点任务 kickoff 时顺手更新**（P3 尚未启动，届时一并刷新为"P1/P2 已实施、P3 进行中"）。

#### 5. commit 拆分合理性 — 通过（附 1 项备忘）

- P1（5 文件）纯 Rust 侧 + §8.1 回写；P2（14 文件）纯前端 + 互钉测试 + 文档。边界干净，无交叉文件混入（agents.rs/doc 为两 commit 先后叠加，各自动机清晰）。
- 独立编译/测试链完整（P1 后 cargo 351+3i、P2 后 352+3i 与 447/32）。
- **备忘（非缺陷）**：可回滚粒度——P2-only revert 干净（无后续 commit 依赖）；P1-only revert 会在 agents.rs 冲突（P2 互钉测试落于 P1 新增文件），需先撤互钉测试。该放置位置是 §8.2 设计原文指定（"agents.rs 测试 include_str!"），且 P1+P2 本轮按用户裁定连做、同批交付，实际回滚场景为全撤或撤 P2，均无碍。

#### 6. 遗留风险扫描（Tester/Coder 未覆盖盲点自查）— 无 P1/P2 级问题

- 权限/capability：零变更（diff 无 capability 文件）。
- 依赖：零新增。
- 平台差异：`cfg!(windows)` canonical 路径逻辑未触碰。
- 死引用：`agentShortName`/`AGENT_*`/`AGENT_WHITELIST` 生产代码零残留（grep 证实仅剩文档注释与测试本地字面量常量）；`detect_node` 仍有调用点。
- 互钉测试鲁棒性：TS→Rust 方向的源码文本匹配依赖"每 agent 一行"格式——agents.ts 文件头已显式注记该格式约束（⚠️ 行），格式破坏会使互钉与 Rust→TS contains 双方向**响亮失败**而非静默漏过，可接受。
- `spawn_status` 双层 Result 解包（`map_err(...)?`）类型正确，`?` 透传未知 id Err 路径无 panic。
- `Settings.tsx` 的 `s.id as IntegrationId` 类型断言为存量模式（非本轮引入），tsc 通过。

---

### 问题清单

无 P0/P1/P2 问题。

### 需求边界问题

无。验收标准与实现行为一致；无需求歧义需上报。

### 观察项 / 备忘（汇总，全部非阻断）

1. **P3 文档**：agent-registry.md 全局状态标记（标题行/§1/§6/§8.0 附表）仍称"未启动"，与 §8.1/§8.2 实施记录矛盾——建议 P3 kickoff 时统一刷新。
2. **P3 代码**：TokenStats `agentBadgeOf` 可顺手改为 `specOf` 单次查表 + `text: badgeOf(s.agent)`，使 P2 钉 1 直接覆盖消费点（Tester 观察②，风险低，非本轮必改）。
3. **P3 注释**：lib.rs:106 注释"§6.1 决策 4"引用无对应编号项（§6.1 仅三个编号决策，注入冻结在第 3 条内/评审 P2-2 补答段），建议顺手改为"§6.1 注入式签名冻结"。
4. **流程**：后续轮次流程口径 F 的构建产物时间戳建议 `stat` 落档（Tester 观察①）。
5. **交付目验**：右键菜单/气泡留待用户交付时自然目验（与用户裁定一致）。

无 CASE_BUG 裁定请求（本轮 Tester 未提交）。

---

**交付把关状态**：HEAD `db8dc714afcb34425f91601960f49d6668d29a0a` = testedSha，双 SHA 一致；工作区纪律完好；本轮为 R1 审查，用户尚未确认交付，无 PR 留痕需求（无 PR 号，待用户交付指令后按流程执行 gh pr review）。**放行。**

---

### R1 Tester 报告（2026-08-29 12:50，逐字收录）

# R1 验收测试报告：task-pulsepet-v2-registry（P1+P2 agent registry 收敛）

## testVerdict: **PASS**

- **testedSha**: `db8dc714afcb34425f91601960f49d6668d29a0a`（验证全程 HEAD 未动，工作区用户未提交改动零触碰）
- 验证方式：既有网回归实测 + 7 枚新钉逐一核对 + 静默错误修复实证 + 全量 diff 读码语义等价抽查（按任务指示未实机目验）

---

## 1. 既有网回归（全部亲测）

| 项 | Coder 申报 | 实测 | 结论 |
|---|---|---|---|
| `cargo test`（src-tauri/） | 352 passed / 0 failed / 3 ignored | **352 / 0 / 3** | ✓（基线 346+3i，净增 6 = P1 钉 4 枚〔含 register_states 功能钉，时序钉为改写不计增〕+ P2 互钉 1 枚 + status_for 钉 1 枚） |
| `npm test` | 447 passed / 32 文件 | **447 / 32** | ✓（基线 442/31，+5 = agents.test.ts 五个 it） |
| `npx tsc --noEmit` | OK | **OK** | ✓ |
| `cargo build` | 零警告 | **0 warning**（实测 grep 计数 0） | ✓ |
| `npm run build` | OK | **OK**（vite 构建成功） | ✓ |
| 流程口径 F（tauri build 产物晚于提交） | 两 commit 均补 | `PulsePet.app` mtime **11:06:51** > db8dc71 提交 **11:06:08** ✓；P1 中间产物（10:59）已被 P2 后构建覆盖，无法从产物复核，以 Coder 报告为准 | ✓（见观察项①） |

**注入式签名冻结硬约束**：lib.rs diff 的全部 hunk（`@@ -1,4 / -94,10 / -106,8 / -121,20 / -142,13 / -173,10 / -198,8 / -207,7 / -289,10 / -308,7 / -356,7 / -745,28`）**均不含 idle 闭包注入单测区**；实读 ：597-741 确认 `claude_code_idle_never_queries_opencode_db`（含 "codex" 防御钉 ：626-640）/ `opencode_idle_reports_and_injects_success` 等用例原文未动且通过。integrations 侧 fn 级 diff 仅 status_for 拆分（删 1 增 4）+ 1 个新测试，`#[test]` 计数 20→21，**tempdir 内层函数（install_opencode/install_cc/uninstall_*）签名零改动、全套免改通过**。

## 2. 新钉 7 枚核对表（逐枚确认真实在跑，`cargo test --lib` 输出逐条命中）

| 钉 | 测试 | 断言核对 | 实测 |
|---|---|---|---|
| P1-1 find 命中 | `agents::tests::find_known_ids_hit` | id/short/stats/integration 全字段 + needs_node_probe/install_hint 双向 | ok ✓ |
| P1-2 未知 id→None | `find_unknown_id_returns_none` | "codex"/""/"claude"(typo)/"task" 四态 | ok ✓ |
| P1-3 id 唯一且无 task | `agent_ids_unique_and_no_task` | dedup 计数 + all(!= "task") | ok ✓ |
| P1-4 status_for 未知 id Err | `integrations::tests::status_for_unknown_id_is_explicit_error` | `expect_err` + 错误信息含 id 本身 + 前提钉 find("codex").is_none() | ok ✓ |
| P1-5 时序钉改写 | `order_nails::agent_states_registered_before_window_creation_and_server_start` | **双断言**：register_states < 窗口创建循环 且 < `http_server::start(`——比设计“窗口创建前”下限更强，方向正确（见偏差③） | ok ✓ |
| P2-1 badgeOf 未知显原名 | `agents.test.ts` case 2 | `badgeOf("codex")→"codex"` 非 "oc" + 空串 | ok ✓ |
| P2-2 include_str 互钉 | `agents::tests::frontend_agents_table_matches_rust_registry` | 双向：Rust→TS 逐 (id,short) 对 contains；TS→Rust 条目数相等 + 每 id 已注册；注释行过滤正确（`id: string;` 接口声明不误匹配） | ok ✓ |

## 3. 两处静默错误修复实证

- **#4 status_for**（integrations/mod.rs:880）：签名改 `Result<IntegrationStatus, String>`，未知 id → `Err("未知接入 id：{id}")`，不再落 CC 探测；`spawn_status` 经 `?` 透传。钉子 P1-4 守住。✓
- **#8 badgeOf**（agents.ts:52 + TokenStats.tsx:81-86）：`specOf(agent)?.short ?? agent`，未知 id 显原名；会话行渲染 `spec ? {short, t(labelKey)} : {s.agent, s.agent}`。钉子 P2-1 守住。✓

## 4. 行为零变化抽查（读 diff 逐项语义等价）

- **/state 白名单**：`find(&agent).is_none()` ≡ `!AGENT_WHITELIST.contains()`（表恰含原两 id，含空串/typo 输入）；`state_unknown_agent_returns_400`（未改）与 `state_whitelist_accepts_both_agents`（仅遍历源改 AGENTS）均过。✓
- **idle 分流两臂**：`OpenencodeDb` 臂 = 原 opencode 臂逐行等价（`spec.id` ≡ "opencode" 字面量，SQL 汇报 + success 注入）；`CcTranscript` 臂 = 原 claude-code 臂（后台线程 transcript，零 SQL）；未知 id 走原 `other` 分支的**同一行日志原文**；`StatsSource::None` 臂当前注册表无人使用（死分支，P4 预留）。`make_idle_hook` 签名变了（去掉 cc_cache 参数），但冻结承诺针对的是 `idle_hook_body` 注入签名与闭包——两者未动。✓
- **doctor 输出**：`IntegrationStatus` 各字段逐项溯源（opencode 各路径 `node_available` None 恒等、CC `Some(node)` 恒等、config_path/hook_file/message/error 同源），`integrations_status` 输出序 = 注册表序 = 原两行序 → **结构逐字节一致**。仅 plog 诊断行形态微调（node 探测耗时从 CC 状态行 `(probe {}ms)` 片段拆为独立 `integrations node probe` 行；`node.unwrap_or(false)` 在 needs_node_probe=true 下恒 Some 等价）——**不影响任何消费方，可接受**。✓
- **token_stats_query**：Rust `token_stats.rs` 两 commit **均未触碰**，行为不变由构造保证。✓
- **前端消费点**：`shortOf` ≡ 原 `agentShortName` 全输入等价（task 特例+原名兜底）；`agentLabel` 等价；`hasCostOf` 在 TokenRow.agent 值域 {opencode, claude-code}（Rust wire 保证）内与原比较恒等，未知→"—" 仅差于不可达输入且更安全；Settings `descKeyOf`+原名兜底在可达值域（integrations_status 只出两张卡）内与原三元恒等。既有兜底钉 `bubble-queue.test.ts:330` 原样通过。✓

## 5. Coder 7 点偏差逐条裁定

| # | 偏差 | 裁定 | 依据 |
|---|---|---|---|
| ① | install/uninstall 经薄适配函数挂表 | **可接受** | 内层函数零改动（fn 级 diff 证明），适配层以真实路径调用同一内层，tempdir 单测 20 枚全免改通过；`install_oc` 还消了原 `map(\|_\| ())` 之外的任何语义差 |
| ② | node 探测计时日志移至 probe_status 分发层 | **可接受** | IntegrationStatus 输出逐字节一致（已逐字段溯源）；变化的仅是 stderr/日志文件诊断行，无消费方解析该行 |
| ③ | register_states 放 HTTP server 启动前 | **可接受（正确且必要）** | cc_dispatch 闭包改经 `app.state` 取缓存句柄（旧代码闭包直持 Arc clone），server 先起则在 manage 前到达的 idle 事件会 panic——比设计“窗口创建前”更强的下限是语义等价的前提而非锦上添花；时序钉双断言两个方向都真实把守 |
| ④ | bubble-queue.ts / pet-menu.ts 盘点外消费方迁移 | **可接受** | 纯 import 改名 + 调用点 `agentShortName→shortOf`，两函数全输入等价；§8.7.1 兜底钉 :330 原样通过 |
| ⑤ | 2 处定点 `#[allow(dead_code)]` | **可接受** | `StatsSource::None`（:39，注释注明 P4 接入出现构造点）与 `short_name`（:51，注释注明 P3 消费）；先例引用属实——`StateEvent.project` 即 http_server.rs:159-160，另有 Kind::ALL 等 15 处同类先例 |
| ⑥ | register_states mock 测试泛型内层 + Wry 薄壳 | **可靠** | `register_cc_cache_inner<R: Runtime>` 被 mock_app 驱动实证 manage 真实发生（未 manage 时 `state()` 直接 panic，测试即证）；生产指针 `register_cc_cache` 经指针相等断言钉在表上；cargo build/test 编译通过即类型层面自证 |
| ⑦ | A/B“已在历史提交清偿”声明 | **采信（免重验）** | 编排者已 grep 复核属实；本次验证中设计文档 §8.1/§8.2 实施记录的佐证亦一致 |

## 6. commit 卫生抽查

`git show --stat` 两 commit：P1（5 文件）/ P2（14 文件）**全部为任务清单内文件**，无 `.opencode/*`、V2-OPEN-ITEMS.md、blog、images/ 混入；验证前后 `git status` 完全一致（用户未提交改动原样）。✓

---

## 观察项 / 非阻断备忘

1. **流程口径 F 的 P1 中间构建产物已被 P2 后构建覆盖**，仅 P2 的产物时间戳（11:06:51 > 11:06:08）可实物复核；P1 的 10:59:22 构建以 Coder 报告为准。后续建议：如需留痕，两次构建产物时间戳可在报告中以 `stat` 输出形式落档。
2. **TokenStats.tsx `agentBadgeOf` 内联查表而非调用 `badgeOf`**（因其还需 labelKey 组 title，单用 badgeOf 不够）。行为与 badgeOf 恒等，但 P2 钉 1 守的是 helpers 而非消费点本身——若未来有人改回 else→"oc"，钉子不直接拦截。低风险（AGENTS 表单一事实源 + 互钉把守漂移），可在 P3/P4 顺手统一为 `specOf` 单次查表。
3. Coder 申报的 dev 冒烟（启动/设置页两卡 doctor/Token 页/needs_node_probe 路径）已按用户裁定免重复实机目验，右键菜单/气泡留待交付时用户自然目验——与任务约定一致。
