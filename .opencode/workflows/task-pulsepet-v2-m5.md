---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-m5
target: pulse-pet
coderTaskId: ses_fbf33918dffeE2tlZ1L1srIsTK
testerTaskId: ses_fbf1306f9ffeZJy2FGRa7o3zXw
committerTaskId: ses_fbe7f0e6cffeOQ9a282i1IqB5g
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: ca2b6006a3dca4884a3a3ab626da7f3ad6e24c89
reviewedSha: ca2b6006a3dca4884a3a3ab626da7f3ad6e24c89
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [pulse-pet/src-tauri/src/transcript.rs, pulse-pet/src-tauri/src/token_stats.rs, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/i18n.rs, pulse-pet/src/lib/token-stats.ts, pulse-pet/src/lib/token-stats.test.ts, pulse-pet/src/lib/token-chart.ts, pulse-pet/src/lib/token-chart.test.ts, pulse-pet/src/lib/i18n.ts, pulse-pet/src/lib/i18n.test.ts, pulse-pet/src/lib/claude-code-hook.test.ts, pulse-pet/src/panel/TokenStats.tsx, pulse-pet/src/pet/todayToken.ts, pulse-pet/src/styles/global.css, pulse-pet/src/styles/tokens.css, pulse-pet/opencode-plugin/claude-code-hook.js, pulse-pet/opencode-plugin/claude-code-hook.d.ts]
endReason: null
createdAt: 2026-08-26T23:30:05+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-08-27T12:58:11+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-pulsepet-v2-m5: PulsePet v2 M5——Token by agent（CC transcript 解析 + 统一视图 + CC 汇报）

## 任务原文

用户原文（2026-08-26）："聚焦pulse-pet项目，开始V2版本M5阶段的开发工作"

实施 **V2-DESIGN §5（已终审定稿 2026-08-23，§5.11 两轮评审 P1×1/P2×6/P3×16/N×7 全部采纳）**：M5 Token by agent，落 M2 设计系统之上。

**权威文档**：
- 设计：`pulse-pet/docs/v2/V2-DESIGN.md` §5.0~§5.10（Spike S1~S8 事实基线 + §5.0 裁定汇总）
- 范围：`pulse-pet/docs/v2/V2-SCOPE.md` §3.5（数据源/cost 口径/统一视图/汇报气泡）
- 验收用例：`pulse-pet/docs/v2/V2-TEST-CASES.md` 五、TC-M5-01~10

**前提回填（R8 例程徽标可行性）**：TC-M4-08 已实测确认 `--title "pulsepet 例程: …"` 保留（M4 R1 tester 报告："--title 未被自动摘要覆盖，R8 可行性成立"，132 md 真实例程）——**可行性前提成立，按主方案实施**（§5.2 title.startsWith 前缀匹配 + ⚡ 徽标），备选方案（spawn 时间窗 + cwd 粗匹配）不启用。

**范围（按 V2-DESIGN §5.1~§5.6）**：

1. **数据层：Rust 新模块 `transcript.rs`（§5.2）**——扫描/解析/文件级缓存，产出与 TokenRow 同构的会话行：
   - `transcript_scan(dir)`：递归一层 `*.jsonl`，**排除 `memory/` 子目录**（P3-5）；`parse_session(path)` 单文件解析（坏行跳过不崩，防御式：未知行类型跳过、usage 缺字段按 0）
   - **message.id 去重（S3 最大发现）**：assistant 行收集 (message.id, 快照)，**按 message.id 去重、按行序取最后一条**（勿按 timestamp——尾行可能无 ts）；id 缺失行按行级顶层 uuid 兜底去重、两者皆缺独立计入（P3-4）——不去重 token 直接翻倍
   - SUM 五维 usage：`input_tokens`→input、`output_tokens`→output、`cache_creation_input_tokens`→cache_write、`cache_read_input_tokens`→cache_read、`output_tokens_details.thinking_tokens`→reasoning（S2）
   - model 取最后一条 message.model（纯字符串非 JSON）；title = 首条 `type=="user"` 且 content 为 string 的行截断（**`chars().take(60)`**，中文按字符——P3-13），无 → sessionId 前 8 位
   - project = **首条含非空 cwd 的行**的 cwd → basename（P2-6：snapshot 行稀释防御，非众数）；全无 cwd → None（回退标签）
   - time_created/time_updated = **首/末条含 timestamp 的事件行**（P1-1：mode/last-prompt/file-history-snapshot 等非事件行无 ts，按字面首末行取值会得 None → CC 行被时间过滤剔除+汇报永不触发）；UTC ISO8601 带 Z → epoch ms 本地口径统一转换（S5）
   - **last_assistant_ts** = 末条 assistant 行 timestamp（N-1 护栏专用字段——分组/过滤用 time_updated，护栏只看 assistant 行；实测末条 system 行晚于末条 assistant 3 分钟，护栏用 time_updated 会误判静置会话为新鲜）
   - **TranscriptCache**（managed state，**窗口创建循环之前 manage `Arc<Mutex<TranscriptCache>>`**——issue #9 铁律 + N-5，照 session_state 的 Arc 模式）：`Mutex<HashMap<PathBuf, (mtime, size, CcSessionRow)>>`（P2-1：查询命令与 CC idle hook 双方访问）+ **`HashMap<String, PathBuf>` sessionId 索引**（P2-2：idle hook 只有 (agent, session_id)，从事件无法推导 munged 项目目录路径）；查询时 mtime+size 未变直接用缓存、变了重解析；无常驻 watcher（查询驱动懒解析）；缓存缺失时（首查/idle 先于查询）由 scan 补建
   - 目录探测：`~/.claude/projects`（Windows `%USERPROFILE%\.claude\projects`）；目录不存在 → CC 源整体缺席（**静默**，不报错不提示，Token 页自然只显示 opencode）
2. **双源容错（C1 裁定 + N-4 承载定案）**：opencode 源报错（no-database/legacy-storage/schema-mismatch）而 CC 源有数据时，`token_stats_query`/`token_stats_today` **降级返回 CC-only 结果**；返回体**包装为 `{rows: Vec<TokenRow>, degraded: Option<String>}` / `{today: TodayStats, degraded: Option<String>}`**；兼容承诺修正为「**单源场景行为不变**」：CC 缺席时 rows/degraded 行为与 M3 单测钉住的原样一致（degraded 仅在 CC 有数据时为 Some）；**degraded 横幅仅 panel**（TokenStats.tsx 顶部细横幅），pet 侧三层（悬停卡/菜单/追加段）**静默显示 CC-only 数值、不呈现 degraded**（宠物不打扰原则）；双源全缺才走既有错误路径（M3「无库→—」语义保留给全缺态）
3. **查询双源化与 agent 维度（§5.3）**：`TokenRow` 增 `agent` 字段（opencode 恒 `"opencode"`）；`query_by_session` 与 CC 缓存会话行合并（时间倒序统一排序）；`query_grouped`（day/week）opencode SQL `GROUP BY day_expr, agent, model_id` + CC 侧 Rust 内存按 `day × agent × model_id` 聚合（本地日转换 S5）；**week 标签复刻 SQLite `%Y-W%W` 语义**（自定义纯函数：周一起始的日历年周号——**勿用 chrono `iso_week()`**，ISO 年周与 `%W` 跨年边界分叉致双源同周拆柱，P2-4）；`query_by_range` CC 按 `agent × model_id` 聚合（P3-6 明示）；`token_stats_today` 双源合计（opencode SQL 当日聚合 + CC 缓存当日过滤求和）——M3 三层快捷查看自动覆盖 CC；`build_idle_report` 不动（opencode 专用，CC 汇报走新函数）
4. **CC 会话汇报气泡（§5.4，M1 预留位兑现）**：CC hook Stop → `/state(idle, agent=claude-code)` → idle_hook 分支（http 请求线程仅做派发、**解析在后台线程**——N-3：`std::thread::spawn` 线程内直接完成「解析（缓存未命中 scan 补建）→ 护栏判定 → apply + emit」，不 join 回 http 线程；AppHandle/State 的 Arc 均 Send 可移入）→ 经 TranscriptCache sessionId 索引定位文件 → 新鲜度护栏（**last_assistant_ts 距 idle 事件 < 60s**，对齐 opencode 口径）→ 五维有非零用量 → ① apply_event（**复合键 `claude-code:{sessionId}`**，P2-5）+ notify 注入 success 状态 ② 气泡「本期用了 Xk input / Yk output」**无 cost 段**（S4 口径）+「 · 今日 T」追加段（token_stats_today 双源合计，与 opencode 同模板）；无记录/全零/陈旧 → 静默跳过（TC-TK-12 口径）；气泡经 `pulsepet://bubble`（info 级 source="token-report"，与 opencode 汇报同源同级，M2 同源合并 10s 窗口防双发）；**竞态诚实口径（P2-3 修订）**：护栏只防「陈旧」不防「尾行未 flush」——Stop 先于 transcript 尾行落盘时解析结果可能**欠计最后一条 message**（接受，对齐 R3「截至上次快照」；可选增强：idle 后延迟 1-2s 再查一次，实施时按实测决定）
5. **CC hook 工具级气泡（§5.5，M3 R7 兑现）**：`claude-code-hook.js` 照抄 M3 协议（`detail="tplId:param"`）：PreToolUse Edit/Write/MultiEdit/NotebookEdit → `edit`（file_path → basename）；Bash → `bash`（剥 KEY=value + 首词 basename，M3 强化规则同款）；Read → `read`（basename）；Grep/Glob → `search`（pattern 净化 ≤40）；WebFetch/WebSearch → `web`（url/query → hostname）；**一次性进程不做文件级节流**（M1 §1.3.2 裁定延续——App 侧 10s 同源合并即节流，detail 桶概念仅存在于 opencode 常驻插件）；发布联动：CC hook 变更随 App 重装（M1 安装器内嵌单一来源，无手动重装负担）
6. **Token 页 UI（§5.6，M3 预留位落实）**：
   - **agent 筛选 chip 第二组**（M3 `filter-row` 多组容器设计兑现）：`opencode` / `claude-code` 两 chip（**有数据的 agent 才渲染**），默认全勾；作用域**仅柱图**（与模型筛选一致，M3 E 口径）；`computeStackedBars` 的 `agentFilter` 参数位填实现（M3 N12 单测钉子已在）
   - **会话列表**：增 agent 标识微列（`oc` / `cc` 等宽小字徽标，i18n title 提示全名）；**例程 ⚡ 徽标**：`title.startsWith("pulsepet 例程:")` → 标题前 ⚡ 图标（title 属性「定时任务例程」，零 schema 改动）；CC 行标题 = 首 prompt（§5.2）
   - **费用 KPI 卡**：副行小字「仅 opencode」（CC 恒 0 口径标注）；会话列表 CC 行 cost 列显示 `—`
   - 深浅主题：新增元素全走 token（M2 系统）
