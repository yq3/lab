---
taskId: task-pulsepet-m3
target: pulse-pet/
supervisorSessionId: null
coderTaskId: ses_ff7e8ade4ffePERPzQNYS6QP3n
testerTaskId: ses_ff7cf1c84ffeWL5964a6cpFQ6a
committerTaskId: ses_ff7b6e460ffewwaPs9moFfJeBF
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: affe86a3bca255a34c5f0ed03520dfac588e89a5
reviewedSha: affe86a3bca255a34c5f0ed03520dfac588e89a5
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: []
endReason: null
createdAt: 2026-08-16T08:58:21+08:00
updatedAt: 2026-08-16T10:15:26+08:00
---

# task-pulsepet-m3: pulse-pet M3 token 统计

## 任务原文

在 `lab/pulse-pet/`（M2 已落地，HEAD=bef11ac 已合入 develop，见 task-pulsepet-m2 检查点）开发 M3 token 统计。依据 DESIGN.md §10.2 里程碑 M3、§4 Token 统计、TEST-CASES.md TC-TK 章节（TC-TK-01~13）对应用例。开发分支 `develop_opencode`（coder 固定提交分支，提交前先同步 origin/develop）。

**M3 范围（DESIGN.md §10.2 + §4，1 周）**：
1. **Rust 侧 `token_stats.rs`**（§4.1/§4.2）：
   - 路径探测（启动时按优先级）：macOS `~/.local/share/opencode/opencode.db` → `opencode-canary.db`；Windows `%LOCALAPPDATA%\opencode\opencode.db` → canary（TC-TK-01/02）
   - 旧版本兜底探测：`~/.local/share/opencode/storage/session/*.json` 存在 → 提示"请升级 opencode"，不做完整解析，不崩溃（TC-TK-04）
   - 连接模式：`OpenFlags::SQLITE_OPEN_READ_ONLY | SQLITE_OPEN_NO_MUTEX`，不用 WAL 不写 journal；**每次查询新建只读连接即开即关**（NO_MUTEX 不可跨线程共享，Tauri command 在 tokio 线程池）
   - 聚合查询：by session（原样行 + ORDER BY time_updated DESC）、by day（strftime 天维度 + SUM 聚合 + GROUP BY day, project_id）；周/任意跨度由前端传 from/to（§4.1 两条 SQL 为准）
   - 三个 command：`token_stats_opencode_path() -> Option<PathBuf>`、`token_stats_query(from_ms, to_ms, group_by) -> Vec<TokenRow>`（group_by: "session" | "day" | "week" | "range"）、`token_stats_current_session(session_id) -> Option<TokenRow>`
   - **schema 白名单检测（TC-TK-13）**：查询前 `PRAGMA table_info(session)` 检查 `tokens_*`/`cost` 字段白名单，缺失 → "请升级 pulse-pet"提示，不崩溃、不查错列
   - WAL 缺失处理（§12 风险）：wal/shm 不存在时只读打开可能报错 → 回退"数据库未运行/未初始化"提示
2. **前端 Token 标签页**（§4.3 + TC-TK-08/09）：
   - panel 新增 Token 标签页（现为 M1/M2 占位页，见 src/panel/Panel.tsx）
   - 顶部 KPI 卡：跨度内总 input / output / cache_read / cost
   - 时序图：默认按天柱状图，**自画 SVG**（不引入重依赖库）
   - 项目分布：占比饼图 + 列表
   - 会话列表：按 token 降序，单条可展开详情（input/output/reasoning/cache 分布）
   - 时间跨度切换：7d / 30d / 任意（任意跨度由前端传 from/to 到 Rust，后端不写死维度，TC-TK-07/08）
3. **当前会话气泡汇报**（§4.3 + TC-TK-10/11/12）：
   - 宠物收到 `session.status == idle` 且本会话有 ≥1 条 token 记录时，气泡显示"本期用了 Xk input / Yk output / $ Z"（数字来自 opencode.db）
   - **M3 done 补充验证项①（TC-TK-11）**：实测 opencode `session` 表 `cost`/`tokens_*` 写入时机（逐 message 写 or session 结束聚合写），记录结论；若进行中数字滞后/为零，气泡仅在 `time_updated` 与 `session.status=idle` 时间差 < 阈值时显示，避免陈旧数字
   - **M3 done 补充验证项②（TC-TK-12）**：正跑中的 session 在 session 表无记录（0 行）时，前端必须"无记录则不出气泡"，不显示 0/陈旧数字
   - 气泡文案约束沿用 M2 净化规则（单行、1-140 字符、白名单模板）
4. **success 状态事件驱动（M3/M4 引入项，随 M2 遗留）**：token 会话汇报作为 success 状态的事件来源之一（M2 检查点遗留"success 无事件驱动→M3 token 会话汇报引入"）；DESIGN §3.3 优先级链 success 定案位 error>waiting-permission>testing>editing>thinking>success>working>idle

**M3 明确不做**：提醒调度器与烟花逻辑（M4）、atlas 加载（M5）、穿透切换/拖拽/热键/右键菜单（M6）、todo 插件机制（M7）、CI workflow 修改（§13）、Windows 实机验证（M8）、v2 排行榜（§4.4，不引入后端服务）、旧格式 json 完整解析（v1.1）。

## 需求确认

- [x] 用户已确认（确认后 status=implementing）——2026-08-16 用户确认：① M3 范围照执行；② 遗留事项并入口径认可——P2-9/P2-10 + 测试缺口 4 条 + P3 ①②③⑥ 并入本轮；P3 ④⑤ + 限流豁免 /health 继续移交（去向注明）；同桶升级放行 M5 前定案（去向=M5）
- 历史遗留事项清单（supervised-coding 扫描 task-pulsepet-m1/m2 检查点汇总，默认并入本任务，见 README §4.6）：

## 遗留事项（跨任务移交）

