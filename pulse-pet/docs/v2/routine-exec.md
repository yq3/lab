# 例程 exec 批次：执行历史快照化 + 多 agent 模板注册表 + 执行上下文增补

> 日期：2026-08-30 ｜ 状态：Part A **已实施（cargo 377+3 / npm 448 / tsc 0，实施记录见 §2 末）**；Part B **已实施（cargo 378+3 / npm 463 / tsc 0，实施记录见 §3.7；填充恒可点修订经用户目验驱动）**；Part C **已实施（cargo 379+4 ignored / npm 463 / tsc 0 + 真实 v4 库副本 migrate 演练 ok，实施记录见 §4.7）**。Part A/C 用户目验待办；三 Part 经 tester 独立复核（PASS WITH NOTES，§4.7 末）与 committer 审查（APPROVED WITH NITS，P2/P3 已处置）。

## 1. 文档定位与迁移说明

- 本文档是例程 exec 侧增强批次的完整留痕（仿 agent-registry.md / pet-size.md 模式），含三部分：
  - **Part A（§2）**：执行历史批次——分页 50→15 + 快照化三列 + 分页控件移位。原为 `V2-OPEN-ITEMS.md` §二十五，2026-08-30 整体迁入（该处保留指针条目防断链）；**审查/复核记录中的「:767 / :778」等行号以迁移前的 V2-OPEN-ITEMS.md 为准**。
  - **Part B（§3）**：例程模板注册表——多 agent 例程模板（OpenCode / Claude Code / codex…）的 UI 组件方案，已实施（2026-08-30，含填充恒可点修订）。
  - **Part C（§4）**：执行上下文增补批次——cwd 快照列 + `executed_command` 删列 + 命令单展示（含 Part A「三字段」裁定的演进），已实施（2026-08-30，含真实 v4 库副本迁移演练）。
- 同会话另一答疑产物（exec 的 cwd 缺省行为）备查于文末附录。

---

## 2. Part A：执行历史批次（原 V2-OPEN-ITEMS §二十五，2026-08-30 方案定稿，**已实施同日**——见本节末实施记录）

> 来源：用户会话（2026-08-30）——问「例程-执行历史有做分页吗」起逐项裁定收敛为本批次。分页功能本身齐全（Rust COUNT + LIMIT/OFFSET 50 条/页、命令 `action_logs_list`、前端页码 + 上一页/下一页 + 按例程过滤，TC-M4-16），但裁定改大小、移位置，并补齐快照能力。

**背景与问题**：

1. **分页大小写死 50 且散在两处**：`reminder_scheduler.rs` 中 `list_action_logs` 局部 `const PAGE_SIZE: i64 = 50`（真 LIMIT）与 `pub const ACTION_LOG_PAGE_SIZE: i64 = 50`（命令返回 `page_size`，前端 `Tasks.tsx` 据此算总页数）两份独立维护——只改其一即 page_size 与 LIMIT 失配、总页数算错；50 系 V2-DESIGN §4.7 裁定口径；
2. **分页控件位置**：「第 x/y 页 · 共 N 条」+ 上一页/下一页现居顶部 controls 行（与筛选下拉同排），用户裁定移至执行历史块**底部居中**，筛选下拉原位不动；
3. **历史行无任务名**：行内只有 时间 / 徽标 / summary / 状态；
4. **快照缺失（本批核心）**：`action_logs` 不存命令——展开区只有 output_tail；「存储的任务命令 vs 实际执行的任务命令」均无从回查；且规则被改名、改命令、删除后，已有历史随之失据。执行历史的语义 = **执行时点的任务内容快照**——初版方案曾用「reminder_id 关联当前配置」（前端 rules 映射 / SQL LEFT JOIN），被用户否决（「任务名可能会改或删，但执行历史需要看到当时的内容」）。

**方案（用户逐项裁定，2026-08-30）**：

1. **分页 50→15 + 常量收归一处**：`ACTION_LOG_PAGE_SIZE` 值改 15；删 `list_action_logs` 局部 `PAGE_SIZE`，改用统一常量（单一事实源）；注释/文档同步；
2. **分页控件移位**：`Tasks.tsx` controls 行只剩筛选下拉；列表 `</ul>` 后新增 `.task-history-pagination` 容器装页码文案 + 上一页/下一页，CSS `justify-content: center`；
3. **action_logs 新增 3 快照列（迁移 004）**——用户明确「至少应增加 3 个字段」且三字段构成为任务名、配置的任务命令、实际执行的任务命令：

   | 列 | 写入时机 | 语义 |
   |---|---|---|
   | `label` | running / skipped 插入 | 当时的任务名（命名沿用来源列 `reminders.label` 同名——用户裁定，快照与来源字段对位） |
   | `command` | 同上 | 当时配置的任务命令（`action_params.command`） |
   | `executed_command` | 仅 running | 实际执行（spawn 传给 sh 的命令串） |

4. **前端展示全读快照，不关联 rules**：行内徽标后加任务名（`log.label`）；展开区两块等宽 `<pre>`：「存储命令（当时配置）」= `log.command`、「实际执行命令」= `log.executed_command`。

**口径**：

- `executed_command` 与 `command` 当前实现恒同值（同一解析结果既配置又执行）——分列是语义显式（配置 vs 实际），防未来执行器变换命令时快照失真，注释钉明；**恒同值在解析失败边缘也成立**：提取助手与 `run_task` 完全同源（`from_str().ok()` → `{}` 兜底 → 取 `command` as_str），解析不出命令时 `command`/`executed_command` 写 **NULL 而非空串**（空串会被展示层渲染成空命令块，无法与「配置命令为空」区分——复核 P3-1'）；**展示规则统一走下行判定，`command` 列 NULL 恒「未记录」**（审查 P2-2 + 复核 P2-1'）；
- **快照时机 = 派发/判定时刻**：`PendingExec.rule` 是派发时刻克隆，排队期间规则被改名/改命令 → 快照取派发时刻配置，与实际执行（用的是同一克隆）天然一致——口径注明防将来被当 bug（审查 P3-4）；
- **skipped**：记 label + command（当时配置），`executed_command` 恒 NULL——展示「—（未执行）」；
- **迁移前旧存量行**：三列 NULL——任务名/命令展示「—（未记录）」；**`executed_command` 为 NULL 时的展示判定（统一规则，同时覆盖旧 skipped 行与解析失败新行）**：`label` 非空（新行——**含解析失败行，其确实未 spawn，「未执行」语义成立**）→「—（未执行）」；`label` 为 NULL（旧行）→「—（未记录）」（审查 P2-3 + 复核 P2-1'，反向同样防住：若实现成「NULL 即未执行」，旧 ok/failed 行会错显）；
- i18n 新键 ×4 zh/en 成对：`tasks.history.storedCommand` / `executedCommand` / `unrecorded` / `notExecuted`（键完备性测试自动把守）；CSS 新增 `.task-history-pagination`（flex 居中）+ `.task-history-name`（限宽 ellipsis）；
- 仅执行历史分页受影响；token / todo 列表无分页不波及。

**实施清单（文件级，实施时照单）**：