7. **i18n**：`token.agent.*`（chip/列徽标）、`token.costOpencodeOnly`、`token.taskBadge`、CC 汇报气泡模板（zh/en；Rust 侧 build_cc_idle_report 模板入 i18n.rs）；zh/en 键集合一致（完备性测试守护）

**CC 行字段**：`agent: "claude-code"`（常量）、`cost: 0.0`（S4 口径：数据层恒 0，展示层 CC 显示 `—`）、model_id、title、project_name、五维 token、时间戳——与 opencode 会话行同构。

**AgentAdapter 收口（SCOPE §5.4 遗留，本里程碑裁定：不收口）**：token 源实现留在 Rust（token_stats.rs=opencode / transcript.rs=claude-code），TS `AgentAdapter.tokenSource` 维持声明性；记录于不采用（§5.10）。

**数据库：零迁移**（TranscriptCache 纯内存；无新表新列）。

**不含（§5.1/§5.10）**：M6 抢镜（气泡 agent 标识 UI 属 M6，M5 只备数据）、子代理感知（isSidechain，彩蛋池，数据已留）、CC 自配单价表估算 cost、字节偏移增量解析（文件级缓存等价）、transcript watcher 常驻、AgentAdapter 收口、CC 会话气泡 agent 标识（属 M6）、双源同名 basename 歧义处理（同口径同缺陷，记录 P3-16）。

**开发纪律**：分支 develop_opencode（当前 d51ba9c = origin/develop_opencode，与 origin/develop（5cf0d67，PR #16 合入后）无差异，开工先 fetch + merge origin/develop 确认无新提交）；提交信息 `[task-pulsepet-v2-m5] R<n>`；cargo 网络用 CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false；新代码日志一律 plog!（不新增 eprintln!）；每轮验证证据必含 tauri build 成功 + 产物时间戳；`token_stats_query`/`token_stats_today` 改 async fn + 扫描/解析进 spawn_blocking（IPC 契约不变）；CC idle 解析线程内直接 apply+emit 不 join；窗口创建前 manage TranscriptCache（issue #9）。

**R2 修订（2026-08-27 用户反馈 R1 偏差，方案 A 已确认）**：Token 时序筛选改两级交互——① agent 维度 tab（分段单选，Settings `theme-seg` 同款 `role="radiogroup"` + `seg active`）置于「Token 时序（按日/按周）」标题 `<h3>` 右侧同一行：选项 = **「全部」（恒显，默认选中）** + 仅有数据的 agent（无数据不渲染；仅一个 agent 有数据时「全部」仍并列恒显）；② 模型复选框组保留在 filter-row（唯一一组）：选中「全部」→ 列双源模型并集；选中具体 agent → 收窄为该 agent 有数据的模型；切换 tab 时模型勾选**重置为全选**；③ 作用域仍仅柱图（M3 E 口径），KPI/会话列表不随 tab 变化；④ R1 的 agent 复选框第二组移除，noAgents 空态不可达（移除或降为防御分支），模型空集口径不变；⑤ `computeStackedBars` agentFilter 语义适配（具体 agent = 单元素集 /「全部」= 不传或全量集）；⑥ i18n 新增 `token.agent.all`（zh「全部」/ en "All"），zh/en 键集合一致。验收口径见 V2-TEST-CASES TC-M5-04/TC-M5-10（已由 supervised-coding 修订落笔）。R2 起新开 coder 会话（旧 coderTaskId 于新会话返回后覆盖）。

## 验收标准（V2-TEST-CASES 五、TC-M5-01~10 + V2-DESIGN §5.8）

