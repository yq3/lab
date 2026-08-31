---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-m3
target: pulse-pet
coderTaskId: ses_fc939fb1effevuzJTxLw3kKqiP
testerTaskId: ses_fc8c3493cffe1p6ccsyfVYju3b
committerTaskId: ses_fc7638655ffeTEQV6k98nsR5gH
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: f529e89ed0f1974333b6dc2ef1617a38eab6971a
reviewedSha: f529e89ed0f1974333b6dc2ef1617a38eab6971a
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [pulse-pet/README.md, pulse-pet/opencode-plugin/pulse-pet-hook.d.ts, pulse-pet/opencode-plugin/pulse-pet-hook.js, pulse-pet/src-tauri/src/http_server.rs, pulse-pet/src-tauri/src/i18n.rs, pulse-pet/src-tauri/src/interaction.rs, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/token_stats.rs, pulse-pet/src/lib/i18n.test.ts, pulse-pet/src/lib/i18n.ts, pulse-pet/src/lib/pet-menu.test.ts, pulse-pet/src/lib/pet-menu.ts, pulse-pet/src/lib/plugin-hook.test.ts, pulse-pet/src/lib/token-chart.test.ts, pulse-pet/src/lib/token-chart.ts, pulse-pet/src/lib/token-stats.test.ts, pulse-pet/src/lib/token-stats.ts, pulse-pet/src/lib/tool-bubble-bridge.test.ts, pulse-pet/src/lib/tool-bubble-bridge.ts, pulse-pet/src/main.tsx, pulse-pet/src/panel/Settings.tsx, pulse-pet/src/panel/TokenStats.tsx, pulse-pet/src/pet/HoverToday.tsx, pulse-pet/src/pet/Pet.tsx, pulse-pet/src/pet/PetCanvas.tsx, pulse-pet/src/pet/PetMenu.tsx, pulse-pet/src/pet/petStore.ts, pulse-pet/src/pet/todayToken.ts, pulse-pet/src/styles/global.css]
endReason: null
createdAt: 2026-08-25T10:26:49+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-08-25T19:47:41+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-pulsepet-v2-m3: PulsePet v2 M3——Token 看板增强 + 工具级气泡

## 任务原文

用户原文（2026-08-25）："聚焦pulse-pet项目，开始V2版本M3阶段的开发工作"

实施 **V2-DESIGN §3（已终审定稿 2026-08-23，含 §3.14 评审两轮处置全部采纳）**：M3 Token 看板增强 + 工具级气泡，落 M2 设计系统与气泡排队模型之上。

**权威文档**：
- 设计：`pulse-pet/docs/v2/V2-DESIGN.md` §3.0~§3.14（Spike S1~S8 事实基线 + §3.1 裁定表）
- 范围：`pulse-pet/docs/v2/V2-SCOPE.md` §3.3（A~H 全项）
- 验收用例：`pulse-pet/docs/v2/V2-TEST-CASES.md` 三、TC-M3-01~17

**范围（八块，V2-DESIGN §3.2~§3.7）**：

1. **数据层（token_stats.rs）**：TokenRow +3 字段——`model_id`（json_extract(model,'$.id')，仅按 id 归并；NULL/JSON 损坏→None「未知模型」）、`project_name`（LEFT JOIN project 取 worktree 列、Rust 侧 Path::file_name 切 basename；`/`（global）或未命中→None）、`title`（by-session 独有）；`query_by_session` 增列+JOIN；`query_grouped`（day/week）改 `GROUP BY day_expr, model_id`、project_id 移除；range 同口径；**mock 过滤（S4 裁定）覆盖全部查询含 query_current_session**：`WHERE COALESCE(json_extract(model,'$.providerID'),'') <> 'mock'`；`SESSION_REQUIRED_COLUMNS` + `model` + `title`；新命令 `token_stats_today`（async fn + spawn_blocking，from=本地今天 0 点，TodayStats{input,output,cache_read,cost}，复用全套错误处理）。
2. **idle 汇报追加今日累计**：make_idle_hook（lib.rs）气泡末尾追加 ` · 今日 {format_tokens_k(total)}`，total = in+out+cache_read（reasoning 不计）；同连接一次查询；60s 新鲜度护栏不变；今日聚合失败静默省略追加段；仅 agent=="opencode"；模板入 i18n.rs（`token_report_today`，zh/en）。
3. **今日 preset 与面板默认**：RangePreset 加 "today"（from=本地今天 0 点）；面板默认选中今日（原 7d）；分段控件首位插入「今日」。
4. **三层快捷查看今日 token**（共享 token_stats_today，pet 桥层 30s 缓存）：① 被动层=idle 汇报追加（见 2）；② 主动层=悬停宠物 500ms（非穿透）→ HoverToday 卡片（总量大字 + in/out/cacheRead 三行等宽字体），移开即消；显示期间 setHoverPaused(true) 冻结队列、视觉替换气泡位（底层 current 不销毁）；与右键菜单互斥（后开者胜，菜单打开即解除冻结 N4）；穿透切换兜底（N14：订阅 pulsepet://pass-through，穿透开启即取消计时器/隐藏卡/解除冻结）；全零数据照常显示 0；错误态一行「暂无数据」；③ 入口层=右键菜单第 0 项「今日 token：42M」三态（loading `…` / ok / error `—`，formatTokens 与 idle 追加段同口径 N11），点击 → openPanel("token")；`buildPetMenuItems(passThrough, todayToken, lang?)` 签名扩展、PetMenuAction 增 "today-token"、信息项分隔线、menuH 104→130。
5. **堆叠柱状图 + 模型筛选**：`computeStackedBars(rows, selectedModels, opts)` 新纯函数（柱内三段自底向上 output→input→cache read；reasoning 不计；勾选剔除后聚合；空集→空态文案）；**opts 预留 `agentFilter?: ReadonlySet<string>` 参数位（M3 声明不传值，N3/N12 钉子）**；删 computeBars/pieSlices 及测试（grep 无残余消费 R6）；HTML tooltip（日期+三值+占比+总量）+ 图例三项仅说明不可交互；模型 chip 筛选（distinct model_id 按总量降序、默认全勾、作用域仅柱图）；agent 筛选 UI 预留位（filter-row 多组容器，M5 插第二组，M3 只渲染模型组不留空位）；KPI 首卡「总量」= in+out+cache_read（sumRows+total），四卡布局：总量/input/output/cost，cache read 移首卡副行小字；range 维度无柱图（隐藏柱图与筛选区）。
6. **砍饼图 + 会话列表改造**：删 ProjectPie/PROJECT_COLORS/.token-columns 双栏，会话列表升全宽；首列=title（flex 省略，title 属性 tooltip=完整标题+session id+本地时间；New session* 回退行原样；NULL→session id 前 8 位）；项目列=project_name basename（global/未命中→回退标签 token.project.global/unknown）；展开详情追加「模型」行；排序维持前端 token 降序重排（两行为均维持现状）。
7. **工具级气泡（宠物从「状态灯」升级「播报员」）**：
   - 插件侧（pulse-pet-hook.js）：`detail = "<tplId>:<param>"` 模板 ID 协议（read/edit/bash/search/web 五模板，zh/en 双语）；param 提取净化（file path→basename；bash 先剥行首 KEY=value 段再取首词、首词含 / 或 \ 取 basename——P1-4；search pattern≤40 字符含 / 取末段；web URL→hostname）；仅 tool.execute.before 携带（args=output?.args）；detail 独立 20s 节流桶（全局单桶，reaction 放行后才判定消耗，网络成败不回滚 N7；状态被 reaction 桶吞时 detail 桶不消耗）；绝不携带路径/参数/URL 原文（TC-SEC 口径）。
   - Rust 侧：http_server detail 透传回调（不落盘不解析 N8）；lib.rs `emit_to("pet","pulsepet://tool-bubble",{detail})`（不判开关）；新命令 `tool_broadcast_get`/`tool_broadcast_set`（app_state 键 `bubble.toolBroadcast` 缺省 true；set 后 `emit_to("pet","pulsepet://tool-broadcast")` 广播）。
   - pet 桥侧（新 tool-bubble-bridge.ts）：首个 `:` 切分（param 可含 :）；tpl 白名单校验 + param 再净化（单行/≤40/去控制字符，格式级兜底 R8）；开关 store（get 初始化+广播订阅，判定零 IPC）；通过→pushBubble({level:"ambient", source:"tool:<tplId>"})（dwell 4s，M2 ambient 语义可顶可丢）；文案 i18n `toolb.<tplId>` 渲染。
   - 开关 UI：设置页「宠物与播报」区（与点击穿透同区 settings-check 形态，新增小节标题；**不放功能管理区** P2-4）；默认开；关闭立即静默（广播生效无需重启）；panel 初始显示值经 get 初始化（N13）。
   - 插件改动发布联动：README/发布说明提醒重跑 install.sh。
8. **i18n**：新键 `token.preset.today`/`token.kpi.total`/`token.col.model`/`token.project.global`/`token.project.unknown`/`token.todayUnavailable`/`menu.todayToken`/`toolb.read|edit|bash|search|web`/`settings.toolBroadcast*`/`settings.sectionPet*`（+实施细项微调增补，zh/en 键集合一致，完备性测试守护 N6）。

**不含（§3.1）**：CC transcript 数据与 CC hook 携带 detail（M5，R7 记录协议届时照抄）、agent 筛选实现（M5——UI 预留位已落实）、M4 定时任务、穿透语义改动。

