---
taskId: task-pulsepet-m2
target: pulse-pet/
coderTaskId: ses_ffa20a813ffeTUOeSvJg47Nyuh
testerTaskId: ses_ff82d16e7ffeIYuGs3lzDtAQdh
committerTaskId: ses_ff810893affelsNTm9Ow45smH2
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 53f495b9f9159c09ce7153073ed6e08d887ca0eb
reviewedSha: 53f495b9f9159c09ce7153073ed6e08d887ca0eb
filesChanged: [pulse-pet/src-tauri/src/http_server.rs, pulse-pet/src-tauri/src/session_state.rs, pulse-pet/src-tauri/src/runtime.rs, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/db.rs, pulse-pet/src-tauri/src/windows.rs, pulse-pet/src-tauri/Cargo.toml, pulse-pet/src-tauri/Cargo.lock, pulse-pet/opencode-plugin/pulse-pet-hook.js, pulse-pet/opencode-plugin/pulse-pet-hook.d.ts, pulse-pet/opencode-plugin/opencode-config.mjs, pulse-pet/opencode-plugin/opencode-config.d.mts, pulse-pet/opencode-plugin/install.sh, pulse-pet/opencode-plugin/install.ps1, pulse-pet/opencode-plugin/README.md, pulse-pet/src/lib/http-bridge.ts, pulse-pet/src/lib/agent-adapter.ts, pulse-pet/src/lib/adapters/opencode.ts, pulse-pet/src/pet/petStore.ts, pulse-pet/src/pet/PetCanvas.tsx, pulse-pet/src/main.tsx, pulse-pet/package.json, pulse-pet/package-lock.json, pulse-pet/src/lib/opencode.test.ts, pulse-pet/src/lib/http-bridge.test.ts, pulse-pet/src/lib/opencode-config.test.ts, pulse-pet/src/lib/plugin-hook.test.ts, pulse-pet/src/lib/plugin-http.test.ts]
endReason: null
createdAt: 2026-08-15T22:43:26+08:00
updatedAt: 2026-08-16T08:44:20+08:00
---

# task-pulsepet-m2: pulse-pet M2 事件链路开发

## 任务原文

在 `lab/pulse-pet/`（M1 已落地骨架，HEAD=efd67f1 已合入 develop）开发 M2 事件链路。依据 DESIGN.md §10.2 里程碑 M2、§3 事件链路、TEST-CASES.md TC-EV 章节（+TC-SEC 相关用例）对应用例。开发分支 `develop_opencode`（交付后约定：coder 固定提交分支，提交前先同步 origin/develop）。

**M2 范围（DESIGN.md §10.2，1 周）**：
1. **Rust 侧 HTTP server**（§3.2，`src-tauri/src/http_server.rs`）：
   - 绑定 `127.0.0.1:<port>`，端口固定首选 `47811`，冲突回退随机端口写 endpoint 文件
   - 路由：`GET /health`（无鉴权）、`GET /whoami`（token）、`POST /state`（token，body `{sessionId, kind, agent, project?, detail?}`）、`POST /bubble`（token）
   - 限流：共享 30 req/s；单次连接 `Connection: close`（一次性）；连接超时 ~2s、响应超时 ~3s；body 上限 ≤16KB
   - body 契约校验：`sessionId/kind/agent` 必填，`project/detail` 可缺省；`kind` 非法值 → 400
   - v1 return channel：response 带 `{action:null}`
   - 选用 `tiny_http`（零异步运行时依赖，体积小，DESIGN §2.1 倾向）