- [x] **M2 移交修复级 2 条（来源 task-pulsepet-m2，2026-08-16 清偿）**：P2-9 tokenizer literal 防零消费（opencode-config.mjs:57-66 if(i>start)…else i+=1 + block 注释/非法输入 2 用例，tester 真实 install.sh 不挂死）；P2-10 token 文件 OpenOptions.mode(0o600) 创建即收紧（runtime.rs:55-77 + chmod 兜底旧文件，实测 -rw-------）
- [x] **M2 移交测试缺口 4 条（来源 task-pulsepet-m2，2026-08-16 清偿）**：tokenizer block 注释/非法输入用例、Backoff 并发行为（createDeliverer 3 用例）、服务端空闲连接语义锁定（accept 超时循环不退出 + 挂起连接断开恢复 2 条 Rust 集成 + AbortSignal 3s 1 条）
- [x] **M2 移交 P3 ①②③⑥（来源 task-pulsepet-m2，2026-08-16 清偿）**：accept Err 不再静默（eprintln+50ms 防热转+继续）、Backoff 并发不跳级（createDeliverer 队列串行化）、connection:close forbidden header 删除、session_state 回收 remove（含 idle 条目超时清理，锁内）；④⑤ 继续移交（install.ps1 BOM tokenizer 已容忍；classifyEvent permission.asked 前端已双处理）——去向=继续移交随 M8 收尾
- [ ] **M2 移交 M3/M4 引入项（来源 task-pulsepet-m2）**：success 状态事件驱动——M3 token 会话汇报已引入（idle→查库→注入 success→气泡，2026-08-16 清偿）；限流豁免 /health 评估——继续移交（M3+ 心跳引入时）
- [ ] **M5 前定案项（来源 task-pulsepet-m2，已回 spec DESIGN §3.1）**：同桶升级放行语义（新 kind 优先级 > 已投递 kind 时绕过冷却）——M5 atlas 前实现，去向=M5 前定案
- [ ] **M3 新移交（2026-08-16，committer R1 P3 五条不阻断，随 M4 顺带清偿）**：①摘要计数偏差（token-stats "12测"实为 9、token_stats.rs "20单测"实为 18+1 ignored，后续报告注意精度）；②fetchCurrentSession/token_stats_current_session 死代码（spec §4.2 要求暴露，TS 封装未消费，M4 接入或删除）；③parseStatsError 无单测（错误态 UI 关键路径，GUI 已覆盖）；④token_stats_opencode_path 返回 Option vs DESIGN Result 签名微偏；⑤schema-mismatch 提示"请升级 pulse-pet"文案冗余（出现两次）
- [x] **回 spec 落笔（2026-08-16 用户确认，supervised-coding）**：DESIGN.md §4.1 by session SQL 列名勘误（`id AS session_id`，注明 M3 实测真实 schema 主键为 id）；DESIGN.md §4.3 气泡汇报补 cost=0（订阅/plan）省略 "$ Z" 段约定。共 2 处 DESIGN。

## 验收标准（对应 TEST-CASES.md）

- **TC-TK-01 数据库路径探测（macOS）**：opencode 已用过 → `token_stats_opencode_path` 返回 `Some(path)`
- **TC-TK-02 路径探测（canary / Windows）**：主库不存在、canary 存在（macOS）；Windows `%LOCALAPPDATA%\opencode\opencode.db` → 分别探测到
- **TC-TK-03 数据库不存在**：无 db 无 wal/shm → 返回 `None`；UI 显示"数据库未运行/未初始化"类提示，不崩溃
- **TC-TK-04 旧版本兜底探测**：仅存在旧格式 `storage/session/*.json` → 探测到并提示"请升级 opencode"，不做完整解析，不崩溃
- **TC-TK-05 只读连接与 opencode 并发**：opencode 跑任务（WAL 写入中）同时反复查询 → 正常返回，无锁冲突、无 "database is locked"，opencode 不受影响，连接只读（对 opencode.db 无任何写入）
- **TC-TK-06 聚合查询准确性**：设计的两条 SQL（by session / by day）与 UI 核对 → by session 行数与字段一致；by day 的 strftime 天维度、SUM 聚合一致（对账误差 ≤0.01 USD）
- **TC-TK-07 group_by 维度**：切换 session / day / week / range → 每种返回结构正确的 TokenRow 集合；week 与任意 range 由前端传 from/to 到 Rust 计算；不出现后端写死维度
- **TC-TK-08 时间跨度切换**：切换 7d / 30d / 任意跨度 → KPI 卡、时序图、项目分布、会话列表随之更新；时间边界正确（含当天）
- **TC-TK-09 展示组件**：① 顶部 KPI 卡：跨度内总 input/output/cache_read/cost；② 时序图默认按天柱状图（自画 SVG，不依赖重依赖库）；③ 项目分布：占比饼图 + 列表；④ 会话列表：按 token 降序，单条可展开详情
- **TC-TK-10 当前会话气泡汇报（正向）**：本会话 ≥1 条 token 记录 + `session.status == idle` → 气泡显示"本期用了 Xk input / Yk output / $ Z"，数字来自 opencode.db
- **TC-TK-11 写入时机实测（M3 补充验证项①）**：实测 `session` 表 `cost`/`tokens_*` 写入时机并记录结论；若进行中数字滞后/为零，气泡仅在 `time_updated` 与 idle 时间差 < 阈值时显示
- **TC-TK-12 无记录不出气泡（M3 补充验证项②）**：正跑 session 无记录（0 行）→ idle 时不弹气泡、不显示 0/陈旧数字
- **TC-TK-13 schema 白名单检测（风险项）**：构造缺 `tokens_*` 列的旧 schema → 检测生效，提示"请升级 pulse-pet"，不崩溃、不查错列
- **M2 遗留修复验收**：P2-9 tokenizer 死循环（非法输入不再挂死，install.sh 幂等仍成立）+ block 注释/非法输入用例；P2-10 token 文件 mode 0600 一步到位（无 umask 短窗口）；测试缺口 4 条补齐
- 回归基线：npm test（M2 53 项 + 新增模块单测）全通过；cargo test（M2 34 项 + 新增 token_stats 测试）全通过；npm run build / tauri build 成功

## 轮次记录