**开发纪律**：分支 develop_opencode（**当前落后 origin/develop 3 提交，开工先同步**：fetch + merge origin/develop）；提交信息 `[task-pulsepet-v2-m3] R<n>`；cargo 网络注意 CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false；新代码日志一律 plog!；每轮验证证据必含 tauri build 成功 + 产物时间戳（v2-m2 supplement-5 纪律）；DB 零迁移（bubble.toolBroadcast 走 app_state 键值）。

## 验收标准（V2-TEST-CASES 三、TC-M3-01~17 + V2-DESIGN §3.11）

- **TC-M3-01 数据层字段扩展（单测）**：TokenRow 3 字段映射（model_id 提取/JSON 损坏→None/title/project JOIN/global→None）；带后缀 id 原样归并；grouped 含 model_id 不含 project_id；白名单+2 列（缺列→schema-mismatch 不崩溃）
- **TC-M3-02 mock 模型过滤口径（单测）**：全部查询（by-session/day/week/range/query_current_session/token_stats_today）mock 行均被过滤
- **TC-M3-03 token_stats_today 命令（单测）**：0 点边界（注入固定时刻）；全套错误透传；async+spawn_blocking；三层共享单一数据源
- **TC-M3-04 今日 preset 与面板默认（单测+实机）**：默认今日、首位「今日」；rangeForPreset 边界（含跨午夜）；7d/30d/自定义不回归
- **TC-M3-05 堆叠柱状图（单测+实机）**：三段自底向上 output→input→cache read；tooltip 内容；图例不可交互；token 化色值深浅可读；空集空态；agentFilter 不传=不过滤钉子；computeBars/pieSlices 删除无残余；range 无柱图
- **TC-M3-06 模型筛选（实机）**：chip 来源/总量降序/默认全勾；仅柱图联动；probe-model 不出现；filter-row 多组容器预留位
- **TC-M3-07 KPI 首卡与 reasoning 口径（单测+实机）**：总量=in+out+cache_read（reasoning 不计）；四卡布局；cache read 副行小字；sumRows 注入非零 reasoning 断言
- **TC-M3-08 砍饼图与会话列表改造（实机）**：饼图/双栏消失；首列标题（tooltip 完整标题+id+时间；回退行原样；NULL→id 前 8 位）；项目列 basename+回退标签；展开「模型」行；排序不变
- **TC-M3-09 被动层 idle 追加（单测+实机）**：追加段格式逐字（token_report_today）；total 口径；护栏沿用；失败省略分支单测（P2-6）；仅 opencode
- **TC-M3-10 主动层悬停卡（实机）**：500ms 防抖/移开即消；冻结/视觉替换/恢复续走；菜单互斥后开者胜+解除冻结；穿透切换兜底 N14；穿透下不可达；全零显示 0；错误态「暂无数据」；30s 缓存
- **TC-M3-11 入口层右键菜单（单测+实机）**：三态 label（…/42M/—，formatTokens 口径）；点击直达 openPanel("token")；分隔线；4 项+menuH 130 不越屏；打开时 invoke 共享缓存
- **TC-M3-12 三层口径交叉断言（实机）**：会话静止窗口内三处数值相等（同 0 点+mock 过滤+reasoning 不计；活跃写入秒级差异正常 N2）
- **TC-M3-13 工具级气泡插件侧（单测）**：extractDetailParam 各工具族（basename/首词/env 剥离/绝对路径→npm/hostname/pattern 净化/无参→无 detail）；仅 tool.execute.before；detail 独立桶语义四条（冷却期省略/被吞不消耗/不影响状态桶/反应后消耗）；绝不携带原文
- **TC-M3-14 工具级气泡 App 侧（单测）**：首个 : 切分（param 含冒号）；白名单拒绝/空白丢弃；再净化；ambient 入队参数与 i18n 渲染；Rust emit_to 透传；tool_broadcast get/set（缺省 true/非法回退/持久化/广播断言）；关闭静默
- **TC-M3-15 工具气泡实机 + ambient 排队补验（实机）**：真实 opencode 会话「正在编辑 X.md」ambient 4s；20s 节流；无原文目验；critical 显示中排队不顶替（M2 §2.10 遗留承接）；多条 ambient 上限驱逐可观察
- **TC-M3-16 工具播报开关（实机+单测）**：位置在「宠物与播报」区；默认开；关闭立即静默（广播）；重启保留；插件照发
- **TC-M3-17 M3 新键 i18n 完备性（单测）**：zh/en 键集合一致（§3.9 清单+实施细项）
- 回归基线：npm test（vitest 314 基线 + 新增）全绿；cargo test（221+1 ignored 基线 + 新增）全绿；npm run build / tauri build（产物时间戳）成功；既有纯函数测试不破坏（bubble.ts/plugin-hook 既有/token-chart 旧删除项同步清退）

## 需求确认
- [x] 用户已确认（确认后 status=implementing）——2026-08-25 10:33 用户确认：① M3 范围照 V2-DESIGN §3 定稿执行；② 遗留事项按拟处置执行（M2 目验 7 项待反馈、P3-5 默认继续移交、P3-6~10 与 v2-m1 A/B/C/D 继续移交）；无范围调整
- 历史遗留事项清单：（supervised-coding 扫描 task-pulsepet-v2-m1/m2 检查点汇总，默认并入本任务，见 README §4.6）

## 遗留事项（跨任务移交）

