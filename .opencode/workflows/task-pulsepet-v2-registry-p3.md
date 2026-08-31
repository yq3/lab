---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-registry-p3
target: pulse-pet
coderTaskId: ses_fb3cedc83ffezYo3Tffn7Jp5T7
testerTaskId: ses_fb3a4b6e7ffe6FdbUuXxSNCjHE
committerTaskId: ses_fb397c7c3ffePu8loS15IOmU9Q
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 79c3fac3c4ec47481db47c4fab806b67cba2a77e
reviewedSha: 79c3fac3c4ec47481db47c4fab806b67cba2a77e
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["src-tauri/src/token_stats.rs", "src-tauri/src/agents.rs", "src-tauri/src/lib.rs", "src/lib/i18n.ts", "src/lib/token-stats.ts", "src/panel/TokenStats.tsx", "docs/v2/agent-registry.md", "docs/v2/V2-TEST-CASES.md(编排者改,coder原样stage)"]
endReason: null
createdAt: 2026-08-29T14:15:07+08:00
updatedAt: 2026-08-29T15:45:39+08:00
---

# task-pulsepet-v2-registry-p3: PulsePet agent registry P3——N 源编排 + degraded/报错口径 A′（语义扩展）

## 任务原文

实施 `pulse-pet/docs/v2/agent-registry.md`（2026-08-28 定稿，已过评审轮 + 测试覆盖核定）收敛方案 **P3 阶段**（§8.3）。前置：P1（Rust agents.rs）/ P2（前端 agents.ts）已于 task-pulsepet-v2-registry R1 实施完毕、双通过并合入 develop（PR #22，merge commit `4857f81`）。

**P3：N 源编排 + degraded/报错口径 A′（~300 行，语义扩展——本阶段含三处有意行为变更）**
- `query_stats_dual`/`today_stats_dual` → `query_stats_all`/`today_stats_all`（避开与现存单源函数 `query_stats`/`today_stats` 重名——旧单源函数保留原名，继续被 idle 汇报引用）：遍历 AGENTS 逐源查询合并（enum dispatch，无 trait object）；源结果三态化 **Ok / Missing / Failed**，判据按文件存在性两段式（§6.4：opencode = `detect_db_path` None→Missing、Some×后续任何错→Failed；CC = 目录不存在→Missing、目录在→Ok，坏行静默跳过既定健壮行为，P3 不新建解析失败探测）；
- 三处有意行为变更（§6.4 差异表）：① CC-only（oc Missing × CC 有数据）从常驻横幅改静默正常；② oc Missing × CC Ok-0行（目录在、无 transcript）从 Err 改空态；③ oc Failed × CC Ok-0行 从 Err 改空态；
- `AgentSpec` 增 `is_primary`（仅 opencode true）；degraded = 主源 **Failed** × 其余有数据 → `Some`（Missing 不触发）；硬报错 = 全部源无数据且无一源 Ok，文案 N 源中性化（`token.error.noDatabase`「未找到 opencode 数据库」→ 中性措辞重写）；
- 消费点全覆盖：`token_stats.rs` 两命令层（`token_stats_query`/`token_stats_today`）、by_agent 合并、`build_cc_idle_report` 今日段（degraded 语义沿用现状 `.ok()` 吞错静默省略，TC-M3-09-3 既有口径不变）；
- 性能口径：维持单 `spawn_blocking` 内**串行**逐源查询（已知取舍，源数上双位数再议并行/缓存）；
- 测试（§8.3 + §8.7.2 P3 新钉 6 枚，**P3 必须新增用例而非纯回归**——三处行为变更靠新钉证明）：
  - `m5_degraded_opencode_error_with_cc_data_degrades` 改用**伪造 schema 错误**构造 Failed 场景（预期从 degraded=Some 变 None）；
  - 补「db 文件在但打不开/损坏」Failed 用例（防"文件在但坏"误判 Missing）；
  - 补三组行为变更钉子：Missing × 有数据 = 无横幅、oc Missing × CC Ok-0行 = 空态、oc Failed × CC Ok-0行 = 空态；
  - `m5_degraded_both_missing_error_passthrough` 回归确认（语义不变仍 Err）；
  - TC-M5-08/09 预期口径同步；i18n `token.degraded` / `token.error.noDatabase` 两文案 zh/en 联动；其余双源用例语义不变；
  - 新增三源用例——第三源注入形态已定：**a) tempdir 伪造 transcript 源**（设计建议优先，用户 2026-08-29 授权采纳；与"测试不碰真实目录"约束一致）。

**并入的移交事项（来源 task-pulsepet-v2-registry 遗留事项，用户 2026-08-29 确认）**：
- ① P3 文档：`agent-registry.md` 全局状态标记刷新（标题行状态栏 / §1 结论 / §6 标题 / §8.0 附表——实施完成后统一为「P1/P2/P3 已实施」，并随 §8.3 补实施记录回写）；
- ② P3 代码：TokenStats `agentBadgeOf` 内联查表改为 `specOf` 单次查表（`text: badgeOf(s.agent)`），使 P2 钉 1 直接覆盖消费点（风险低，顺带消除钉子盲区）；
- ③ P3 注释：lib.rs:106 注释「§6.1 决策 4」引用无对应编号项 → 改为「§6.1 注入式签名冻结」；
- ~~④ P3 收尾：`V2-OPEN-ITEMS.md` §13 交叉引用与闭环记录回写~~ → **用户 2026-08-29 明示：不要改动 V2-OPEN-ITEMS.md——本轮跳过，继续移交**；
- ⑤ 流程沉淀：流程口径 F（每 commit 后补完整 `npm run tauri build`）的构建产物时间戳本轮起以 `stat` 输出形式落档。