- **TC-M5-01 transcript 解析（单测，tempdir 注入）**：① message.id 去重（6 行含 thinking/text 重复行 → 3 条 SUM，按行序取末条——S3 回归钉子；id 缺失按顶层 uuid 兜底、两者皆缺独立计入）② 五维映射 ③ 坏行/空文件/非 JSON 行跳过不崩（防御式、usage 缺字段按 0）④ **时间戳取自首/末条含 timestamp 的事件行（P1-1 钉子）**（mode/last-prompt 包夹首末行不影响）；UTC ISO8601 → epoch ms 本地（跨日边界注入时区断言）⑤ **week 标签复刻 %W 语义（P2-4）**：2026-12-28 / 2027-01-01 / 2027-01-04 跨年对齐断言 ⑥ title 首 prompt 截断（**中文 60 字符**）/无 prompt 回退 sessionId 前 8 位 ⑦ project = 首条含非空 cwd 行 basename（含无 cwd snapshot 行稀释 fixture，P2-6）/全无 → None ⑧ **last_assistant_ts** = 末条 assistant 行（护栏专用，与 time_updated 两口径分离）⑨ `memory/` 子目录排除；目录不存在 → 空结果静默
- **TC-M5-02 缓存与索引（单测）**：① TranscriptCache（`Arc<Mutex<...>>`，窗口创建前 manage——issue #9）：`(mtime, size)` 缓存命中不重解析/变了重解析/CC 原子写 tmp+rename 落位新 mtime → 缓存自动失效 ② sessionId → PathBuf 二级索引（idle hook 只有 (agent, session_id) 可定位文件）；缓存缺失首查/idle 先于查询由 scan 补建 ③ 无常驻 watcher（查询驱动懒解析）
- **TC-M5-03 双源查询与统一视图（实机）**：① 真实 CC 会话（本机 DataAgent 项目存量）→ 今日/7d 出现 CC 会话行（首 prompt 标题 + `cc` 徽标 + cost `—`）② KPI 总量含 CC（grouped 行 SUM 全 agent 合计）；费用卡「仅 opencode」标注可见 ③ day/week 聚合增 agent 维度（GROUP BY day,agent,model_id + CC 内存聚合 concat）；range 维 agent×model_id ④ 模型 chip 双源同模型自然归并（deepseek 系跨 agent 合法）⑤ CC 行与 opencode 行时间倒序统一排序；`token_stats_query`/`token_stats_today` 为 async fn + spawn_blocking（IPC 契约不变）⑥ **三层交叉断言双源复验**：会话静止窗口内悬停卡 = 面板今日 KPI = 右键菜单——均含 CC 双源合计（同 0 点起点 + mock 过滤 + reasoning 不计）；degraded 态下悬停/菜单静默显示 CC-only 数值不呈现横幅。观察项记录级：R2 MB 级首次解析延迟体感、R7 TZ 显式设置双源同日拆柱（不判失败）
- **TC-M5-04 agent 筛选（实机）**：① chip 仅渲染有数据的 agent（默认全勾）② 只勾 opencode → **柱图剔除 CC 数据**，KPI/会话列表不变（M3 E 口径）；`computeStackedBars` agentFilter 参数位填实现（M3 N12 钉子扩展：勾选剔除/不传=全量）③ agent 空集空态复用 M3 模型空集口径
- **TC-M5-05 CC 会话汇报气泡（实机 + 单测）**：① 气泡「本期用了 Xk input / Yk output · 今日 T」**无 cost 段**；今日段 = token_stats_today 双源合计（与 opencode 同模板）；`pulsepet://bubble` info 级 source="token-report"（10s 同源合并防双发）② 新鲜度护栏：**last_assistant_ts 距 idle < 60s**；文件缺席/无 assistant 行/全零/陈旧 → 静默跳过 ③ apply_event 复合键 `claude-code:{sessionId}` + notify；idle 分支 http 线程仅派发、解析在后台线程（不阻塞派发）④ opencode 会话汇报无回归（双发同源合并）⑤ 竞态诚实口径（P2-3）：护栏只防陈旧不防尾行未 flush（欠计接受；可选 1-2s 延迟复查按实测决定）⑥ 单测：`build_cc_idle_report`（护栏消费 last_assistant_ts/全零静默/无 cost 段文案）
- **TC-M5-06 CC 工具级气泡（实机 + 单测）**：① M3 协议照抄：「正在编辑 X」「正在跑 npm」同模板同 ambient ② 单测：`extractDetailParam` CC 工具族五类平移（Edit/Write/MultiEdit/NotebookEdit→edit basename；Bash→剥 KEY=value + 首词 basename；Read→read；Grep/Glob→search；WebFetch/WebSearch→web hostname）③ 一次性进程不做文件级节流（M1 先例延续）——App 侧 10s 同源合并即节流；合并键 `tool:<tpl>` 跨 agent 共桶（双 agent 同工具 10s 内一条，R6 接受）④ 开关对双 agent 统一生效；CC hook 随 App 重装更新 ⑤ **R8 边界复核**：CC 播报同样不含路径/参数/URL 原文（TC-SEC 口径目验；App 侧 param 再净化为格式级兜底，路径剥除责任由 CC hook param 提取层继承——照抄 M3 规则即继承同等责任）
- **TC-M5-07 例程 ⚡ 徽标（实机，前提已回填）**：M4 定时任务跑一次 opencode run → Token 页新会话标题前 ⚡（`title.startsWith("pulsepet 例程:")`；title 属性「定时任务例程」）；零 schema 改动
- **TC-M5-08 CC 缺席回退（实机）**：临时改名/删除 `~/.claude/projects` → 安静回退 opencode-only——无错误横幅、无 degraded 字段（rows 原样 + degraded=None，**单源场景行为与 M3 单测钉住的原样一致**——N-4 兼容口径回归）
- **TC-M5-09 双源容错 degraded（实机 + 单测）**：① 临时改名 opencode.db（CC 有数据）→ Token 页 CC-only 数据 + 「opencode 源不可用」细横幅（仅 panel 顶部不遮蔽内容）；返回体 `{rows,degraded}`/`{today,degraded}` ② **pet 三层（悬停卡/菜单/追加段）静默显示 CC-only 数值、不呈现 degraded**（宠物不打扰）③ 恢复后正常（双源齐全横幅消失）④ 双源全缺 → 既有错误路径（M3「无库→—」语义保留）⑤ 单测：opencode 错 × CC 有数据 → Ok(CC-only)+degraded=Some；CC 缺席 → rows 原样+None（M3 回归）；双源全缺 → 既有错误码透传
- **TC-M5-10 主题与双语目验（实机）**：深/浅主题 + zh/en 目验新增元素——agent chip / cc 徽标 / ⚡ / 费用卡标注 / cost `—` / degraded 横幅全走 M2 token；新键（`token.agent.*`/`token.costOpencodeOnly`/`token.taskBadge`/CC 汇报模板）zh/en 集合一致
- 回归基线：npm test（vitest 375 基线 + 新增）全绿；cargo test（279+1 ignored 基线 + 新增，含 transcript/token_stats/token-chart）全绿；tsc 0；npm run build / tauri build（产物时间戳）成功；TC-M3 三层快捷查看 + TC-M4 汇报气泡回归（同源合并不回归）；既有纯函数测试不破坏

## 需求确认
- [x] 用户已确认（确认后 status=implementing）——2026-08-26 23:32 用户确认：M5 范围照 V2-DESIGN §5 定稿执行（TC-M5-01~10 验收口径）；R8 前提已由 M4 回填按主方案；遗留事项处置照清单（P3-5 继续移交打磨轮、目验 7 项继续待反馈、其余维持原去向）；无范围调整
- 历史遗留事项清单：（supervised-coding 扫描 task-pulsepet-v2-m1/m2/m3/m4 检查点汇总，默认并入本任务，见 README §4.6）

## 遗留事项（跨任务移交）

- [ ] **v2-m2 实机目验 7 项（来源 task-pulsepet-v2-m2 经 v2-m3/m4 移交，去向=用户反馈）**：TC-UI-01 主题三档 / TC-UI-03 面板壳+芯片 / TC-UI-06 双 agent 芯片跟随 / TC-UI-07 功能管理禁用 Todo 全链路 / TC-UI-10 气泡排队实机 / TC-UI-11 气泡与右键菜单视觉 / TC-UI-12 四 tab 对照样例目验——**继续待用户反馈**（发现问题随本轮修复；无反馈继续移交）
- [ ] **v2-m2 P3-5（经 v2-m3/m4 移交，去向=M5 或打磨轮——动 atlas.rs 时顺手清）**：atlas.rs AtlasData Clone derive 死代码——M5 范围（§5.7 变更表）不动 atlas.rs，继续移交打磨轮
- [ ] **v2-m2 P3-6~10（去向注明，不并入）**：P3-6 notice 重复计算 + P3-7 禁用语汇四套不一致（CSS/微打磨轮）；P3-8 插件开关失败静默 + P3-9 panel://tab 冷启动竞态（UX 观察项）；P3-10 Rust 命令错误串未 i18n（M8 类约定扩展时）
- [ ] **v2-m1 遗留（去向已注明，不并入）**：A 实机验证类（多屏/Windows，具备硬件时）；B v0.1.3 收尾用户目视验收（待用户反馈）；C v0.1.3 Release publish（待用户指示）；D 观察项（默认不动）
- [ ] **M4 新移交（2026-08-26 终审 committer 定级，去向已注明，不并入）**：P3① logging.rs ends_with("x"×64) 残余竞态（打磨轮——测试专用助手持全局 slot 锁内轮转或删 ends_with 只留 len>=）；P3② action_exec.rs:622-635 注释块复制粘贴重复（打磨轮顺手清）；P3③ 理论双记账边界（记录级，不修）；Windows 实机观察项（TC-M4-18 与 TC-INT-13 同批，具备硬件时）
- 注意：TC-M4-08 已回填 R8 可行性前提（--title 保留），本任务按主方案实施（见任务原文）
- [x] **事故环境清理（2026-08-27 10:33 事故残留）**：✅ 已执行（11:19，用户裁定"按建议做"，来源 INC-20260827-1033）——① vite dev server（pid 41765）已终止；② pp-v2-test-cc-sandbox 假 CC fixture 已删除（projects 下仅剩真实两目录）；③ after-crash 库三件套**留档一周**（至 2026-09-03 审计后删）
- [x] **TC-M5-08/09 实机改名类步骤安全修订（事故整改）**：✅ 已落笔（11:19，用户裁定，V2-TEST-CASES.md 五、两处修订注记）——live rename 改**用户人工执行**，agent 禁触 `~/.local/share/opencode` 与 `~/.claude` 变更，注记引用 INC-20260827-1033；单测路径不受影响。**衍生未了项**：tester 派工词禁区清单待下轮测试派工时启用（supervised-coding）；mv/rm 权限加固**用户裁定暂不做**（2026-08-27 11:19）
- [ ] **事故报告与留档（来源 INC-20260827-1033）**：报告已存 `.opencode/incidents/INC-20260827-1033-opencode-db-rename-crash.md`；after-crash 库三件套留档至 2026-09-03，到期确认无用后删除
- [ ] **TEST_BUG real_db_reconciliation_manual（来源 R2 tester 2026-08-27，非阻断）**：src-tauri manual 冒烟测试（ignored，不在 301+3i 基线内）参考 SQL 仍 DESIGN §4.1 旧口径（GROUP BY day,project_id + 全量 session），未随 M5 `GROUP BY day,agent,model_id`+mock 过滤更新——by day 83 vs 30 / by session 210 vs 214，cost 双向一致证明数据无错。去向=下轮 coder 顺手修或打磨轮
- [ ] **实机验收缺口 4 项（来源 R2 tester，去向=用户人工配合）**：① TC-M5-08 CC 缺席回退（mv ~/.claude/projects）；② TC-M5-09 实机三步（degraded 横幅/恢复/双缺）；③ TC-M5-05 CC 汇报气泡（真实 CC 干活后 Stop）；④ TC-M5-06 CC 工具级气泡实机。tester 报告内附人工步骤清单（操作 ~/.local/share/opencode 与 ~/.claude 前务必完全退出 opencode——INC 教训）
- [ ] **committer P3×4（来源 R2 committer 终审 2026-08-27，去向=打磨轮，不阻断）**：P3-1 transcript.rs:208-210 注释块复制粘贴重复（删一行）；P3-2 transcript.rs:590-624 assert_ne!(本地日,UTC日) 硬假设非零时区偏移（TZ=UTC 环境会红——去 assert_ne 或 TZ 注入，保留 oracle 对账）；P3-3 TokenStats.tsx:521 symmetricToggle 注释「模型/agent 共用」过时（R2 后仅模型用）；P3-4 token_stats.rs:709-712 TranscriptCache 全目录解析在 Mutex 持有期执行（观察项：文件体量增长时改锁内判定+锁外解析）
- [ ] **文档滞后 2 项（来源 R2 committer 需求边界问题，轻度非代码缺陷，去向=文档维护轮，supervised-coding/用户处置）**：① V2-DESIGN §5.6 仍写「agent 筛选 chip 第二组」（R1 形态）与 R2 修订口径（tab 单选两级筛选）矛盾；② V2-TEST-CASES TC-M5-03-2「费用卡副行」措辞与实际（M4 移除 cost 卡后为 KPI 区注释小字）不一致