- [ ] **v2-m2 新移交——实机目验 7 项（来源 task-pulsepet-v2-m2，去向=用户反馈，持 R2 产物 09:14）**：TC-UI-01 主题三档 / TC-UI-03 面板壳+芯片 / TC-UI-06 双 agent 芯片跟随 / TC-UI-07 功能管理禁用 Todo 全链路 / TC-UI-10 气泡排队实机 / TC-UI-11 气泡与右键菜单视觉 / TC-UI-12 四 tab 对照样例目验——**待用户反馈目验结果**（若发现问题随本轮修复；无反馈继续移交）
- [ ] **v2-m2 committer P3-5（来源 task-pulsepet-v2-m2，2026-08-25 用户确认继续移交）**：atlas.rs AtlasData Clone derive 死代码——M3 设计范围（§3.8/§3.9）不动 atlas.rs，本轮不清偿；**去向=后续动 atlas.rs 的里程碑（M5 或打磨轮）顺手清**
- [ ] **v2-m2 committer P3-6~10（去向注明，不并入）**：P3-6 notice 重复计算 + P3-7 禁用语汇四套不一致（后续 CSS/微打磨轮）；P3-8 插件开关失败静默 + P3-9 panel://tab 冷启动竞态（UX 观察项记录不修）；P3-10 Rust 命令错误串未 i18n（M8 类约定扩展时）
- [ ] **v2-m1 遗留（去向已注明，不并入）**：A 实机验证类（多屏/Windows，具备硬件时）；B v0.1.3 收尾用户目视验收四项+双场景（待用户反馈）；C v0.1.3 Release publish 决定（待用户指示）；D 观察项（默认不动）
- [ ] **M3 新移交（2026-08-25 R1 双通过后，committer 定级）**：
  - P2 面板 Token 页数据 App 启动时刻定格（TokenStats.tsx:128 load 仅挂载执行 + tauri.conf.json panel visible:false 隐藏创建即挂载；TC-M3-11 无缝衔接/TC-M3-12 交叉在长运行 App 首开不成立）——**去向=M4 面板改动轮**（修复方案：仿 Settings tauri://focus 双触发）
  - P3① idle 汇报「 · 今日 X」追加段在 220px 气泡被单行省略截断不可见（文案口径正确单测钉住）——**去向=气泡文案/CSS 打磨轮**
  - P3② 合成事件测试工具限制（非产品缺陷）——**记录**
  - P3③ V2-DESIGN §3.8"build_idle_report 不动"陈旧措辞与实现（删旧建 with_today）冲突——**随本轮交付回 spec 由 supervised-coding 顺手修订**
  - P3④ todayToken.ts resetTodayCache 死导出（悬停卡移除后无调用方）——**可选清理，后续顺手**
  - P3⑤ plugin-hook.test.ts:763 注释草稿痕迹——**打磨轮清理**
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1（第 1 次调用，2026-08-25 10:34 用户确认）：**网络中断，Task 被取消**。用户 10:57 提示从 opencode.db 找回 task_id：`ses_fc939fb1effevuzJTxLw3kKqiP`（"v2 M3 R1 实施 (@Coder subagent)"，10:35:42 创建、10:50:21 最后活动），已写入 frontmatter。中断现场（supervised-coding 查证）：**develop_opencode 已同步至 origin/develop（HEAD=330feea）✅**（开工第一步完成）；半成品改动未 commit——`M pulse-pet/src-tauri/src/token_stats.rs`（数据层已开始）；其余工作区改动均为流程文件（.opencode 文档/检查点/images 非任务产物）。处置：续接该会话继续 R1。
- R1: coder 续接会话完成（网络中断恢复），commit `914ded0`（`[task-pulsepet-v2-m3] R1: M3 Token 看板增强 + 工具级气泡`，develop_opencode，commit 前已 fetch+merge origin/develop 无新提交；supervised-coding 已核验 HEAD=914ded0、29 files +2799/−606、工作区干净）。改动八块全量——Rust 5：token_stats.rs（TokenRow+model_id/project_name/title、by-session/current_session LEFT JOIN project Rust 侧 basename、grouped/range 改 GROUP BY day_expr,model_id 移除 project_id、json_valid 守卫 mock 过滤覆盖全部查询、白名单+model+title、token_stats_today async+spawn_blocking、build_idle_report_with_today 同连接一次查询、+10 单测）；i18n.rs（token_report_today zh/en+逐字钉子）；lib.rs（idle 追加今日累计段/失败静默省略/仅 opencode+3 测、detail_hook emit_to("pet","pulsepet://tool-bubble")、命令注册）；http_server.rs（StateEvent.detail 透传回调 DetailHook+集成测试）；interaction.rs（tool_broadcast_get/set：app_state bubble.toolBroadcast 缺省 true/非法回退、set 定向 pet 广播+mock runtime 断言）。前端 21：token-stats.ts（RangePreset+today 0 点边界/sumRows+total/fetchTodayStats）；token-chart.ts（删 computeBars/pieSlices grep 零残余 R6、computeStackedBars 三段自底向上+agentFilter 预留位 N12 钉子、computeModelChips）；i18n.ts（20 新键 zh/en+完备性断言、清退 pie/chart.bar 死键）；pet-menu.ts（buildPetMenuItems 签名扩展/TodayTokenState 三态/PetMenuAction+today-token/info 分隔线/menuH 104→130）；tool-bubble-bridge.ts 新（首个 : 切分/白名单/再净化单行≤40 去控制字符/开关 store get+广播订阅/ambient 入队 source="tool:<tpl>"，12 用例）；pet/todayToken.ts 新（30s 缓存悬停卡+菜单共享）；pet/HoverToday.tsx 新（500ms 防抖/离开即消/setHoverPaused 冻结/视觉替换/菜单互斥后开者胜 N4/穿透兜底 N14/全零显 0/错误态「暂无数据」）；PetCanvas/PetMenu/Pet/petStore（悬停接线/菜单三态+点击直达 openPanel("token")/菜单打开拉数据共享缓存）；TokenStats.tsx（默认今日+首位「今日」/KPI 四卡总量+cache read 副行/堆叠柱图+HTML tooltip+图例不可交互/filter-row 多组容器 M5 预留位/range 维隐藏柱图筛选区/会话列表全宽首列 title+tooltip/项目列 basename+global unknown 回退/展开「模型」行）；Settings.tsx（「宠物与播报」区 settings-check 形态不放功能管理区 P2-4/get 初始化 N13）；main.tsx/global.css（桥接线/新样式删 pie/columns）。插件：pulse-pet-hook.js+.d.ts（extractDetailParam：read/edit basename、bash 剥 KEY=value+首词+路径 basename P1-4、search ≤40 含 / 取末段、web URL→hostname；DetailThrottle 独立 20s 单桶 reaction 放行后判定消耗 N7；仅 tool.execute.before 携带 fire 两参形态保持既有断言零改动）；README（升级提醒重跑 install.sh）。自测证据：vitest **348 passed（27 files）**（基线 314：+43 新增−9 旧 chart 清退）；cargo **236 passed+1 ignored**（基线 221+1i，+15）；tsc exit 0；npm run build ✓；tauri build 成功零 warning（PulsePet.app @11:44:03 / dmg @11:44:23）；运行时冒烟——真库 SQL（mock 过滤 175−4=171 行与 S4 吻合、GROUP BY day,model_id 今日聚合 glm-5.3 194.6M、global 行 worktree='/' JOIN 命中）、插件 node 直跑（/opt/homebrew/bin/npm test→bash:npm、FOO=secret npm test→bash:npm、URL→web:maven.aliyun.com、无参→null、节流桶 true→false→true）、R6 清退 grep 零匹配。**实施裁定点 6 条**（均依设计找到行为依据）：① json_valid 守卫——SQLite json_extract 对非 JSON 文本抛错而非返 NULL（设计 R1「天然降级」不成立），改 CASE WHEN json_valid 守卫，损坏 JSON→NULL→「未知模型」，降级语义照设计达成（单测钉住）；② global/未命中区分——Rust 均 None，前端以 project_id==="global" 区分两种回退标签（spike 数据复核 global 行 id 恒为字面量）；③ tool_broadcast 命令移驻 interaction.rs（crate root 泛型 command 与 tauri 宏冲突，编译期实证），注册与行为不变；④ 删旧 build_idle_report（同连接要求下无调用方 dead_code），本期数字逻辑原样复用；⑤ websearch 无 URL 按 search 同款净化（webfetch 严格 hostname），提取层实施细节；⑥ vite 1 条 informational 提示（atlas.ts M2 既有非本次引入）。无范围外预实现（agentFilter 仅声明参数位）。遗留/待裁定：无。
（R1 起逐轮记录 coder/tester/committer 结果）

- R1 补充轮（2026-08-25 12:30 用户目验 R1 产物后提出两个 UI 改动点）：① **KPI 卡**——去掉 cost 卡，替换为 cache read 独立卡，从左到右顺序 **总量 / cache read / input / output**（首卡副行小字随之取消）；② **柱图 tooltip**——三项数值行从上往下应为 **cache read → input → output**（当前顺序有误；柱内堆叠顺序不变）。**验收口径变化已由 supervised-coding 落笔**（2026-08-25 12:37）：V2-DESIGN §3.5 两处（tooltip 行序注记 + KPI 卡布局修订注记）+ V2-TEST-CASES TC-M3-05 预期 2 / TC-M3-07 预期 2（coder 禁改文档，以此为准）。status: testing → implementing（补充轮），round 不变。coder 修复对象：TokenStats.tsx KPI 卡布局与 tooltip 行序（含相关测试断言同步）。
- R1 补充轮: coder 完成（同会话续接），commit `7783bf5`（`[task-pulsepet-v2-m3] R1: 补充——KPI 卡布局与 tooltip 行序（用户 2026-08-25 两点改动）`，commit 前已 fetch+merge origin/develop；supervised-coding 已核验 HEAD=7783bf5、6 files +41/−20、docs/v2 修订未入 commit 留交付阶段统一提交）。改动：TokenStats.tsx（KPI 四卡 总量→cache read→input→output、cost 卡移除、首卡副行小字取消；tooltip 三行自上而下 cache read→input→output；柱内堆叠序不动）；token-chart.ts（新导出 TOOLTIP_ROW_ORDER 常量=行序唯一权威，与堆叠序分离）；i18n.ts（清退 token.kpi.totalSub zh/en）+ i18n.test.ts（m3Keys 移除+新增清退断言）；token-chart.test.ts（+TOOLTIP_ROW_ORDER 钉子：正序断言+与堆叠序互逆独立性断言）；global.css（清退 .kpi-sub 死样式）。cost 数据零删减（会话详情 formatCost 与 TodayStats 字段不动）。自测证据：先红（vitest 2 failed=新钉子预期失败）→ `npm test` **350 passed（27 files）**（基线 348+2）；cargo test --lib 236+1 ignored（Rust 零 diff 快跑）；tsc exit 0；npm run build ✓；tauri build 成功（PulsePet.app @12:41:45 / dmg @12:42:05）。**待验对象更新为 7783bf5**（914ded0→7783bf5 线性单提交）。
- R1: tester 验证 **PASS**（testedSha=7783bf5，testerTaskId=ses_fc8c3493cffe1p6ccsyfVYju3b）。独立复跑基线与 coder 声明逐项一致（vitest 350/27 files、cargo 236+1i、tsc 0、build 成功——1 条 vite informational 经 `git show 914ded0^` 验证为 M2 既有非 M3 引入；产物时间戳 12:41/12:42 吻合）。**TC-M3-01~17 全 PASS（17/17，0 失败）**：01 数据层（Rust 断言真实+实机渲染正确）；02 mock 过滤（真实库 4 条 probe-model 行，面板 chips 无 probe-model）；03 token_stats_today（午夜边界+错误路径透传+async/spawn_blocking 代码核验）；04 默认今日（OCR 目验+跨午夜单测+切 7d/30d 不回归）；05 柱图（三段堆叠+TOOLTIP_ROW_ORDER 逆序独立性；**实机 tooltip 目验 2026-08-25 共 242.0M/cache read 98.1%/input 1.7%/output 0.2% 自上而下**✓修订口径）；06 模型筛选（chips 总量降序 glm-5.3>flash>pro>glm-4.6v、probe-model 不现、filter-row 容器）；07 KPI（**实机四卡序 总量 224.3M/cache read 219.8M/input 4.1M/output 375.4K**✓修订口径；sumRows reasoning 不参与钉住）；08 会话列表（首列标题/项目列 basename+「全局」回退/**title tooltip 常驻窗口内容逐字吻合**/展开「模型」行/排序维持/饼图双栏无残留）；09 idle 追加（实机真实会话 idle 数值与 DB 精确对账；同连接+失败省略单测；**观察项：追加段在 220px 窗口被单行省略截断不可见**→P3）；10 悬停卡（500ms 防抖/移开即消/菜单互斥后开者胜/**N14 切穿透卡立即消失+冻结解除**/穿透下不可达/全零错误态代码+单测）；11 右键菜单（4 项实测：今日 token 233.3M ok 态/三态单测/**点击直达 Token 页默认今日**/menuH 130 不越屏/30s 缓存共享吻合）；12 三层交叉（悬停 232.6M/菜单 233.3M/sqlite 同窗口 232.9M 方向时序自洽+面板刷新 237.3 vs sqlite 237.5 秒级差；single==grouped 双 SQL 等价实测；**观察项：面板首开显示 App 启动时刻定格数据**→P2）；13 插件侧（extractDetailParam 各族+P1-4 强化+websearch 同款净化=裁定点⑤核实+DetailThrottle 四语义+TC-SEC 无原文断言）；14 App 侧（首个 : 切分/再净化/ambient 入队/开关零 IPC/Rust 透传 emit_to 实测打通）；15 工具气泡实机（**「正在编辑 V2-DESIGN.md」4s 自动消失净化无路径**；**critical 显示中排队不顶替完整证据链**（critical 8s 结束后 13:40:22 工具气泡接续显示）；**5 条连发队尾驱逐丢弃**与 evictOverflow 一致；方法说明：opencode 单例无法热加载插件，实机以 POST 注入新版插件确切载荷驱动 App 侧全链路，插件侧由单测覆盖；install.sh 已装新版磁盘插件 md5 一致，opencode 重启生效）；16 开关（「宠物与播报」区/默认开/关闭立即静默/**重启仍静默持久化**/重开恢复/插件照发）；17 i18n（M3 新键完备+totalSub 清退断言）。**缺陷清单：P0/P1 无；P2×1（建议修复）**——面板 Token 页数据 App 启动时刻定格（load 仅挂载时执行+panel visible:false 隐藏创建即挂载；长运行 App 首开面板需手动刷新，TC-M3-11 无缝衔接/TC-M3-12 交叉在首开时不成立；v1/M2 既有行为 M3 用例显性化；建议仿 Settings tauri://focus 双触发）；**P3×2**——idle 追加段 220px 气泡单行省略截断不可见（文案口径正确单测钉住，视觉不可见；建议两行或精简或记录已知边界）；悬停/菜单依赖合成事件小步移动（工具限制非产品）。观察项 3 条（M3测试提醒每 4 分钟触发=正常调度+喝水烟花自然周期；TC-M3-05 柱内三段真实数据亚像素无法目验以单测为准；TC-M3-10-2 dwell 冻结秒级时序未实测由 25 条单测覆盖）。**coder 裁定点 6 条全部核实与用例自洽**（①json_valid 守卫 token_stats.rs:105-114 注释如实；②global 前端判定；③tool_broadcast 移驻 interaction.rs lib.rs:151-153 注释；④旧函数已删；⑤websearch 同款净化；⑥vite informational M2 既有）。环境恢复：测试提醒 id=40 及 logs 已删、pass_through=false、toolBroadcast=true、pet.position 恢复 (2482,1186)、进程杀净、**新版插件已 install.sh 安装（交付面正确状态，opencode 重启生效；运行中 opencode 未受影响）**、临时产物 199 文件全在系统临时目录、仓库零残留、opencode.db 全程只读。

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### Tester R1 报告（2026-08-25，testVerdict=PASS）