**验收标准**：
- `cargo test` 全绿：基线 352 passed + 3 ignored + P3 新钉（§8.7.2 P3 清单 6 枚/三组）；`cargo build` 零警告；
- `npm test` / `npx tsc --noEmit` / `npm run build` 全绿（i18n 两文案 zh/en 联动后键完备性测试通过）；
- 三处行为变更由新钉证明（非纯回归）；`m5_degraded_both_missing_error_passthrough` 仍 Err；
- **测试纪律（用户 2026-08-29 指示）**：一切测试（cargo 新钉 / 三源用例 / 三态场景构造）一律 tempdir / 隔离路径注入，**禁止改动真实用户数据目录与文件**（`~/.local/share/opencode/`、`~/.claude/projects/` 等）；
- dev 冒烟：只做**只读**基础冒烟（正常态：启动、Token 页、设置页两卡 doctor）——三态场景（CC-only 静默 / Failed 横幅 / Ok-0行 空态）由 cargo tempdir 新钉覆盖，**不在真实环境构造**；
- 独立 commit（`[task-pulsepet-v2-registry-p3] R<n>`）、可单独回滚；commit 后补完整 `npm run tauri build`（流程口径 F）+ stat 时间戳落档（⑤）。

**约束**：
- §6.7 明确不做依旧生效：不激活 AgentAdapter、不动 HTTP 协议/DB schema/气泡菜单状态机、不接 codex、不动 killswitch 粒度、不引新依赖；
- **V2-OPEN-ITEMS.md 本轮禁改**（用户 2026-08-29 明示，含其未提交改动原样保留）；
- 分支：既有 `develop_opencode`，切出后**立即快进同步最新 develop**（当前 develop HEAD=c18fbc6，含 4857f81 P1/P2 合入）；commit 前再次确认已同步 origin/develop；
- 工作区用户未提交改动（`.opencode/README.md`、`.opencode/agent/supervised-coding.md`、`.opencode/agent/tester.md`、`pulse-pet/docs/v2/V2-OPEN-ITEMS.md`、blog ×2 未跟踪、`pulse-pet/images/` 未跟踪）不属于本任务，禁止 stage/commit/修改；
- **V2-TEST-CASES.md 口径已由编排者落笔（2026-08-29 14:23，TC-M5-08 加 A′ 注记 / TC-M5-09 按口径 A′ 重写步骤与预期）**——协议规定 coder 禁改用例文档内容；该文件本次改动属本任务范围，coder **可原样 stage 入 P3 commit（只 stage 不改一字）**；
- 用户附加指令（2026-08-29）：**coder 完成后重新 build 一次应用**（与流程口径 F 一致，完整 `npm run tauri build`）；
- 文档联动（§8.4）：`agent-registry.md` 回写 P3 实施记录（即移交事项 ①）。

## 需求确认

- [x] 用户已确认（2026-08-29 14:19，两项裁定：**V2-OPEN-ITEMS.md 不改动**〔移交事项 ④ 跳过、继续移交〕；**测试不改动真实目录和文件**〔全部 tempdir 隔离构造，dev 冒烟只做只读正常态检查〕。①②③⑤ 按默认并入，三源用例采纳设计建议 a) tempdir 伪造 transcript 源。status → implementing）
- 历史遗留事项清单：见下方"遗留事项"小节（①~⑤ 为 task-pulsepet-v2-registry R1 双通过后确立的 P3 kickoff 移交清单；其余历史检查点均 approved 闭环无未了结事项）

## 遗留事项（跨任务移交）

- [x] ① P3 文档：agent-registry.md 全局状态标记刷新（标题行/§1/§6/§8.0，与 §8.1/§8.2 实施记录矛盾消除）+ §8.3 实施记录回写——✅ 已清偿（来源 task-pulsepet-v2-registry；coder commit 79c3fac，tester/committer 双核数字与事实一致）
- [x] ② P3 代码：TokenStats agentBadgeOf → specOf 单次查表——✅ 已清偿（来源 task-pulsepet-v2-registry tester 观察②；commit 79c3fac，agentLabel 同簇一并收敛）
- [x] ③ P3 注释：lib.rs「§6.1 决策 4」引用修正——✅ 已清偿（来源 task-pulsepet-v2-registry committer 终审观察项；commit 79c3fac，按内容定位行 99）
- [x] ④ ~~P3 收尾：V2-OPEN-ITEMS.md §13 交叉引用与闭环记录回写~~（来源 task-pulsepet-v2-registry）→ **用户 2026-08-29 明示本轮不改 V2-OPEN-ITEMS.md，跳过**；继续移交 → 去向待定（该文件工作区改动落定后再议，可并入 registry P4/codex 接入或独立收尾任务）
- [x] ⑤ 流程沉淀：构建产物时间戳 stat 落档——✅ 已清偿（来源 task-pulsepet-v2-registry tester 观察①；本轮起执行，coder 报告三产物 stat 齐备且 tester 复核）

**本任务新移交（2026-08-29 R1 双通过后确立，去向=registry P4/codex 接入 kickoff 清单）**：
- [ ] **P4-①**：第二 transcript 形态源出现时，TranscriptCache 需 per-source cache（retain(seen) 单目录前提，本轮三源测试实证，源码注释与 §8.3 微调③已注记）（来源 tester 观察②/committer 备忘）
- [ ] **P4-②**：P4 若动 MergeAcc 可顺手补「oc Failed × CC Missing → Err」专属钉 + 清理主源 has_data 冗余计算（来源 tester 观察①/committer 备忘 2）
- [ ] **P4-③**：V2-OPEN-ITEMS.md §13 闭环回写（即上表 ④，随该文件工作区改动落定一并处理）

（处理完毕回写勾选并注来源任务 ID；继续移交的注明去向）

## 轮次记录