- R1: coder 完成，commit `affe86a`（`[task-pulsepet-m3] R1: token 统计（只读聚合查询+panel Token 页+会话气泡汇报/success 驱动）+ 遗留清偿（P2-9/P2-10/P3-①②③⑥+测试缺口 4 条）`，分支 develop_opencode，提交前已同步 origin/develop=0 ahead（基于 43384db））。改动：28 文件 +2904/-46——Rust 侧 token_stats.rs（路径探测主库→canary、旧版 storage 兜底、READ_ONLY|NO_MUTEX 即开即关连接、session/day/week/range 四维聚合、schema 白名单 PRAGMA 检测、气泡汇报编排+新鲜度护栏 PULSEPET_TOKEN_REPORT_MAX_LAG_MS=60s、3 个 command；20 单测+1 ignored 真实库对账+TC-TK-11 结论注释）、lib.rs（注册 3 命令+make_idle_hook：idle→查库→注入 success+emit pulsepet://bubble）、http_server.rs（新增 IdleHook 参数，notify 前调用避免 idle→success 抖动+集成测试）；前端 token-stats.ts（命令封装/错误码解析/format/rangeForPreset 含当天/sumRows，12 测）、token-chart.ts（自画 SVG computeBars+pieSlices，7 测零依赖）、TokenStats.tsx（KPI 4 卡/按天按周柱状图/项目饼图+列表/会话降序可展开/7d 30d 自定义/错误态分码提示）、bubble.ts（净化单行 1-140+8s 自动隐藏，5 测）、Bubble.tsx+petStore（气泡状态/自动隐藏，5 测）、Panel.tsx tab 结构、http-bridge.ts 监听 pulsepet://bubble、Pet.tsx/petStore/global.css 气泡渲染、Cargo.toml serde derive 提升、README（M3 范围+TC-TK-11 实测结论）；遗留清偿：P2-9 tokenizer literal 分支 if(i>start)…else i+=1 防零消费+block 注释/非法输入 2 测、P2-10 runtime.rs OpenOptions.mode(0o600) 创建即收紧（cfg 区分 Windows）+测试强化、P3-① accept Err eprintln+50ms 防热转+继续+挂起连接测试、P3-② createDeliverer promise 队列串行化（Backoff 不跳级不误复位）+并发 3 测、P3-③ 删 connection:close forbidden header+断言更新、P3-⑥ tick 回收改 remove（含 idle 条目按超时清理，锁内操作）+3 测；测试缺口 4 条全补（tokenizer block/非法输入、Backoff 并发、空闲连接语义锁定：accept 超时循环不退出+挂起连接断开恢复 2 条 Rust 集成+AbortSignal 3s 中止 1 条插件侧）。自测证据：npm test 85 passed（11 files，基线 53→+32）、cargo test 58 passed（基线 34→+24；1 ignored）、npm run build 成功、tauri build 成功（.app+.dmg）、真实 opencode.db 对账（by day 13 vs 13/cost 6.075194 diff 0.00000000；by session 39 vs 39 一致；sqlite3 CLI 交叉核对）。**TC-TK-11 实测结论**：cost/tokens_* 逐 message 增量写入（非 session 结束聚合写）——进行中会话 5s 两次采样 tokens_input 58263→58748、time_updated 秒级滞后跟随；cost 可为 0（订阅/plan 模式）；新鲜度护栏 time_updated 与 idle 差 <60s 可配。遗留/裁定点：① DESIGN §4.1 SQL 写 SELECT session_id 但真实 schema 主键列名 id（实现以 id AS session_id 落地，TC-TK-06 对账按语义；如需 DESIGN 勘误由 supervisor 落笔）；② week 标签 %Y-W%W 格式 TEST-CASES 未规定；③ TC-TK-02 Windows 分支 cfg 实现实机留 M8；④ 气泡位置 pet 窗口顶部悬浮（DESIGN 未规定）；⑤ P3-⑥ 范围略宽（idle 条目也按 30s remove，显示语义不变=缺席即 idle）；⑥ cost=0 订阅会话气泡显示 $0（是否省略待裁定）；⑦ 继续移交 P3-④⑤/M8、限流豁免 /health、同桶升级放行 M5 前；⑧ TC-TK-08/09/10 UI 观察与 TC-TK-05 实跑并发需端到端验证（tauri dev 手动）。
- R1: tester 验证 **PASS**（testedSha=affe86a）。环境：macOS 26.5.2、node 24.18/rustc 1.97.1、**真实 GUI 会话**（.app 实跑 + screencapture + OCR）、opencode.db 261MB WAL（PID 94299 全程写入中）。自动化基线全复跑：npm test 85 passed（11 files）、cargo test 58 passed（1 ignored 另跑）、npm run build success、tauri build 成功、真实库对账 by day 13 vs 13/cost 6.089180 diff 0.00000000、by session 40 vs 40 diff 0。**TC-TK-01~13 全 PASS**：01 真实库探测 Some；02 canary 单测+Windows cfg 代码级（M8 实机）；03 临时 HOME 无 db → UI 提示不崩溃；04 旧格式 storage json → 升级提示不崩溃；05 只读并发（写被拒单测+WAL 写入中 10 次并发读+真实库 3 次反复只读零锁冲突）；06 与 sqlite3 CLI 同时间窗背靠背对账 diff 0（id AS session_id 语义成立）；07 四维度 group_by 单测+GUI 实测周标签 2026-W32 与 SQLite 一致；08 GUI 实测 7d/30d/自定义切换数值与同口径 SQL 一致、边界含当天；09 四区块 GUI+OCR 实测（KPI 4 卡/SVG 柱状图/饼图+列表/会话降序+点击展开逐位一致）；10 气泡正向（POST idle → 白卡片+OCR "90.1k input / 29.7k out…"与 db 吻合）；11 写入时机独立复核（逐 message 增量写：58631→63069 跨 message 递增、time_updated 秒级跟随；300k tokens 会话 cost=0 订阅模式；新鲜度护栏单测）；12 无记录不出气泡（不存在 session_id → 0 白像素+单测）；13 schema 白名单（缺列库副本 → "请升级 pulse-pet"提示不崩溃不查错列）。**遗留事项全 PASS**：P2-9（真实 install.sh 连跑 2 次不挂死+非法输入冒烟+幂等恒 1）；P2-10（先删再建走创建路径 mode 0600 实测 -rw-------）；测试缺口 4 条（block/非法输入 2 用例、Backoff 并发 3 用例、空闲连接语义 2 Rust 集成+AbortSignal 3s 1 条）；P3-①（eprintln+50ms 继续）、③（header 已删）、⑥（回收 remove 锁内+3 用例）。**无阻断缺陷（P0/P1/P2 均无）**。观察项：O1 DESIGN §4.1 SQL 列名 session_id vs 真实 schema id，建议 supervisor 勘误（实现已正确）；O2 cost=0 订阅会话气泡 $0 建议省略（非阻断优化）；O3 coder 摘要 token-stats "12 测"实为 9 测（总数一致不影响）；O4 WebKit 透明窗口合成偶发假阴性（README 已知）；O5 会话列表滚动正常。裁定点 8 条全结论：①SQL 口径成立建议落笔勘误 ②week 格式可接受 ③Windows M8 ④气泡顶部悬浮正常 ⑤P3-⑥ 范围略宽可接受 ⑥$0 建议省略 ⑦继续移交项确认未动 ⑧端到端 UI 已实测无未实测项。环境已恢复（进程 0 残留、插件卸载+opencode.jsonc 备份还原、临时目录清理、runtime 已空、git status 干净）。
- R1: committer 审查 **APPROVED**（reviewedSha=affe86a）。基线：28 文件 +2904/-46 全在 pulse-pet/ 内无越界，HEAD=testedSha=reviewedSha 三方一致，父提交 43384db 已同步 0 ahead；Cargo 仅新增 serde derive 无重依赖；npm 85 本人复跑复现，cargo 58+1 采信 tester。需求对应性：M3 四大项（路径探测/只读连接/聚合 SQL/三命令/schema 白名单/WAL 回退、Token 页四区块+7d30d自定义、气泡+success 驱动防抖动、写入时机实测+新鲜度护栏 60s、无记录不出气泡）+ 遗留（P2-9 防零消费、P2-10 mode 创建即收紧+chmod 兜底旧文件、P3-①eprintln+50ms 继续、P3-②createDeliverer 串行化、P3-③header 删除、P3-⑥锁内 remove、测试缺口 4 条）全落地有真实测试；不做项零预实现（Panel 占位 tab 文案除外）。代码质量：锁序核验无死锁（state 锁独立块释放→idle_hook 再锁→notify 再锁）、shutdown 停机语义仍成立、SQL 注入面（match 白名单+?1 绑定+硬编码字面量）、气泡文案数字格式化+sanitizeBubbleText 双保险。**无 P0/P1/P2**。P3 五条（不阻断）：①摘要偏差（token_stats.rs "20 单测"实为 18+1 ignored）；②死代码 fetchCurrentSession/token_stats_current_session 已实现注册但前端无调用方（spec §4.2 要求暴露，实现合规）；③parseStatsError 无单测（GUI 已覆盖）；④token_stats_opencode_path 返回 Option vs DESIGN Result（探测不可失败语义等价）；⑤schema-mismatch 提示"请升级 pulse-pet"出现两次。Tester 观察项裁定：O1 采纳回 spec 勘误（DESIGN §4.1 session_id→id）、O2 采纳 P3 优化非阻断（cost=0 省略 $0，非需求边界问题——TC-TK-10 未规定）、O3/O4/O5 确认。coder 裁定点 ①-⑥ 全成立/可接受。**回 spec 建议 2 条**：DESIGN §4.1 列名勘误（id AS session_id）；DESIGN §4.3 可选补"cost=0 省略 $0"约定。
- **合入（2026-08-16 用户确认）**：PR #3 已合入 develop（merge commit `99fdcc4`，`gh pr merge 3 --merge --delete-branch=false`，develop_opencode 分支保留）。**M3 任务完成，status=approved 终态。**（检查点随后提交推送 origin/develop）