# PulsePet v2 M3 R1 验收测试报告

## 一、环境与被测对象核验

| 项 | 值 | 核验结果 |
|---|---|---|
| HEAD (testedSha) | `7783bf58c3fb5ecf26befdaea19aa48160552a7a`（= 7783bf5） | ✓ 与被测 commit 一致 |
| 提交链 | 914ded0（M3 全量）→ 7783bf5（补充：KPI 卡布局+tooltip 行序） | ✓ git log 确认 |
| 产物 .app | `src-tauri/target/release/bundle/macos/PulsePet.app` 二进制 2026-08-25 **12:41:45** | ✓ 时间戳吻合 |
| dmg | `PulsePet_0.1.3_aarch64.dmg` 2026-08-25 **12:42:05** | ✓ 时间戳吻合 |
| 被测库 | `~/.local/share/opencode/opencode.db`（WAL 模式，opencode 实时写入中） | 全部**只读**查询（sqlite3 -readonly），零写入 |
| 修订口径 | V2-TEST-CASES.md 两处修订（TC-M3-05 tooltip 行序 / TC-M3-07 KPI 卡序）已按权威用例执行 | ✓ |

## 二、独立复跑基线表（不引用 coder 数字，全部独立重跑）

| 命令 | 结果 | 与声称对比 |
|---|---|---|
| `npm test` | **350 passed / 27 files**，3.28s | ✓ 一致 |
| `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo test` | **236 passed / 1 ignored / 0 failed** | ✓ 一致 |
| `npx tsc --noEmit` | exit 0 | ✓ |
| `npm run build` | 成功；1 条 vite informational（atlas.ts 动态/静态双引入——已用 `git show 914ded0^` 验证为 **M2 既有**，非 M3 引入） | ✓ coder 裁定点⑥属实 |

## 三、逐 TC 结论（TC-M3-01~17，共 17 条）

| 用例 | 分级 | 结论 | 证据 |
|---|---|---|---|
| TC-M3-01 数据层字段扩展 | 单测+实机对账 | **PASS** | Rust 测试 `m3_by_session_row_has_model_id_title_project_name`/`m3_grouped_rows_have_model_id_without_project_id`/`m3_schema_whitelist_requires_model_and_title` 断言真实（model_id/title/project_name basename/global→None/JSON 损坏→None/聚合行无 project_id）；实机会话列表正确渲染 title/项目/模型 |
| TC-M3-02 mock 过滤 | 单测+实机 | **PASS** | `m3_mock_provider_rows_filtered_everywhere` 覆盖全部 6 条查询路径；**真实库含 4 条 mock 行（probe-model）**，面板 chips 无 probe-model ✓ |
| TC-M3-03 token_stats_today | 单测 | **PASS** | `m3_local_today_start_is_midnight`（午夜边界）+ `m3_today_stats_window_and_error_paths`（no-db/legacy/schema 透传）；生产代码 `async fn + spawn_blocking`（token_stats.rs:607） |
| TC-M3-04 今日 preset 与面板默认 | 单测+实机 | **PASS** | 面板初开**默认「今日」**（OCR 目验 + `useState("today")`）；rangeForPreset 单测（today 跨午夜边界）真实；实机切**近7天**（柱图 08-19→08-25）与**近30天**（KPI 1530.0M）均生效 ✓ |
| TC-M3-05 堆叠柱状图 | 单测+实机 | **PASS** | 单测钉住三段自底向上 output→input→cacheRead + `TOOLTIP_ROW_ORDER=[cacheRead,input,output]` 互为逆序；**实机 tooltip 目验：2026-08-25：共 242.0M / cache read 98.1% / input 1.7% / output 0.2%（自上而下）** ✓；agentFilter 不传=不过滤钉子 ✓；computeBars/pieSlices 无残余 ✓；段色走 M2 token ✓ |
| TC-M3-06 模型筛选 | 单测+实机 | **PASS** | chips 按总量降序（glm-5.3 207.7M > flash > pro > glm-4.6v 99.1k）目验 ✓；probe-model 不出现在 chips ✓；`filter-row` 多组容器结构（M5 预留位）代码核验 ✓；剔除重聚合由单测覆盖 |
| TC-M3-07 KPI 首卡与 reasoning | 单测+实机 | **PASS** | **实机目验四卡序：总量 224.3M / cache read 219.8M / input 4.1M / output 375.4K**（修订口径，cost 卡移除、首卡无副行小字）✓；sumRows 单测钉住 reasoning 不参与（341 vs 2228）✓ |
| TC-M3-08 会话列表改造 | 实机 | **PASS** | 首列标题（如「实施 M2 前端 UI 基础」）✓；项目列 basename「lab」✓、global 会话显示**「全局」**回退标签 ✓；**title tooltip = 完整标题+session id+本地时间**（实测抓到一个常驻 tooltip 窗口，内容逐字吻合）✓；展开详情「模型」行（glm-4.6v）✓；排序总量降序 ✓；ProjectPie/双栏无残留 ✓ |
| TC-M3-09 idle 汇报追加今日 | 单测+实机 | **PASS**（含观察项） | 实机真实会话 idle → 气泡「本期用了 5.0k input / 493 output…」（数值与 DB 精确对账）；`build_idle_report_with_today` 同连接一次查询、today=None 静默省略均有单测钉住；**观察项：追加段在 220px 窗口内被单行省略截断不可见**（见缺陷清单 P3） |
| TC-M3-10 悬停卡 | 实机 | **PASS** | 500ms 防抖（<500ms 移开不显示 ✓）；到点显示「今日/238.3M/input/output/cache read」✓；**移开即消**（复验通过）✓；悬停中右键→菜单开+卡片隐藏+冻结解除（互斥后开者胜）✓；**N14 穿透兜底**：卡片显示中切穿透→卡片立即消失+pass_through=true ✓；穿透下悬停无卡、右键穿透到桌面（出现 macOS 桌面菜单）✓；全零/错误态由代码+单测覆盖（HoverToday.tsx 诚实显 0 / 暂无数据） |
| TC-M3-11 右键菜单 | 单测+实机 | **PASS** | 实机菜单 4 项：**今日 token：233.3M**（ok 态，三态由单测钉住 …/42M/—）/设置…/切换交互模式（穿透：关）/隐藏宠物 ✓；**点击「今日 token」→ 面板打开 Token 页**（默认今日）✓；menuH=130 clamp 单测 + 实机菜单未越屏 ✓；30s 缓存与悬停卡共享（值连续变化吻合缓存窗口）✓ |
| TC-M3-12 三层口径交叉 | 实机+sqlite 对账 | **PASS**（含观察项） | 悬停卡 232.6M / 菜单 233.3M / sqlite mock 过滤同窗口 SUM 232.9M——同 0 点起点+同过滤+reasoning 不计，方向与时序自洽；面板刷新后 KPI 237.3M vs sqlite 237.5M（秒级差）✓；**`single==grouped` 双 SQL 等价性实测确认**；观察项：面板首开显示 App 启动时刻定格数据（见缺陷清单 P2） |
| TC-M3-13 插件侧提取与节流 | 单测 | **PASS** | extractDetailParam 各工具族断言真实（read/edit basename、bash P1-4 净化强化：`FOO=secret npm test`→npm、`/opt/homebrew/bin/npm test`→npm、search ≤40、web hostname、websearch query 同款净化——裁定点⑤核实 ✓）；DetailThrottle 独立 20s 单桶 + deliver 四条语义（reaction 吞掉不消耗等）全钉住；TC-SEC 口径断言（不含路径/参数/URL 原文）✓ |
| TC-M3-14 App 侧解析与入队 | 单测+实机 | **PASS** | parseToolDetail 首个 `:` 切分（macOS 文件名含冒号）✓；sanitizeToolParam ≤40/单行/控制字符 ✓；ambient 入队 source=`tool:<tpl>` ✓；开关静默判定只读 store 位 ✓；Rust http_server detail 透传 + `emit_to("pet")` 实测打通 ✓ |
| TC-M3-15 工具气泡实机 + ambient 排队 | 实机 | **PASS** | **「正在编辑 V2-DESIGN.md」ambient 气泡实机显示、4s 自动消失、净化无路径** ✓；**critical 显示中工具播报排队不顶替**：critical「M3测试提醒」显示中 POST 工具事件→气泡仍为 critical（g1-seq-13 帧）；critical 8s dwell 结束后 **13:40:22.76 工具气泡「正在编辑 QUEUE-FINAL.md」接续显示**（g1-seq-14 帧）——完整排队证据链 ✓；**ambient 驱逐**：5 条快速连发→A1/B2/C3/D4 依次显示、第 5 条被队尾驱逐丢弃（与 evictOverflow 语义一致）✓；方法说明：因 opencode server 单例无法热加载新版插件（重启会终止当前会话），实机链路以 POST /state 注入新版插件的**确切载荷**驱动（App 侧全链路真实），插件侧提取/节流由 TC-M3-13 单测全量覆盖；install.sh 已使磁盘插件为最新版（md5 19caf… 与 repo 一致），opencode 下次重启生效 |
| TC-M3-16 工具播报开关 | 实机 | **PASS** | 开关位于「宠物与播报」区（与穿透同区、不在功能管理区）✓；默认开 ✓；关闭后 **POST 工具事件立即静默**（无需重启）✓；**重启 App 后仍静默（持久化）** ✓；重开后气泡恢复（「正在跑 cargo」）✓；插件照发、App 侧过滤 ✓；`tool_broadcast_get/set` 缺省 true/非法回退/定向广播单测 ✓ |
| TC-M3-17 M3 新键 i18n | 单测 | **PASS** | i18n.test.ts「M3 新键 zh/en 均存在」断言含全部清单键 + `token.kpi.totalSub 已清退`（修订口径配套）✓ |