1. `src-tauri/migrations/004-action-logs-snapshot.sql`（新）：3 条 ALTER TABLE ADD COLUMN（SQLite 一次一列）；
2. `src-tauri/src/db.rs`：新 const + `MIGRATIONS` 加 `(4, …)` + `SCHEMA_VERSION` 3→4 + `migrate()` 补 `if version < 4`（**手写展开非循环，const 表与展开块两处都要动**）+ 迁移测试补三列存在断言**与「004 后旧 action_logs 行三列值为 NULL」断言（「未记录」口径的数据基础，仅断言列存在不够，审查 P3-1）**；
3. `src-tauri/src/reminder_scheduler.rs`：`ActionLog` +3 字段（`Option<String>`，兼容旧行 NULL）；`insert_action_log_running` +3 参（**`label: &str` / `command: Option<&str>` / `executed_command: Option<&str>`**——类型显式钉明，审查 P2-2 后半）、`insert_action_log_skipped` +2 参（`label: &str` / `command: Option<&str>`）；**skipped 数据管线（审查 P1-1 修订）**：insert 调用点 :1371 在 `persist_skipped` 内、循环变量是 `SkippedRule`（:531-538，**无 `action_params` 字段**，原方案「手上有规则对象」失实）——`SkippedRule` 加 `action_params: Option<String>` 字段，在 `collect_due` 两处构造点（暂停分支 :603 / 超窗分支 :646，两处均有 `let rule = rs.rule.clone()` 在手）以 `rule.action_params.clone()` 填充，`persist_skipped` 经同源助手解析出 command 传入 insert（取**判定时刻**配置，与 running 的派发时刻快照语义对齐）；`list_action_logs` SELECT 三列 + 统一 `ACTION_LOG_PAGE_SIZE`（15）；测试：分页断言改 15/15/tail-31/15 **并新增第 5 页断言（`page5.len()==1` 且末条 tail-0——61 条 5 页，tail-0 落末页，直接照改会丢「最早一条位于末页末尾」覆盖，审查 P2-1）**、孤儿快照保留（删规则后三快照仍可读——正是本批场景）、skipped 快照、既有 insert 调用点补参（测试 :3728/:3738/:3759/:3779/:3802）；
4. `src-tauri/src/action_exec.rs`：`start_exec_run` 插日志前提取 label + `action_params.command`（小助手函数，**与 `run_task` 的 params 解析完全同源**；**提为 pub 共用——`start_exec_run`（本文件）与 `persist_skipped`（reminder_scheduler.rs）两调用方**）→ 传入 insert（executed_command 同值；解析不出命令 → 写 NULL，见口径）；测试调用点 :1555 补参；
5. `src/lib/reminders.ts`：`ActionLog` 接口 +3 字段；doc 注释 15 条/页；
6. `src/panel/Tasks.tsx`：controls 行收缩 + 底部分页容器 + 行内任务名 + 展开双命令块；文件头注释同步；
7. `src/lib/i18n.ts`：4 键 ×zh/en；`src/styles/global.css`：`.task-history-pagination`（`display:flex` + `justify-content:center` + `align-items:center` + gap + `margin-top` 与列表分隔——只写 justify-content 不成活，审查 P3-3）、`.task-history-name`（`flex:none` + max-width + ellipsis——防被 `.task-history-summary` 的 `flex:1; min-width:160px` 挤没，后者 min-width 视实际调小）；
8. 文档收尾：V2-DESIGN §4.7 执行历史区 bullet 重写（15 条/页 + 三快照列 + 行内任务名 + 双命令）+ 修订注记（2026-08-30）；**§4.5 执行链两处（:1067 insert 行 / :1076 update 行）补三快照列描述、§4.8 变更汇总表加 004 行（`migrations/004` 三快照列、SCHEMA_VERSION=4）**（审查 P2-4——不补则文档与实施失实）；V2-TEST-CASES TC-M4-16 同步（预期 2 补行内任务名、预期 3 补双命令块、预期 4 补三快照保留 + skipped「未执行」+ 旧行「未记录」）（**§4.2 CREATE TABLE 块 / TC-M4-01 预期 2 顺带加 004 修订注记，不强制改写正文——复核 P3-2'**）；
9. 验证：`cargo test`（基线 375 passed + 3 ignored）/ `npm test`（448）/ `npx tsc --noEmit`（**基线数字为实施前参考值，新增迁移断言/快照钉后按实际增长，实施记录以新基线回写**，审查 P3-5）；目验 = 分页底部居中、行内快照任务名、双命令、删规则/改名/改命令后历史不变、skipped「—（未执行）」、旧存量「—（未记录）」。

**Reviewer 审查（2026-08-30，reviewer subagent）**：**CHANGES REQUIRED → 已全部修订入上方方案**（1 P1 + 4 P2 + 6 P3）。P1-1 skipped 快照数据源缺失（`SkippedRule` 无 `action_params`，原清单「调用点手上有规则对象」失实）→ 清单 3 补数据管线；P2-1 末页 tail-0 断言保留 → 清单 3；P2-2 解析失败边缘 NULL 语义 + 助手同源钉 → 口径 + 清单 4；P2-3 旧 skipped 行渲染优先级 → 口径；P2-4 文档收尾扩 §4.5/§4.8/TC-M4-16 → 清单 8。P3 处置：P3-1 迁移 NULL 断言（清单 2）、P3-3 CSS 细节（清单 7）、P3-4 派发时刻口径、P3-5 基线注记均已纳入；P3-2 §4.2 CREATE TABLE / TC-M4-01 属迁移 003 历史范围文档，实施时顺带加 004 修订注记（不强制改写正文）。两澄清项采纳 reviewer 建议并已钉入口径：skipped command 取**判定时刻**配置；解析失败写 **NULL**。**P3-6 悬置待用户裁定**：空历史（total=0）时底部分页仍显示「第 1/1 页 · 共 0 条」+ 禁用按钮（与现顶部行为一致、非回归）——可选优化为隐藏分页容器，缺省保持现状。审查核实背书（记录备查）：insert 全仓 prod 调用点确为 2 处无漏报、测试 6 处已列全；R5 启动清理与 Exit 处置只 UPDATE status/summary 确认无需动三快照列；`reminder://trigger` 载荷与气泡链路 notify-only 不受影响；`action_logs_list` 唯一消费者 Tasks.tsx、`page_size` 只喂 totalPages、15 自适应无回归；迁移写法与 003 同构（3 条独立 ALTER + 事务化 migrate_one + 编译期断言兜底）；全仓「50 条/页」字面 8 处已全覆盖无遗漏。

**复核前自审（2026-08-30）**：对照 reviewer 原文逐条复核落回情况——P1-1 / P2-1 / P2-3 / P2-4 / P3-1~P3-5 均确认落回；发现 **P2-2 后半句（insert 参数类型未规定）首轮未落全** → 清单 3 已补显式类型（`label: &str` / `command: Option<&str>` / `executed_command: Option<&str>`，skipped 同理）；P1-1 同源助手钉明 pub 共用落点（清单 4，`start_exec_run` 与 `persist_skipped` 两调用方）。Reviewer 引用事实亲验：`SkippedRule` :531-538 确无 `action_params`、全仓恰两处构造点（:603/:646，均有 `rule.clone()` 在手）、无测试字面量构造不受加字段波及、`persist_skipped` insert 在 :1371、V2-DESIGN §4.5 insert/update 行 :1067/:1076 属实。

**Reviewer 复核（2026-08-30，同 subagent 续审）**：**APPROVED WITH NITS，可进入实施**——上轮 13 条意见（1 P1 + 4 P2 + 6 P3 + 2 澄清）逐条确认落回且可照单实施；自审块事实声称抽查全部属实（SkippedRule 恰两处构造点且无测试字面量、§4.5 行号、「50 条/页」全仓恰 8 处字面全在清单覆盖内）。残余 3 条已当场修订入文：P2-1' 解析失败新行的 executed 展示在口径 :767/:770 间有歧义 → 统一为「`command` 列 NULL 恒未记录；`executed_command` NULL 且 label 非空（含解析失败行，确实未 spawn）→ 未执行；label 亦 NULL → 未记录」；P3-1'「空串语义」括号语焉不详 → 改写为展示层区分理由；P3-2' P3-2 处置未入实施清单 → 清单 8 已补。P3-6（空历史隐藏分页容器）仍悬置待用户裁定，缺省保持现状。