## 最新验证意见原文

（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### Tester R1 报告原文（2026-08-16，testVerdict=PASS）

# PulsePet M3 Token 统计 + 遗留事项清偿 — Tester 勾验报告

## 1. 环境
| 项 | 值 |
|---|---|
| macOS | 26.5.2 (Build 25F84) |
| node | v24.18.0 |
| rustc / cargo | 1.97.1 / 1.97.1 |
| 真实 GUI 会话 | **是**（Aqua / console 用户；用 tauri build 产物 `.app` 以 `open`/直启方式跑真实会话，全程 `screencapture` 截屏 + 像素分析 + Vision OCR 验证） |
| opencode.db | `/Users/youqi/.local/share/opencode/opencode.db`（261 MB，WAL 模式，30d 窗口 40 行 / 7d 窗口 28 行）；opencode 进程全程运行中（PID 94299，验证期间持续写入） |
| 被测 commit | `affe86a3bca255a34c5f0ed03520dfac588e89a5`（分支 develop_opencode，HEAD=被测，无增量改动） |

## 2. 自动化基线（全部复跑，非引用）
| 项 | 结果 |
|---|---|
| `npm test` | **85 passed（11 files）** ✓ |
| `cargo test` | **58 passed / 0 failed / 1 ignored** ✓（ignored = 真实库对账，另行手动跑） |
| `npm run build` | success（tsc + vite build，bundle 210.8 kB）✓ |
| `npm run tauri build` | success（`.app` + `.dmg` 重新打包成功）✓ |
| cargo 真实库对账（--ignored） | by day 13 vs 13 / cost 6.089180，diff **0.00000000**；by session 40 vs 40，diff **0.00000000** ✓ |