- R1 kickoff（2026-08-29 14:19 用户确认）：两项裁定落档（V2-OPEN-ITEMS.md 不改 / 测试全 tempdir 隔离）；①②③⑤ 并入、④ 跳过继续移交；三源用例定 a) tempdir 伪造 transcript 源；用户附加指令=完成后重新 build 应用。14:23 编排者按口径 A′ 更新 V2-TEST-CASES.md（TC-M5-08 注记 / TC-M5-09 重写，coder 只 stage 不改内容）。14:24 用户同意调用 Coder（R1 实施轮）。
- R1: **Coder 首次调用被取消（14:49，vision 越界权限卡死——与上一任务 R1 同因，用户中断）**；经 opencode.db 恢复会话 coderTaskId=`ses_fb3cedc83ffezYo3Tffn7Jp5T7`。中断前实际进度（14:52 编排者 git/db 实测）：**P3 commit `79c3fac` 已落 develop_opencode**（14:42:11，8 文件：token_stats.rs N 源核心 / agents.rs is_primary / lib.rs 注释修正 / TokenStats.tsx specOf / i18n 双文案 / token-stats.ts / agent-registry.md 文档刷新 / V2-TEST-CASES.md 口径原样 stage ✓），tauri build 产物 14:42:38 晚于提交 ✓，工作区用户改动零触碰 ✓；卡点=dev 冒烟进行中（面板已唤起、Token 页已渲染、日志证据在 /tmp/pulsepet-dev*.log），截屏存 `/tmp/pp-panel-1.png`（工作区外）委托 Vision 目验触发越界卡死。dev 实例仍在跑（pid 52657 debug）。编排者已将截图拷入工作区 `.opencode/tmp/pp-panel-1.png`。用户指示：**续接 Coder 继续；vision 调用必须先确保图片拷入当前工作区**。
- R1: **Coder 完成（2026-08-29 15:0x 报告，续接会话 ses_fb3cedc83ffezYo3Tffn7Jp5T7）**。单 commit `79c3fac`（8 文件 +606/−171）：token_stats.rs 核心（query_stats_dual/today_stats_dual → query_stats_all/today_stats_all、SourceSpec/SourceKind enum dispatch、SourceState<T> 三态 Ok/Missing/Failed 文件存在性两段式判据、MergeAcc 口径 A′ 四规则、sources_from_agents、编排 factored 为 query_stats_sources/today_stats_sources 源清单注入、missing_reason 保 legacy-storage 透传、消费点全覆盖）；agents.rs is_primary（仅 opencode true + 全表恰一断言）；lib.rs 注释修正③（行号漂移 106→99 按内容定位）；i18n token.error.noDatabase/token.degraded zh/en 中性化重写；token-stats.ts 注释同步；TokenStats.tsx specOf 单次查表②（agentLabel 同簇一并改）；agent-registry.md 五处状态刷新+§8.3 实施记录回写①；V2-TEST-CASES.md 原样 stage 一字未改 ✓。**自测证据**：cargo test 357 passed+0 failed+3 ignored（基线 352+3i+新钉 5 枚：p3_cc_only_opencode_missing_silent / p3_opencode_missing_cc_ok_zero_rows_empty_state / p3_opencode_failed_cc_ok_zero_rows_empty_state / p3_opencode_db_corrupt_file_failed_banner_kept / p3_three_source_merge_with_fake_third_transcript_source）；m5_degraded 3/3、m6_today 5/5（both_missing 仍 Err+补 legacy 断言）；cargo build/test 双档零警告；npm 447/32、tsc OK、npm run build OK；tauri build 三产物 stat 均晚于 commit 48s/28s（⑤落档）；fetch 后 rev-list count=0 无分叉。**偏差 7 点**：①最重要——检查点/§8.7.2 括注「m5 改写预期 degraded=Some 变 None」与 §6.4 规则3/评审 P1-2/TC-M5-09 预期5 矛盾（schema 错=Failed→横幅保留 Some；Some→None 属旧无db=Missing 构造，由新钉①钉住）——实施按 §6.4/TC-M5-09，改写用例断言 Some，澄清落档 §8.3 实施记录①（未动 §8.7.2 原文，留 committer 裁定）；② m6_today_by_agent_degraded_cc_only_single_row 更名去 degraded+断言翻转（无db×CC数据属行为变更①既有用例）；③ 三源测试双 transcript 源各配独立 cache（TranscriptCache retain(seen) 单目录前提，生产无此形态，P4 注记）；④ 顺手根治 P1 遗留 test 构建函数指针 == 警告（fn_addr_eq，超字面范围但方向正确）；⑤ Missing 态携带原因错误供硬报错透传（保 TC-TK-04 可行动提示，防第四处未授权行为变更，both_missing 补 legacy 断言）；⑥ dev 冒烟因用户 11:08 遗留 vite 占 1430 改等价路径（复用 vite + cargo run --no-default-features）；⑦ 其余逐条照检查点无偏差。**dev 冒烟（只读正常态）**：启动日志干净无 panic；real_dual_query_manual 真实库只读对账四维度全绿 degraded=None（走 P3 生产函数）；热键唤起面板 Vision 目验 Token 页正常（KPI/图表/会话列表、无横幅）；AX 点击「设置」tab→两卡 doctor 与后端日志一致（oc installed·事件正常 / cc not-installed·node就绪 probe 15ms）；三态场景未在真实环境构造（tempdir 钉覆盖）。dev 实例已退出；用户遗留 vite（pid 42590）未处置留用户裁定；冒烟截图 7 张在 .opencode/tmp/（未跟踪）。status → testing。
- R1: **Tester PASS（2026-08-29 15:20 报告，testerTaskId=ses_fb3a4b6e7ffe6FdbUuXxSNCjHE，testedSha=79c3fac=HEAD）**：全项亲测（cargo 357+3i / npm 447·32 / tsc / 双档零警告 / npm run build 全过，未采信 Coder 自报）；新钉 5 枚逐枚点跑断言核对相符（`p3_` 5 passed）；m5_ 21 / m6_ 15 点跑通过；3 枚 ignored 以 --ignored 实跑（real_dual_query_manual 走 P3 生产函数真实库只读对账全绿）；三处行为变更钉证与 §6.4 差异表 7 行逐行对齐；**tempdir 纪律审计零违规**（新增行扫描真实路径特征零命中；生产查询链 SQLITE_OPEN_READ_ONLY；fs 写操作全在测试模块指向 temp；plog 写 ~/.pulsepet/ 属 M3 既有行为备案不违规）；偏差 7 条全裁定：**①裁定 Coder 处理正确（CASE_BUG 归 §8.7.2 括注文字，建议 committer 顺手对齐一行）**、②~⑥全部接受、⑦核实属实；文档核查：V2-TEST-CASES.md commit diff 恰为编排者两处改动无夹带、agent-registry.md 实施记录数字与实测逐项一致、工作区纪律零触碰、V2-OPEN-ITEMS.md 确认未动。观察 4 项非阻断（①oc Failed×CC Missing 无专属新钉——现状即 Err 风险极低 ②TranscriptCache 单目录前提已注记 ③plog 日志备案 ④§8.7.2 括注对齐建议）。**注：tester 验证性 rebuild 使 target/release/pulse-pet 裸二进制时间戳变为 15:15:06（非跟踪产物）；交付物 .app 14:42:38 / dmg 14:42:59 未变，仍晚于 commit。** 结论：R1 一轮通过，建议进入 committer 终审。status → 待 committer。
- R1: **Committer APPROVED（2026-08-29 15:33 报告，committerTaskId=ses_fb397c7c3ffePu8loS15IOmU9Q，reviewedSha=79c3fac=testedSha=HEAD）**：独立读码复核——§8.3 逐条零偏差（更名/旧单源保留/idle 汇报引用 intact、enum dispatch、两段式判据、is_primary、消费点全覆盖含 build_cc_idle_report .ok()、串行单 spawn_blocking）；§6.7 零越界（Cargo.toml/package.json/tauri.conf.json/capabilities/db.rs/http_server.rs diff 全空）；口径 A′ 语义 §6.4 四规则+差异表 7 行逐行对齐，**无第 4 处未授权行为变更**（legacy 透传与旧 open_checked 逐字节一致）；测试质量裁定断言真实把守非同义反复（钉④ Failed 唯一可达 Some 路径、三源数值交叉断言）；commit 卫生 8 文件恰好、V2-TEST-CASES.md 恰两 hunk 无夹带、工作区纪律 ✓。**CASE_BUG 裁定：属实——§8.7.2:369 括注文字错误（P2 唯一问题），实现按 §6.4/TC-M5-09 正确；处置=编排者交付前顺手改一行，无需新轮**。需求边界问题：无。观察 5 项全非阻断（oc Failed×CC Missing 无专属钉/主源 has_data 冗余无害/TOCTOU 微窗口归 Failed 不违口径/损坏 db degraded code=no-database 与旧一致/tester rebuild 时间戳注记）。**放行**。15:34 编排者已按裁定改正 §8.7.2:369 括注（与 §8.3 微调①对齐，注明终审裁定来源）——该文件工作区改动待交付阶段由 coder stage+commit（复用 V2-TEST-CASES.md 先例）。status → approved（待用户交付指令）。
- R1: **交付启动（2026-08-29 15:38 用户指令"交付"）**：遗留事项小节回写完毕（①②③⑤ 清偿、④ 跳过继续移交；新移交 P4-①②③）；编排者已按 committer 裁定改正 §8.7.2:369 括注（工作区 M 待 coder commit）。交付序列：Coder 续接（commit §8.7.2 修正 → fetch 同步核验 → push develop_opencode → 开 PR base=develop）→ Committer 续接（gh pr review 评论式留痕）→ Coder 补 evidence manifest 进 PR description → 汇报合入请求（不自动合入）。
- R1: **交付完成（2026-08-29 15:43）**：①Coder 续接——docs 修正 commit `ea7fdcd`（1 file +1/−1，§8.7.2 括注更正，diff 预核仅此一处）→ fetch 核验 origin/develop 无新提交 → push 成功（`db8dc71..ea7fdcd` fast-forward，SSH 认证通过）→ **PR #23 开立**（https://github.com/yq3/lab/pull/23 ，base=develop ← head=develop_opencode，OPEN/MERGEABLE，commits=[79c3fac, ea7fdcd]）；②Committer 续接——`gh pr review 23 --comment` 成功（state=COMMENTED，review ID PRR_kwDOTsiHgs8AAAABLXBSuw），批语含 APPROVED 结论/ea7fdcd docs-only 不改变代码结论/无 P0 P1/平台限制说明，并预核对 commit 集合与文件清单一致；③Coder 续接——evidence manifest JSON 经 `gh pr edit` 回填 PR description（原 7 小节完整保留、占位清零、临时文件工作区外用毕即删），manifest 含双 SHA/双 verdict/测试计数基线→实测/5 新钉名/三行为变更配钉/产物 stat 三时间戳/handover 三段。**PR #23：OPEN + MERGEABLE，待用户合入指令；未 merge、未动 develop/main。** 本地 develop_opencode HEAD=ea7fdcd。
- R1: **合入闭环（2026-08-29 15:45 用户指令"合入"）**：`gh pr merge 23 --merge`（沿 PR #22 双亲合并惯例，保留 P3 独立 commit）→ **state=MERGED，mergeCommit=`31a3a427d0c7eeaa05969283f28a0a5e2e2bee0a`（15:44:39 本地时区）**；本地 develop 已 ff 同步至 31a3a42（c18fbc6..31a3a42），P3 两 commit（79c3fac/ea7fdcd）在主线历史完整可见；develop_opencode 分支保留（工作流常驻分支，HEAD=ea7fdcd）。**registry 收敛方案 P1/P2/P3 全部落地合入，任务全闭环**（status=approved 沿历史惯例保持；遗留事项：P4 清单 3 项在"遗留事项"小节，V2-OPEN-ITEMS §十四跨天会话归属仍独立排队）。