**实施记录（2026-08-30）**：已实施（TDD 三步走，每步先红后绿，证据为命令输出）。① 迁移：`migrations/004-action-logs-snapshot.sql`（3 条 ALTER）+ `db.rs` 四处（`M4B_SQL` const / `MIGRATIONS` 行 / `SCHEMA_VERSION=4` / `migrate()` 展开块）+ 新钉 `m4b_migration_adds_snapshot_columns_old_rows_null`（红 `action_logs 缺列 label` → 绿）；附带更新 `m4_migration_idempotent_v2_to_v3_and_skip_on_v3` → `m4_migration_idempotent_steps_and_skip_on_current`（「v3 停 3」断言随版本升 4 过期，v3 亦升 4）。② 分页：`ACTION_LOG_PAGE_SIZE` 50→15、删 `list_action_logs` 局部 `PAGE_SIZE` 收归单点；分页断言 15/15/tail-31 + 新增第 5 页断言（`page5.len()==1`、末条 tail-0）（红 `15 != 50` → 绿）。③ 快照管线：`ActionLog` +3 字段；`insert_action_log_running` +3 参 / `insert_action_log_skipped` +2 参（显式类型照方案）；`SkippedRule` + `action_params` + `collect_due` 两构造点填充；`persist_skipped` 经 `command_from_params` 提取（判定时刻配置）；`list_action_logs` SELECT 三列；`action_exec.rs` 新 pub 助手 `command_from_params`（与 `run_task` 同源）+ `start_exec_run` 快照传参 + 新钉 `command_from_params_same_source_parse`（红 E0061/E0425/E0609 → 绿）；快照断言含孤儿悬空可读（三列）与 skipped「executed 恒 None」。④ 前端：`reminders.ts` `ActionLog` +3 字段 + doc 15 条/页；`i18n.ts` 4 新键 zh/en 成对；`global.css` `.task-history-pagination`（flex 居中）+ `.task-history-name`（限宽 ellipsis + `.is-unrecorded` faint）；`Tasks.tsx` controls 只留筛选下拉、底部分页容器、行内任务名、展开双命令块（渲染判定照口径：`command` NULL 恒未记录；`executed_command` NULL 时 label 非空→未执行 / label NULL→未记录）+ 文件头注释同步。⑤ 文档：V2-DESIGN §4.2 004 修订注 / §4.5 insert 行补快照 + update 行注记 / §4.7 bullet 重写 + ⑦⑧⑨ 修订注 / §4.8 表 004 行；V2-TEST-CASES TC-M4-16 预期 1-5 更新 + TC-M4-01 预期 2 修订注；本记录。**验证证据**：`cargo test` **377 passed + 3 ignored**（基线 375+3，+2 新钉）/ `npm test` **448 passed**（32 files，基线持平）/ `npx tsc --noEmit` **exit 0**。**实施偏差**：无（照清单落）。**用户目验（待办）**：分页底部居中、行内任务名随快照、点开双命令、删规则/改名/改命令后历史不变、skipped「—（未执行）」、旧存量「—（未记录）」；P3-6（空历史分页显示）维持现状未动（悬置裁定）。

> **修订（2026-08-30，Part C 演进——本 Part 的 executed_command 相关表述以 Part C 为准）**：快照字段集合演进为 任务名/命令/工作目录——① §2 方案 3 表格的 `executed_command` 行与方案 4 的「实际执行命令」块：005 起**删列**（命令串逐字节原样传给 sh/powershell、目录经进程属性生效，实录与配置**恒同值**，双展示冗余合并为「命令（当时）」单块）；② 口径 bullet 1（恒同值）/ bullet 3（skipped 恒 NULL——skipped 行「未执行」语义改由状态色点/文案承载）/ bullet 4（executed NULL 展示判定）：随列删除不再适用；③ 实施清单 3-4 与下方实施记录中 executed_command 的 insert/SELECT/断言描述：005 起参数位换 `cwd`（当时工作目录快照）。历史审查/复核记录不改写（记录当时的事实判断，均成立）。

---

## 3. Part B：例程模板注册表（2026-08-30 方案定稿；已过 reviewer 审查与复核（NITS → 修订 → APPROVED），**已实施同日——见 §3.7 实施记录**）

> 来源：同日用户会话——「目前只有 opencode 例程，如果后续还要加 Claude 例程、codex 例程等等，UI 组件如何设计？」。讨论稿经用户四项裁定（§3.2）当日升级为定稿。

### 3.1 现状与问题

- `.task-tpl-block`（Tasks.tsx）= 标题 + hint + 指令输入框 + `--auto` checkbox + 一键填充按钮，**OpenCode 单模板硬编码**；
- `buildOpencodeCommand` 写死在 reminders.ts（§4.6「执行层不感知 opencode」——模板是纯填表辅助）；
- 表单状态 `tplInstruction` / `tplAuto` 两个 opencode 专属字段；`opencode_auto` 持久化进 `action_params`（Rust validate 有布尔校验，action_exec.rs :216-220）；编辑回填 `execFromParams` 同样 opencode 专属；
- **既有隐患（本批顺带修复，2026-08-30 设计期确认）**：`tplInstruction` 不持久化（编辑回填恒空串），而 `onLabelInput`（Tasks.tsx :417-431）在 command 含 `opencode run` 时以 `x.tplInstruction` 重拼——**编辑已有例程改任务名 → 原指令被空指令覆盖**。

### 3.2 用户裁定（2026-08-30，四项主裁定 + 次要口径）

| # | 裁定点 | 裁定 |
|---|---|---|
| 1 | Claude 模板无人值守 flag | **提供** `--dangerously-skip-permissions` 勾选项——默认不勾 + 危险色警示（同 `--auto` 口径；不勾时 `-p` 非交互模式权限请求默认拒绝，带权限的操作会被拒） |
| 2 | Claude 例程会话 Token 页辨识 | **接受已知边界**——⚡ 徽标匹配机制 = `isRoutineSession` 的 `title.startsWith("pulsepet 例程:")` 前缀匹配（TokenStats.tsx :77-79），CC 无 `--title` 通道且 title 派生自 transcript 首条 user 行截断 60 字符（transcript.rs :262-271 / :328-345），前缀永不命中（审查 P2-1 修订：原引 token-stats.ts :31 系接口字段注释，不支撑「title 恒 null」）；by-session 视图仍显示 CC 自动派生的指令首行 title，辨识线索充分；CC hooks / token 统计链路照常（agent 层免费）；**落地为零改动**（不做补偿代码、不伪造标题） |
| 3 | flag 持久化结构 | **泛化 `tpl_agent` + `tpl_flags`**——保存一律写新格式，读侧兼容旧 `opencode_auto`；Rust validate 补两条宽松校验，未来加 flag 零 Rust 改动 |
| 4 | 实施安排 | **与 Part A 分开实施**——独立批次，先过 reviewer 审查，再等用户批准 |