## 3. TC-TK-01~13 逐条
| # | 用例 | 结论 | 证据 |
|---|---|---|---|
| TC-TK-01 | 路径探测（macOS） | **PASS** | 真实库对账测试输出 `db = /Users/youqi/.local/share/opencode/opencode.db`（`detect_db_path` 返回 Some）；GUI 面板实时出数。 |
| TC-TK-02 | canary / Windows | **PASS** | canary：单测 `detect_prefers_main_db_then_canary`（主库缺失→canary→主库优先）覆盖；Windows：代码级 `opencode_data_dir()` 为 `#[cfg(target_os="windows")]` + `%LOCALAPPDATA%`（src-tauri/src/token_stats.rs:85-96），实机留 M8（裁定点③）。 |
| TC-TK-03 | 数据库不存在 | **PASS** | 真实 GUI：临时 HOME（无 db）→ 面板显示"数据库未运行/未初始化：未检测到 opencode 数据库（opencode.db / opencode-canary.db）。"不崩溃；单测 `query_stats_no_db_maps_to_no_database`。 |
| TC-TK-04 | 旧版本兜底 | **PASS** | 真实 GUI：临时 HOME 构造 `storage/session/*.json` → 面板显示"检测到旧版 opencode 存储格式（storage/session/*.json）…请升级 opencode 后使用。"不崩溃；单测 `query_stats_legacy_storage_maps_to_upgrade_hint`。 |
| TC-TK-05 | 只读连接并发 | **PASS** | 单测 `readonly_connection_rejects_writes`（写被拒）+ `concurrent_reads_while_writer_active`（WAL 写事务中 10 次并发读）；**实跑**：opencode 全程 WAL 写入中，真实库对账 3 次反复开只读连接均正常，无 "database is locked"，opencode 进程不受影响（持续写入，time_updated 09:33→09:50 一路推进）。连接为 `READ_ONLY\|NO_MUTEX` 即开即关，对 db 零写入。 |
| TC-TK-06 | 聚合准确性 | **PASS** | 与 sqlite3 CLI **同一时间窗**背靠背对账：by_day 13 行 / 6.089180、by_session 40 行 / 6.089180，**与实现输出完全一致**（diff 0）。对账按语义 `id AS session_id`（裁定点①成立）。 |
| TC-TK-07 | group_by 四维度 | **PASS** | 单测 `query_stats_dispatches_group_by_and_rejects_unknown`（session/day/week/range 各返回正确行 + 非法值拒绝）；week/range 由前端传 from/to，后端无写死维度（代码审查）；GUI 实测：按天/按周/整段切换生效，周标签 `2026-W32` 与 sqlite3 `strftime('%Y-W%W')` 一致。 |
| TC-TK-08 | 时间跨度切换 | **PASS** | 真实 GUI 实测：7d 默认（KPI 4.5M/613.7k/218.9M/$3.32，会话 28，轴 2026-08-10..08-16 含当天）→ 点"近30天"（7.3M/929.6k/408.6M/$6.13，会话 40，轴 08-03..08-16）→ "自定义"单日 08-16（1.4M/244.0k/84.1M/$0.73，会话 8）——**各项与 db 同口径 SQL 一致**（微小漂移 = opencode 实时写入）。时间边界含当天 ✓。 |
| TC-TK-09 | 展示组件四区块 | **PASS** | 真实 GUI + OCR 实测：① KPI 卡 4 张（input/output/cache read/cost）② 时序图自画 SVG 柱状图（"Token 时序（按天/按周）"、轴标签、柱色 #6366f1 像素 43554，bundle 无重依赖图表库）③ 项目分布饼图+列表（`37a03d…` 99.9% / `global` 0.1% $0.0033，与 db 一致）④ 会话列表 token 降序（Top5 与 db ORDER BY 完全一致）+ **点击展开详情实测**：input 1,093,980 / output 90,256 / cache_read 56,578,176，与 db 该行逐位一致。 |
| TC-TK-10 | 气泡正向 | **PASS** | 真实 GUI：`POST /state {kind:idle, sessionId:新鲜会话}` → pet 窗口顶部出现白卡片气泡（白 1635 / 边框 #e5e7eb 1686 / 文字像素 13262）；OCR 读到 "**90.1k input / 29.7k out…**"，与当时 db 值（89.5k→90.3k 区间，实时写入）吻合。文案格式 "本期用了 Xk input / Yk output / $ Z"。 |
| TC-TK-11 | 写入时机实测 | **PASS（独立复核）** | 独立采样：进行中会话 `ses_ff7cf1c84ffe` 的 tokens_input 09:32 时 58631 → 09:34 时 63069（跨 message 递增），message 间稳定、time_updated 跟随（09:33:36→09:34:13），**逐 message 增量写入成立**；另观测到 300,783 tokens 会话 **cost=0.0**（订阅模式）。新鲜度护栏 `should_report`（time_updated 差 <60s）单测覆盖（陈旧→不出）。coder 结论复核一致。 |
| TC-TK-12 | 无记录不出气泡 | **PASS** | 真实 GUI：`POST /state idle` 带不存在 session_id → pet 顶部气泡区 **0 白像素（无气泡）**；单测 `build_idle_report_end_to_end`（无记录→None）+ 前端 `showBubble` 空文案丢弃。 |
| TC-TK-13 | schema 白名单 | **PASS** | 真实 GUI：构造缺 tokens_* 列的库副本 → 面板显示 "opencode.db schema 不兼容（session 表缺少列 [tokens_…tokens_reasoning，tokens_cache_read，tokens_cache_write]，请升级 pulse-pet）：请升级 pulse-pet。"不崩溃、不查错列；单测 `schema_missing_token_columns_rejected`（全链路拦截）。 |