**通过 17 / 17，失败 0。** 单测类全部核对了测试真实性（断言为具体数值/逐字文案/边界注入，非走过场）；实机类全部为真实 GUI 会话（open .app 完整路径 + screencapture + OCR + Vision + CGEvent 合成输入 + sqlite3 只读对账）。

## 四、缺陷清单

| 级别 | 位置 | 描述 | 建议 |
|---|---|---|---|
| **P2（观察项→建议修复）** | `src/panel/TokenStats.tsx`（load 仅挂载时执行）+ `src-tauri/tauri.conf.json` panel `visible:false`（隐藏创建即挂载） | 面板 Token 页数据在 **App 启动时刻定格**：实测面板显示 12:47:31 快照（224.3M），而菜单/悬停卡实时（232.6~233.3M），差 ~9M。TC-M3-11「点击今日 token → 无缝衔接详情」与 TC-M3-12 三层口径交叉在长运行 App 上首开面板时不成立（需手动点「刷新」）。v1/M2 既有行为，M3 用例使其显性化 | 仿 Settings.tsx:164 的 `tauri://focus` 双触发模式，面板可见时刷新 TokenStats（或 openPanel 时触发） |
| **P3（观察项）** | `src/styles/global.css` `.pet-bubble`（nowrap + max-width:208px 单行省略） | idle 汇报「 · 今日 X」追加段**在 220px 宠物窗口内被单行省略截断不可见**（实测多次捕获均截断于 "output…"；文案本身与口径正确、单测钉住）。「气泡末尾追加」的验收语义达成，但视觉上用户看不到追加段 | 气泡允许两行或精简汇报文案；或记录为已知边界 |
| P3（记录） | 测试环境 | 悬停/菜单依赖合成事件（小步移动才触发 webview pointer 事件、单次大跳不触发）——纯自动化工具限制，非产品缺陷；已用悬停卡移开即消复验排除产品侧问题 | — |

未发现 P0/P1。coder 实施裁定点 6 条全部核实与用例自洽（① json_valid 守卫——SQLite json_extract 对非 JSON 抛错，CASE WHEN 守卫达成同等降级语义（token_stats.rs:105-114 注释如实记录）；② global 判定靠前端 project_id==="global"；③ tool_broadcast 移驻 interaction.rs（lib.rs:151-153 注释说明宏冲突）；④ 旧 build_idle_report 已删无调用方；⑤ websearch 无 URL 走 search 同款净化；⑥ vite informational 为 M2 既有）。

## 五、观察项（记录级）

1. 测试提醒「M3测试提醒」每 4 分钟触发一次（3min dedup + 1min interval 落在 :14 tick），期间喝水提醒（id 39）在 13:33:14 按其 30 分钟自然周期触发了一次烟花——正常调度行为，非测试注入。
2. TC-M3-05 柱内三段堆叠顺序（output→input→cache read 自底向上）无法用真实数据目验（output 0.2% / input 1.7% 为亚像素高度），以单测断言 + 段序常量钉住为准。
3. TC-M3-10-2 悬停冻结/恢复（dwell 冻结）为代码 + bubble-queue 25 条单测覆盖，实机未做秒级时序观测。

## 六、环境恢复声明

- ✅ 测试提醒（id=40）及其 reminder_logs 已删除（reminders 仅剩原「喝水」规则）
- ✅ `pet.pass_through` 恢复 false、`bubble.toolBroadcast` 恢复 true（默认值）
- ✅ `pet.position` 恢复测试前 (2482, 1186)
- ✅ PulsePet App 进程全部退出（pgrep 0 残留）
- ✅ 插件：**新版 pulse-pet-hook.js 已通过 install.sh 安装**（md5 与 repo 一致；配置合并幂等无重复条目）——这是交付面正确状态，opencode server 重启后生效；运行中的 opencode（pid 67666）内存中仍为旧插件，未受影响
- ✅ 测试截图/工具全部位于系统临时目录 `/var/folders/9k/.../opencode/m3-test/`（199 个文件），仓库零残留
- ✅ 仓库工作区未被本次测试改动（git status 显示仅为既有的 12:30 裁定文档修订 + 未跟踪文件，均非测试产物）
- ✅ opencode.db 全程只读

## 七、结论

**testVerdict: PASS**（17/17 用例通过，0 失败；2 项观察项不影响验收）

**testedSha: `7783bf58c3fb5ecf26befdaea19aa48160552a7a`**

### Tester R2 焦点复验报告（2026-08-25，testVerdict=PASS）

# PulsePet v2 M3 R2 焦点复验报告（悬停卡移除）

## 一、环境与被测对象核验

| 项 | 值 | 核验结果 |
|---|---|---|
| HEAD (testedSha) | `f529e89ed0f1974333b6dc2ef1617a38eab6971a`（= f529e89） | ✓ 与被测 commit 一致 |
| 提交链 | 914ded0 → 7783bf5 → **f529e89**（悬停卡移除） | ✓ git log 确认 |
| 产物 .app | 二进制 2026-08-25 **14:17:15** | ✓ 时间戳吻合 |
| dmg | **14:17:36** | ✓ 时间戳吻合 |
| 用例口径 | V2-TEST-CASES.md 工作区修订：TC-M3-10 标记「作废留档 2026-08-25 用户裁定」（HoverToday 删除、不执行原用例）、TC-M3-12 修订为**两层口径** | ✓ 已读确认 |

## 二、独立复跑基线

| 命令 | 结果 | 备注 |
|---|---|---|
| `npm test` | **351 passed / 27 files** | ✓ = 350 + 1 清退断言（token.todayUnavailable 已清退） |
| `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo test --lib` | **236 passed / 1 ignored** | ✓ |
| `npx tsc --noEmit` | exit 0 | ✓ |
| 产物时间戳 | 14:17:15 / 14:17:36 | ✓ |
| `git diff --stat 7783bf5..f529e89` | **9 files, +25/−219** | ✓ 与 coder 自报逐项一致；**src-tauri/ 零 diff**（diff 输出 0 行）——Rust 侧完全未动 |

diff 内容核对（与自报一致）：HoverToday.tsx 整文件删除（123 行）、PetCanvas.tsx 悬停接线移除并恢复 `onPointerLeave={endDragTrack}`（M6 原语义，顺带修复 `};  const` 格式）、Pet.tsx 引用移除、petStore.ts hoverEntered 字段/action/setPassThrough 清零分支移除、i18n.ts zh/en 键删除、i18n.test.ts 清退断言新增、todayToken.ts/PetMenu.tsx 注释更新、global.css .hover-today* 块删除（55 行，非 hover-today 变更行为 0）。