次要口径（设计者定，有异议可翻）：chips 单选交互；新建默认预选 OpenCode（视觉零变化起步）；注册表独立文件 `routine-templates.ts`（不并入 agents.ts——模板能力与 agent 注册正交，有 headless run CLI 才有模板行，不自动从 AGENTS 派生）；i18n 键 camelCase（`tasks.tpl.opencode.*` / `tasks.tpl.claudeCode.*`，与 `token.agent.claudeCode` 风格锁步）；**重拼判定永远看 command 是否 `matches()`，不看 chips 选中态**（手写命令不被重拼）；chips 切换时 `tplFlags` 重置为该模板全 false（danger flag 不跨模板携带，command 不因切换而变——审查 P3-6）；**填充按钮 = 动词键 `tasks.tpl.fill`，chips 文案复用 agents.ts `labelKey`（无需 per-agent title 键，审查 P3-9）**；~~指令空时填充按钮禁用~~（**修订 2026-08-30 用户目验反馈**：恢复**恒可点**——空指令也填充骨架命令，随后输入指令自动重拼；保留高级用户「先填充骨架、后手改 command」的口子，推翻审查 P3-5 处置）；flag 的 hint 键 = `i18nKey + "Hint"` 派生（auto/autoHint 既有形态，审查 P3-7）。

### 3.3 方案

**注册表**（`src/lib/routine-templates.ts`，新文件）：

```ts
interface RoutineFlagSpec { key: string; i18nKey: string; danger: boolean }
interface RoutineTemplateSpec {
  agentId: string   // 展示名复用 agents.ts 的 labelKey（chips 文案）
  matches: (command: string) => boolean   // 重拼启发式 + 编辑回填反推选中态
  build: (taskName: string, instruction: string, flags: Record<string, boolean>) => string
  flags: RoutineFlagSpec[]
}
```

- **opencode 行**：`buildOpencodeCommand` 自 reminders.ts 迁入（`shellQuote` 留在 reminders.ts 供两行共用）；`matches` = `startsWith("opencode run ")`；flag `auto`（danger）；
- **claude-code 行**：`claude -p '<指令>' [--dangerously-skip-permissions]`（任务名只进 PulsePet label 不进命令——CC 无 `--title`）；`matches` = `startsWith("claude -p ")`；flag `skipPerms`（danger，默认不勾）；**CLI 细节（无人值守 flag 有无更优形态、输出格式）接入时以 `claude --help` 实测为准，UI 结构不依赖**；
- 加 codex 例程 = 注册表一行 + build + i18n 键对，**UI 零改动**；
- 注册表注释钉明 matches 边界形态：裸 `opencode run`（无尾空格）、`claude --print`（长形式）不匹配 startsWith 模式——手写这两形态不被重拼，有意语义（审查 P3-4）；已核 build 输出对自身 matches 幂等（`opencode run --title…` / `claude -p '…'` 均以对应前缀开头），重拼稳定；
- flag 值仅布尔（审查 P3-3 备忘：未来带值 flag 如 `--model xxx` 需结构升级，且与 Rust「所有值布尔」校验两处锁步改）。

**UI**（`task-tpl-block` 泛化）：块标题「例程模板」（`tasks.tpl.blockTitle`）+ chips 单选（按注册表序，默认预选 OpenCode）+ 共享指令框 + 当前模板 flags 行（danger checkbox + 警示文案）+ 一键填充按钮（按选中模板 build）。

**状态与持久化**：`ExecFormState.tplAuto` → `tplFlags: Record<string, boolean>` + 新增 `tplAgent: string`；`action_params` 写 `tpl_agent` + `tpl_flags`（保存一律新格式）；`execFromParams` 读兼容兜底全集（审查 P2-4，与单测钉锁步）：`tpl_agent` 缺失但 `opencode_auto === true` → opencode + `{auto: true}`；`tpl_agent` 存在但 `tpl_flags` 缺失/非法 → flags `{}`（**`tpl_agent` 存在时 `opencode_auto` 忽略**——新格式恒不同时写出，并存仅手改数据，复核 P3-1'）；`tpl_agent` 为未知值（未来版本写入后降级读）→ 回落默认预选 opencode、flags 照常解析、command 不动（重拼只看 matches）；`opencode_auto === false` 或均无 → 默认预选 opencode、flags 空。**`execParamsJson` / `execFromParams` 自 Tasks.tsx 迁至 reminders.ts 导出为纯函数 + 单测**（现状为组件内部函数无测试面）；**`ExecFormState` 类型随迁 reminders.ts 导出、Tasks.tsx 改 import**（防 lib→panel 反向依赖循环，审查 P2-2）。

**启发式泛化**：`includes("opencode run")` → 注册表 `matches(command)`（三处联动点：指令 onChange / flag checkbox / `onLabelInput`）；编辑回填按 `matches()` 反推恢复 `tplAgent` 选中态；`startsWith` 比 `includes` 更严（复合命令如 `cd x && opencode run …` 不再被自动重拼）——有意语义。

**顺带修复**：空指令守卫——`tplInstruction.trim()` 非空才联动重拼（编辑态改任务名不再 clobber 原 command）。

**Rust**（`action_exec.rs` validate_params，现状宽松白名单——未知键已忽略不报错）：补两条宽松校验——`tpl_flags` 若存在须为对象且所有值布尔（`null` 命中即非法，与 `opencode_auto` 现行为同款先例，审查 P3-10）、`tpl_agent` 若存在须为字符串；`opencode_auto` 旧校验保留（读兼容期间旧数据仍可过 validate）。**前端 `validateExecParams`（reminders.ts）补同规则预检**（v1「Rust 权威 + 前端同规则预检」既有模式，审查 P3-1）。执行层不感知 agent 原则不变（模板纯填表辅助）。

**i18n**：新键 `tasks.tpl.blockTitle` + `tasks.tpl.fill`（按钮动词键）+ `tasks.tpl.opencode.hint/auto/autoHint` + `tasks.tpl.claudeCode.hint/skipPerms/skipPermsHint`（zh/en 成对；chips 文案复用 agents.ts `labelKey`，**无需 per-agent title 键**——审查 P3-9 简化）；旧键 `tasks.tpl.title/hint/auto/autoHint` 改名空间后**清退**——zh/en 键集合一致由完备性测试把守，**旧键消费者清退由同批 Tasks.tsx 改造完成**（已核消费者全在 Tasks.tsx :632/:633/:676/:679/:683；完备性测试不发现「键已删代码仍引用」，`t()` 缺键回退键名——审查 P3-2 表述修正）；`tasks.tpl.smartQuoteWarn/Fix` 不动（挂 command 框，与模板无关）。

### 3.4 实施清单（文件级，实施时照单）