## 4. 遗留事项逐条
| 项 | 结论 | 证据 |
|---|---|---|
| P2-9 tokenizer 死循环 | **PASS** | 真实 install.sh 连跑 2 次（0.59s/0.04s，不挂死）+ 真实用户配置再跑 3 次 merge 均 exit 0、managed 计数恒为 1（幂等成立）；非法输入（@/单引号/emoji）冒烟不挂死；npm 用例 `opencode-config.test.ts` 11 passed（block 注释 + 非法输入 2 条）。 |
| P2-10 mode 0600 一步到位 | **PASS** | 单测 `token_file_is_0600`（**先删再建**走创建路径，通过）；真实 app 启动即创建 `update-token`，实测 `-rw------- 600`（无 write-then-chmod 窗口）。 |
| 测试缺口·tokenizer block/非法输入 | **PASS** | opencode-config.test.ts 新增 2 用例（见上）。 |
| 测试缺口·Backoff 并发行为 | **PASS** | plugin-hook.test.ts `createDeliverer` 3 用例：并发失败不跳级（0→1000→2000）、失败后成功 reset 不误复位、killswitch/节流/null 保留。 |
| 测试缺口·服务端空闲连接语义 | **PASS** | http_server.rs 集成测试 2 条：accept 超时循环不杀服务（空转 3 周期仍响应 200）、挂起连接断开后恢复（P3-① 日志+继续）；插件侧 AbortSignal 3s 中止 1 条（plugin-http.test.ts，3001ms 实测通过）。 |
| P3-① accept Err 不静默退出 | **PASS** | 代码：`Err(e) => { eprintln!(…); sleep 50ms; }` 继续循环（http_server.rs）；挂起连接测试通过。 |
| P3-③ forbidden header 已删 | **PASS** | 代码：postState headers 无 `connection: close`（pulse-pet-hook.js）；plugin-http 测试通过。 |
| P3-⑥ session_state 回收 remove | **PASS** | 代码：tick 改为收集过期 id 后 `sessions.remove`（含 idle 条目超时清理，锁内）；3 用例通过（reclaimed 后 len=0、display()=idle 语义不变、回收后新事件可重建）。 |

## 5. coder 裁定点 8 条结论
1. **SQL 口径（session_id vs id）**：成立。真实 `PRAGMA table_info(session)` 主键列为 `id`，**无 `session_id` 列**；实现 `id AS session_id` 落地正确，与 sqlite3 CLI 对账 diff 0。建议 supervisor 落笔勘误 DESIGN §4.1（非实现缺陷）。
2. **week 标签 %Y-W%W**：可接受。经 sqlite3 `strftime('%Y-W%W')` 验证 2026-08-10/11/16 均为 `2026-W32`，实现与 SQLite 语义一致；TEST-CASES 未规定格式，无冲突。
3. **Windows cfg 分支**：代码级通过（`#[cfg(target_os="windows")]` + `%LOCALAPPDATA%`），实机验证留 M8，符合范围。
4. **气泡位置 pet 顶部悬浮**：真实 GUI 观察确认——气泡为窗口顶部居中白卡片（`top:2px`，白底+边框+文字），视觉正常，无遮挡异常。
5. **P3-⑥ 范围略宽（idle 条目也 remove）**：可接受。显示语义"缺席=idle"由 `reclaimed_sessions_are_removed_from_map` 用例锁定（remove 后 display()=idle），内存不再随 session 数无界增长，收益明确。
6. **cost=0 会话气泡显示 $0（建议）**：当前 `format_cost_usd(0)="$0"`；`should_report` 仅在有真实用量时出气泡，故 token>0 且 cost=0 的订阅会话会显示 "$0"。**建议省略 "$0"**（如仅显示 "本期用了 300.8k input / 50.3k output"），因为 coder 实测大量 token 会话 cost=0（订阅/plan），显示 $0 有"零花费"误导。**非阻断**，作为优化项。
7. **继续移交项**：确认不在本轮。P3-④⑤（install.ps1 BOM、classifyEvent permission.asked）、限流豁免 /health、同桶升级放行（M5 前定案）——本轮提交（affe86a）无相关改动，与用户 2026-08-16 确认口径一致。
8. **端到端 UI 验证程度**：**已实测**（真实 GUI 会话）。TC-TK-08/09/10/12 及 TC-TK-03/04/13 错误态均在真实 `.app` + opencode 实跑环境验证；TC-TK-05 并发以"opencode 持续写入期间反复只读查询真实库"实跑验证。**无"未实测"项**（Windows 实机除外，属 M8 范围）。

## 6. 确认缺陷与观察项
**阻断缺陷：无（P0/P1/P2 均无）**
观察项：
- **O1（文档）**：DESIGN §4.1 SQL 列名 `session_id` 与真实 schema `id` 不一致，建议 supervisor 勘误（实现已正确落地）。
- **O2（建议）**：cost=0 订阅会话气泡 `$0` 建议省略（裁定点⑥）。
- **O3（摘要误差）**：coder R1 摘要称 token-stats.ts "12 测"，实际 token-stats.test.ts 为 9 测（npm 总数 85 与摘要一致，不影响结论）。
- **O4（已知现象）**：验证中一次捕获出现 pet 窗口无白色像素（WebKit 透明窗口合成偶发/非前台），README §运行时视觉验证 已记录该假阴性；重激活后正常，非缺陷。
- **O5（UI 行为）**：会话列表为 `overflow-y:auto`，首屏仅显示表头，需滚动查看条目——正常滚动行为。

## 7. testVerdict
**PASS**

## 8. 环境恢复
- pulse-pet 进程：已全部退出（pgrep 确认 0 残留，含 `open -n` 第二实例）。
- opencode 插件：`install.sh --uninstall` 已执行，用户 `~/.config/opencode/opencode.jsonc` 已用备份原样恢复（diff 一致），`plugins/pulse-pet-hook.js` 已删除；用户 opencode 会话进程（PID 94299）全程未受影响、持续正常写入。
- 临时 HOME 目录（tk-home-empty / legacy / badschema）、截图/脚本/BMP/PNG、日志文件：已清理。
- runtime 残留：`~/.pulsepet/runtime/` 已空（token/endpoint 随 app 退出自动清除，附证 TC-EV-08 退出清理）。
- 项目工作区：`git status` 干净，仅 `.opencode/workflows/task-pulsepet-m3.md`（流程文件，非本任务改动）。

**testedSha: `affe86a3bca255a34c5f0ed03520dfac588e89a5`**

### Committer R1 报告原文（2026-08-16，reviewVerdict=APPROVED）

# PulsePet M3 Token 统计 + 遗留清偿 — Committer 审查报告