## 三、焦点验收逐项结论（证据）

### 1. TC-M3-10 作废后补充验收：实机悬停无卡片 — **PASS**

| 场景 | 证据 |
|---|---|
| 长悬停 ≥500ms（1.5s） | OCR 无文字 + **Vision 双确认**：窗口上部无任何卡片/面板/气泡，仅像素小猫 ✓ |
| 多次进出（3 轮） | 3 帧 OCR 均无卡片文字；Vision 复核 inout-2 帧确认无 UI 卡片 ✓ |
| 穿透模式悬停 | pass_through=true 后悬停：无卡片 ✓；穿透下**动画照常**（6 帧 2 个交替哈希）✓ |
| JS 错误 | 系统日志 `log show` 12 分钟窗口**零 error/crash/exception/fault**；pulsepet.log 无 panic；宠物持续正常渲染（React 无卸载）✓ |

### 2. 移除干净度 — **PASS**

`grep -rn "HoverToday\|hoverEntered\|setHoverEntered\|hover-today\|todayUnavailable" src/` 仅命中 **i18n.test.ts 清退断言自身**（5 处，均为断言/注释，属允许范围），src/ 零代码残余 ✓。

### 3. 回归抽查 — **PASS**

| 项 | 结果 | 证据 |
|---|---|---|
| TC-M3-11 右键菜单 | **PASS** | 实机菜单 4 项：「今日 token：291.8M」（ok 态）/设置…/切换交互模式（穿透：关）/隐藏宠物；**点击直达 → 面板打开 Token 页默认「今日」** ✓；三态由单测钉住（R1 已验） |
| TC-M3-12 两层口径（修订后） | **PASS** | 菜单 291.8M（14:26:0x）< sqlite mock 过滤同窗口 SUM 292.8M（14:26:16）✓ 时间序自洽；面板 KPI 289.4M = App 启动（14:23:52）挂载快照，与 2.5 分钟 token 增量吻合 ✓——同 0 点起点 + mock 过滤 + reasoning 不计口径一致 |
| TC-M3-09 idle 追加段 | **PASS**（抽查） | Rust 零 diff，`m3_build_idle_report_with_today_*` 单测在（cargo 236 全绿）；R1 实机已验 |
| 气泡排队不回归 | **PASS** | POST tool detail → 「正在编辑 REG.md」ambient 显示 → 4.5s 自动消失 ✓；**悬停中 POST → 气泡照常显示**（不再有悬停冻结干扰——原 setHoverPaused 消费方已移除）✓；setHoverPaused 接口/测试保留数（petStore.ts 5 / bubble-queue.test.ts 6 / petStore.test.ts 4 引用）与自报吻合 |
| M6 拖拽/右键原语义 | **PASS** | 拖拽生效：窗口 (1241,593) → (1355,707)，位移与拖距吻合（onPointerLeave={endDragTrack} 恢复后拖拽正常）；拖后右键菜单正常弹出（4 项）✓ |

## 四、挂账观察项（只记录不要求修复）

- **P2 面板数据定格**：本轮复现（面板 289.4M 为 14:23:52 挂载快照，非打开时刻实时值）——与 R1 报告一致，继续挂账
- **P3 idle 追加段截断** / **P3 合成事件限制**：未涉及本轮变更，继续挂账

## 五、环境恢复声明

- ✅ App 进程退出（pgrep 0 残留）；`pet.pass_through=false`、`bubble.toolBroadcast=true`（默认值未动）
- ✅ `pet.position` 恢复 (2482, 1186)（拖拽测试后的 (2710,1414) 已重置）
- ✅ opencode.db 全程只读（sqlite3 -readonly）
- ✅ 测试截图（13 张本轮）位于系统临时目录 `/var/folders/9k/.../opencode/m3-test/`，仓库零残留
- ✅ 仓库工作区与 R1 结束时一致（既有 docs 修订 + 未跟踪文件，非测试产物）；HEAD 未变

## 六、结论

**testVerdict: PASS**（焦点验收 5 项全部通过，0 失败；基线 351/236+1/tsc 0 全绿；改动与自报 9 files +25/−219 完全一致）

**testedSha: `f529e89ed0f1974333b6dc2ef1617a38eab6971a`**

- R1 补充轮 2（2026-08-25 14:05 用户裁定：**移除主动层悬停卡**——"悬停光标到宠物上浮现今日token消耗窗口，这个效果实际体感很差，让coder去掉这个功能点"）：三层快捷查看降为两层（① 被动层 idle 追加 + ③ 入口层右键菜单）；HoverToday 组件与 PetCanvas 悬停接线删除；token_stats_today 与 30s 缓存由右键菜单独享；M2 setHoverPaused 冻结接口为 M2 交付物保留（无运行时消费方，测试保留）；i18n 键 token.todayUnavailable 清退。**验收口径变化已由 supervised-coding 落笔**（2026-08-25 14:09）：V2-DESIGN §3.4（表格 ② 行+细节段移除声明）/§3.9（HoverToday 行+键清单）/§3.11（实机 item 3 两层化）/§3.12（R3 失效注记）共 6 处 + V2-TEST-CASES TC-M3-10（作废留档+移除后补充验收：悬停无卡片浮现）/TC-M3-12（三层→两层）/TC-M3-17（todayUnavailable 清退断言）共 3 处。status: reviewing → implementing（补充轮 2，tester R1 PASS 报告已在档但待验对象将更新），round 不变，testedSha 置空待新 HEAD。
- R1 补充轮 2: coder 完成（同会话续接），commit `f529e89`（`[task-pulsepet-v2-m3] R1: 补充——移除悬停今日 token 卡（用户 2026-08-25 裁定，三层降两层）`，commit 前已 fetch+merge origin/develop；supervised-coding 已核验 HEAD=f529e89、9 files +25/−219）。改动：HoverToday.tsx 删除；PetCanvas.tsx 悬停接线移除（onPointerEnter/Leave 防抖、setHoverEntered 订阅；canvas 恢复 onPointerLeave={endDragTrack} M6 原语义；顺手修复 endDragTrack 与 onContextMenu 挤行）；Pet.tsx 引用/渲染移除（留裁定注记）；petStore.ts hoverEntered 字段/setHoverEntered action/setPassThrough 悬停清零分支移除——**setHoverPaused 及接线原样保留（M2 交付物：petStore 5/bubble-queue 2/测试 6 处未动）**；todayToken.ts 保留（30s 缓存右键菜单独享，实现零改动）；i18n.ts 清退 token.todayUnavailable zh/en（grep 确认唯一消费方是 HoverToday）+ i18n.test.ts m3Keys 移除+新增清退断言；PetMenu.tsx 注释措辞同步零实现改动；global.css .hover-today* 8 样式块清退。自测证据：先红（vitest 1 failed=清退断言预期失败）→ `npm test` **351 passed（27 files）**（350+1 清退断言；HoverToday 本无专属单测）；cargo test --lib 236+1 ignored（Rust 零 diff 快跑）；tsc exit 0；npm run build ✓；tauri build 成功（PulsePet.app @14:17:15 / dmg @14:17:36）；残扫 grep HoverToday/hoverEntered/hover-today/todayUnavailable 零代码残余。**待验对象更新为 f529e89**（提交链 914ded0→7783bf5→f529e89）。
- R1（补充轮 2 后）: tester 焦点复验 **PASS**（testedSha=f529e89，同会话）。独立复跑基线全绿（vitest 351/27、cargo --lib 236+1i、tsc 0、产物 14:17 吻合）；diff --stat 7783bf5..f529e89 = 9 files +25/−219 与自报逐项一致、src-tauri 零 diff。焦点 5 项全过：① TC-M3-10 作废后补充验收——实机长悬停 1.5s/3 轮进出/穿透模式均**无任何卡片浮现**（OCR+Vision 双确认）、log show 12 分钟窗零 error/crash、宠物动画正常（穿透下 6 帧 2 哈希交替）；② 移除干净度——grep 五关键词 src/ 零代码残余（仅 i18n.test.ts 清退断言自身）；③ 回归抽查全过——TC-M3-11 菜单 4 项 ok 态 291.8M+点击直达默认今日、TC-M3-12 两层口径（菜单 291.8M<sqlite 292.8M 时间序自洽、面板 289.4M=启动挂载快照吻合）、TC-M3-09 抽查（Rust 零 diff 单测在）、气泡排队（ambient 4.5s 消失、**悬停中 POST 气泡照常显示——冻结干扰消除**）、M6 拖拽/右键原语义（位移吻合、菜单正常）。挂账确认：P2 面板数据定格本轮复现继续挂账、P3×2 未涉及。环境恢复：进程杀净、pass_through/toolBroadcast 默认值、pet.position 恢复 (2482,1186)、opencode.db 只读、13 张截图在临时目录、仓库零残留。
- R1: committer 审查 **APPROVED**（reviewedSha=f529e89=committerTaskId 会话 ses_fc7638655ffeTEQV6k98nsR5gH；**双通过达成，reviewedSha=testedSha=HEAD 核验一致**）。评审对象核对：三提交 stat 逐项吻合、净 28 files（+2625/−605，HoverToday 链内加删互抵）全在 pulse-pet/ 内、develop_opencode 恰 M3 三提交领先（开工同步纪律落实）、依赖零新增、DB 零迁移、docs 工作区 9+5 处修订逐条与实现吻合；bash 受限采信 tester 两轮证据+静态计数交叉核（+44−7=+37 与 314→351 吻合、Rust +15 吻合）。需求对应性 12 项全 ✅（数据层六路径 mock 过滤/token_stats_today/open_checked 复用、idle 追加四分支、悬停卡移除干净+onPointerLeave=endDragTrack M6 原语义恢复+setHoverPaused M2 交付物保留（引用计数 bubble-queue 5/petStore 5/测试 10）、柱图/KPI 四卡/tooltip 行序两裁定落实、砍饼图零残余、工具气泡三层净化责任划分与 R8 一致+N7 消耗语义+零阻塞契约不回归、i18n 双清退断言、不含项零预实现、裁定点 6 条复审全成立）。代码质量：SQL 全参数化、spawn_blocking+即开即关、无锁跨 await、删除残余 grep 零命中、PetCanvas 与 M6 基线净零 diff、plog! 纪律遵守。测试质量：断言真实性抽查全过、既有测试零篡改（改动均为签名适配或配套清退，无断言削弱）。**问题清单：P0/P1 无**；P2×1 继承 tester 挂账（面板数据定格——**处置意见：挂账去向=M4 面板改动轮**，修复方案仿 Settings tauri://focus 双触发）；P3×5：① idle 追加段截断（气泡文案/CSS 打磨轮）② 合成事件限制（记录）③ **V2-DESIGN §3.8"build_idle_report 不动"措辞与实现冲突——文档陈旧措辞，随交付回 spec 由 supervised-coding 顺手修订**④ todayToken.ts resetTodayCache 死导出（可选清理）⑤ plugin-hook.test.ts:763 注释草稿痕迹（打磨轮）。无需求边界问题。交付步骤清单 5 步已列（回写检查点→docs 回 spec 提交+§3.8 顺手修→push 三提交（用户指示后）→gh pr review 留痕（manifest 双 SHA 核验）→交付后跟进 P2/P3/插件发布联动）。