1. `src/lib/routine-templates.ts`（新）：接口 + `ROUTINE_TEMPLATES` 两行（opencode / claude-code）+ helpers（`templateOf(agentId)` / `matchOf(command)`）；`src/lib/routine-templates.test.ts`（新）：build 逐字钉（opencode 沿用 reminders.test.ts 既有断言迁移）+ matches 钉（**三正向**：`opencode run …`→opencode / `claude -p …`→claude-code / `echo hi`→无模板，matchOf helper 钉——审查 P3-11；**负例**：`cd x && opencode run …` 复合命令不匹配）+ claude 拼装（skipPerms 两态）；
2. `src/lib/reminders.ts`：`buildOpencodeCommand` 迁出；新增导出 `execParamsJson` / `execFromParams`（新格式 + 旧 `opencode_auto` 读兼容 + `matches()` 反推 + **兜底全集四态单测钉**，审查 P2-4）+ **`ExecFormState` 类型随迁导出**（Tasks.tsx 改 import，审查 P2-2）+ `validateExecParams` 补 `tpl_agent`/`tpl_flags` 同规则预检（审查 P3-1）；`reminders.test.ts` 模板钉随迁 + 兼容钉（旧键数据 → opencode + `{auto:true}`）；
3. `src/panel/Tasks.tsx`：模板块泛化（chips / 共享指令框 / 动态 flags 行 / 填充按钮按选中模板，**指令空时禁用**——审查 P3-5）；`ExecFormState` 泛化（`tplFlags` / `tplAgent`，类型改从 reminders 导入）；三处联动点启发式换 `matches()` + 空指令守卫；import 改道；**文件头注释与「opencode 例程模板块」字样同步**（审查 P3-8）；
4. `src/lib/i18n.ts`：新键 zh/en 成对 + 旧键清退（消费者清退由本批清单 3 完成，完备性测试把守 zh/en 集合一致）；
5. `src/styles/global.css`：chips 行样式（复用 `seg` 系加选中态类或新类，实施时定）；
6. `src-tauri/src/action_exec.rs`：validate_params 两条宽松校验 + 单测（`tpl_flags` 非对象 / 值非布尔 / **`null` 命中拒绝**（审查 P3-10）/ `tpl_agent` 非字符串 → 拒绝；合法 → 通过；旧 `opencode_auto` 校验保留钉）；
7. 文档收尾：本节实施记录回写；**V2-DESIGN §4.6 重写为多模板注册表描述 + §4.7 表单行「opencode 模板块」字样同步 + TC-M4-08 同步为多模板 / 追加 claude 例程实机项**（审查 P2-3）；`agent-onboarding.md` checklist 补「例程模板行」一项（§3.5）+ **reminders.ts / reminder_scheduler.rs 的 action_params 形状注释同步**（审查 P3-8）；V2-OPEN-ITEMS §二十五指针同步 Part B 状态；
8. 验证：`cargo test` / `npm test` / `npx tsc --noEmit`；目验 = chips 切换两模板、claude 填充与 skipPerms 警示、编辑回填选中态恢复、旧 `opencode_auto` 例程编辑保存后转新格式、空指令守卫（编辑改任务名不再覆盖原指令）、**负例：手写命令例程编辑 → chips 回落默认 OpenCode 且 command 不被重拼**（「重拼不看选中态」可见行为验证）。**本批基于 Part A 落地后基线实施**（两批同改 Tasks.tsx / reminders.ts / action_exec.rs 但区域不相交——A：历史区/ActionLog/insert；B：模板块/表单态/validate_params，按函数名定位可 rebase）。

### 3.5 与 agent-onboarding 的关系

Part B 落地后，「例程模板行」成为新 agent 接入 checklist 的一项（手册 `agent-onboarding.md` 补一行：有 headless run CLI 的 agent 在 routine-templates.ts 加一行 + i18n 键对）；未落地时不妨碍接 agent——现状模板块只是不覆盖新 agent，无功能性断裂。

### 3.6 审查记录

**Reviewer 审查（2026-08-30，reviewer subagent）**：**APPROVED WITH NITS**——§3.1 clobber 隐患论断（`execFromParams` :147 恒空 tplInstruction + `onLabelInput` :417-431 空指令重拼）、三处联动启发式（:420/:646/:665）、持久化兼容方向、实施清单覆盖面经逐条追码核实**全部属实，无 P1**。4 条 P2 已当场修订入文：P2-1 裁定 2 依据引用失实（原引 token-stats.ts :31 系接口字段注释；真实机制 = `isRoutineSession` 前缀匹配 × CC title 派生自 transcript 首条 user 行，by-session 视图实际显示指令首行 title）→ §3.2 改引正确依据并修正辨识线索表述；P2-2 `ExecFormState` 类型随迁 reminders.ts（防 lib→panel 反向依赖循环）→ §3.3 / 清单 2；P2-3 文档收尾漏 V2-DESIGN §4.6/§4.7 + TC-M4-08 → 清单 7；P2-4 读兼容枚举不全 → 兜底全集四态入 §3.3 + 单测钉。P3 处置（11 条）：P3-1 前端同规则预检、P3-2 完备性测试表述修正（不发现「键已删代码仍引用」）、P3-4 matches 边界形态注释钉（裸 `opencode run`/`claude --print` 不匹配，幂等已核）、P3-5 指令空禁用填充按钮、P3-6 chips 切换重置 flags、P3-7 hint 键 `i18nKey+"Hint"` 派生、P3-8 注释字样同步入清单、P3-9 按钮动词键 `tasks.tpl.fill` + chips 复用 `labelKey`（**连带简化：无需 per-agent title 键**）、P3-10 `tpl_flags: null` 拒绝、P3-11 matches 三正向钉——均已纳入方案；P3-3 布尔值型升级余地记备忘。附注已纳：本批基于 Part A 落地后基线实施；**claude CLI 细节实施时先行 `claude --help` 实测再钉 build 逐字测试，勿按方案字面写死**；裁定 2 落地为零改动（不做补偿代码、不伪造标题）。

**Reviewer 复核（2026-08-30，同 subagent 续审）**：**APPROVED**——4 条 P2 逐条落回无歧义（P2-1 行号亲验 token_stats.rs :735 / transcript.rs :262-271；P2-4 兜底四态互斥完备、与「重拼只看 matches」原则无冲突）、11 条 P3 处置全部属实（P3-9 简化后新键 8 枚 ×zh/en 键集自洽亲验：chips 走既有 `token.agent.*`、flag label/hint 由 `i18nKey`/`i18nKey+"Hint"` 覆盖，无遗漏无冗余）、§3.6 审查记录声称与正文逐条吻合、修订未引入新矛盾。残余 1 条 P3-1'（兜底四态未显式钉「tpl_agent 存在时 opencode_auto 忽略」优先级，单测易漏并存用例）已当场补入 §3.3。**判定：方案可等用户批准实施。**

### 3.7 实施记录（2026-08-30）

已实施（TDD 先红后绿全程；前置 = `claude --help` 实测确认 `-p, --print` 与 `--dangerously-skip-permissions` 存在，claude 二进制在 `~/.npm-global/bin`——§二十四 PATH 增广目录内，GUI 启动可达）。① `src/lib/routine-templates.ts`（新）：`shellQuote` 迁入 + `ROUTINE_TEMPLATES` 两行（opencode / claude-code）+ `templateOf`/`matchOf`/`tplHintKey`；`routine-templates.test.ts`（新）**11 钉**（红 `Cannot find module` → 绿；含 build 逐字迁移钉、matches 三正向 + 复合命令/裸命令/长形式负例 + 幂等、skipPerms 两态、hint 键派生）。② `reminders.ts`：新增导出 `ExecFormState`/`emptyExecState`/`execParamsJson`（新格式 `tpl_agent`+`tpl_flags`）/`execFromParams`（兜底四态 + matchOf 反推 + 旧 `opencode_auto` 读兼容）+ `validateExecParams` 补两键预检（i18n 校验键 2×zh/en）；`buildOpencodeCommand`/本地 `shellQuote` 清退（shellQuote 迁至 routine-templates，防循环依赖——reminders 单向 import routine-templates）；reminders.test.ts 新增 **5 测**（红导出缺失 → 绿）+ §4.6 旧 build 钉迁移收尾。③ `action_exec.rs`：validate_params 两条宽松校验（`null` 命中即非法，同 opencode_auto 先例）+ `exec_validate_tpl_agent_flags_lenient_checks` 钉（红 `tpl_flags = "x"` 未拒 → 绿）。④ `Tasks.tsx`：模板块泛化（chips 单选复用 `seg`+`active` / 共享指令框 / 声明式 flags 行 danger 警示 / 填充按钮指令空禁用）、三处联动点启发式换 `matchOf` + **空指令守卫（顺带修复编辑改任务名空指令 clobber 隐患）**、本地类型与序列化函数删除改 import（防 lib→panel 反向依赖）；i18n 新键 **8×zh/en**（blockTitle/fill/opencode.hint·auto·autoHint/claudeCode.hint·skipPerms·skipPermsHint）+ 旧键 4×2 清退（消费者全在 Tasks.tsx 同批改造）；CSS `.task-tpl-chips` / `.seg.tpl-chip.active`。⑤ 文档：V2-DESIGN §4.6 重写（多模板注册表）+ §4.7 ⑩ 修订注 + 表单行字样同步；TC-M4-08 泛化重写；agent-onboarding checklist 补「例程模板行」；reminders.ts / reminder_scheduler.rs 的 action_params 形状注释同步；本记录。**验证证据**：`cargo test` **378 passed + 3 ignored**（377+1 新钉）/ `npm test` **463 passed**（33 files；448 基线 −2 迁移 +11 注册表 +5 持久化 +1 重包）/ `npx tsc --noEmit` **exit 0**。**实施偏差（2，均已钉）**：① `tplHintKey` 助手（hint 键 kebab→camel 派生）为实施时补的小函数——§3.2「hint 键派生」口径的实现形态，含测试钉；② 中途一处编辑事故（误删 `onceToLocalInput`）当场发现修复，最终 tsc 0 背书。**用户目验（待办）**：chips 切换两模板、claude 填充与 skipPerms 警示、编辑回填选中态恢复、旧 `opencode_auto` 例程编辑保存后转新格式、空指令守卫、负例（手写命令编辑回落默认 OpenCode 且 command 不被重拼）。