## 最新验证意见原文

### R1 Tester 报告（2026-08-29 15:20，逐字收录）

# Tester 验证报告 — task-pulsepet-v2-registry-p3 R1

**testVerdict: PASS**
**testedSha: 79c3fac3c4ec47481db47c4fab806b67cba2a77e**（= develop_opencode HEAD，commit 2026-08-29 14:42:11，验证全程 HEAD 未动、零 commit/push）

**验证方式**：全部逐项亲测——cargo test / npm test / npx tsc --noEmit / cargo build 双档 / npm run build 在本机实跑；新钉 5 枚 + 改写用例按名点跑（`cargo test --lib p3_` 等）；3 枚 ignored 用例以 `-- --ignored` 实跑（含 `real_dual_query_manual` 走 P3 生产函数对真实库只读对账）；代码级逐行核对 token_stats.rs N 源骨架、agents.rs、前端三文件、两文档 diff；截图（工作区 `.opencode/tmp/`）直接目验；tempdir 纪律以 diff 全文扫描 + 生产代码读写面核查。未采信 Coder 任何自报数字。

## 1. 既有网回归表（Coder 申报 vs 实测）

| 项目 | Coder 申报 | 实测 | 结论 |
|---|---|---|---|
| cargo test | 357 passed + 0 failed + 3 ignored | **357 passed; 0 failed; 3 ignored**（lib 单元套件） | ✅ 一致 |
| npm test | 447 passed / 32 文件 | **447 passed (447) / 32 文件** | ✅ 一致 |
| npx tsc --noEmit | OK | exit 0、零输出 | ✅ |
| cargo build 零警告 | 双档零警告 | dev / release 双档 grep warning 均计 0；cargo test 日志 0 警告 | ✅ |
| npm run build | OK | ✓ built in 422ms（tsc + vite 全绿） | ✅ |
| tauri build 产物 | 三产物晚于 commit | PulsePet.app 14:42:38 / dmg 14:42:59 vs commit 14:42:11（release 裸二进制现值 15:15:06 系本人验证性 rebuild 所致，非跟踪内容，不影响判定） | ✅ |
| 分支形态 | 快进同步 develop | 79c3fac 直接落在 c18fbc6（= origin/develop）之上，无分叉 | ✅ |