## 1. 评审对象核对
| 项 | 值 | 核对结果 |
|---|---|---|
| 被测 commit | `affe86a3bca255a34c5f0ed03520dfac588e89a5` | ✅ HEAD == testedSha == 被测 SHA，三者一致 |
| 分支 | develop_opencode | ✅ |
| 增量基线 | `origin/develop...affe86a`（父提交 43384db，已同步 0 ahead） | ✅ |
| 改动文件 | 28 个，+2904/-46 | ✅ 全部位于 `pulse-pet/` 内，**无越界文件** |
| 越界检查 | `.opencode/workflows/task-pulsepet-m3.md` 为 untracked 流程文件，**不在 commit 内** | ✅ 非本任务代码改动 |
| 依赖变更 | Cargo.toml/Cargo.lock 仅新增 `serde`（derive feature，供 TokenRow Serialize） | ✅ 无新增重依赖 |
| 独立复跑 | `npm test` 85 passed（11 files） | ✅ 本人复跑通过 |
| 独立复跑 | `cargo test` | ⚠️ 本环境 bash 仅放行 git 命令，无法独立复跑；采信 tester 权威报告（58 passed / 1 ignored，真实库对账另行手动跑 diff 0） |

## 2. 需求对应性逐项结论
| 需求项 | 结论 | 证据 |
|---|---|---|
| token_stats.rs 路径探测（macOS 主库→canary / Windows %LOCALAPPDATA%） | ✅ 落地 | token_stats.rs:85-107；TC-TK-01/02 单测 + Windows cfg 代码级（M8 实机留待） |
| 旧版本兜底探测（storage/session/*.json → 请升级 opencode，不解析不崩溃） | ✅ 落地 | token_stats.rs:109-115、351-368；TC-TK-04 |
| 只读连接 READ_ONLY\|NO_MUTEX 即开即关 | ✅ 落地 | token_stats.rs:161-169；TC-TK-05（写被拒 + WAL 写中并发读） |
| 聚合 SQL（by session / by day 按 DESIGN §4.1；week/range 前端传 from/to） | ✅ 落地 | token_stats.rs:192-327；TC-TK-06/07 |
| 三命令注册（opencode_path/query/current_session） | ✅ 落地 | token_stats.rs:476-496 + lib.rs invoke_handler |
| schema 白名单（PRAGMA table_info 缺失 → 请升级 pulse-pet，不查错列） | ✅ 落地 | token_stats.rs:131-159；TC-TK-13 |
| WAL 缺失回退"数据库未运行/未初始化" | ✅ 落地 | token_stats.rs:163-169 打开失败映射 no-database；TC-TK-03 |
| Token 标签页（KPI 4 卡 / 自画 SVG 时序 / 项目饼图+列表 / 会话降序可展开 / 7d-30d-自定义） | ✅ 落地 | TokenStats.tsx / token-chart.ts / Panel.tsx；TC-TK-08/09 |
| 气泡汇报 + success 驱动（idle+有用量→气泡；idle→查库→注入 success→统一 notify 防抖动） | ✅ 落地 | lib.rs make_idle_hook + http_server.rs:395-407；TC-TK-10 |
| M3 done ①写入时机实测（逐 message 增量写结论 + 新鲜度护栏 60s） | ✅ 落地 | token_stats.rs 模块注释:17-26 + README；TC-TK-11 |
| M3 done ②无记录不出气泡（0 行→不出气泡不显示 0/陈旧） | ✅ 落地 | should_report/build_idle_report + 前端 showBubble 空文案丢弃；TC-TK-12 |
| 遗留 P2-9 tokenizer 死循环 | ✅ 修复 | opencode-config.mjs:57-66 `if(i>start)…else i+=1` + block 注释/非法输入 2 用例 |
| 遗留 P2-10 mode 0600 一步到位 | ✅ 修复 | runtime.rs:55-77 OpenOptions.mode(0o600) 创建即收紧 + 后补 chmod 兜底旧文件 |
| 遗留 P3-① accept Err 不静默 | ✅ 修复 | http_server.rs:345-351 eprintln + 50ms sleep + 继续 |
| 遗留 P3-② Backoff 并发不跳级 | ✅ 修复 | pulse-pet-hook.js createDeliverer promise 队列串行化 + 3 用例 |
| 遗留 P3-③ forbidden header 删除 | ✅ 修复 | pulse-pet-hook.js:226-230 删除 connection:close + 断言更新 |
| 遗留 P3-⑥ session_state 回收 remove | ✅ 修复 | session_state.rs:138-152 锁内 remove + 3 用例 |
| 测试缺口 4 条补齐 | ✅ 落地 | tokenizer block/非法输入、Backoff 并发、空闲连接语义 2 Rust 集成 + AbortSignal 1 条 |
| **不做项零预实现**（M4 调度器/烟花、M5 atlas、M6 穿透/拖拽/热键、M7 todo、v2 排行榜、旧格式完整解析、CI workflow） | ✅ 零预实现 | diff 28 文件无任何上述模块；Panel.tsx 的 reminders/settings/todo 均为占位 tab 文案 |

## 3. 代码质量要点
**P0 / P1 / P2 级缺陷：无。**
锁序核验（关键路径）：`handle_incoming` 中 state 锁在独立块内释放 → idle_hook 再锁 state 注入 Success → notifier.notify 再锁 —— 无死锁（http_server.rs:396-406）。http_server 停机语义：`shutdown()` 走 AtomicBool 标志 + 循环顶部检查，P3-① 移除 `Err→break` 后停机仍成立（http_server.rs:273-275、330-352）。SQL 注入面：`group_by` 走 match 白名单、`session_id` 走 `?1` 参数绑定、`day_expr` 为硬编码字面量，无拼接注入。气泡文案仅由数字格式化生成 + 前端 `sanitizeBubbleText` 双保险。

以下为 P3 级（不阻断，留痕）：
1. **[P3] 摘要偏差**：coder R1 摘要称 token_stats.rs "20 单测 + 1 ignored"，实际 18 单测 + 1 ignored（19 个 `#[test]`）。与 O3 同类的摘要计数误差，不影响总数（cargo 58+1 与 34→+24 精确吻合）。
2. **[P3] 死代码** `pulse-pet/src/lib/token-stats.ts:97`：`fetchCurrentSession` + Rust 命令 `token_stats_current_session`（token_stats.rs:494）已实现/注册但前端无调用方——气泡链路走 Rust idle hook 内部 `current_session`（token_stats.rs:385），Token 页走 `token_stats_query`。属 spec §4.2 要求暴露的命令（实现合规），但 TS 封装为未消费代码。
3. **[P3] 测试缺口** `pulse-pet/src/lib/token-stats.ts:51`：`parseStatsError`（错误码解析，错误态 UI 关键路径）无单测（token-stats.test.ts 9 测不含它）。GUI 端到端已覆盖 TC-TK-03/04/13，纯函数层缺覆盖。
4. **[P3] 签名微偏** `pulse-pet/src-tauri/src/token_stats.rs:477`：`token_stats_opencode_path` 返回 `Option<PathBuf>`，DESIGN §4.2 写作 `Result<Option<PathBuf>, String>`。探测不可失败，语义等价，无害。
5. **[P3] 文案冗余** `TokenStats.tsx:42` + `token_stats.rs:155`：schema-mismatch 提示 "请升级 pulse-pet" 出现两次（errorHint 包裹 + err.message 内自带），tester OCR 已观察到。纯文案，无功能影响。

## 4. 测试质量结论
新增用例均为真实行为覆盖，**非空转**：
- Rust token_stats：路径探测 3 态、legacy 兜底、schema 白名单（含全链路拦截）、四维聚合（浮点近似比较）、只读拒绝写、WAL 写中并发读、气泡新鲜度护栏（陈旧/全零/无 time_updated 三态）、端到端 build_idle_report（含无库静默）；真实库对账为 `#[ignore]` 手动项。
- 前端：格式化边界（0/1000/百万/负 cost）、时间跨度含当天、KPI 汇总、柱状图比例/零值 NaN 防护/全零、饼图占比和 100%/单项 100% 两段弧、气泡 8s 自动隐藏（fake timers）+ 计时重置 + 手动清除。
- 遗留：P2-9 直接验证死循环修复（非法字符跑完即证推进）+ 幂等；createDeliverer 3 测真实验证串行化交错顺序（post/wait 严格交替、0→1000→2000 不跳级、reset 不误复位）；AbortSignal 实测 3002ms。
计数一致性：npm 85（11 files）复现 ✅；cargo 58+1 采信 tester ✅。**摘要两处计数偏差**：token-stats "12测"→9（O3）、token_stats.rs "20单测"→18+1 ignored（本报告 P3-1）。

## 5. Tester 观察项 O1-O5 逐条裁定
- **O1（DESIGN §4.1 SQL 列名 session_id vs 真实 schema id）**：**采纳，回 spec 勘误**。实现以 `id AS session_id` 落地正确，真实 PRAGMA 主键列为 id，对账 diff 0。属文档勘误（supervisor 落笔），非实现缺陷。
- **O2（cost=0 会话气泡 $0 建议省略）**：**采纳，作为 P3 优化项，不阻断**。订阅/plan 模式大 token 会话 cost=0 时显示 "$0" 有"零花费"误导。**非需求边界问题**——TC-TK-10 文案 "$ Z" 未规定 cost=0 时是否省略，实现行为未与验收标准矛盾；属 UX 改进，建议（可选）回 spec 补约定。
- **O3（摘要 12 测 vs 9 测）**：**确认**。总数一致不影响结论；另发现 token_stats.rs "20 单测" 实为 18（见 P3-1）。摘要精度应修正。
- **O4（WebKit 透明窗口合成偶发假阴性）**：**认可非缺陷**，README 已记录，重激活恢复。
- **O5（会话列表滚动）**：**认可非缺陷**，`overflow-y:auto` 正常滚动。

## 6. coder 遗留裁定点 ①-⑥ 逐条裁定
1. **① SQL 口径（id AS session_id）**：**成立**，建议 supervisor 落笔勘误（同 O1）。
2. **② week 标签 %Y-W%W**：**可接受**。与 SQLite `strftime('%Y-W%W')` 语义一致，TEST-CASES 未规定格式，无冲突。
3. **③ Windows cfg 分支**：**代码级通过**（`#[cfg(target_os="windows")]` + %LOCALAPPDATA%），实机验证留 M8，符合范围。
4. **④ 气泡位置顶部悬浮**：**认可**，真实 GUI 视觉正常。
5. **⑤ P3-⑥ 范围略宽（idle 条目也 remove）**：**可接受**。"缺席=idle"显示语义被 `reclaimed_sessions_are_removed_from_map` 锁定，内存不再无界增长，收益明确。
6. **⑥ cost=0 $0 显示**：**见 O2**，建议省略（P3 优化，非阻断）。

## 7. reviewVerdict
**APPROVED**
无 P0/P1/P2 阻断缺陷。M3 四大项 + 并入遗留事项（P2-9/P2-10/P3-①②③⑥ + 测试缺口 4 条）全部实现且有真实测试覆盖；不做项零预实现；改动全部限定在 pulse-pet/ 内；HEAD == testedSha；测试基线复现（npm 85 本人复跑，cargo 58+1 采信 tester）。
遗留 P3 观察项（1 摘要偏差 / 2 死代码 / 3 parseStatsError 无单测 / 4 签名微偏 / 5 文案冗余）与 O2 优化建议均**不阻断交付**，可留待后续或随 M4 顺带清偿。

## 8. 回 spec 建议清单（需 supervisor 落笔）
1. **DESIGN.md §4.1**（by session SQL）：列名 `session_id` → `id`（真实 schema 主键列名），或注明实现以 `id AS session_id` 别名落地（O1，勘误）。
2. **DESIGN.md §4.3**（可选，采纳 O2 时）：补充 "cost=0（订阅/plan 模式）时气泡省略 $0 段" 的约定。

**交付阶段说明**：当前为纯审查结论（POC 约定不自动合入）。如需我落 PR 审查留痕，请提供 PR 编号/确认在 develop_opencode 上执行 `gh pr review`，我将核验 evidence manifest 完整性（双 SHA 与 HEAD 一致）后再放行留痕。