2. **runtime 目录与 token/endpoint/killswitch 机制**（§3.1）：
   - POSIX 端 `~/.pulsepet/runtime/`；Windows 端 `%LOCALAPPDATA%\pulsepet\runtime\`
   - `update-token`：随机 token，mode 0600（POSIX），App 启动生成写入、退出清除、下次启动重新生成（每次会话轮换）
   - `endpoint`：存 `127.0.0.1:<port>`，端口冲突换端口时更新
   - `hooks-disabled`：存在则插件整体跳过（killswitch）
3. **opencode 插件 JS**（`opencode-plugin/pulse-pet-hook.js`，~200 行，§3.1）：
   - 监听官方 hooks → 归一化 kind → POST /state
   - 事件归一化全集（TC-EV-04 表）：`session.status` idle→idle（状态复位主信号）、其它→working；`chat.message`→thinking；`tool.execute.before` edit/write/patch/apply_patch→editing；`tool.execute.before` bash/shell/terminal 含 test/vitest/jest/pytest/npm test→testing；`permission.asked`→waiting-permission；`session.error`→error；`event` bus→按分类透传
   - 状态复位（M2 done 补充验证项①②）：实测 `tool.execute.after` / `chat.message` 完成事件是否存在及字段区分；据此选定主复位信号 + 兜底信号（设计默认：`tool.execute.after`→working 为主，`session.status` 非 idle 兜底；若 opencode 无 after 事件则反之）
   - 节流（v1 定案表，§3.1）：speech 20s（thinking/success/error）、permission 3s（waiting-permission）、reaction 10s（working/editing/testing/idle）；三类互不干扰
   - 自忽略：正则跳过 `pulsepet_status/say/react` 工具防回环
   - 消息净化：气泡文案只来自白名单语音池（thinking/success/error/permission/waiting 五类模板），不展示原始 prompt/输出/路径/URL/secret；命令行具体内容仅用于分类不发给宠物；waiting 类为 PulsePet 扩展模板
   - 气泡文案单行、1-140 字符（超长截断或丢弃）
   - 失败静默 + 指数退避（TC-EV-07）：endpoint/token 文件缺失、连接拒绝、超时、401 一律静默跳过（不打日志不报错）；首次立即重试 1 次，之后 1s→2s→5s→30s 封顶；文件重新出现后下次事件恢复立即投递
   - killswitch：`hooks-disabled` 存在则整体跳过
4. **安装脚本**（`opencode-plugin/install.sh` / `install.ps1` + README）：
   - 拷贝 hook 到 `~/.config/opencode/plugins/`；`opencode.json` 的 `plugin` 数组合并 `pulse-pet` 一项（带 `--pulse-pet-managed` 标记）
   - 幂等（重复安装不产生重复项）；JSONC 感知（注释行与尾逗号保留，合并后仍为合法配置）；用户原有 plugin 项保留
   - 卸载只移除带 `--pulse-pet-managed` 标记的项 + 删插件文件
5. **`session_state.rs` 多 session 状态机 + 优先级合并**（§3.3）：
   - `HashMap<SessionId, SessionState>`；显示状态优先级合并：`error > waiting-permission > testing > editing > thinking > working > idle`
   - 30s 无 `/state` 事件的 session 回收为 idle；`/health` 不参与回收判定
   - 瞬态超时兜底（§3.1 ③）：任一瞬态 N 秒（默认 30s，可配）内无新事件 → 回退 working；再无事件 30s → 回退 idle
6. **前端 `http-bridge` + `petStore` + 状态驱动动画**（§9 项目结构）：
   - `src/lib/http-bridge.ts`：收来自 Rust 的 Tauri event（事件→petStore）
   - petStore 升级：当前 state / session 优先级合并；状态驱动占位精灵动画（M1 已有 5 状态渲染，接入事件源）
   - `src/lib/agent-adapter.ts` + `src/lib/adapters/opencode.ts`：AgentAdapter 抽象（id / normalizeRawEvent / tokenSource / iconSet），v1 仅实现 OpenCodeAdapter（TC-EV-23）
7. **端到端验证**（TC-EV-22 + M2 done 补充验证项③）：开 opencode 跑真实任务 → 宠物切换 idle/thinking/working/success；验证宠物不会卡在 editing/thinking 超过 30s

**M2 明确不做**：token 统计（M3）、提醒调度器与烟花逻辑（M4）、atlas 加载（M5）、穿透切换/拖拽/热键/右键菜单（M6）、todo 插件机制（M7）、CI workflow 修改（§13，首次发版前再做，TC-CI-02 不在本轮）、Windows 实机验证（M8，TC-EV-03/08b 只做代码级/文档级）。

## 需求确认

- [x] 用户已确认（确认后 status=implementing）——2026-08-15 用户确认：① M2 范围无修改；② M1 遗留 8 项全部并入；③ P2-8 口径回写由 supervised-coding 落笔（已执行：TEST-CASES.md TC-APP-01 预期 6、TC-SP-01 追加口径）
- 历史遗留事项清单（M1 检查点 task-pulsepet-m1.md，默认并入本任务）：
  1. **P2-1** db.rs 未开 `PRAGMA foreign_keys=ON`（ON DELETE CASCADE 不生效，M4/M7 级联删除陷阱）→ M2 修复
  2. **P2-2** lib.rs CloseRequested 只护 panel，pet 窗口 ⌘W 可销毁且无重建路径 → M2 修复（防护扩到 label=="pet"）
  3. **P2-3** PetCanvas loadCatImage 无 .catch（素材缺失 unhandled rejection）→ M2 修复（console.error + 纯色兜底）
  4. **P2-4** dpr 回落竞态（onDprChange rAF 延迟一帧再 resize）→ M2 修复
  5. **P2-5** Moved 每次同步写 2 条 SQL（M6 拖拽热点）→ M2 加 ~150ms trailing 防抖
  6. **P2-6** 恢复位置无屏幕边界校验 → M2 低成本 clamp 到 current_monitor 可视范围（跨显示器语义 M6）
  7. **P2-7（用户定案：提前到 M2）** 状态圆点移除——宠物左上角状态圆点（idle 灰点等）用户要求 M2 阶段移除（原计划 M5）；M1 R4 已移除文字仅剩纯色圆点，M2 移除圆点本身
  8. **P2-8（需求边界，随 P2-7 落实）** TEST-CASES.md TC-APP-01/TC-SP-01 补回写"pet 画布无任何文字渲染、无状态圆点"口径（由 supervised-coding 落笔，coder 禁改用例文档）
  - 遗留事项对应的测试用例更新：TEST-CASES.md TC-APP-01/TC-SP-01 验收口径（画布无文字、无状态圆点）；TC-EV-06 已含 30s 超时兜底验收

## 遗留事项（跨任务移交）

- [x] M1 遗留 8 项 P2 全部清偿（来源 task-pulsepet-m1，2026-08-16）：P2-1 FK pragma / P2-2 pet ⌘W 防护 / P2-3 loadCatImage catch / P2-4 dpr 竞态 / P2-5 Moved 防抖 / P2-6 位置 clamp / P2-7 画布无状态圆点 / P2-8 TEST-CASES 口径（supervised-coding 落笔）。tester 逐条 PASS。
- [ ] **新移交 M3（2026-08-16）**：
  - P2-9 opencode-config.mjs:57-59 tokenizer literal 分支死循环（非法 JSONC 字符 → install.sh 挂死；修复：literal 分支 `if(i===start) i+=1` + 补非法输入与 block 注释用例）
  - P2-10 runtime.rs:64-68 token 文件先 write 后 chmod 0600 的 umask 短窗口（修复：OpenOptions mode(0o600) 一步到位）
  - P3 六条（不阻断）：http_server accept Err 静默退出无重启 / 插件并发 deliver Backoff 跳级 / connection:close fetch forbidden header 冗余可删 / install.ps1 Out-File BOM / classifyEvent 未处理总线 permission.asked / session_state 回收不 remove 内存累积
  - 测试缺口 4 条：tokenizer block 注释用例、tokenizer 非法输入用例（随 P2-9）、Backoff 并发行为、服务端空闲连接语义锁定测试（TC-EV-14 措辞更新后补）
- [ ] **M5 前定案项（回 spec 已落笔 DESIGN §3.1）**：同桶升级放行语义（新 kind 优先级 > 已投递 kind 时绕过冷却）需在 M5 atlas 前实现
- [ ] **M3/M4 引入项**：success 状态事件驱动（M3 token 会话汇报 / M4 todo 完成）；限流豁免 /health 评估（M3+ 心跳引入时）

## 验收标准（对应 TEST-CASES.md）

- **TC-EV-01 插件安装（macOS）**：hook 拷贝、opencode.json 合并带 `--pulse-pet-managed`、用户原 plugin 保留、幂等、JSONC 感知
- **TC-EV-02 插件卸载**：只移除 managed 项 + 删文件，用户原项保留
- **TC-EV-04 事件归一化全集**：真实 opencode 场景 8 种事件 → 8 种归一化 kind 全部正确切换
- **TC-EV-05 状态复位①**：实测 tool.execute.after / chat.message 完成事件存在性与字段区分，选定主复位 + 兜底信号并记录
- **TC-EV-06 状态复位③**：瞬态 30s 超时回退 working → 再 30s 回退 idle；完整任务不卡瞬态超 30s
- **TC-EV-07 App 未启动插件静默**：无报错无日志；指数退避序列（模块级单测断言 1s→2s→5s→30s）；恢复后立即投递
- **TC-EV-08 token 文件生命周期**：存在 mode 0600 随机 token；退出清除；重启轮换
- **TC-EV-09 endpoint 端口回退**：首选 47811 写文件；冲突换随机端口更新；插件读最新端口
- **TC-EV-10 killswitch**：hooks-disabled 存在期间整体跳过；删除后恢复；无需重启 opencode
- **TC-EV-11 HTTP 鉴权**：无 token 401 / 错 token 401 / 对 token 200（{action:null}）
- **TC-EV-12 HTTP 路由表**：/health 200 无鉴权；/whoami、/state、/bubble 带 token 200；未知路由 404；body 缺 sessionId/kind/agent → 400、kind 非法 → 400、合法 body 含缺省字段 → 200
- **TC-EV-13 限流**：超共享 30 req/s 被拒（429 或连接拒绝）；全局共享非 per-session
- **TC-EV-14 超时与连接语义**：连接 ~2s、响应 ~3s 超时；Connection: close 一次性
- **TC-EV-15 body 上限**：>16KB 被拒（413/400）不崩溃；≤16KB 正常
- **TC-EV-16 多 session 状态机**：A editing + B error → 宠物 error；优先级合并正确
- **TC-EV-17 session 回收**：30s 无事件回收 idle；/health 不参与
- **TC-EV-18 节流**：speech 20s / permission 3s / reaction 10s 冷却生效且互不干扰
- **TC-EV-19 自忽略**：pulsepet_status/say/react 事件被跳过防回环
- **TC-EV-20 消息净化（插件侧）**：气泡只来自五类白名单模板；无原始路径/URL/secret/代码片段
- **TC-EV-21 气泡文案约束**：单行、1-140 字符
- **TC-EV-22 展示一致性**：无人值守 30 分钟真实任务，状态吻合无卡死
- **TC-EV-23 AgentAdapter 抽象**：接口存在（id/normalizeRawEvent/tokenSource/iconSet），v1 仅 OpenCodeAdapter，新增 adapter 不改主链路（文件级）
- **TC-SEC-03 本地 HTTP 安全边界**：仅绑 127.0.0.1；无 token 全 401；不暴露局域网
- **TC-SEC-04 token 文件权限（POSIX）**：mode 0600 owner 当前用户
- **TC-SEC-06 隐私**：事件不明文落盘（仅内存 HTTP 传递）
- **M1 遗留修复验收**：FK pragma 生效（级联删除正确）；pet ⌘W 防护（CloseRequested 覆盖 pet）；loadCatImage 有 catch；dpr 回落无竞态；Moved 防抖；恢复位置 clamp；**画布无状态圆点**（TC-APP-01/TC-SP-01 口径更新后）
- 回归基线：npm test（M1 12 项 + 新增模块单测）全通过；cargo test（M1 3 项 + 新增 http_server/session_state 测试）全通过；npm run build / tauri build 成功

## 轮次记录

- R1: coder 完成，commit `53f495b`（`[task-pulsepet-m2] R1: M2 事件链路（tiny_http server + opencode 插件 + 状态机）+ M1 遗留 8 项 P2`，分支 develop_opencode，提交前已同步 origin/develop=0 ahead）。改动：28 文件 +2882/-46——Rust 侧 http_server.rs（tiny_http 路由/鉴权/契约校验/30req/s 限流/16KB 上限/Connection close/2s 超时）、session_state.rs（Kind 8 值+优先级合并+30s 回收+瞬态两步兜底）、runtime.rs（token 0600/endpoint/killswitch 平台路径）、lib.rs（M2 接线+get_display_state command+P2-2 pet ⌘W 防护）、db.rs（P2-1 FK pragma+级联测试）、windows.rs（P2-5 150ms trailing 防抖+P2-6 clamp_position 纯函数 4 单测）；opencode-plugin/ 插件本体（归一化+三桶节流+指数退避+净化白名单+自忽略）+ install.sh/ps1（JSONC 幂等合并/卸载 managed 标记）+ README；前端 http-bridge.ts/agent-adapter.ts/adapters/opencode.ts/petStore 升级/PetCanvas（P2-3 catch、P2-4 rAF 延迟一帧、P2-7 移除圆点）。自测证据：npm test 53 passed（7 files）、cargo test 34 passed、npm run build 成功、tauri build 成功（.app+.dmg）、install.sh 实测（JSONC 合并+幂等+卸载）、端到端真实 opencode（临时 XDG config + mock server 47812，收到 thinking/working POST）。**TC-EV-05 实测结论**：opencode 1.18.18 插件 API 与 DESIGN 假设有偏差——① 无 plugin() 工厂，正确格式 export default {id, server}；② plugin 数组本地项必须路径 spec（裸名当 npm 包、全局 plugins/ 不自动扫描）；③ tool.execute.after 存在（input:{tool,sessionID,callID,args}）→ 选为主复位信号→working；④ chat.message 存在→thinking，无独立完成事件；⑤ 兜底复位=event bus session.status（idle/busy/retry）+ session.idle 事件→idle，App 侧另有 30s 超时兜底。遗留/局限：① reaction 节流副作用——busy→working 先于 tool.execute.before→editing，同属 reaction 10s 桶，真实流 editing/testing 常被首个 working 节流合并（建议 supervisor 裁定瞬态是否升级覆盖 working）；② response 超时 3s 无法在 tiny_http 严格强制（recv_timeout 2s + Connection close 一次性实现）；③ success 状态 v1 无事件驱动（SessionStatus 仅 idle/busy/retry），留待 M3/M4；④ Windows 未实机验证（M8）；⑤ agent/project/detail v1 校验不落盘。
- R1: tester 验证 **PASS**（testedSha=53f495b）。环境：macOS 26.5.2 M4 Retina 2×、node 24.18/rustc 1.97.1、真实 GUI 会话 open .app + release 直跑（M2 标记 strings 核对）、环境完整恢复。自动化基线：npm test 53 passed（7 files）、cargo test 34 passed、npm run build 成功、tauri build 产物与 commit 一致（未重跑）。**TC-EV-01~23 全 PASS**：01 安装（路径 spec+JSONC+幂等+边界用例）、02 卸载、04 归一化 8 场景+真实 e2e（thinking/working POST 到达）、05 复位信号独立实测（tool.execute.after 存在为主复位→working；chat.message 无独立完成事件；session.status idle/busy/retry+session.idle 兜底）、06 瞬态 30s→working→30s→idle 两步回退（单测+运行时眨眼信号实证 0/60→35s 0/60→70s 3/60）、07 静默+退避（死端口实测无报错；退避序列 mock 0→1s→2s→5s→30s；恢复立即投递 9→11）、08 token 0600+退出清除+重启轮换、09 端口回退 47811→51371 endpoint 更新+curl 实测、10 killswitch（9→9 跳过→9→11 恢复）、11 鉴权（401/401/200 {action:null}）、12 路由表（/health 200、/whoami/state/bubble token、404、body 400 契约全）、13 限流（40 连发 30×200+10×429；不同 sessionId 仍 30×200+5×429 证全局共享）、14 超时（Connection close 一次性 EOF 实测；空闲连接服务端不主动断——观察项②）、15 body 上限（17KB→413 不崩、16.2KB→200）、16 多 session 优先级（运行时 blink 观测+单测全序）、17 回收（>2min 无事件→idle 眨眼恢复；/health 不参与）、18 节流三桶独立、19 自忽略、20 净化（detail 根本不发送）、21 文案 1-140 单行、22 展示一致性（全链路 POST→眨眼实证+真实 e2e）、23 AgentAdapter（接口+仅 OpenCodeAdapter+文件级）。**TC-SEC-03/04/06 PASS**（lsof 仅 127.0.0.1、LAN 拒绝、0600、不明文落盘）。**M1 遗留 8 项 P2 全 PASS**（P2-1 级联单测、P2-2 ⌘W hide 实测、P2-3 catch、P2-4 rAF、P2-5 150ms 防抖运行时 800ms 后写库、P2-6 clamp 单测+屏外 (9000,9000) 恢复落 (1250,736)、P2-7 grep 0 匹配+截屏仅猫本体 39504 bright px、P2-8 口径一致性核验）。回归：TC-APP-01/02/13、TC-SP-01/01b/02 全 PASS。**确认缺陷无**；4 观察项（P2 不阻断）：① reaction 节流合并——busy→working 先占 reaction 10s 桶，真实流 editing/testing 从未到达服务器（占位阶段降级渲染无视觉影响，M5 atlas 后需裁定瞬态升级覆盖 working，M5 前处理即可）；② TC-EV-14 字面偏差——空闲连接服务端不主动断、3s 响应超时无服务端强制（recv_timeout 2s 抗慢连接+插件 AbortSignal 3s 客户端兜底，语义成立，需 committer 裁定用例措辞）；③ SIGTERM 强杀残留 runtime 文件（下次启动覆盖无危害）；④ 限流计费含 /health 与 401（v1 无心跳无影响）。coder 5 遗留项裁定：①确认 P2 不阻断、②确认 P2、③success 无事件驱动=设计事实非缺陷（M3/M4 引入）、④Windows M8、⑤校验不落盘与 DESIGN 一致。
- R1: committer 审查 **APPROVED**（reviewedSha=53f495b）。基线：28 文件 +2882/-46，HEAD=testedSha=reviewedSha 三方一致；M1 已审区域零改动。需求对应性：7 大项全有实现+测试+验证；24 验收条（TC-EV-01~23 除 03/08b Windows 代码级外 + TC-SEC-03/04/06）逐条成立；M2 不做项零预实现；M1 遗留 8 项 P2 全修复有验证。偏离裁定（a~h）：a 插件 export default {id,server} 合理适配（实测依据三方一致，建议 DESIGN §3.1 回写一行）；b plugin 路径 spec 合理适配（建议 TC-EV-01 预期 2 措辞同步，低优先）；c 复位信号实测定案非偏离（任务原文 M2 done 验证项①要求的实测流程）；d **success 无事件驱动=需求边界问题**（DESIGN §10.2 含"切换 success"但 opencode 无 success 事件，建议补注"M3/M4 引入"，M2 按"不可达、链路就绪"记录）；e 优先级链 success 插入 thinking/working 之间合理适配（建议 DESIGN §3.3 回写定案）；f 插件只发三字段合理适配（更严格、隐私更优）；g response 3s 无服务端强制合理适配+TC-EV-14 用例口径需更新；h 限流含 /health 与 401 接受。代码质量：http_server 分层可测/限流固定窗口可接受/锁无 panic；session_state 两步回退重置计时基准正确、回收置 idle 不 remove（~100B/会话缓慢累积 POC 接受）；runtime rand 0.8.7 ChaCha12 CSPRNG 190bit 熵足够；lib.rs 接线无竞态；插件归一化与 DESIGN 表一致（permission.ask hook vs 总线 permission.asked 双处理）；install 幂等安全。**无 P0/P1**。新增 P2（建议并入 M3 遗留清单）：P2-9 opencode-config.mjs:57-59 tokenizer literal 分支死循环（非合法 JSONC 字符如 @/单引号时 while 零消费→install.sh 挂死；建议 literal 分支 if(i===start) i+=1 + 补非法输入用例）；P2-10 runtime.rs:64-68 token 文件先 write 后 chmod 0600 存在 umask 短窗口（建议 OpenOptions mode(0o600) 一步到位）。P3 六条：① http_server accept Err 静默退出无重启；② 插件并发 deliver 失败 Backoff 跳级；③ connection:close 为 fetch forbidden header 被忽略（纯冗余可删）；④ install.ps1 Out-File BOM（tokenizer 已容忍）；⑤ classifyEvent 未处理总线 permission.asked 事件类型（前端兜底已双处理）；⑥ session_state 回收不 remove 内存累积。测试质量良好（jsoncToJson 独立校验、退避 mock 真等待序列、Rust TcpStream 集成测试）；缺口 4 条不阻断（block 注释用例、tokenizer 非法输入、Backoff 并发、空闲连接语义锁定测试）。观察项裁定：① reaction 节流合并=**需求边界问题**（DESIGN §3.1 未定义同桶升级语义；建议口径"同桶升级放行——新 kind 优先级>已投递 kind 时绕过冷却"，M5 前定案，本轮不动代码）；② TC-EV-14 措辞需更新（改为"accept 周期 2s + 插件 AbortSignal 3s 兜底 + Connection: close 一次性"，supervised-coding 落笔）；③ SIGTERM 残留接受不做处理（死 token/死端口，下次启动覆盖）；④ 限流计费接受不改（401 计入反有抑制暴力猜 token 之效）。**回 spec 事项 5 条（supervised-coding 落笔，coder 不动）**：① DESIGN §3.1 节流表补"同桶升级放行"语义；② TC-EV-14 措辞更新；③ DESIGN §10.2 补注 success 不可达（M3/M4 引入）；④ DESIGN §3.3 优先级链回写 success 定案位；⑤（低）DESIGN §3.1 插件注册格式/路径 spec 与 TC-EV-01 预期 2 措辞同步。
- **双通过确认（2026-08-15）**：testVerdict=PASS + reviewVerdict=APPROVED，reviewedSha=testedSha=HEAD=53f495b，status=approved。待：向用户汇报 + 回 spec 5 条落笔确认 + 交付确认（分支推远端 + PR → develop + gh pr review 留痕 + evidence manifest）。
- **回 spec 落笔（2026-08-15 用户确认，supervised-coding）**：DESIGN.md §3.1 节流表补"同桶升级放行"语义（editing(4)>working(1) 绕过冷却，M5 前实现，30s 超时兜底）+ §3.1 插件注册格式修正（export default {id,server}、plugin 路径 spec、全局 plugins/ 不自动扫描）+ §3.3 优先级链 success 定案位（error>waiting-permission>testing>editing>thinking>success>working>idle）+ §10.2 M2 实测结论（tool.execute.after 主复位/chat.message 无完成事件/session.status+session.idle 兜底）+ success 不可达注记（M3/M4 引入）；TEST-CASES.md TC-EV-14 措辞（recv_timeout 2s + AbortSignal 3s 兜底 + Connection close 一次性）+ TC-EV-01 预期 2 路径 spec。共 4 处 DESIGN + 2 处 TEST-CASES。
- **交付执行（2026-08-15/16）**：Coder 提交回 spec 文档 `bef11ac`（`[task-pulsepet-m2] R1: 回 spec 文档口径`，仅 DESIGN.md+TEST-CASES.md +9/-5）→ 同步 origin/develop（Already up to date）→ SSH 推送 develop_opencode 成功（efd67f1..bef11ac）→ 开 PR：**https://github.com/yq3/lab/pull/2**（base develop / head develop_opencode，title `[pulse-pet] M2 事件链路：tiny_http server + opencode 插件 + 多 session 状态机`，body 8 节：摘要/验收结论/M2 范围/TC-EV 通过摘要/P2 修复/Known Issues/回 spec 5 条/Evidence Manifest）。Committer 已执行 `gh pr review` 留痕——**COMMENTED**（同账号 POC 约定，2026-08-16T00:35:49Z）：正文五节（评审对象核对：30 文件全在 pulse-pet/、双 SHA 三方一致、bef11ac 纯文档免增量重审 + 5 条回写逐条复核一致；APPROVED 结论摘要；knownIssues 移交 M3；不自动合入声明）。Coder 已把 evidence manifest JSON 写入 PR description（JSON.parse 校验通过：taskId/headSha=testedSha=reviewedSha=53f495b/2 commits/verdicts/testEvidence 9 键/knownIssues/specUpdates/reviewers）。**交付三步完成，PR 待用户合入决定**。
- **合入（2026-08-16 用户确认）**：PR #2 已合入 develop（merge commit `491e504`，`gh pr merge 2 --merge --delete-branch=false`，develop_opencode 分支保留）。检查点已提交并推送 origin/develop（`b35a2d8` docs(opencode): 提交 task-pulsepet-m2 检查点）。**M2 任务完成，status=approved 终态。**

## 最新验证意见原文

（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