**修订（2026-08-30，用户目验反馈）**：一键填充按钮恢复**恒可点**（删 `disabled` + handler 空指令守卫，Tasks.tsx 两处）——实施时采纳的审查 P3-5「指令空禁用」处置被用户推翻：禁用且无提示的静默无响应改变旧工作流，且堵死高级用户「先填充骨架、后手改 command」的口子。空指令填充拼出骨架命令（`… ''`），输入指令后经 textarea 联动自动重拼补齐（该守卫保留）；`onLabelInput` 空指令守卫（编辑态 clobber 防护）不受影响保留。验证：tsc 0 / npm test 463 原样（无测试钉禁用态）/ 重新 `npm run tauri build`。

---

## 4. Part C：执行上下文增补——cwd 快照列 + `executed_command` 删列 + 命令单展示（2026-08-30 方案定稿；已过 reviewer 审查与复核（NITS → 修订 → APPROVED），**已实施同日——见 §4.7 实施记录**）

> 来源：用户目验 Part A 后两轮反馈（2026-08-30）——① 以为「实际执行命令」会包含 cd 到目录等上下文，经双平台机制确认后裁定补「当时执行目录」的可见性；② 确认「配置命令与执行命令恒同值」后裁定双展示冗余合并。**本 Part 含 Part A「三字段」裁定的演进**：快照字段集合变为 **任务名 / 命令 / 工作目录**。

### 4.1 背景与机制确认（双平台实测）

- 执行链实测（action_exec.rs `exec_run_with_timeout` :287-314 / `build_shell_command` :407-425）：spawn 进程 = Unix `sh -c "<命令串>"` / Windows `powershell -NoProfile -Command "<命令串>"`，**命令串逐字节原样、零拼接**；cwd 经 `current_dir`（Windows 即 CreateProcess `lpCurrentDirectory`）作为**进程属性**生效——`cd` 从未作为命令存在；PATH 经环境变量注入（仅 Unix 增广，§二十四；Windows 靠注册表 PATH）。
- 推论：`executed_command` 与 `command` **恒同值**（Part A 口径已钉，实测一致）——展开区两块同文冗余；且「当时在哪个目录执行」无处可见（cwd 未快照、未展示；从 action_params 现值读违背时点快照语义，例程改/删后失据）。

### 4.2 用户裁定（2026-08-30，三项）

| # | 裁定点 | 裁定 |
|---|---|---|
| 1 | 上下文缺口 | **补 cwd 快照列**（迁移 005 第 4 快照列；Part A「三字段」裁定演进为 任务名/命令/工作目录） |
| 2 | 命令双展示 | **合并为一块「命令（当时）」**（读 `command` 列）——恒同值下双展示冗余 |
| 3 | `executed_command` 列 | **迁移 005 顺手 `DROP COLUMN`**——004→005 存量行该列与 command 同值，删除零信息损失；表结构干净反映真实语义 |

### 4.3 方案与口径

- **迁移 005**：`ADD COLUMN cwd TEXT` + `DROP COLUMN executed_command`（一条迁移两语句，事务化 migrate_one 既有机制承载）；db.rs 四处接线照 004 模式。
- **快照写入**：`insert_action_log_running` 参数 executed 位换 `cwd: Option<&str>`、`insert_action_log_skipped` 同步（skipped 同样快照 cwd——「配置了但没跑」的完整上下文）；提取助手 `cwd_from_params`（与 `run_task` 取 cwd **同源**：`get("cwd").as_str` + `!trim().is_empty()` 过滤——缺省/空串/非字符串 → NULL，非空 → Some）；写入时机同 Part A（running = 派发时刻、skipped = 判定时刻）。
- **展示口径**（Tasks.tsx 展开区，顺序：命令 → 工作目录 → 输出尾部）：
  - 命令块：`log.command ?? 「—（未记录）」`（沿用 `tasks.history.unrecorded`，旧行 NULL）；
  - 工作目录块：`log.cwd ?? 「（未配置——继承 App 进程目录）」`（新键 `tasks.history.cwdNone`）——对今后绝大多数不填 cwd 的行是**准确文案**（未配置是正常态：进程目录继承，GUI 启动为 `/`，见文末附录）；005 前旧行无法追回当时是否配置过 cwd，此失真可忽略（该功能使用率极低，存量行极少）；
  - skipped 行「未执行」语义由状态色点 + 状态文案承载（原 `notExecuted` 占位键随 executed 列删除而清退）。
- **i18n 键变化**：删 `tasks.history.storedCommand` / `executedCommand` / `notExecuted`（−3），新增 `tasks.history.command`（命令（当时））/ `tasks.history.workdir`（工作目录（当时））/ `tasks.history.cwdNone`（+3）；zh/en 成对（完备性测试把守）。
- **Rust validate**：不涉（action_params 的 cwd 校验既有，无新键）。

### 4.4 实施清单（文件级，实施时照单）