## 轮次记录
- R1: coder 完成（2026-08-27 00:03 交付，coderTaskId=ses_fc14b8f73ffejpX0TPskNsg7az），commit `6d7a1c7`（`[task-pulsepet-v2-m5] R1: Token by agent——CC transcript 解析与缓存 + 双源查询/degraded 容错 + CC 汇报气泡 + agent 筛选/徽标 UI + CC hook 工具级 detail`）+ `a70d3a6`（`[task-pulsepet-v2-m5] R1: CC idle 后台线程 apply+notify 成对（success 状态即时推送，不依赖 1s tick 兜底）`），commit 前 fetch 确认 origin/develop=5cf0d67 无新提交；supervised-coding 已核验 HEAD=a70d3a6、领先 origin/develop 恰 2 提交、17 files +2134/−88、工作区干净仅流程文件（.opencode/ 与 images/ 未提交）。改动七块：**transcript.rs 新 1000+ 行**（transcript_scan 递归一层排除 memory/；parse_session message.id 去重按行序取末条/uuid 兜底/独立计入；五维 usage 映射；P1-1 首末含 ts 事件行；chars(60) 中文标题；首 cwd basename；last_assistant_ts 两口径分离；sqlite_week_label 复刻 %W；TranscriptCache SystemTime 纳秒 mtime+size 缓存 + sessionId 二级索引 + refresh/find_session 补建）；**token_stats.rs**（TokenRow +agent；SQL 三查询 'opencode' AS agent + GROUP BY day,agent,model_id；QueryResponse/TodayResponse 包装；query_stats_dual/today_stats_dual C1/N-4 三态容错；CC 内存聚合 day/week/range；build_cc_idle_report 护栏消费 last_assistant_ts 无 cost 段；两命令 async fn + spawn_blocking + State）；**lib.rs**（cc_cache Arc<Mutex<...>> 窗口创建前 manage；idle_hook CC 分支 http 线程只派发、std::thread::spawn 后台解析→护栏→apply+notify+emit 不 join；复合键 claude-code:{sessionId}）；**i18n.rs**（cc_token_report zh/en 无 cost 段+双语单测）；**前端**（token-stats.ts TokenRow+agent+AGENT 常量+{rows,degraded}/{today,degraded} 解析；token-chart.ts agentFilter 参数位填实现；TokenStats.tsx agent chip 第二组有数据才渲染默认全勾作用域仅柱图+oc/cc 徽标+⚡ 例程徽标+CC cost —+degraded 细横幅；todayToken.ts 消费 {today,degraded} 只取 today pet 静默；i18n.ts token.agent.*/costOpencodeOnly/taskBadge/degraded/chart.noAgents/aria.agent zh/en；global.css/tokens.css degraded 横幅/徽标/⚡/--warn token 双主题）；**claude-code-hook.js + .d.ts**（M3 detail 协议照抄五类工具族 extractDetailParam/buildDetail + PreToolUse POST 附带 detail）。自测：cargo test **301 passed+3 ignored**（279+1i 基线 +22 测试 +2 手动 ignored 对账）；npm test **383/27**（375+8）；tsc 0；npm run build ✓；tauri build 成功（PulsePet.app @00:03:10/dmg @00:03:10）；关键钉子 TDD 红→绿：S3 去重（红测 1222≠611 翻倍捕获）、P1-1 时间戳双钉子、%W 跨年（2026-12-28→W52/2027-01-01→W00/2027-01-04→W01 与 SQLite localtime oracle 逐点对账 ≠ISO W53）、degraded 三态（opencode 错×CC 有数据降级/CC 缺席 rows 与 M3 query_stats 逐字段相等回归/双源全缺错误码透传）、缓存命中/原子写失效/sessionId 补建/memory 排除/中文 60 字符/快照稀释/UTC 跨日双 oracle；实机冒烟：真实 ~/.claude/projects 11 文件 11 会话全解析成功（真实 231e3997 双写行 in=24395 未翻倍）、双源查询 session 141 行（cc=11）/day 37（cc=3）/week 21（cc=2）/range 14（cc=1）/today 双源合计 degraded=None、App 启动三窗口正常无 panic。裁定点 5 条（详见下）：① 费用 KPI 卡与「仅 opencode」标注——M5 文档写「费用卡副行」但用户 2026-08-25 M4 R1 已裁定移除 cost KPI 卡（现行四卡 UI，totalSub 清退），实现以 KPI 区注释小字承载 token.costOpencodeOnly 标注、CC 行 cost 列/详情显示 —，**待 committer 裁定是否按文档字面重建** ② pet 三层→两层（悬停卡 2026-08-25 已移除），现行 pet 侧=右键菜单+idle 追加段两层静默消费双源合计 ③ degraded 判定口径：CC「有数据」= 扫描到 ≥1 可解析会话文件（与查询窗口无关），opencode 任何 StatsError 在 CC 有数据时均降级（比设计列举三类错误码更一般，语义兼容）④ cargo test --release 下 logging 轮转 flaky 属 M4 遗留打磨轮项（debug 档 301 全绿非本任务引入）⑤ 竞态诚实口径 P2-3 未做 1-2s 延迟复查（观察项，单测覆盖逻辑）。**待验对象=a70d3a6（提交链 6d7a1c7→a70d3a6）**。status=implementing→testing，调 Tester。