## 2. 新钉 5 枚核对表（真实在跑 + 断言与目的相符）

| 测试名 | 断言核对（对照 §6.4 / §8.3 目的） | 实测 |
|---|---|---|
| `p3_cc_only_opencode_missing_silent` | oc Missing（tempdir 无 db）× CC 有数据 → query+today 双路 `degraded=None`、CC 行正常、by_agent 仅 cc——行为变更①钉证，断言完备 | ✅ ok |
| `p3_opencode_missing_cc_ok_zero_rows_empty_state` | oc Missing × CC **目录在但空**（`temp_dir` 实建目录≠缺目录）→ Ok 空 rows 空态、today 零值、by_agent 空——行为变更②钉证 | ✅ ok |
| `p3_opencode_failed_cc_ok_zero_rows_empty_state` | oc Failed（`CREATE_SESSION_OLD` 缺列 schema 错）× CC Ok-0行 → 空态且**非横幅**（degraded=None）——行为变更③钉证 | ✅ ok |
| `p3_opencode_db_corrupt_file_failed_banner_kept` | db 文件写垃圾字节（在但坏）× CC 有数据 → degraded=**Some**——评审 P1-2 反例钉证（防按错误码误判 Missing 杀横幅），断言"Failed 非 Missing"明确 | ✅ ok |
| `p3_three_source_merge_with_fake_third_transcript_source` | 源清单注入 3 源（伪造第三 transcript 源）：三源 Ok 合并 170、by_agent 总量交叉断言；主源 Failed × CC Missing × 第三源有数据 → 横幅（N 元"其余有数据"判据）——注入形态 a 落地 | ✅ ok |

`cargo test --lib p3_` 实跑：5 passed / 0 failed / 355 filtered。改写/联动用例点跑：`m5_` 21 passed（含改写后 `m5_degraded_opencode_error_with_cc_data_degrades`、`m5_degraded_both_missing_error_passthrough`、`m5_degraded_cc_absent_rows_unchanged_m3_regression`）、`m6_` 15 passed（含更名后 `m6_today_by_agent_cc_only_single_row`）。

## 3. 三处行为变更钉证核对（非纯回归）

| 行为变更（§6.4 差异表） | 钉证 | 实现语义核对 |
|---|---|---|
| ① CC-only 静默化（横幅取消） | p3_①（query 路）+ m6_today_by_agent_cc_only_single_row（today 路，断言翻转 None） | MergeAcc：Missing 只记 primary_error 不记 primary_failed → decide 恒 None ✅ |
| ② oc Missing × CC Ok-0行：Err → 空态 | p3_② | any_ok（CC Ok 含 0 行）→ 不进硬报错臂 → Ok 空 rows ✅ |
| ③ oc Failed × CC Ok-0行：Err → 空态（非横幅） | p3_③ | any_ok + others_have_data=false → degraded=None ✅ |

对照 §6.4 差异表逐行核过：7 行场景与实现/测试全对齐（含"双 Missing → Err 透传主源错误"与"双源 0 行 → 空态不变"两不变行）；`token.degraded` / `token.error.noDatabase` zh/en 四条文案均已中性化重写、src/ 全域零旧文案残留、键集合完备性测试在位（i18n.test.ts:48 enKeys==zhKeys，随 npm test 通过）。

## 4. tempdir 纪律审计结论（用户明示红线）