1. `src-tauri/migrations/005-action-logs-cwd.sql`（新）：`ALTER TABLE action_logs ADD COLUMN cwd TEXT;` + `ALTER TABLE action_logs DROP COLUMN executed_command;`；`db.rs`：const M5_SQL + `MIGRATIONS` 加 `(5, …)` + `SCHEMA_VERSION` 5 + `migrate()` 补 `if version < 5` + **m4b 迁移测试改版并改名 `m4c_migration_adds_cwd_drops_executed_old_rows_null`**（v3 库 migrate 至当前后：label/command/**cwd** 存在、**executed_command 不存在**、旧行快照列全 NULL——TDD 先红「缺列 cwd / executed 仍在」→ 绿；单一体 v3→当前即可，004 步失败即整测失败，传递性覆盖中间态——审查 3.4/P3-3）+ **db.rs 两处注释随迁**（模块头 004 行后补 005 行；idempotent 测试内「SCHEMA_VERSION=4 / v3 亦升到 4」注释升 5——审查 P3-4）；
2. `src-tauri/src/reminder_scheduler.rs`：`ActionLog` −executed_command +cwd（`Option<String>`，注释同步——快照字段集合口径：任务名/命令/工作目录）；`insert_action_log_running` / `insert_action_log_skipped` 参数 executed 位换 `cwd: Option<&str>`；`list_action_logs` SELECT 调整（**`row.get(N)` 索引随列序全量重编号——删一列插一列后整体漂移，编译期不拦，靠孤儿/分页断言拦——审查附注 1**）；测试断言随迁（孤儿悬空可读变 label/command/**cwd** 三断言；skipped 换 cwd 快照断言；既有 insert 调用点补参——**测试调用点 6 处：reminder_scheduler 5 + action_exec 1，实施记录列全防漏报——审查附注 2**）；
3. `src-tauri/src/action_exec.rs`：新增 `cwd_from_params`（**提为 pub 共用**——`start_exec_run` 与 `persist_skipped` 两调用方，照 Part A `command_from_params` 口径——审查 P3-2；**只 trim 判空、存原串**——与 `run_task` 的 filter 语义严格同源（`current_dir` 拿原串，助手不得误 trim 存值）——审查 P3-1）+ 新钉（缺省/**空串/纯空白串**/非字符串 → None；**非空带首尾空白的值原样返回**）；`command_from_params` 保留不动；`start_exec_run` / `persist_skipped` 提取 label/command/cwd 传 insert；测试调用点补参；
4. `src/lib/reminders.ts`：`ActionLog` 接口 −executed_command +cwd（注释同步）；
5. `src/panel/Tasks.tsx`：展开区两块命令 → 一块「命令（当时）」+ 一块「工作目录（当时）」（渲染判定见 §4.3 口径；**`notExecuted` 三元判定逻辑整体删除，非仅换键——审查附注 4**）；文件头注释同步；
6. `src/lib/i18n.ts`：−3 +3 键 zh/en 成对；
7. 文档收尾：本 Part 实施记录回写；V2-DESIGN §4.2 追加 005 修订注（004 注之后）；§4.5 insert 行快照描述调整 + **update 行「004」tag 顺带确认/更新（审查 P3-5）**；§4.7 执行历史区 bullet（正文）按 005 调整 + **Part A 修订注 ⑧ 不改写、其后追加 ⑪ 修订注（cwd 快照 + executed_command 删列 + 命令单块，指向本 Part）——与「审查记录加注不改写」口径统一（审查 P2-2，澄清项 1 裁定：追加）**；§4.8 表加 005 行；V2-TEST-CASES TC-M4-16 预期 3 重写 + 预期 2/4 措辞随迁（快照集合 = 任务名/命令/工作目录）+ **TC-M4-01 预期 2 的 004 修订注后追加 005 注（+cwd / −executed_command、SCHEMA_VERSION=5，正文留档不动——审查 P2-3）**；V2-OPEN-ITEMS §二十五指针（**Part C 状态串翻转为已实施——审查 P3-8**）与清偿记录追加；**AGENTS.md docs/v2 地图行 Part C 状态「过审待批准实施」→「已实施 2026-08-30」、快照字段表述同步为 任务名/命令/工作目录（审查 P2-1；复核残差 1：锚点以实施时现值为准）**；**Part A §2 修订注点名范围：方案 3 表格 executed_command 行 / 方案 4 / 口径 bullet 1/3/4（恒同值 / skipped 恒 NULL / 展示判定）/ 实施清单 3-4 / 实施记录——审查/复核记录不加注（审查 P3-7；复核残差 2：bullet 2 快照时机不含 executed_command）**；
8. 验证：TDD 证据链 + `cargo test`（378+3 基线，断言随迁 + 新钉净增：m4c 改版不增不减、`cwd_from_params` +1、孤儿/skipped 随迁不增不减）/ `npm test`（463 基线，i18n −3+3 完备性原样）/ `npx tsc --noEmit`；完成后 `npm run tauri build` 重出双 bundle 供目验；**DB 级确认：对真实 v4 存量库副本（`~/Library/Application Support/com.pulsepet.app/pulsepet.db` 拷贝）跑 v4→v5 migrate 演练（现网库 executed_command 已含值，DROP 与值无关已核实，现场验一次——审查附注 3）**。

### 4.5 风险与边界

- **DROP COLUMN 支持性**：需 SQLite ≥3.35（2021-03）——**已实证**（审查实测：rusqlite `0.40.2` + bundled → libsqlite3-sys `0.38.2` 内嵌 **SQLite 3.53.2** ≥3.35；action_logs 无索引/视图/触发器引用该列，DROP 限制条件全满足；`migrate_one` 事务化 DDL 可整步回滚，A1 模式兼容）；迁移测试为二级防线（若未来升级环境不支持则以预期理由红，降级预案 =「留列停止写入」并回改本档）；
- **不可逆**：DROP 后 004→005 间存量行的 executed_command 数据消失（与 command 同值，用户已知悉零损失）；
- **未来执行器若引入命令变换**（包装/重写命令串）：届时实录能力需重新加列——YAGNI 接受，本节留痕即可。

### 4.6 审查记录

**Reviewer 审查（2026-08-30，reviewer subagent）**：**APPROVED WITH NITS**——无 P0/P1。关键事实全部实证：**DROP COLUMN 可行**（bundled SQLite 3.53.2 ≥3.35、无索引/视图/触发器引用、事务化 DDL 整步回滚与 A1 兼容；v4 为真实可达中间态，005 对含值列 DROP 无依赖）；`executed_command` 全仓引用面清点与清单比对**无漏**（Rust/TS 侧编译期强制兜底）；`cwd_from_params` 同源声称**严格成立**（run_task :282-285 filter 语义一致）；m4b 改版为单一体 v3→当前**充分**（004 步失败传递性覆盖）；i18n −3 键消费者全在 Tasks.tsx、+3 新键无撞键；skipped 行「未执行」由状态色点承载的声称属实。3 条 P2 已修订入清单 7：P2-1 AGENTS.md 地图行状态翻转、P2-2 V2-DESIGN §4.7 ⑧ 修订注处置（**澄清项 1 裁定：追加 ⑪ 不改写 ⑧**）、P2-3 TC-M4-01 预期 2 追加 005 注。P3 处置：P3-1 存原串只 trim 判空 + 空白串钉、P3-2 pub 显式钉、P3-4 db.rs 两处注释、P3-5 update 行 tag、P3-7 Part A §2 修订注点名范围、P3-8 状态串翻转均已纳入清单；P3-3 m4b 单一体维持（备查）。**澄清项 2 裁定：m4b 测试改版并改名 `m4c_migration_adds_cwd_drops_executed_old_rows_null`**（原名名不副实，照 idempotent 测试改名先例）。实施注意附注已纳清单：`row.get(N)` 索引全量重编号（编译不拦、断言拦）、6 处测试调用点实施记录列全、**真实 v4 库副本 migrate 演练（DB 级确认）**、`notExecuted` 三元判定整体删除、基线数字核对无误（378+3 / 463 / 0）。

**Reviewer 复核（2026-08-30，同 subagent 续审）**：**APPROVED**——3 P2 + 8 P3 + 2 澄清项 + 5 附注逐条确认落回；§4.5 实证改写与其核实结论一致无夸大；§4.6 记录声称与正文/原报告逐条相符无曲解；四处状态口径一致。残余 3 条 P3 措辞残差已当场修正：残差 1 清单 7 AGENTS.md 锚点改为「以实施时现值为准」+ §1 Part C bullet 同步「过审待批准」；残差 2 §2 修订注点名范围改「口径 bullet 1/3/4」；残差 3 本段补记 P3-6 已直接落实于 §4.5 正文。**判定：可等用户批准实施。**