### Committer R1 报告原文（2026-08-25，reviewVerdict=APPROVED）

# PulsePet v2 M3 R1 — Committer 复审报告

## 一、评审对象核对

| 项 | 核对结果 |
|---|---|
| HEAD = testedSha | ✅ `f529e89ed0f1974333b6dc2ef1617a38eab6971a`（`git rev-parse HEAD` 一致） |
| 提交链 | ✅ `914ded0`（29 files +2799/−606）→ `7783bf5`（6 files +41/−20）→ `f529e89`（9 files +25/−219），三提交 stat 与声明逐项吻合 |
| diff 边界 | ✅ 基线 `330feea`（914ded0^）→ `f529e89` 净 28 files（+2625/−605），**全部在 pulse-pet/ 内**；`HoverToday.tsx` 在链内加删互抵（914ded0 +123 → f529e89 −123），filesChanged 29 项含之留档，一致 |
| develop_opencode 相对 origin/develop | ✅ 恰为 M3 三提交领先（开工同步纪律已落实，无混入其它提交） |
| 依赖变更 | ✅ **零新增**：28 个文件无 package.json / Cargo.toml / Cargo.lock |
| DB 迁移 | ✅ 零迁移：`bubble.toolBroadcast` 走 app_state 键值（db.rs 不在 diff） |
| docs 工作区修订一致性 | ✅ V2-DESIGN 9 处（§3.4 悬停移除注记/表②行/细节段、§3.5 tooltip 行序/KPI 卡序、§3.9 两行、§3.11 两层口径、§3.12 R3 失效）+ V2-TEST-CASES 5 处（TC-M3-05/07/10/12/17）逐条与实现吻合（详见二） |
| 环境声明 | bash 受限仅放行 git 只读命令，**未独立复跑** vitest/cargo/tsc/tauri build；采信 tester 两轮独立复跑证据（R1: 350/27·236+1i·tsc 0；R2: 351/27·236+1i·tsc 0·产物 14:17:15/14:17:36），并做了静态计数交叉核（新增 it 约 44 − 清退 7 = +37，与 314 基线→351 吻合；Rust +15 与 221+1→236+1 吻合） |

## 二、需求对应性逐项（以修订后文档为准）

1. **数据层** ✅ TokenRow +3 字段（model_id/json_valid 守卫/model NULL·损坏→None；project_name Rust 侧 `Path::file_name`、`/`→None；title by-session 独有）；LEFT JOIN project、GROUP BY day_expr,model_id、project_id 移除、range 同口径（`query_grouped("NULL")` 复用）；**mock 过滤覆盖全部 6 条查询路径含 query_current_session 与 token_stats_today**（token_stats.rs:108/113/253/323/368/468）；白名单 +model+title；`token_stats_today` async fn + spawn_blocking（:607）全套错误透传（open_checked 抽取复用，legacy-storage 判定较 v1 更全）。
2. **idle 追加今日** ✅ `build_idle_report_with_today` 同连接一次查询、total=in+out+cache_read（query_today_on SELECT 结构性不含 reasoning）、失败静默省略、仅 opencode（idle_hook_body agent 分流，CC 零查询单测保留）、`token_report_today` zh/en 逐字钉住（i18n.rs:117）。
3. **今日 preset** ✅ RangePreset+"today"、面板默认 `useState("today")`、分段首位今日；rangeForPreset 跨午夜单测。
4. **三层快捷查看→两层（用户 14:05 裁定）** ✅ 悬停卡移除干净：HoverToday.tsx 全删、PetCanvas 悬停接线移除且 **onPointerLeave={endDragTrack} 恢复 M6 原语义**（与 330feea 基线 diff 仅余注释）、petStore hoverEntered 三处移除、`setHoverPaused` **M2 交付物保留**（bubble-queue 5/petStore 5/测试 10 处引用在，无运行时消费方——与裁定一致）；token_stats_today + 30s 缓存菜单独享；被动层 idle 追加 + 入口层右键菜单构成两层，TC-M3-10 作废留档 + 移除后补充验收（tester 实机 OCR+Vision 双确认无卡片）。
5. **堆叠柱图 + 筛选** ✅ computeStackedBars 三段自底向上 output→input→cacheRead（几何断言钉住）、**agentFilter 仅参数位不实现**（N12 钉子：传 undefined ≡ 不传）、computeBars/pieSlices 删除 grep 零残余（仅注释提及）；HTML tooltip + 图例 aria-hidden 不可交互；chip 总量降序默认全勾仅柱图作用域；filter-row 多组容器 M5 预留位只渲染模型组；range 维无柱图。
6. **KPI 四卡（用户 12:30 裁定）** ✅ 实序 **总量 / cache read / input / output**（TokenStats.tsx:230-245），cost 卡移除、首卡无副行；sumRows reasoning 注入钉子（341 vs 2228）；cost 数据零删减（会话详情 formatCost 与 TodayStats.cost 均在）。
7. **tooltip 行序（用户 12:30 裁定）** ✅ `TOOLTIP_ROW_ORDER=["cacheRead","input","output"]` 唯一权威常量，TokenStats 渲染消费之；与柱内堆叠序独立（互逆断言钉子）。
8. **砍饼图 + 会话列表** ✅ ProjectPie/PROJECT_COLORS/.token-columns 双栏/pie 样式 grep 零残余；首列 title flex 省略 + tooltip（标题+id+本地时间）、NULL→id 前 8 位、New session* 回退原样；项目列 basename + global（project_id==="global"，裁定点②）→「全局」/unknown 回退；展开「模型」行；排序维持前端 token 降序。
9. **工具级气泡** ✅ 插件侧：DETAIL_TPLS 五族与 §3.7.1 表一致、extractDetailParam（read/edit basename、bash 剥 env 段+首词+路径 basename——P1-4、search ≤40 含分隔符取末段、web hostname、**websearch 无 URL 走 search 同款净化=裁定点⑤**）、detail 独立 20s 单桶、**消耗判定在 reaction 检查之后 + 网络成败不回滚（N7）**、仅 tool.execute.before 携带（两参调用形态保持，零阻塞契约 6 钩子返回 undefined 钉子不回归）；Rust：http_server 非空透传不解析不落盘（N8）、lib.rs emit_to("pet") 不判开关；桥：首个 `:` 切分、白名单、再净化（单行/≤40/控制字符 R8）、开关 store get 初始化+广播订阅零 IPC、ambient 入队 source=tool:\<tpl\>；开关 UI「宠物与播报」区 settings-check 形态不放功能管理区（P2-4）；README install.sh 重跑提醒。
10. **i18n** ✅ M3 新键 zh/en 完备断言 + totalSub/todayUnavailable 双清退断言；pie 旧键清退。
11. **不含项零预实现** ✅ CC hook/transcript 未动（claude-code-hook.js 不在 diff）；agent 筛选仅参数位无 UI；M4 定时任务/M5 atlas 零改动；穿透语义未改。
12. **coder 裁定点 6 条复审** ✅ ① json_valid 守卫（注释如实记录 R1 实测反例，达成同等降级——`m3_grouped_null_model_buckets_into_unknown_group`/损坏 JSON 用例钉住）；② global 判定前端 project_id==="global"（Rust 均 None，测试 s2 钉住）；③ tool_broadcast 移驻 interaction.rs（lib.rs:151 注释说明宏冲突，mock runtime 实测广播链路）；④ 旧 build_idle_report 已删无调用方（grep 确认 make_idle_hook 唯一消费 with_today）；⑤ websearch 同款净化（单测钉住）；⑥ vite informational 为 M2 既有（atlas.ts 不在 M3 diff，成立）。

## 三、代码质量