**通过，零违规。**
- 本次 commit 全部新增 `+` 行扫描 `\.claude|\.local|HOME|opencode_data_dir|cc_projects_dir|/Users/youqi|set_var|chdir`：**零命中**；
- 所有场景构造走 `temp_dir()`（`std::env::temp_dir()/pulsepet-tk-<pid>-<纳秒>-<tag>`，进程+时间双隔离）与 `make_db()`（temp 内建 db）；CC fixture `write_cc_session` 全部调用点均传入 temp 路径；
- 生产查询链只读：`open_checked` → `open_readonly`（`SQLITE_OPEN_READ_ONLY`）；transcript.rs 生产代码（`#[cfg(test)]` 前）仅 `read_dir/read/metadata/File::open`，全部 fs::write/rename/remove 均在测试模块内且指向 temp；
- `real_dual_query_manual`（ignored）实测确认**只读**：真实 `opencode_data_dir()` + `cc_projects_dir()` 仅查询 + println，四维对账 + today + by_agent 全绿 `degraded=None`（走 P3 生产函数 `query_stats_all`，即 dev 冒烟的等价数据面证据）。

## 5. Coder 7 点偏差逐条裁定

| # | 偏差 | 裁定 |
|---|---|---|
| ① | m5 改写预期矛盾（检查点/§8.7.2 括注 Some→None vs §6.4 规则3/TC-M5-09 预期5） | **Coder 处理正确（CASE_BUG，归检查点/§8.7.2 括注文字，需 committer 裁定改文字）**。独立判定依据：a) §6.4 是用户两轮拍板的权威口径，差异表第 3 行明文"oc Failed × CC 有数据 → 横幅**保留**（2026-08-28 用户确认）"，schema 错构造按两段式判据（评审 P1-2：文件存在性、与错误码解耦）= Failed → degraded=Some；b) 编排者已按 A′ 重写的 TC-M5-09 预期5 明文"oc Failed（伪造 schema 错）× CC 有数据 → degraded=Some"——实现与用例文档（需求载体）完全一致；c) 反之若按括注断言 None，则与用例文档直接矛盾，且"Some→None"只有在保留"无 db"（=Missing）构造时成立——该场景恰是行为变更①，已由 p3_① 独立钉住，m5 改写若不改构造就与 p3_① 重复且把"Failed×有数据→Some"这条用户拍板保留的路径置于零钉把守。Coder 按 §6.4/TC-M5-09 实施、澄清落 §8.3 实施记录①、未擅动 §8.7.2 原文（留 committer）——克制得当。建议 committer 顺手将 §8.7.2 括注与 §8.3① 对齐（文字级，一行） |
| ② | m6_today_by_agent_degraded_cc_only_single_row 更名 + 断言翻转 None | **接受**。该旧用例断言编码的正是被行为变更①废除的旧语义（oc Missing×CC 数据→Some），不改必红；更名去"degraded"如实反映新语义（静默 CC-only），today 路翻转由本用例钉住、query 路由 p3_① 钉住，双路闭合 |
| ③ | 三源测试双 transcript 源各配独立 cache | **接受**。TranscriptCache.plan_refresh 的 retain 以单目录扫描为前提，共享 cache 会互相驱逐——独立 cache 是正确工程解；生产路径一个 CcTranscript spec 无此形态，P4 注记已落源码注释与 §8.3③，无生产影响 |
| ④ | 顺手根治函数指针 `==` 警告（fn_addr_eq） | **接受**。纯测试代码改动（agents.rs 自测），`std::ptr::fn_addr_eq` 语义等价且消除真实告警，直接服务"双档零警告"验收项；超字面范围但方向正确、风险为零 |
| ⑤ | Missing 态携带原因错误供硬报错透传 | **接受**。防住一处未授权的第 4 处行为变更（TC-TK-04"请升级 opencode"可行动提示丢失）；`missing_reason()` legacy 优先 + both_missing 用例补 legacy 断言（ERR_LEGACY_STORAGE + "升级 opencode"文案）实测通过，§6.4 规则 2"透传主源错误"因此才真正可落地 |
| ⑥ | dev 冒烟等价路径（复用用户遗留 vite :1430 + `cargo run --no-default-features`） | **接受**。tauri.conf.json devUrl 本就指向 `http://localhost:1430`，复用同口 vite 与 `tauri dev` 运行形态等价；本项目 Cargo.toml 无自定义 `[features]` 段，`--no-default-features` 为无操作不改行为。冒烟证据目验通过：Token 页四 KPI 卡 + 时序图 + 模型 chips 正常渲染、无横幅无错误态；设置页两卡 doctor 与真实状态一致（opencode 已安装·事件正常 / CC 未安装·node 就绪）；`real_dual_query_manual` 四维 degraded=None 作数据面旁证。等价路径成立 |
| ⑦ | 其余逐条照检查点无偏差 | **核实属实**：更名 query_stats_all/today_stats_all（旧名单存于文档注释）、enum dispatch 无 trait object、消费点全覆盖（lib.rs 命令层 ：1197/:1222、by_agent 合并、build_cc_idle_report :1163 沿用 `.ok()` 吞错）、i18n 四文案、agents.rs is_primary（全表恰一断言实测在）、lib.rs §6.1 注释修正③（按内容定位行 99）、TokenStats specOf 单次查表②、agent-registry.md 状态刷新①、stat 时间戳⑤、V2-TEST-CASES.md 原样 stage |

## 6. 文档/纪律核查结果

- **V2-TEST-CASES.md**：commit 内 diff 恰为两个 hunk——TC-M5-08 加 A′ 注记（+2 行）、TC-M5-09 加 A′ 修订注记 + 步骤/预期按口径 A′ 重写——与编排者 14:23 落笔描述逐字吻合，**无 coder 夹带**；工作区该文件 clean；
- **agent-registry.md**：5 处状态刷新（标题状态栏 / §1 结论 / §6 标题 / §8 标题 / §8.0 附表"实施状态"行）+ §8.3 实施记录回写；实施记录内全部数字（352→357、447、零警告、tsc/build 绿、is_primary、factored 函数名、五处微调①~⑤）与本人实测**逐项一致**；§8.1（P1 351）/§8.2（P2 352+447）实施记录在位，链条自洽；
- **工作区纪律**：`git status` 终态仅含用户原有未提交改动（.opencode/README.md、supervised-coding.md、tester.md、V2-OPEN-ITEMS.md、blog ×2、images/）+ 本任务自身产物（workflows 检查点、.opencode/tmp/ 截图）——**零触碰、零 stage**；commit 文件清单恰 8 文件，V2-OPEN-ITEMS.md 未入 commit（④ 跳过落实）；
- **验证自身零残留**：全程只读 + 仓库内命令，HEAD 未动，无 commit/push（cargo build 产物仅落 target/，未跟踪）。