- R2: 用户反馈 R1 需求偏差（2026-08-27 09:15）——agent 筛选应为两级（标题右侧 tab 单选 + 模型复选框联动），R1 两组复选框并排混杂；方案 A 确认（tab 含「全部」恒显默认选中、模型复选框联动收窄、切换重置全选、作用域仅柱图不变）；V2-TEST-CASES TC-M5-04/TC-M5-10 已由 supervised-coding 修订；按用户指示新开 coder 会话（不复用 R1 task_id，返回后覆盖 coderTaskId）；status=implementing，round=2
- R2 coder 交付（2026-08-27 09:37，**新会话 coderTaskId=ses_fbf33918dffeE2tlZ1L1srIsTK，旧 id 已按用户指示覆盖**），commit `ca2b600`（`[task-pulsepet-v2-m5] R2: Token 时序两级筛选——agent 维度 tab 单选（标题右侧 radiogroup，「全部」恒显默认）+ 模型复选框联动收窄（切换重置全选、数据刷新回落全部）；移除 agent 复选框组与 noAgents 空态（zh/en 键同步清退）`），R1 两提交之上，fetch 确认 origin/develop=5cf0d67 无新提交；6 files +200/−78（token-chart.ts：computeModelChips 增 agentFilter 参数 + 新 agentsWithRows 纯函数；token-chart.test.ts +2 测试；i18n.ts +token.agent.all、token.aria.agent 调整、noAgents zh/en 清退；i18n.test.ts 键清单更新+钉子断言；TokenStats.tsx：selectedAgents Set→agentTab 单选（null=全部）、.token-chart-head 标题行 radiogroup、切换重置模型全选、刷新回落、删 agent 第二组与 noAgents 分支；global.css：.token-chart-head 同行布局 wrap 兜底）。**Rust 零改动**（src-tauri 0 文件，未跑 cargo test）。自测：TDD 红→绿（4 红测：agentFilter 收窄/agentsWithRows 缺失/agent.all 缺键/noAgents 未清退）；npm test **386 passed**（R1 基线 383 + 3 新增，stash 复测确认无回归）；tsc 0；npm run build ✓；tauri build 成功（app @09:33:46 / dmg @09:34:07）；**DOM 级自测**（playwright + mock `__TAURI_INTERNALS__` 双源数据，TC-M5-04 逐条）：初始全部[checked]+chips 并集全选、切 Claude Code→chips 收窄+柱图 9.0k+**KPI 恒 13.6k 会话列表不变**、切 opencode→勾选重置全选、range 维整体隐藏、移除 CC 数据刷新→tab 回落「全部」、深色主题 tab 样式命中。口径说明一项：agent tab 具体项显示 i18n 显示名（"Claude Code"）而非裸标识串（agentLabel 未知 agent 回退原串）。supervised-coding 已核验 HEAD=ca2b600、6 文件与报告一致、pulse-pet/ 工作区仅余本任务用例文档修订（V2-TEST-CASES.md 未提交，交付时随检查点一并提交）。status=testing
- **R2 测试轮事故（2026-08-27 10:33，重大）**：tester 会话（ses_fbf1306f9ffeZJy2FGRa7o3zXw，09:54 启动，验收至 TC-M5-03 DOM 阶段）执行 TC-M5-09 步骤 1 时于 10:33:17 执行 `mv ~/.local/share/opencode/opencode.db opencode.db.m5test.bak`——**该库是正在运行的全部 opencode 会话（含 tester 自身与 supervised-coding）的实时存储**，20ms 后数据库层雪崩（part/session 查询失败→disk I/O error），所有会话崩溃，supervised-coding 的 Task 调用收到 interrupted，tester 验收报告未出（testerTaskId 保持 null）。数据损失：恢复会话确认内容完整至 10:32:05，10:32:05–10:33:17 约 72s 的消息随旧 WAL 丢失不可找回。用户 10:36 重启 opencode（生成空新库），10:36–10:46 恢复调查会话取证（opencode.db.after-crash.db 留档），10:47 用户退出后执行 restore-old-db.sh 归位 1.6GB 原库，恢复完成。代码与检查点无损（HEAD=ca2b600 未变）。**根因（supervised-coding 11:13 复盘）**：① TC-M5-09 用例设计自指危险——"临时改名 opencode.db" 把 agent 运行时自身的实时库当成被动数据文件；② supervised-coding 派工词仅要求"测完恢复原状"，未禁止/替换该操作（责任在派工）；③ 权限门失效：external_directory 询问 7s 后被放行（门只覆盖目录访问语义，覆盖不了"改名"动作），bash 通配 allow 对 mv 无拦截；④ tester 无沙箱隔离（真实 HOME 运行）。**环境残留待清理**：nohup vite dev server（pid 41765，09:27 起）、~/.claude/projects/pp-v2-test-cc-sandbox 假 CC fixture（污染真实 Token 视图）、after-crash 库三文件（留档可后删）。**整改待用户确认**：TC-M5-08/09 实机改名类步骤改人工执行或沙箱化（文档修订）+ tester 派工词加禁区清单 + mv/rm 类权限加固。status=incident_review；测试轮需在新用例口径下重跑（round 保持 2）
- **事故处置（2026-08-27 11:19，用户四项裁定）**：① 环境清理已执行（vite pid 41765 已杀 + pp-v2-test-cc-sandbox 假 fixture 已删）；② TC-M5-08/09 安全修订已落笔 V2-TEST-CASES.md（live rename 改用户人工执行、agent 禁触 ~/.local/share/opencode 与 ~/.claude，注记引用 INC-20260827-1033）；③ 权限加固用户裁定**暂不做**；④ 事故回溯报告落盘 `.opencode/incidents/INC-20260827-1033-opencode-db-rename-crash.md`（含完整时间线/根因/整改表）。status=incident_review → testing（事故闭环，等待重跑测试轮；重跑派工将启用禁区清单，TC-M5-08/09 实机步骤转用户人工执行）
- **R2 测试轮续接（2026-08-27 11:25，用户指示）**：测试轮**不作废**——复用事故前 tester 会话（testerTaskId 由 null 回填为 ses_fbf1306f9ffeZJy2FGRa7o3zXw，其上下文完整至 10:32:05，进度：cargo/npm/构建已验、DOM 测试至 TC-M5-03 会话列表 cc 徽标行）。续接派工要点：① 事故通报（INC-20260827-1033，tester 执行 TC-M5-09 旧步骤 mv opencode.db 致全部会话崩溃，约 72s 数据丢失）；② **禁区清单**（~/.local/share/opencode 与 ~/.claude 禁一切变更；项目目录+临时沙箱外禁 mv/rm/写）；③ TC-M5-08/09 已修订（live rename 转用户人工，tester 跳过实机操作部分只跑单测路径）；④ 环境变化告知（vite 已杀、假 CC fixture 已删不得重建、pp-m5-dom mock 资产应仍在）；⑤ 用户要求聚焦重点用例尽快收尾，事故前已验部分可引用不重跑。status=testing（继续）
- **R2 测试轮续接重试（2026-08-27 11:33）**：11:25 首次续接调用被用户取消——tester 恢复后调 Vision 子代理做截图目验时卡死（Vision 流卡住非首次：事故前 10:33 同症状）。重试调整：派工词**禁用 Vision 子代理**，截图类目验（TC-M5-10 主题等）降级为 DOM/CSS 断言（getComputedStyle/class 命中/boundingBox，coder R2 自测同款方法）；其余续接要点不变（事故通报/禁区清单/TC-M5-08/09 修订口径/环境变化/聚焦收尾）。仍复用 testerTaskId=ses_fbf1306f9ffeZJy2FGRa7o3zXw
- **R2 tester 交付（2026-08-27 11:36，续接会话，testVerdict=PASS）**：testedSha=ca2b600（零代码改动），报告全文见「最新验证意见原文」。结论：TC-M5-01/02/03/04/07/09(单测)/10 全 PASS（cargo 301+3i、npm 386、tsc 0、tauri build 产物在位）；TC-M5-04 两级 tab 逐条 DOM 断言过（含真实数据复核）；TC-M5-03 三端闭环（manual 冒烟+sqlite 直查+真实面板，KPI 948.9M vs 直查 950M 吻合）；未执行不判失败：TC-M5-05/06 实机触发（需真实 CC 活跃会话，开新 CC 会话触禁区）、TC-M5-08 实机、TC-M5-09 实机三步（均需用户人工配合，tester 已给人工步骤清单）。**非阻断 TEST_BUG**：real_db_reconciliation_manual（ignored manual 冒烟，非基线）参考 SQL 仍 DESIGN §4.1 旧口径未随 M5 GROUP BY day,agent,model_id 更新——行数差异为预期行为变更、cost 双向一致，已记遗留事项。执行纪律：全程未碰禁区、未用 Vision、自起进程已清理（http.server/playwright/PulsePet）、63 张截图留档 pp-m5-dom/ 供人工复核。status=testing（待 committer 评审）
- **committer 终审（2026-08-27 12:44，committerTaskId=ses_fbe7f0e6cffeOQ9a282i1IqB5g，reviewVerdict=APPROVED）**：reviewedSha=ca2b600…=testedSha=HEAD（三方一致，supervised-coding 已复核 HEAD）。P1/P2 零项；P3×4（打磨轮级，已记遗留事项）：P3-1 transcript.rs:208 注释重复、P3-2 transcript.rs:590 assert_ne 时区假设（TZ=UTC 环境会红）、P3-3 TokenStats.tsx:521 symmetricToggle 注释过时、P3-4 token_stats.rs:709 锁内解析观察项。需求边界问题 2 项（轻度、非代码缺陷、不阻断）：① V2-DESIGN §5.6 文字滞后（仍写"agent chip 第二组"=R1 形态，与 R2 修订矛盾——文档维护轮回改）；② TC-M5-03-2 费用卡副行措辞滞后（M4 移除 cost 卡后实为 KPI 区注释小字）。关键语义核验全过：R1 Rust（S3 去重 HashMap 覆盖/P1-1/%%W 公式对账/C1-N-4 逐行钉子/issue #9 order_nails 源码级钉子/hook 五类规则逐分支对照）、R2 前端（两级状态机/agentFilter N12/作用域/i18n 清退）、工程纪律（无 eprintln!/无 debug 残留/双主题 token）。tester TEST_BUG 去向采纳（下轮顺手修或打磨轮）。**双通过达成：testVerdict=PASS + reviewVerdict=APPROVED + SHA 三方一致 → status=approved**，待用户裁定是否交付（交付=同步 origin/develop→push develop_opencode→PR base=develop→gh pr review 留痕→evidence manifest 入 PR description）
- **用户交付裁定（2026-08-27 12:48）**：确认交付。**范围修正：流程文件暂不交付**——检查点/用例修订（V2-TEST-CASES.md 工作区版）/事故报告/incidents 等一律不提交，coder 只推送自己产出的 3 commit（6d7a1c7/a70d3a6/ca2b600）；实机验证 4 项后续再做（遗留事项在案）。交付链启动：① coder（复用会话）同步 origin/develop→push develop_opencode→gh pr create（base=develop）；② committer（复用会话）gh pr review 留痕；③ coder 把 evidence manifest JSON 写入 PR description；④ 汇报合入请求（不自动合入）
- **交付① coder push+PR（2026-08-27 12:51）**：fetch 确认 origin/develop=5cf0d67 无新提交；push 成功 `d51ba9c..ca2b600 develop_opencode`；**PR #17** 已创建（https://github.com/yq3/lab/pull/17，base=develop，标题"pulse-pet v2 M5: Token by agent（CC transcript 双源 + 统一视图 + CC 汇报 + agent tab 两级筛选）"，body 含概述/3 commit/测试证据/流程文件不随 PR 注记）；工作区流程文件原样未提交（status 核验：supervised-coding.md/V2-TEST-CASES.md 修改 + incidents//workflows 检查点/blog 草稿/images 均在）。待：committer gh pr review 留痕 → coder evidence manifest 入 PR description
- **交付② committer PR 评审留痕（2026-08-27 12:54）**：PR #17 只读核对与终审对象五项全一致（base=develop@5cf0d67/head=ca2b600/恰 3 commit/17 files/+2268−100）；**self-approve 被 GitHub 拒绝**（PR 作者与 committer 同账户 yq3）→ 降级提交 **COMMENT 型 review**（2026-08-27T04:53:45Z 落 PR），正文含 reviewVerdict=APPROVED/P1P2 零/reviewedSha/tester 证据交叉核验/P3×4 清单/需求边界 2 项/实机待办 4 项/self-approve 限制注记——正式 APPROVE 状态可由用户在 PR 页手动点或合入时视为放行。未 merge 未改 PR 未推分支
- **交付③ evidence manifest（2026-08-27 12:55）**：PR #17 description 末尾追加 `## Evidence Manifest` JSON 节（taskId/commits/head=ca2b600…/base=develop@5cf0d67/testVerdict=PASS/reviewVerdict=APPROVED/双 SHA/evidence 全字段/4 项实机转人工 per INC-20260827-1033/流程文件排除注记，deliveredAt=12:54:54+0800 实时取值）；原 body 26 行逐字保留，仅末尾追加。**交付链三步完成（PR #17 待用户 merge）**