- **SQL**：全参数化（?1/?2），format! 仅注入编译期常量（day_expr/MODEL_ID_SQL/MOCK_FILTER_SQL），无注入面；GROUP BY day, model_id 改造与 ORDER BY day DESC 兼容 range 全 NULL。
- **线程/锁纪律**：token_stats_today spawn_blocking + 每次即开即关只读连接（NO_MUTEX 不跨线程）；tool_broadcast_set 短暂持锁后释放再 emit，无锁跨 await；detail hook 同步透传无锁。
- **净化边界**：插件提取层（剥 env/取 basename/hostname/≤40）→ Rust 透传（仅非空校验）→ 桥层格式兜底（白名单+单行+≤40+控制字符）——三层责任划分与 R8 一致；React 文本节点渲染天然转义；detail 受 http body 16KB 上限约束，无 DoS 放大面。
- **删除残余**：HoverToday/hoverEntered/setHoverEntered/hover-today/todayUnavailable grep 仅命中 i18n.test.ts 清退断言自身（与 tester R2 一致）；.kpi-sub/token-columns/pie-c*/.bar-fill 零残余；PetCanvas 与 M6 基线净零 diff（顺手修复的 `};  const` 挤行已归位）。
- **无新 eprintln**，新代码 plog! 纪律遵守。

## 四、测试质量

- 断言真实性抽查全过：TOOLTIP_ROW_ORDER 互逆钉子、清退断言（totalSub/todayUnavailable 双向）、P1-4 bash 净化族（`FOO=secret npm test`→npm、`/opt/homebrew/bin/npm test`→npm、混合 env+绝对路径）、TC-SEC 无原文（`--password`/`token=xyz`/路径片段不出现）、agentFilter N12 钉子、detail 桶四语义（含"状态被吞 detail 桶不消耗"与"网络失败不回滚"）、mock 过滤 6 路径、Rust 逐字文案钉。
- 既有测试零篡改：全部既有断言改动均为签名适配（buildPetMenuItems 增参）或删除函数配套清退（computeBars/pieSlices、build_idle_report→with_today 场景全覆盖：新鲜/陈旧/无记录/无库四分支保留）；无任何断言削弱。
- 计数：静态核新增/清退净量与 tester 独立复跑 351/236+1 吻合（环境受限未复跑，采信 tester 证据）。

## 五、问题清单

**P0 / P1：无。**

**P2（继承 tester 挂账，不阻塞交付）**：
- `src/panel/TokenStats.tsx:128`（load 仅挂载执行）+ `src-tauri/tauri.conf.json:38`（panel visible:false 隐藏创建即挂载）——面板 Token 页数据定格于 App 启动时刻；TC-M3-11「无缝衔接」/TC-M3-12 交叉在长运行 App 首开时不成立。v1/M2 既有行为、M3 用例显性化。**处置意见：挂账，去向=交付后小修（建议并入 M4 面板改动轮，避免重复返工）**；修复建议采纳 tester 方案——仿 Settings.tsx:164 的 `tauri://focus` 双触发（模式已在 Settings 验证）。

**P3**：
1. idle 追加段在 220px 气泡被单行省略截断（tester R1 实机多次捕获）——文案/口径正确且有单测钉住，纯视觉可见性问题。**挂账记录，去向=气泡文案/CSS 打磨轮**（两行或精简文案）。
2. 合成事件工具限制（悬停/菜单测试依赖小步移动）——测试环境限制非产品缺陷。**记录**。
3. `pulse-pet/docs/v2/V2-DESIGN.md §3.8` 行"`build_idle_report` 不动（追加在 lib.rs hook）"与 §3.2「同连接顺带 SUM（一次查询）」及实现（删旧建 `build_idle_report_with_today`）措辞冲突——行为遵循 §3.2 无矛盾，**属文档内部陈旧措辞，随交付阶段回 spec 提交时由 supervised-coding 顺手修订**，不转 coder。
4. `src/pet/todayToken.ts:19` `resetTodayCache` 死导出（悬停卡移除后无调用方，2 行）——可选清理，不阻塞。
5. `src/lib/plugin-hook.test.ts:763` 行内注释含草稿痕迹（"t = 9_000; // …未到？—— t = 11_000"）——断言正确，注释可随打磨轮清理。

## 六、需求边界问题

无行为级矛盾（§3.8 措辞冲突见 P3-3，属文档修订范畴）。spec 与实现行为在修订后口径下全部自洽。

## 七、结论

**reviewVerdict: APPROVED**
**reviewedSha: `f529e89ed0f1974333b6dc2ef1617a38eab6971a`**（= testedSha）

无 CASE_BUG 裁定请求，无裁定结论节。

## 八、交付步骤清单（用户确认交付后执行）

1. supervised-coding 回写检查点：reviewVerdict=APPROVED、reviewedSha=f529e89、committerTaskId、endReason、updatedAt 更新。
2. docs 工作区修订随回 spec 提交（V2-DESIGN 9 处 + V2-TEST-CASES 5 处；**顺手修订 §3.8 陈旧措辞**，P3-3）。
3. 推送三提交至 origin/develop（SSH 路径，用户明确指示后；push 前 `ssh -T git@github.com` 确认）。
4. 用户确认交付后我执行 `gh pr review` 落痕（此时 gh 写入类命令放行）；核验 evidence manifest 双 SHA 与 HEAD=f529e89 一致方可放行。
5. 交付后跟进项（不阻塞）：P2 面板定格修复（M4 轮）、P3 打磨项、插件发布联动（磁盘插件已为最新 md5，README 升级提醒已落）。

- **交付启动（2026-08-25 19:20 用户确认"交付"）**：三步执行——① coder 回 spec 提交（docs/v2 两文件全部修订 + supervised-coding 顺手修 §3.8 措辞 P3-3 与 tool_broadcast 落位注记，已落笔 2026-08-25 19:21）+ 同步 origin/develop + SSH 推送 develop_opencode + 开 PR（base=develop，留 manifest 占位）；② committer gh pr review 留痕；③ coder 补写 evidence manifest 进 PR description。不自动合入。
- **交付执行①（2026-08-25 19:26）**：Coder 完成——回 spec 提交 `562879a`（`[task-pulsepet-v2-m3] R1: 回 spec 文档口径`，仅 V2-DESIGN.md + V2-TEST-CASES.md 两文件，diff 逐字核验；.opencode/ 与 images/ 未进提交）→ fetch origin/develop=330feea 无新提交 → SSH 推送成功（2f3b86a..562879a）→ 开 PR：**https://github.com/yq3/lab/pull/15**（base develop / head develop_opencode，4 commits：914ded0→7783bf5→f529e89→562879a；body 六节齐备 + EVIDENCE_MANIFEST_PLACEHOLDER 占位）。待：② committer gh pr review → ③ manifest 补写。
- **交付执行②（2026-08-25 19:31）**：Committer 已执行 `gh pr review 15 --comment` 留痕——**COMMENTED**（同账号 POC 约定，Review ID `PRR_kwDOTsiHgs8AAAABKx4zYg`，submittedAt 2026-08-25T11:30:58Z UTC）：正文五节（① 评审对象核对：4 commits 链、双 SHA=f529e89、回 spec 562879a 纯文档 11+5 处逐字复核一致（§3.8 措辞修订=P3-3 建议落地）、净 28 files 依赖零新增；② R1 审查结论摘要：APPROVED 无 P0/P1、需求 12 项、裁定点 6 条、两次用户裁定落实；③ tester 两轮 PASS 摘要；④ knownIssues 移交：P2→M4 + P3×5 + M2 目验 7 项待用户；⑤ 交付声明：COMMENTED 留痕、不自动合入、manifest 待补写后复核）。前置 reviews=[] 确认、提交后二次核验恰 1 条无重复（正文 2357 字符逐字一致）。PR 保持 OPEN。
- **交付执行③（2026-08-25 19:35）**：Coder 已把 Evidence Manifest JSON 写入 PR #15 description（占位替换，body 5605→7388 字节；14 顶层键：taskId/pr/milestone/headSha(f529e89)/specCommit(562879a)/commits 4 链/verdicts（tester PASS×2 + committer APPROVED 双 SHA + reviewer COMMENTED PRR_kwDOTsiHgs8AAAABKx4zYg）/testEvidence 六类/acceptanceCriteria（16 PASS + TC-M3-10 作废留档 + 用户三次裁定）/specUpdates（11+5 处 + §3.8 修订）/knownIssues 三组/userDataNote（插件已装、opencode 重启生效）/environment/timestamp）。核验：PLACEHOLDER=0、前六节正文逐字节一致（startswith 断言）、JSON 14 键可解析、Review 留痕仍在（id 5018366818）。**交付三步全部完成，PR #15 OPEN 等待用户合入决定（不自动合入）**。

- **合入（2026-08-25 19:46 用户确认"合入"）**：`gh pr merge 15 --merge --delete-branch=false` 成功——**MERGED**（merge commit `53e447fdc2c283faa3fce57d1e757dedafc45bc0`，mergedAt 2026-08-25T11:46:57Z）；本地 develop_opencode 已 fetch + fast-forward 至 53e447f=origin/develop（分支保留）。**M3 任务收官**（status=approved 终态，testedSha=reviewedSha=f529e89，PR 留痕 COMMENTED + manifest 齐备）。遗留事项已回写：M3 新移交 5 条去向注明（P2→M4 面板改动轮、P3×5）；M2 目验 7 项继续待用户反馈；P3-3 §3.8 措辞已随回 spec 提交清偿。检查点文件随收官提交至 develop。