### 4.7 实施记录（2026-08-30）

已实施（TDD 先红后绿全程，证据为命令输出）。① 迁移：`migrations/005-action-logs-cwd.sql`（+cwd / −executed_command 两语句）+ `db.rs` 四处接线（`M5_SQL` const / MIGRATIONS 行 / SCHEMA_VERSION=5 / migrate 块）+ m4b 测试改版**改名 `m4c_migration_adds_cwd_drops_executed_old_rows_null`**（红 `action_logs 缺列 cwd` → 绿）+ db.rs 两处注释随迁（模块头 005 行 + idempotent 测试注释升 5）。② 快照换列：`ActionLog` −executed_command +cwd；`insert_action_log_running` / `insert_action_log_skipped` executed 参数位换 `cwd: Option<&str>`；`list_action_logs` SELECT 换列（`row.get(5)` 位由 executed 变 cwd，其余索引未漂移——两列同位）；测试断言随迁（孤儿悬空可读 = label/command/cwd 三断言；skipped 换 cwd 快照断言；红 E0061/E0425/E0609 → 绿）。③ `cwd_from_params`（pub；只 trim 判空、存原串）+ 新钉 `cwd_from_params_trim_check_only_store_raw`（含纯空白串 → None 与带首尾空白原样返回钉）；`start_exec_run` / `persist_skipped` 提取 label/command/cwd；测试调用点补参 6 处（reminder_scheduler 5：crud 循环行/running 行/skipped 行/R2 ×2 + action_exec 1：退出竞态钉——R2 两处参数形态 None 不变仅语义随签名换位）。④ 前端：`reminders.ts` `ActionLog` −executed_command +cwd；`Tasks.tsx` 展开区双命令块 → 「命令（当时）」+「工作目录（当时）」两块（**`notExecuted` 三元判定整体删除**）+ 头注释同步；`i18n.ts` −3 键（storedCommand/executedCommand/notExecuted）+3 键（command/workdir/cwdNone），`unrecorded` 保留（command NULL 占位）。⑤ 文档：见清单 7 全落点（V2-DESIGN §4.2 005 注 / §4.5 两行 / §4.7 bullet + ⑪ 注 / §4.8 表；TC-M4-16 预期 2/3/4 + TC-M4-01 005 注；Part A §2 修订注；V2-OPEN-ITEMS + AGENTS.md；本记录）。**验证证据**：`cargo test` **379 passed + 4 ignored**（378 基线 +1 新钉；ignored 3→4 = 新增 `#[ignore]` 钻子默认排除）/ `npm test` **463 passed**（33 files，−3+3 键账目持平）/ `npx tsc --noEmit` **exit 0**。**DB 级演练证据**（清单 8）：现网库前置取证（user_version=4、11 行 action_logs、2 行 executed_command 有值=id72/73）→ 副本拷贝 → `PULSEPET_DRILL_DB=… cargo test -- --ignored migrate_drill` **ok** → 副本 sqlite3 复核（user_version=5、11 行全保留、id72/73 command 快照完整且 cwd NULL=未配置）。**实施偏差**：无（照清单落；清单 8 预期「m4c 不增不减、cwd_from_params +1、孤儿/skipped 随迁不增不减」与实际 378→379 完全一致）。**用户目验（待办）**：新 build 下点开历史行 = 命令（当时）+ 工作目录（当时）（未配置行显示「继承 App 进程目录」）；旧行（005 前）command/cwd 显示未记录/未配置占位。

**Tester 验证（2026-08-31，tester subagent 独立复核 Part A/B/C 全部改动）**：**PASS WITH NOTES**——三件套独立复跑与声称基线逐字一致（379+4 ignored / 463 / 0）；7 组定向测试存在且断言抽查为真钉；**反证法验证**：临时改 `ACTION_LOG_PAGE_SIZE` 15→50 → `action_logs_crud` 红（`left: 50, right: 15` 正中分页断言）→ 恢复后全量绿 + 工作区 diff 逐字节自证无残留；静态核验全过（常量单点、executed_command 前端零引用、填充恒可点、三联动点 matchOf、空指令守卫、i18n 键账目、CSS 类）；持久化兼容三态 node 独立执行 PASS。**活体证据**：复核时现网库已自然升 **v5 / 12 行、含 1 行 cwd 有值**——用户实机使用已触发 005 迁移与 cwd 快照管线真实生效（实施记录的「v4/11 行」系取证时点快照，非矛盾）。P3 处置：P3-1 钻子耦合（现网已 v5 不可直接复跑）→ **已修**（`#[ignore]` 注释补「一次性演练 + 降格副本构造法」，db 模块 13 passed + 1 ignored 验证无破坏）；P3-2 实施记录时点快照 → **不改**（历史记录性质，本段留痕即解）。

**Committer 审查（2026-08-31，committer subagent 对本会话全部工作区改动做语义审查与交付把关）**：**APPROVED WITH NITS，无 P0/P1**。静态核验全过：迁移链 004→005 四处接线与 `migrate_one` 事务语义保持（编译期断言把守）；两 insert `params!` 位置绑定与 SQL 列序逐位一致；`list_action_logs` 13 列 `row.get` 映射逐位核对；cwd/command 助手与 `run_task` 解析链同源成立（cwd 存原串不 trim）；前端兜底四态/恒写新格式/三联动点 `matchOf`/填充恒可点/历史渲染判定与 spec 逐字一致；i18n 键账目（+8−4+3−3）zh/en 成对、旧键消费者全清退；测试真钉评估通过（TDD 红证据链与文档记录自洽、6 处调用点账目一致）；工程纪律无违例；**降级场景安全**（线上 v0.2.1=v3 二进制读 v5 库安全——显式列名读写不受多余列影响、migrate 见 v5≥3 跳过；唯一会断的 004 时代二进制从未发布不可达）。问题处置：P2-1 V2-DESIGN §4.6「指令空禁用」文案失步 → **已修**（改恒可点 + 修订注）；P3-1 routine-templates.ts「re-export」注释失实 → **已修**；P3-2 `command_from_params` 注释补 run_task `{}` 兜底差异 → **已修**；P3-5 状态行目验口径 → **已修**；P3-3 `.task-history-summary` min-width 拥挤风险 → 接受观察（目验确认）；P3-4 钻子 `println!` → 接受（与既有测试风格一致）。修后验证：cargo **379+4 ignored** / npm **463** / tsc **0** + 重新 build 双 bundle。**交付判定：工作区可作为交付物**（等用户 commit 决定——后经用户批准已提交推送）。

---

## 附：会话答疑备查——exec 的 cwd 缺省行为（2026-08-30）

用户问「工作目录如果用户没有填，默认是什么？」——查证 `exec_run_with_timeout`（action_exec.rs :267-275）：cwd 为空/缺省时**不调用 `current_dir`** → 子进程继承 **PulsePet 自身进程的工作目录**，且该目录随启动方式漂移：

| 启动方式 | 实际 cwd |
|---|---|
| macOS GUI（Dock/Finder/`open`） | `/`（launchd 子进程） |
| `npm run tauri dev`（终端） | 项目目录 |
| Windows GUI | exe 所在目录 |

即默认值基本不可预期——与 §二十四 PATH 问题同源的「GUI 启动环境盲区」，相对路径命令会落在意料之外的目录。表单现状只有「工作目录（可选，需填写绝对路径）」label。**可选小改进（未裁定）**：cwd hint 补一句「不填则继承 App 进程目录（GUI 启动为 /），建议填写」。