## 7. 观察项/非阻断备忘

1. **§6.4 差异表"oc Failed × CC Missing → Err"一格无专属新钉**——非行为变更（现状即 Err），decide() 的 `!any_ok → primary_error` 路径由 both_missing（Missing 形态）覆盖，Failed 形态同函数臂，风险极低；P4 若动 MergeAcc 可顺手补一枚；
2. 三源用例暴露的 **TranscriptCache 单目录前提**已由 Coder 注记（per-source cache 待 P4）——与 §8.3③ 一致，属设计内已知边界；
3. 测试运行会经 plog! 写 App 自身日志 `~/.pulsepet/pulsepet.log`（M3 既有行为，非本次引入，不属红线所指用户数据目录）——备案不计违规；
4. 偏差① 的收尾：建议 committer 终审时将 §8.7.2 P3 括注补一句与 §8.3① 相同的澄清（纯文档文字对齐，无代码影响）。

**结论：R1 一轮通过（testVerdict: PASS），建议进入 reviewer 终审。**

---

### R1 Committer 报告（2026-08-29 15:33，逐字收录）

# Committer 终审报告 — task-pulsepet-v2-registry-p3 R1

**reviewVerdict: APPROVED**

- **SHA 一致性核验**：`git rev-parse HEAD` = `79c3fac3c4ec47481db47c4fab806b67cba2a77e` = testedSha = 本次终审对象 ✓；commit 父提交 = `c18fbc6` = `origin/develop`（`git log origin/develop..HEAD` 仅 79c3fac 一条，快进无分叉）✓
- **工作区纪律核验**：全程只读（无文件修改、无 commit/push，HEAD 未动）；`git status` 终态仅含用户原有未提交改动（.opencode/README.md、supervised-coding.md、tester.md、V2-OPEN-ITEMS.md、blog ×2、images/）+ 本任务自身产物（检查点文件、.opencode/tmp/ 14 张截图证据），与任务启动时基线一致 ✓

## 逐项审查结论（1~7）

**1. 方案忠实度（§8.3 逐条）——全部落地，零偏差**
- 更名 ✓：`query_stats_dual`/`today_stats_dual` → `query_stats_all`/`today_stats_all`；旧单源函数 `query_stats`(:442)/`today_stats`(:569) 保留原名，继续被 `build_idle_report_with_today`（lib.rs:181 opencode idle 汇报）引用
- enum dispatch 无 trait object ✓（`SourceKind<'a>` enum；事件链函数指针表维持 §6.1 决策 3）
- 三态判据两段式 ✓：opencode `detect_db_path` None→Missing（携 `missing_reason`）× Some×后续任何错→Failed（open/schema/query，与错误码解耦——P1-2）；CC 目录不在→Missing、目录在→Ok（坏行静默，Failed 对 CC 空集）
- `is_primary` ✓：仅 opencode true，agents.rs 自测钉「全表恰一个主源」
- 消费点全覆盖 ✓：token_stats_query(:1197)/token_stats_today(:1222)/by_agent 合并(:1095)/`build_cc_idle_report`(:1163) 今日段 `.ok()` 吞错沿用（TC-M3-09-3 口径不变，m5_build_cc_idle_report 用例未动仍过）
- 串行单 spawn_blocking ✓（两命令层各单 spawn，内部串行循环）；性能口径注记落源码注释 + §8.3 实施记录

**§6.7 零越界核查 ✓**：Cargo.toml / package.json / tauri.conf.json / capabilities / db.rs / http_server.rs 本轮 diff 全为空；无新依赖、无 DB schema/HTTP 协议/气泡状态机/killswitch 改动、AgentAdapter 未动。

**2. 口径 A′ 语义代码级复核——§6.4 四规则 + 差异表 7 行逐行对照全对齐**
| 场景 | 实现路径 | 结果 |
|---|---|---|
| ① CC-only（oc Missing×CC 有数据）| Missing 只记 primary_error 不记 primary_failed → decide 恒 None | 静默 ✓ |
| ② oc Missing × CC Missing | !any_ok → Err(primary_error=missing_reason) | Err 透传 ✓（文案中性化在 i18n）|
| ③ oc Failed × CC 有数据 | primary_failed × others_have_data → Some | 横幅保留 ✓ |
| ④ oc Failed × CC Missing | !any_ok → Err(primary_error=Failed 原错) | Err 同 ✓ |
| ⑤ oc Missing × CC Ok-0行 | any_ok（Ok 可含 0 行）→ 空态 | 变更② ✓ |
| ⑥ oc Failed × CC Ok-0行 | any_ok × others_have_data=false → None 空态 | 变更③ ✓ |
| ⑦ 双源 Ok-0行 | any_ok → 空态 | 不变 ✓ |

- **无第 4 处未授权行为变更**：既有用例语义翻转仅波及 m6（行为变更① 的 today 路）与 m5 改写（构造换 Failed、预期**仍 Some**——实为语义不变）；both_missing 仍 Err，且 `missing_reason` 的 legacy/no-database 两分支错误码与文案与旧 `open_checked`(:463-475) 逐字节一致——legacy 透传零漂移 ✓
- **硬报错中性化与 legacy 透传并存自洽** ✓：错误码层面 legacy-storage 专属码走 `token.error.legacyStorage` 文案不变；no-database 文案 zh/en 中性化；两键 i18n 测试在位（enKeys==zhKeys + token.degraded 双语非空断言）