- **交付④ PR 合入（2026-08-27 12:58，用户指示）**：`gh pr merge 17 --merge`（沿用 #16 merge commit 惯例）→ **MERGED** @2026-08-27T04:57:59Z，merge commit `2ef7543`；fetch 确认 origin/develop 5cf0d67→2ef7543（ca2b600/a70d3a6/6d7a1c7 三 commit 入 develop）。**task-pulsepet-v2-m5 全流程闭环**（R1→事故→R2→测试→终审→交付→合入）；本地 develop_opencode 未动，流程文件仍在工作区未提交（后续任务或文档维护轮处置）

### 遗留事项清偿/移交汇总（交付回写，2026-08-27 12:55）
- **本轮清偿**：① R1 agent 筛选需求偏差（R2 方案 A 修正，用户验收口径）；② INC-20260827-1033 事故整改：环境清理（vite/假 fixture）+ TC-M5-08/09 安全修订落笔；③ M5 主体全部交付（R1 三块 + R2 修正，双通过 + PR #17）
- **本轮新移交**：① TEST_BUG real_db_reconciliation_manual（下轮 coder 顺手修或打磨轮）；② committer P3×4（打磨轮）；③ 文档滞后 2 项（文档维护轮，supervised-coding/用户处置）；④ 实机验收缺口 4 项（用户人工后续：TC-M5-08/09 实机 + TC-M5-05/06 实机触发）；⑤ tester 沙箱资产 pp-m5-dom/（63 截图，供人工复核后可清）
- **继续移交（历史）**：v2-m2 实机目验 7 项（待用户反馈）；v2-m2 P3-5/P3-6~10（去向已注明）；v2-m1 遗留 A~D（去向已注明）；M4 P3①②③ + Windows 观察项（打磨轮/具备硬件时）；after-crash 库留档至 2026-09-03

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### R2 用户反馈原文（2026-08-27，需求偏差修正依据）
> 聚焦于pulse-pet项目，继续V2版本M5阶段的开发工作，之前coder已经完成了R1轮的开发，但是我发现开发结果有点偏差，我的意图是，token时序可以按照两个维度去筛选，一个是模型维度，另一个是agent维度，而现在coder开发出来的是把这两类维度混杂在一起了。所以应该先有一个tab切换agent维度（放在"token时序"标题右边，类似于setting里面切换深色浅色主题那种tab），切换完agent维度之后，下面才是复选框去选择模型维度。不要用task_id调用之前的coder，新开一个coder，告诉他必要的上下文，等他返回结果之后把检查点文档里面旧的task_id覆盖掉。

> 等一下，我刚才的陈述有点问题，这样就没法全选所有agent了。emmm，你有什么建议么？

> 就这么办（→ 方案 A：agent tab 含「全部」项恒显、默认选中；模型复选框跟随所选 agent 联动收窄、切换重置全选；作用域仍仅柱图）

### R2 tester 报告原文（2026-08-27 11:36 交付，续接会话，testVerdict=PASS）
（supervised-coding 注：以下为 tester 返回报告逐字原文，未删改；恢复/续审时给 coder 的依据以此为准）

# PulsePet v2 M5 验收测试报告（task-pulsepet-v2-m5，R1+R2 合并产物，首次测试轮）

**testedSha：`ca2b6006a3dca4884a3a3ab626da7f3ad6e24c89`**（HEAD 未变，测试中零代码改动；工作区仅流程文件修订 + 截图留档资产在 /var/folders 沙箱）

**执行方式说明**：中断恢复后按续接指示——全程未调用 Vision；目验项降级为 DOM/CSS 断言（playwright + mock `__TAURI_INTERNALS__` 包装页）与真实数据层断言（cargo manual 冒烟 / sqlite3 immutable 直查）；真实 App 截图 63 张留档 `pp-m5-dom/` 供用户人工复核。**严格遵守禁区：未对 `~/.local/share/opencode` 与 `~/.claude` 做任何变更操作**。

---

## 逐 TC 结论

### TC-M5-01 transcript 解析（单测）— **PASS**
`cargo test`：**301 passed, 0 failed, 3 ignored**（R1 基线 + transcript 新增全绿）。关键钉子逐一确认存在且通过：
- S3 去重：`m5_s3_dedup_by_message_id_last_line_wins`（按行序取末条）+ `m5_s3_dedup_fallback_to_uuid_then_independent`
- P1-1 时间戳：`m5_p1_timestamps_from_first_last_event_rows`（首末含 ts 事件行）+ `m5_utc_epoch_ms_is_tz_independent_instant`
- P2-4 week 标签：`m5_week_label_matches_sqlite_percent_w_across_years`（跨年 2026-12-28/2027-01-01/2027-01-04）
- 其余：`m5_bad_lines_skipped_and_empty_file_none`（防御式）、`m5_title_chinese_60_chars_and_fallback`、`m5_project_first_cwd_basename_with_snapshot_dilution`（P2-6）、`m5_p1_two_timescale_separation`（last_assistant_ts 与 time_updated 两口径分离）、`m5_scan_excludes_memory_and_missing_dir_is_empty`

### TC-M5-02 缓存与索引（单测）— **PASS**
`m5_cache_hit_reuses_without_reparse`（mtime+size 命中不重解析）/ `m5_cache_atomic_tmp_rename_invalidates`（tmp+rename 自动失效）/ `m5_cache_session_index_locate_and_rebuild`（sessionId 索引 + scan 补建）全绿。

### TC-M5-03 双源查询与统一视图（实机）— **PASS**（数据层 + DOM + 真实面板三端闭环）
- **真实 CC 数据**（本机 DataAgent + lab 存量）：`real_cc_transcripts_manual` ok——扫描 11 文件=11 会话（memory/ 排除），各会话五维 + model=deepseek-v4-pro + project=lab/DataAgent-main/cc-sandbox + 真实首 prompt 标题；
- `real_dual_query_manual` ok——7d 窗口四维均含 CC 行：session 145 行（cc=11）、day 42 行（cc=3）、week 21 行（cc=2，标签 2026-W34/W33）、range 14 行（cc=1）；today 双源合计 `input=790063 output=110683 cache_read=34913413 cost=0.4271`；
- **真实面板**（截图留档 real-23~40）：7d KPI 948.9M（sqlite3 immutable 直查同窗 950M 吻合）；模型 chips 5 个（含 CC 模型归并）；agent tab 出现 Claude Code；点 CC tab → chips 收窄为仅 deepseek-v4-pro 652.2k（真实 CC 数据全为该模型）、**KPI 保持 948.9M 不变**；柱图 7 柱、x 轴 2026-08-21~08-27；费用卡标注「费用仅统计 opencode（Claude Code 无可靠费用数据）」可见；
- **两层交叉断言**：右键菜单「今日 token：42.7M」（10:07 截图）vs 面板今日 KPI 44.0M（10:11）——同一 `token_stats_today` 双源合计口径，差值由活跃会话持续写入（DB 直查 today 10:23=54.0M，增长轨迹吻合），口径一致；
- **观察项**（记录级不判失败）：R2 首次解析延迟——11 文件全量解析毫秒级未感知；R7 TZ 分叉——本机无显式 TZ 环境，未观察；
- ⚠️ 会话列表真实 cc 行：160 行列表滚动定位未最终截到（cc 行总量 147k-652k 在列表中部），但 DOM mock 已断言 cc 徽标/cost—/标题渲染 + manual 测试确认数据在列，闭环成立；截图留档供复核。

### TC-M5-04 agent 筛选（实机，R2 修订口径）— **PASS**（DOM 断言逐条）
mock 双源数据（KPI 应恒 21.5k）：
- ① `role="radiogroup"` + `role="radio"` + `aria-checked`，置于「Token 时序（按天）」`<h3>` 同一行（`.token-chart-head` display:flex、align-items:center、radiogroup 在 head 内——getComputedStyle 断言）；「全部」恒显默认选中；ocOnly 场景 Claude Code 不渲染；单 agent 时「全部」仍并列；
- ② 切 Claude Code：chips 1 个（deepseek-v4-pro 11.5k）、柱图 max 17.5k→9.0k、**KPI 恒 21.5k、会话（5）不变**；切 opencode：chips=该 agent 模型并集且**全选（重置）**；
- ③ 取消勾选后切回「全部」→ 并集恢复且重置全选；
- ④ range 维：radiogroup/筛选/柱图整体隐藏，KPI+会话列表保留；
- ⑤ 刷新回落：选中 Claude Code → mock 切 ocOnly → 刷新 → 回落「全部」选中、CC tab 消失；
- ⑥ `computeStackedBars` agentFilter 参数位：token-chart.test.ts 新增测试在 npm test 386 全绿内；
- 真实数据复核：面板 7d 中 CC tab 联动收窄 + KPI 不变（见 TC-M5-03）。

### TC-M5-05 CC 会话汇报气泡 — **PASS（单测⑥）** + 实机部分未执行（限制说明）
- 单测 `m5_build_cc_idle_report_guardrail_and_no_cost_segment`：文案 `"本期用了 58.3k input / 910 output"`、`!text.contains('$')` 无 cost 段（S4）、今日段双源合计、全零/陈旧（last_assistant_ts >60s 护栏）/文件缺席 → None 静默，全绿；
- 实机：真实 CC 会话为历史存量，无实时 Stop 窗口；且新开 CC 会话会写 `~/.claude`（禁区）——**未执行，需用户人工配合**（真实 CC 干活后结束会话观察气泡）。

### TC-M5-06 CC 工具级气泡 — **PASS（单测②）** + 实机部分未执行
- `claude-code-hook.test.ts`（25 tests 全绿）：extractDetailParam 五类平移——Edit/Write/MultiEdit/NotebookEdit→edit basename；Bash 剥 KEY=value+首词 basename（`FOO=secret npm run build`→npm、`/opt/homebrew/bin/npm test`→npm）；Read→read；Grep/Glob→search 净化 ≤40；WebFetch/WebSearch→web hostname；buildDetail 协议 `web:example.com`；
- ③④ 代码层确认：CC hook 一次性进程无文件级节流（App 侧 10s 同源合并即节流）；开关对双 agent 统一生效（App 侧过滤）；R8 边界=CC hook 提取层继承 M3 净化规则（单测钉住）；
- 实机：需真实 CC 会话触发工具调用，同 TC-M5-05 限制——未执行。

### TC-M5-07 例程 ⚡ 徽标（实机，前提已回填）— **PASS**
- DOM mock：`title="pulsepet 例程: 数一下 md 文件"` 行渲染 ⚡（`session-task-badge`，title=「定时任务例程」）✓；
- 数据层：sqlite3 immutable 直查 opencode.db 确认 **6 个真实「pulsepet 例程:」会话**（md计数/权限测试/权限测试2，2026-08-26 00:31-00:53 = M4 验收产物），在 7d 窗口内 → 真实数据必命中 `title.startsWith("pulsepet 例程:")` 匹配；
- 实机滚动未最终截到 ⚡ 行（列表定位不准），截图留档供复核；不阻塞。

### TC-M5-08 CC 缺席回退（实机）— **未执行——需用户人工配合**（安全修订口径）
agent 禁触 `~/.claude`。建议人工步骤：① 完全退出相关 agent 会话后 `mv ~/.claude/projects ~/.claude/projects.bak` → ② 打开 Token 页观察：安静 opencode-only、无横幅、无 degraded 字段 → ③ `mv` 恢复。单源行为 = M3 钉住原样已由 `m5_degraded_cc_absent_rows_unchanged_m3_regression` 单测覆盖（见 TC-M5-09）。

### TC-M5-09 双源容错 degraded — **PASS（单测⑤路径）** + 实机三步未执行（需用户人工配合）
- 三态单测全绿：`m5_degraded_opencode_error_with_cc_data_degrades`（opencode 错 × CC 有数据 → Ok(CC-only)+`degraded=Some`，query+today 双路径、CC cost 恒 0）、`m5_degraded_cc_absent_rows_unchanged_m3_regression`（CC 缺席 → rows 与 M3 钉住**逐行相等** + `degraded=None`）、`m5_degraded_both_missing_error_passthrough`（双源全缺 → ERR_NO_DATABASE 透传）；
- DOM mock：degraded 场景 → panel 顶部细横幅「opencode 源不可用：仅显示 Claude Code 数据」（title=原始错误串）+ CC-only 数据（KPI 9.0k）+ 无错误态；**pet 右键菜单「今日 token：9.0k」无任何 degraded 文案**（宠物不打扰原则）；
- 实机三步（改名 opencode.db 等）→ 已按 INC-20260827-1033 修订标记**未执行**，人工步骤见文末。

### TC-M5-10 主题与双语目验 — **PASS**（DOM/CSS 断言）
- zh：全部/Claude Code/opencode、Token 时序（按天）、费用仅统计 opencode（Claude Code 无可靠费用数据）；
- en：All/Claude Code/opencode、Token timeline (By day)、Cost covers opencode only (no reliable Claude Code cost)；
- dark：`data-theme=dark`、`.token-chart-head` flex+center 同行布局断言命中、session-agent 徽标色 rgb(174,184,196)（深色 token 生效）；
- 新键完备性：i18n.test.ts 键集合断言在 npm test 386 全绿内（token.agent.all / costOpencodeOnly / taskBadge / degraded / cc 汇报模板 zh/en 一致）；截图留档 token-dark-zh.png / token-light-zh.png。

---

## 非阻断发现（TEST_BUG，报 coder 修）

**`real_db_reconciliation_manual`（ignored manual 冒烟测试）FAILED**（src/token_stats.rs:1939）：
`by day: rows 83 vs 30 | cost diff 0.00000000`、`by session: 210 vs 214 | cost diff 0.00000000`。该测试为 M5 新增（M4 不存在），参考 SQL 仍是 DESIGN §4.1 旧口径（`GROUP BY day, project_id` + 全量 session），未随 M5 的 `GROUP BY day, agent, model_id` 与 mock 过滤口径更新——行数差异正是 TC-M5-03③ 的预期行为变更，cost 双向完全一致证明数据无错。归类 **TEST_BUG**（参考口径过时），且为 ignored manual 测试、不在验收基线（301+3i）内，不阻断。

## 总判定

**testVerdict = PASS**

- 必测项：全部 PASS（单测基线 301+3i / 386 全绿；tsc 0；tauri build 产物 R2 09:33:46 在位；TC-M5-01/02/04/07/09/10 全项通过，TC-M5-03/05/06 单测+数据层+DOM 全过）
- 未执行项（不判失败，由 supervised-coding 裁量）：TC-M5-05/06 实机触发（需真实 CC 活跃会话）、TC-M5-08 实机、TC-M5-09 实机三步

## 用户人工配合步骤清单（如需补齐实机缺口）

1. **TC-M5-08**（CC 缺席回退）：确认无重要 agent 会话依赖后 `mv ~/.claude/projects ~/.claude/projects.bak` → 打开 Token 页观察（预期：opencode-only、无横幅、无 degraded）→ 立即 `mv` 恢复。
2. **TC-M5-09**（degraded）：完全退出 opencode 后 `mv ~/.local/share/opencode/opencode.db <备份名>`（CC 有数据）→ 打开 Token 页/宠物右键菜单（预期：panel 顶部细横幅 + CC-only 数据；菜单静默 9.0k 级数值）→ 退出后恢复原库（**务必先完全退出 opencode 再操作**，吸取 INC-20260827-1033 教训）。
3. **TC-M5-05/06 实机**：在 DataAgent 项目开真实 CC 会话干活（编辑/跑命令）后结束 → 观察「本期用了 Xk input / Yk output · 今日 T」气泡（无 cost 段）；工具调用时观察「正在编辑 X」ambient 气泡。
4. （可选复核）真实面板 7d 会话列表中部可见 ⚡ 例程行与 cc 徽标行——截图已留档 `pp-m5-dom/real-31~40`。

## 环境备注