**3. 测试质量——断言真实把守不变量，非同义反复**
- 钉①②③：钉行为结果（degraded=None/Some、rows/Err 分道），与 §6.4 目的逐条对应 ✓
- 钉④「db 在但坏」：degraded=Some 是 Failed 唯一可达路径（Missing 不可能触发 Some），故"Failed 非 Missing"被真实钉住，非套话 ✓
- 钉⑥三源：数值交叉断言（三源 170、by_agent 总量==today 总量）+ N 元「其余有数据」横幅判据（第三源满足）✓
- m5 改写：构造 schema 错 + 断言 degraded 前缀 `schema-mismatch`——同时钉住错误串透传，强度高于原用例 ✓；m6 更名断言翻转 None 精确 ✓；both_missing 补 legacy 断言钉住 TC-TK-04 可行动提示 ✓
- 352+5=357 计数与「§8.7.2 六枚钉 = 5 新函数 + m5 改写（非新增）」口径自洽 ✓

**4. CASE_BUG 裁定——见下方专节**

**5. commit 卫生 ✓**：恰 8 文件 +606/−171；V2-TEST-CASES.md diff 恰两 hunk（TC-M5-08 注记 +2 行 / TC-M5-09 重写），与编排者 14:23 落笔逐字吻合，无夹带；V2-OPEN-ITEMS.md 未入 commit（④ 跳过落实）；工作区用户改动零触碰零 stage。

**6. 遗留风险扫描 ✓**：权限 capability/依赖/Windows cfg!/DB 迁移零改动；`query_stats_dual`/`today_stats_dual` 全仓无存活代码引用（仅历史文档与注释性回溯）；i18n 键集合完备（两键 zh/en 联动，测试在位）；前端消费点全覆盖（TokenStats errorHint 码映射 noDatabase/legacyStorage、degraded 横幅、pet 侧静默）。

**7. 文档回写质量 ✓**：五处状态刷新（标题状态栏/§1 结论/§6 标题/§8 标题/§8.0 附表）+ §8.3 实施记录数字与代码-测试实况逐项一致（357/447/零警告/函数名/微调①~⑤）。唯一缺陷即 §8.7.2:369 括注（CASE_BUG 对象，见下）。

## 问题清单

- **P0**：无
- **P1**：无
- **P2**（1 条）：`pulse-pet/docs/v2/agent-registry.md:369` —— §8.7.2 P3 括注「`m5_degraded_opencode_error_with_cc_data_degrades` 改写（预期从 degraded=Some 变 None）」为文字错误（CASE_BUG 已裁定）。处置建议见下节，由编排者交付前顺手改正一行，不发给 coder。

## 需求边界问题

无。任务原文与验收标准自身自洽；矛盾点仅存在于 agent-registry.md 内部括注文字（§8.7.2 与 §6.4/§8.3 实施记录冲突），属文档缺陷而非需求不自洽，无需上报用户改 spec。

## CASE_BUG 裁定（Tester 上报）

**裁定：属实——§8.7.2 括注文字错误；实现按 §6.4/TC-M5-09 正确。** 独立判定依据：
1. §6.4 规则 3 + 差异表第 3 行明文「oc Failed（在但坏）× CC 有数据 → 横幅**保留**（2026-08-28 用户确认）」→ degraded=**Some**；
2. 编排者按 A′ 落笔的需求载体 TC-M5-09 预期 5 明文「oc Failed（伪造 schema 错…）× CC 有数据 → `Ok(CC-only) + degraded=Some`」——实现与之一致；
3. 改写后构造（db 在、列缺）= 两段式判据第二段 **Failed**，预期必须仍为 Some；「Some→None」仅属于旧「无 db」= **Missing** 构造，而那正是行为变更①，已由 `p3_cc_only_opencode_missing_silent` 独立钉住——若按括注实现，将既与用例文档矛盾，又使「Failed×有数据→Some」这条用户拍板保留路径少一枚把守钉。Coder 未擅动 §8.7.2 原文、澄清落档 §8.3 实施记录微调①，处置克制得当。

**处置建议**：交付前由编排者顺手改正 §8.7.2:369 一行（与 §8.3 实施记录微调① 对齐，如「改写（构造从无 db 改伪造 schema 错=Failed，预期**仍** degraded=Some；Some→None 由行为变更钉 ① 钉住）」）。纯文字、零代码影响、无需重测，不构成新一轮 coder 轮。若编排者选择不改，须在交付记录中明确移交后续文档维护。

## 观察项/备忘（非阻断）

1. oc Failed × CC Missing → Err 一格无专属新钉（tester 观察①已记）——与 both_missing 同 decide 臂，风险极低，接受；
2. 主源 `has_data` 在 MergeAcc 中实际不参与判定（`note_ok` 仅非主源 has_data 记 others_have_data）——主源 Ok-0行 与 Ok-有数据决策等价，符合规则 4；无害冗余计算，P4 若扩展可顺手清理或利用；
3. opencode 两段式判据存在 TOCTOU 微窗口（wrapper detect 与 query_stats 内 detect 之间文件被删 → 归 Failed 而非 Missing）——语义上「在但打不开」归 Failed 不违背口径，零风险；
4. 损坏 db 的 degraded 串 code 为 `no-database`（open_readonly 统一映射），横幅 tooltip 会显示「no-database: …」——与旧双源行为一致，非本次引入；
5. tester 验证性 rebuild 使 target/release 裸二进制时间戳后移（非跟踪产物），交付物 .app（14:42:38）/ dmg（14:42:59）晚于 commit（14:42:11）的⑤落档证据成立，不影响判定。

## 放行结论

R1 一轮通过。代码、测试、文档实施记录均忠实于 §8.3/§6.4 方案；唯一遗留为 §8.7.2 一行括注文字（P2，CASE_BUG 已裁定），由编排者交付前顺手改正即可，无需新增 coder/tester 轮。**reviewVerdict: APPROVED**。