- HEAD=ca2b600 未变；测试零代码/文档改动；`src-tauri/tests/` 无残留（探测文件已删）
- 已清理自起进程：vite（用户已杀）、http.server 1431、playwright daemon+Chrome、PulsePet app；沙箱资产 `pp-m5-dom/`（mock 包装页 + 63 张截图 + swift 点击工具）保留供审计
- 事故遗留（非本次产生）：`opencode.db.after-crash.db` 留档至 09-03（用户处置中）
- 测试环境：macOS，单屏 1470x956 points（截图 2x）；真实 CC 存量 11 会话（DataAgent 5 + lab 3 + 已删沙箱 3 中剩余真实 2 项目）；opencode.db 1.6GB 恢复完好

### R2 committer 终审报告原文（2026-08-27 12:44 交付，reviewVerdict=APPROVED）
（supervised-coding 注：以下为 committer 返回报告逐字原文，未删改）

# Committer 终审报告 — task-pulsepet-v2-m5（HEAD `ca2b600`，基线 origin/develop `5cf0d67`）

**审查对象**：R1（`6d7a1c7`+`a70d3a6`）+ R2（`ca2b600`）三 commit 全量 diff（17 files +2268/−100；R2 单独 diff 6 files +200/−78，与检查点记录逐项一致）。HEAD 与检查点 `testedSha=ca2b6006a3dca4884a3a3ab626da7f3ad6e24c89` 完全一致；工作区仅流程文件（V2-TEST-CASES.md 修订注记、supervised-coding.md、检查点、incidents/、images/）未提交，无代码混入。tester 报告与实现交叉核验：301+3i / 386 / tsc 0 / tauri build 证据链可信。

## 1. 问题清单

**P1：无。**
**P2：无。**

**P3（建议，打磨轮处理，不阻断交付）：**

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| P3-1 | `src-tauri/src/transcript.rs:208-210` | 注释块复制粘贴重复：「// 按行序取末条：直接覆盖（S3）」连续出现两次（中间夹 usage5_of 调用） | 删一行注释（与 M4 遗留 P3② 同款，打磨轮顺手清） |
| P3-2 | `src-tauri/src/transcript.rs:590-624`（`m5_utc_epoch_ms_is_tz_independent_instant`） | `assert_ne!(本地日, UTC日)` 硬假设「本机时区非零偏移」——在 TZ=UTC 环境（未来 CI/其他开发者）该测试会红；跨日断言的实际保障来自 SQLite localtime oracle 对账（另一条 assert 已足够） | 去掉 assert_ne 段或改为 TZ 注入（保留 oracle 对账与 chrono Local 一致性断言） |
| P3-3 | `src/panel/TokenStats.tsx:521`（`symmetricToggle` 注释） | 注释「模型/agent 筛选共用」已过时——R2 后 agent 改单选 tab，symmetricToggle 仅模型用 | 注释改回「模型筛选专用」 |
| P3-4 | `src-tauri/src/token_stats.rs:709-712`（`query_stats_dual`/`today_stats_dual` 的 cache refresh） | TranscriptCache 全目录 IO+解析在 Mutex 持有期间执行（查询命令与 CC idle 后台线程共享同锁）——当前 11 文件实测毫秒级无感（R2 观察项已记录），无死锁风险 | 记录级观察：若 CC 会话文件体量增长，可锁内只做 (mtime,size) 判定、解析移锁外 |

## 2. 关键语义核验结论（对照审查重点）

**R1 Rust 侧** — 全部通过：
- `parse_session`：message.id 去重按行序取末条（HashMap 覆盖语义 ✓）、uuid 兜底、双缺独立计入（`\0line-{seq}` 唯一键）；P1-1 首/末含 ts 行（含 system 行，与 S6 事件行定义一致）；`last_assistant_ts` 与 `time_updated` 两口径分离（单测钉住 3 分钟 system 行形态）；`sqlite_week_label` 公式 `(yday+7-wday)/7` 与 SQLite %W 逐字节对账（2026-W52/2027-W00/2027-W01 跨年钉子 + 实机 SQLite oracle 双测）；chars(60) 中文截断；memory/ 排除；目录缺席静默。
- `TranscriptCache`：(mtime,size) 命中/失效/rename 落位失效三测齐全；sessionId 二级索引 + find_session 首查补建；消失文件 entries+index 双清退。
- `token_stats.rs`：SQL 三查询 `'opencode' AS agent` 字面量 + `GROUP BY day,agent,model_id`；C1/N-4 三态容错单测逐行钉住 M3 回归（`rows == expect` 断言）；degraded 仅在 CC 有数据时为 Some ✓；`build_cc_idle_report` 护栏与 opencode `should_report` 同 abs 口径、今日段 in+out+cache_read 同模板、无 cost 段；两命令 async fn + spawn_blocking + State ✓。
- `lib.rs`：CC idle http 线程只派发、后台线程解析→护栏→apply（复合键 `claude-code:{sid}` 经 `format!("{agent}:{session_id}")` 自动成立）→notify→emit，不 join；`Arc<Mutex<TranscriptCache>>` 构造与 `app.manage(cc_cache)` 均在窗口创建循环之前（order_nails 源码级钉子测试守护 issue #9）。
- `claude-code-hook.js`：五类工具族提取规则与 opencode 侧 pulse-pet-hook.js 逐分支对照一致（剥 KEY=value 正则、basename、hostname、≤40 clip）；detail 仅 PreToolUse 携带；测试断言 POST body `detail: "edit:V2-DESIGN.md"` 全链路。

**R2 前端侧** — 全部通过：
- 两级状态机：`agentTab: string|null`（null=全部，恒显默认）✓；`selectAgent` 同步重置模型全选 ✓；rows/dimension 变化 effect 回落「全部」（agentTab 只读不依赖有注释说明、无 eslint 工具链、行为正确）✓；chips 经 `computeModelChips(rows, 单元素集)` 联动收窄 ✓；`computeStackedBars` 的 agentFilter「不传=全量」（N12 钉子测试）✓；作用域仅柱图（KPI `sumRows` 与会话列表独立于 agentTab）✓；range 维 tab/筛选/柱图整体隐藏 ✓；noAgents 键 zh/en 清退 + 清退钉子测试 ✓。
- `token.agent.all` zh「全部」/en "All"；i18n 键集合完备性测试守护；新样式全走 M2 token（`--warn` 双主题、degraded/徽标/⚡/注释小字均 var() 引用）。
- degraded 呈现范围正确：仅 panel 顶部细横幅（title=原始错误串）；pet 侧 `fetchTodayStatsCached` 只解构 `{today}` 静默消费。

**工程纪律** — 通过：全 diff 无新增 `eprintln!`（plog! 沿用；ignored 手动冒烟测试 println! 为既有惯例）、无 debugger/console.log 残留、无死代码、zh/en 键集合一致、async+spawn_blocking 合规。

## 3. 需求边界问题：**有（轻度，2 项，不阻断、非代码缺陷）**

1. **V2-DESIGN §5.6 文字滞后**：仍描述「agent 筛选 chip 第二组」（R1 形态），与 R2 用户反馈 + TC-M5-04 修订注记（tab 单选两级筛选，方案 A）字面矛盾。实现遵循最新修订口径，无代码问题——但设计文档 §5.6 未经修订，后续读者（如 M6）会读到矛盾口径。**建议**：文档维护轮回改 §5.6（coder 禁改文档，由 supervised-coding/用户处置）。
2. **TC-M5-03-2 文字滞后**：「费用卡副行『仅 opencode』标注」与实际形态（M4 用户 2026-08-25 裁定移除 cost KPI 卡后，标注以 KPI 区注释小字承载）不一致。tester 已按实际实现 PASS、实现遵循最新裁定，非缺陷；同上建议文档措辞后续统一。

（Tester 的 TEST_BUG `real_db_reconciliation_manual` 参考 SQL 旧口径问题已由 tester 正确归类非阻断并记遗留，采纳其去向判断：下轮 coder 顺手修或打磨轮。）

## 4. CASE_BUG 裁定请求

本轮 tester 未提交 CASE_BUG 裁定请求，无裁定事项。

## 5. 终态结论

```
reviewVerdict: APPROVED
reviewedSha:   ca2b6006a3dca4884a3a3ab626da7f3ad6e24c89
```

R1+R2 三 commit 与 V2-DESIGN §5.0~§5.10（含 §5.11 两轮评审全部钉子）、TC-M5-01~10（R2 修订口径）逐项对齐；tester PASS 证据链与我独立静态核验交叉一致；P3×4 为打磨轮级（注释清理/测试时区假设/锁粒度观察），不阻断。未执行实机项（TC-M5-05/06 实机触发、TC-M5-08/09 实机）已按 INC-20260827-1033 整改口径转用户人工配合，检查点已附步骤清单，属流程性待办而非交付缺陷。

交付留痕（`gh pr review`）待你确认交付时执行——当前分支 develop_opencode 领先 origin/develop 恰 3 提交（含本任务三 commit），尚未推送到 GitHub，如需我执行 PR 留痕请指示。
