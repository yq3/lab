---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-m2
target: pulse-pet
coderTaskId: ses_fcc4bf586ffebac3wQqHtV6EO4
testerTaskId: ses_fcbb92b69ffeaF9HnaTy6L2a6g
committerTaskId: ses_fcbb59433ffeBiJbtGTx326NAI
status: approved
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: cb50526a296eabbd50f1bd3cdd07c535d682cb35
reviewedSha: cb50526a296eabbd50f1bd3cdd07c535d682cb35
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: ["pulse-pet/src-tauri/src/theme.rs(新)", "pulse-pet/src-tauri/src/lib.rs", "pulse-pet/src-tauri/src/http_server.rs", "pulse-pet/src-tauri/src/atlas.rs", "pulse-pet/src-tauri/src/plugins.rs", "pulse-pet/src-tauri/src/reminder_scheduler.rs", "pulse-pet/src-tauri/src/i18n.rs", "pulse-pet/src-tauri/src/integrations/mod.rs", "pulse-pet/src/styles/tokens.css(新)", "pulse-pet/src/styles/global.css", "pulse-pet/src/lib/bubble-queue.ts(新)", "pulse-pet/src/lib/bubble-queue.test.ts(新)", "pulse-pet/src/lib/theme.ts(新)", "pulse-pet/src/lib/theme.test.ts(新)", "pulse-pet/src/panel/panelStore.ts(新)", "pulse-pet/src/panel/registry.ts(新)", "pulse-pet/src/panel/registry.test.ts(新)", "pulse-pet/src/panel/MiniCat.tsx(新)", "pulse-pet/src/lib/plugin-store.ts(新)", "pulse-pet/src/panel/Panel.tsx", "pulse-pet/src/pet/petStore.ts", "pulse-pet/src/pet/petStore.test.ts", "pulse-pet/src/lib/http-bridge.ts", "pulse-pet/src/lib/reminder-bridge.ts", "pulse-pet/src/lib/todo-bridge.ts", "pulse-pet/src/pet/Bubble.tsx", "pulse-pet/src/panel/Settings.tsx", "pulse-pet/src/panel/Reminders.tsx", "pulse-pet/src/panel/TokenStats.tsx", "pulse-pet/src/lib/i18n.ts", "pulse-pet/src/lib/integrations.test.ts"]（R1 共 32 文件；R1-supplement 追加改动 3 文件：global.css 深色边框系统对齐 b-cool + craft-floor 三项、theme.rs 删未用 THEMES、atlas.rs from_data 标 #[cfg(test)]；R1-supplement-2 改动 5 文件 +110/−433：MiniCat.tsx 删除、Panel.tsx 顶栏两段布局、global.css 三页打磨+控件基线+mini-cat 样式回收、atlas.rs atlas_sheet_png/缓存/base64/4 测试回收、lib.rs 注册移除；R1-supplement-3 仅 global.css +60/−40：.seg 按钮基类+禁用态体系+tab 交互+select 箭头；R1-supplement-4 仅 global.css +10/−3：三处 flex-wrap 溢出修复；R2 改动 9 文件 +69/−22：petStore.ts guard+恢复收敛、Todo.tsx 容器类、bubble-queue.ts preShownMs 保留、三 bridge 注释、i18n.rs 标题+断言、petStore.test.ts/bubble-queue.test.ts/i18n.rs tests 新增测试）
endReason: null
createdAt: 2026-08-24T20:12:47+08:00          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-08-25T09:45:43+08:00          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-pulsepet-v2-m2: PulsePet v2 M2——前端 UI 基础（设计系统 + 面板壳 + 气泡排队 + tab 注册表）

## 任务原文

实施 V2-DESIGN §2（已终审定稿 2026-08-23）：M2 前端 UI 基础——本里程碑只做「壳」。

**权威文档**：
- 设计：`pulse-pet/docs/v2/V2-DESIGN.md` §2.0~§2.13（token 表为唯一实施清单，冲突以表为准；权威样例 = `docs/v2/mockups/a.html`（暖纸浅色）+ `b-cool.html`（冷炭深色），其余样例为过程稿不作实施依据）
- 范围：`pulse-pet/docs/v2/V2-SCOPE.md` §3.2
- 验收用例：`pulse-pet/docs/v2/V2-TEST-CASES.md` 二、TC-UI-01~14

**范围（六块）**：
1. **设计系统**：`src/styles/tokens.css`（新）双主题 token 全量定义（暖纸浅色/冷炭深色，§2.2 表）+ 宠物世界固定色组 `--pet-world-*`（不随主题）；`global.css` 重构为消费 token 的组件层（pet 窗气泡/右键菜单除外——统一走 `--pet-world-*`）。
2. **主题机制**：设置页「外观」三选一分段控件（跟随系统默认/浅色/深色）；`resolveTheme(preference, systemDark)` 纯函数 + 单测；`<html data-theme>` + `[data-theme="dark"]` 覆盖块；Rust `ui_get_theme`/`ui_set_theme`（app_state 键 `ui.theme`，照 ui.language 模式 + `ui://theme` 广播仅 panel 窗消费）。作用域边界：主题只作用 panel 窗口；FOUC 接受记录不修。
3. **面板壳重构**：顶栏（mini 猫 + 标题 + agent 状态芯片）+ tab 栏（激活 tab accent 硬阴影上浮）；Rust 新命令 `atlas_sheet_png()`（async fn + spawn_blocking，AtlasState 缓存、热替换失效）；`src/panel/panelStore.ts`（新）；`MiniCat.tsx`（24×26 canvas，120ms 固定步进，rAF 节流，缺 atlas 优雅降级占位方块）；agent 状态芯片 `● {agent} · {kind}` 等宽字体 + `panel.statusAria`；**前置拉前（P1-1）**：`get_display_state` 扩展返回 `{kind, agent}` + `DisplayNotifier` 去重键改 `(kind, agent)`（M1 §1.5/§1.6 已加修订标注）。
4. **tab 注册表 + feature flag**：`src/panel/registry.ts`（新，TabDef：核心三 token/reminders/settings 静态注册 + 插件 tab 按 name 排序插中间，消费 `plugins_list` 的 enabled + manifest `panel_tab` 键——注意序列化键无 serde rename）；`useTabs()` hook 替代 Panel.tsx 硬编码 TABS；`panel://tab` 直达禁用 tab 回退首个可用；Rust 新命令 `plugins_set_enabled(id, enabled)`（写列 + 触发调度器 reload）；调度器专用 `load_active_rules`（排除 kind='todo' 且源插件 enabled=0，`reminders_list` 的 load_rules 不动）；禁用语义 = 隐藏 tab + 停派生提醒 + 数据保留 + 提醒列表 todo 派生行「已停用（插件关闭）」徽标；设置页「功能管理」区（每启用插件一行开关，核心三不在列）；正查看 tab 被禁用立即切首个可用。
5. **气泡组件重构 + 排队模型**：`src/lib/bubble-queue.ts`（新，纯函数：enqueue/expireCurrent/ackCurrent/setHoverPaused，可注入 now）；单显示位 + 三级优先级队列（critical 8s/info 6s/ambient 4s；顶替回队不结案；同源 10s 合并仅限在显在队；上限 3 = queue 长度不含 current，驱逐序 ambient→info 从队尾，critical/info 永不驱逐允许临时超 3，被顶 ambient 满队即丢；critical 不被 info/ambient 顶；悬停层冻结接口 M3 预留；净化空 auto 结案；记账语义不变）；petStore `bubble: {current, queue}` 改造；桥层适配（http-bridge→info token-report / reminder-bridge→critical reminder:<logId> 烟花叠加编排原样保留 / todo-bridge→info celebration waving 不动）；气泡视觉（暖白+2px 墨边+硬阴影+像素尖角，critical 左侧 4px 蜜橘条）+ 右键菜单视觉翻新（行为零改动）。
6. **四 tab 页轻量翻新 + i18n**：TokenStats/Reminders/Todo 轻量翻新（token 化 + 字号阶收敛 10/11/12/13/17/22，信息架构不动）；Settings 新增「外观」+「功能管理」区（接入管理区统一翻新）；i18n 新键 `settings.theme*`/`plugins.manage*`/`panel.statusAria`（zh/en 键集合一致，完备性测试守护）。

**范围约束**：不含宠物素材/动画、烟花引擎、托盘菜单；提醒 tab 只轻量翻新（表单重做并入 M4）；Token 页结构留 M3；现有纯函数测试不破坏（bubble.ts/plugin-hook pickBubble/token-chart 不动；petStore 单槽位断言有意改写为排队语义——§2.6.4 明示）；数据库零迁移。

**并入的历史遗留（V2-M1 R2 committer 移交，用户 2026-08-24 16:28 裁定归入 M2）**：
- L1（P2-1）：`integrations_install` 对 claude-code 安装路径也追加 `intg_uninstall_hint`——安装后提示条"已安装…已卸载"措辞矛盾（`src-tauri/src/integrations/mod.rs:1047-1050`，一行级 + i18n 一键）。
- L2（P3-1）：提示条文案在动作时点语言烘焙，语言切换后旧提示保持旧语言（`src/panel/Settings.tsx:228-230`，外观瑕疵级）——与 M2 Settings 翻新同文件顺带处理（处理方式：与 L1 一并落（如 key 化重渲染或刷新清除），具体由实施定，不引入新持久化机制）。

**验收标准（Done）**：
- 单测全绿（§2.10）：bubble-queue.test.ts 全覆盖（合并/合并仅限在显在队/上限与驱逐序/被顶 ambient 满队即丢/顶替回队/冻结/记账时机/净化空结案）；resolveTheme；registry 逻辑（禁用过滤/回退/插件插位/panel_tab 键两种构造钉住）；i18n 完备性；既有 bubble.ts/token-chart 不红；petStore.test.ts 排队语义改写；Rust：plugins_set_enabled（过滤/全量/reload/恢复）、ui_get_theme/ui_set_theme（缺省 auto/非法值/广播断言）、atlas_sheet_png（非空/缓存/失效）。
- 实机验收 TC-UI-01~14 全过（主题三档+宠物世界恒定/面板壳+芯片+拉前/mini 猫镜像降级/tab 注册表+feature flag 全链路/气泡排队全链路/视觉对照样例/硬编码色 grep 清零）。
- `npm test`（vitest）与 Rust 侧测试（`cargo test`，注意 CARGO_HTTP_MULTIPLEXING=false 环境）双绿；`npm run build` 通过。

## 需求确认
- [x] 用户已确认（2026-08-24 20:15，确认后 status=implementing）
- 历史遗留事项清单：（supervised-coding 扫描历史检查点汇总，默认并入本任务，见 README §4.6）
  - 并入本任务：V2-M1 检查点 E 组 P2-1（L1）+ P3-1（L2）——用户 2026-08-24 已裁定去向 M2
  - 继续移交（不并入，去向已在 V2-M1 检查点注明）：A 实机验证类（多屏/Windows，去向=具备硬件时）；B v0.1.3 收尾用户目视验收四项（去向=待用户反馈）；C v0.1.3 Release publish 决定（去向=待用户指示）；D 观察项（默认不动）

## 遗留事项（跨任务移交）
- [x] **L1 清偿（来源 task-pulsepet-v2-m1 E P2-1，2026-08-25 本任务清偿）**：integrations_install 对 claude-code 安装路径 hint 改经 action_hint 分派独立键 `intg_install_hint`（不再复用卸载文案，"已安装…已卸载"措辞矛盾消除）——R1 落地，tester PASS（单测断言安装提示含"已安装"不含"已卸载"）。
- [x] **L2 清偿（来源 task-pulsepet-v2-m1 E P3-1，2026-08-25 本任务清偿）**：提示条文案改 status 对象存储、渲染时以当前语言现拼 + 语言切换清空（不引入新持久化机制）——R1 落地，tester PASS（integrations.test.ts 同一 status zh/en 前缀产出不同文案钉子）。
- [x] **冻结期 dwell 语义 spec 补笔（来源本任务 R2 committer 建议，2026-08-25 supervised-coding 已落笔）**：V2-DESIGN §2.6.1 规则④边界声明（冻结期新上屏条目恢复后 dwell 满额计，溢记容差偏长不偏短）。
- [ ] **新移交——实机目验 7 项（去向=用户反馈，持 R2 产物 09:14）**：TC-UI-01 主题三档切换目验 / TC-UI-03 面板壳两段布局+芯片实时更新 / TC-UI-06 双 agent 同 kind 切换芯片跟随 / TC-UI-07 功能管理禁用 Todo 全链路 / TC-UI-10 气泡排队实机 / TC-UI-11 气泡与右键菜单视觉 / TC-UI-12 四 tab 对照样例 a/b-cool 目验+深色可读性（Todo 表单 R2 修复后目验面完整）。
- [ ] **新移交——committer R1 P3 记录项 5~10（去向注明自然清理时机）**：P3-5 atlas.rs AtlasData Clone derive 死代码（**M3 动 atlas.rs 时顺手清**）；P3-6 Settings notice 重复计算 + P3-7 禁用语汇四套不一致（**后续 CSS/微打磨轮**）；P3-8 插件开关失败静默 + P3-9 panel://tab 冷启动 ~100ms 竞态（**UX 观察项，记录不修**）；P3-10 Rust 命令错误串未 i18n（与代码库既有模式一致，**M8 类 i18n 约定扩展时一并考虑**）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1: coder 完成（2026-08-24 20:58，commit `a4cd426` @ develop_opencode，commit 前已 fetch origin/develop 确认无新提交；开工时已合并 origin/develop）。改动：六块全量——设计系统 tokens.css 双主题 + pet-world 固定色组、global.css 全量重构 token 化；主题机制（theme.rs 新 + resolveTheme + data-theme + ui://theme 广播）；面板壳（atlas_sheet_png async+spawn_blocking 代次缓存 / panelStore / MiniCat 120ms / agent 芯片 / P1-1 拉前：get_display_state {kind,agent} + DisplayNotifier (kind,agent) 去重）；tab 注册表（registry.ts + buildTabs/resolveTabId + panel_tab 键 + plugins_set_enabled + load_active_rules 过滤 + 功能管理区 + 已停用徽标）；气泡排队（bubble-queue.ts 纯函数 + petStore {current,queue} + 三桥层适配 + 气泡/右键菜单 pet-world 视觉）；四 tab 轻量翻新 + i18n 新键；L1（intg_install_hint 安装措辞）+ L2（提示条 status 对象渲染时现拼 + 语言切换清空）遗留修复。自测：vitest 26 files / 312 tests passed；cargo test 225 passed / 0 failed / 1 ignored（CARGO_HTTP_MULTIPLEXING=false）；npm run build ✓ 376ms tsc 零错误；TDD red 证据（Rust 批 A 8 FAILED→215 green、批 B 25 errors→225 green；前端 3 文件模块缺失→38 green）；R8 硬编码色 grep 自查 panel 面清零（残留 4 处全在例外域：pet-world 族/PetCanvas FUR_COLOR/Fireworks rgba/tokens.css 定义处）。coder 报告 4 项张力待 committer 关注：①§2.6.1 规则③驱逐措辞张力（实现按硬约束：只驱逐 ambient，无 ambient 可驱即允许超限）②token 表缺气泡 critical 条色 token（以字面 #d96c2c 落 CSS 入 R8 例外清单）③顶栏底线色两样例分歧（按正文规则统一 var(--ink)）④TC-UI-01/03/05 实机项留实机验收。
- R1 补充轮（触发：用户 2026-08-24 21:04 打断 Tester 预告，两问转发 coder）：①写完代码要重新 build 一下应用（完整应用构建，非仅 npm run build 前端产物）②前端 UI 开发过程为什么没有用到 frontend-design / impeccable 两个 skill（V2-DESIGN §2.0 明确"实施阶段可直接使用"）。status 回 implementing，round 不变。
- R1-supplement: coder 完成（2026-08-24 21:31，commit `fc71e86` @ develop_opencode，基于 a4cd426）。问题一：`npm run tauri build` 两次成功（release 15.55s/15.95s 零 warning，产物 PulsePet.app + PulsePet_0.1.3_aarch64.dmg；顺手清偿 2 个 release dead_code 警告：theme.rs THEMES 删除、atlas.rs from_data 标 cfg(test)）。问题二：如实回答=半疏忽半判断（设计已被样例终审 pin 死故认为 skill 无决策面，但漏了 critique/craft-floor 审查面）；本轮实际补做 skill 审查（impeccable critique 按 degraded 单上下文声明执行 A→B→合成，detector detect.mjs 运行 exit 0 findings 0 但欠计数声明）——**发现并修复 R1 真实偏差**：深色主题组件层边框误将浅色 ink 重边通用化（对照 b-cool.html 修复：卡框 --line 低调灰线/chip/seg 容器 --ink-faint/激活 tab accent 边框/KPI 首卡 accent 边框）；补 craft-floor 三项（:focus-visible accent 环 / ::selection / prefers-reduced-motion spinner 静态化）；硬阴影 zero-blur ban 判不适用（neobrutalist chosen world 豁免）、暖纸+terracotta 近俗套判豁免（brief wins）；Vision 截图验证（图片先复制入工作区 .tmp-m2-vision/ 后委托，用毕清理）浅/深双主题 7/7 项过。自测：vitest 312 / cargo test 225 / tsc 零错误 / tauri build 双产物。改动 3 文件 +56/−4。
- R1 补充轮 2（触发：用户 2026-08-24 21:41 目验反馈——"控制面板只有 token 页看得出来优化，提醒、todo、设置这些 tab 页的内容，还是很粗糙啊，组件的大小、位置都很粗糙，让 coder 继续完善"）。status 回 implementing，round 不变。要求：playwright 实际目验四 tab（重点提醒/Todo/设置），对照样例逐页打磨组件尺寸/位置/间距/对齐。
- R1 补充轮 2 追加（用户 2026-08-24 21:43）："控制面板左上角有个很小的活动的宠物，把它去掉"——移除顶栏 mini 猫（V2-DESIGN §2.4 签名元素，需求边界变化）。影响面已查明：atlas_sheet_png/MiniCat 引用全在 §2 内，M3~M6 无其他消费方；牵连 TC-UI-03（三段布局→两段）/TC-UI-04（atlas_sheet_png 命令）/TC-UI-05（mini 猫实机）用例与 §2.4 设计正文——验收口径变化待用户确认删除范围后由 supervised-coding 落笔修订（coder 禁改文档）。
- 用户裁定方案 A（2026-08-24 21:45）：删 MiniCat.tsx + 连带删 atlas_sheet_png 命令及单测；agent 芯片与 P1-1 拉前保留。supervised-coding 已落笔文档（2026-08-24 21:47）：V2-DESIGN §2.1/§2.4（修订标注：mini 猫移除声明）/§2.7 atlas.rs 行/§2.8 MiniCat 行/§2.10 单测与实机 item2/§2.11 R1/R5；V2-TEST-CASES TC-UI-03（两段布局）/TC-UI-04、TC-UI-05（作废留档）。历史评审记录（§2.13、M3 §3.14 引用）不改。
- R1-supplement-2: coder 完成（2026-08-24 22:03，commit `5eb766f` @ develop_opencode）。任务二 mini 猫移除（方案 A）：MiniCat.tsx 删除 + Panel.tsx 两段布局；atlas.rs 回收 atlas_sheet_png/sheet_png_dataurl/base64 编码器/AtlasState generation+png_cache 全套（缓存仅服务此命令）+ lib.rs 注册移除 + 4 单测删除（cargo 225→221 预期）；panelStore/agent 芯片/P1-1 拉前全保留。任务一三页打磨：playwright + 临时 harness 页（复刻三页真实类名 DOM + 假数据）Vision 双轮审查（截图先复制入工作区 .tmp-m2-vision/ 用毕清理）——打磨前定位 12 项（列表行对齐混乱/操作组拥挤/输入框 28~32px 不一/label 间距参差/checkbox 小且基线错位/主按钮弱小等），打磨后逐组确认改善 + 深色 WCAG 对比通过；核心改动：控件规格基线（输入类统一 32px 高/行内小按钮 28px/分段控件 min-height 32px）、**修复主按钮规格 bug**（.reminder-form-actions 的 .seg.primary 从不匹配基础选择器→UA 默认渲染，Vision 报"新建按钮弱小"根源）、checkbox 全局 16×16 + accent-color 主题化、列表行距 10px 8px + reminder-kind 定宽 76px、操作组 margin-left auto 贴右 gap 8px 三页统一、徽章/标签/设置页节奏/表单间距统一；顺手修 1 项残留（分段控件 min-height），其余 2-4px 级建议判过度打磨不追。自测：vitest 312 / cargo 221 / tsc 零错误 / tauri build 14.99s 零警告双产物。改动 5 文件 +110/−433。
- R1 补充轮 3（触发：用户 2026-08-24 22:06 对三页打磨结果仍不满意："还是不太满意，让 coder 用 impeccable skill 重新打磨一下"）。status 回 implementing，round 不变。要求：加载 impeccable skill（/Users/youqi/develop/lab/.opencode/skills/impeccable/SKILL.md 及其引用文件）按其完整方法论对四 tab 重新打磨（不止三页，Token 页也在审视范围）。
- R1-supplement-3: coder 完成（2026-08-24 22:26，commit `c116571` @ develop_opencode，仅 global.css +60/−40）。skill 方法论：补读 reference/polish.md（§1 Establish system 确诊核心为 one-off implementation 型缺陷 / §3 Triage 按状态缺失→系统漂移→视觉不一致排序）；Assessment A/B 仍降级单上下文（权限规则拒通用 subagent，如实声明），A=源码级设计走查 7 项确诊为主力。改动五维度：①**系统性修复**：新增 .seg 行内按钮基类（28px 全规格 + hover/danger/禁用），删三处冗余局部规则——根因 = Token 页「刷新」/表单「取消」按钮裸用 .seg 无规则匹配一直 UA 默认渲染（上轮 .primary 同族缺陷系统收口）；②状态设计补全（.seg:disabled / 表单锁定灰化 surface-2 底+ink-faint）；③交互微反馈（tab hover/激活按压 :active −1px 位移语汇）；④select 移除 appearance:none 恢复下拉箭头（affordance）；⑤卡标题间距 10→12px 对齐样例。前后对比：git checkout 回旧 CSS 拍 before 组 + HMR after 组（含一次 harness 路径事故以 title 校验+MD5+computed border 三重验证重截）；Vision 核对 5/5 修复点生效（其残留清单具体色值经查不存在判定幻觉过报未采信；深色禁用文字 ~3:1 属 WCAG 1.4.3 豁免记录不改）。craft-floor 清单逐项自检通过（Copy 判不适用纯 CSS）。自测：vitest 312 / tsc 零错误。
- R1 补充轮 4（触发：用户 2026-08-24 22:30 截图目验反馈——"按钮都冒出边界了，让 coder 修复一下"；截图仅粘贴于会话，supervised-coding 模型不支持图片输入无法直视，磁盘未寻获文件，由 coder 自行复现定位）。status 回 implementing，round 不变。疑似与 supplement-2/3 的控件规格改动相关（32px 控件/28px 按钮在某些容器/窄列下溢出）。【后续补正：截图实际落盘于 pulse-pet/images/截屏2026-08-24 22.30.15.png，已交 coder 用 vision 直读】
- R1-supplement-4: coder 完成（2026-08-24 22:48，commit `dc58d35` @ develop_opencode，仅 global.css +10/−3）。vision 直读用户截图定位：提醒页列表行操作组（试一试/编辑/删除）水平溢出卡片右缘 5-10px、删除按钮被截断；程序化扫描量化根因：行内固定不可收缩元素总宽 628px + gaps 70 + label 弹性下限 120 ≈ 818px vs 卡片内容区 824px（flex item 默认 min-width:auto 不可收缩），内容稍长即溢出。系统性修复：reminder-item/todo-item/intg-row-head 三处 flex-wrap: wrap——空间不足时操作组整组折行第二行右贴（margin-left:auto 折行后仍生效），信息零丢失、规格零缩小（不推翻基线）；todo 行 gap 统一 10px 12px。验证：扫描断言修复前 5 处溢出→修复后 0（余 1 条为脚本误报已核实）；极端内容折行压测通过 + Vision 判定形态可接受；双主题复核截图（提醒浅/深+Todo 浅）全部按钮在边框内；vitest 312 / tsc 零错误。
- R1 补充轮 5（触发：用户 2026-08-24 22:50 目验"没有变化啊，是不是 coder 改完代码又没有重新 build？"——**核实属实**：release 产物时间戳 22:01（supplement-2 时构建），supplement-3（22:26）/supplement-4（22:48）的 global.css 改动均未重新 tauri build，用户运行旧产物自然无变化；coder 补充轮 3/4 验证证据链缺构建步，打回补构建并固化"每轮交付必须 tauri build"纪律）。status 回 implementing，round 不变。
- R1-supplement-5: coder 完成（2026-08-24 22:52，无代码改动无新 commit，HEAD 保持 dc58d35）。补 tauri build 成功：release 15.38s 零 warning，新产物 PulsePet.app（二进制 22:51:45）+ PulsePet_0.1.3_aarch64.dmg（22:52:06）；产物自验以 vite 内容哈希同一性探针（嵌入资产键 index-su_-fGYt.css 与 dist 逐字一致，含 flex-wrap:wrap 与 .seg padding:5px 12px 两签名；旧构建为不同哈希）+ dmg 挂载复验确认 supplement-3/4 改动已入包。纪律固化声明：后续每轮验证证据必含 tauri build 成功 + 产物时间戳。已提醒用户用新产物替换运行。
- R1: tester 完成（2026-08-24 22:59，testedSha=dc58d35）。**testVerdict: PASS**——PASS 12（TC-UI-02/04 作废/05 作废/08/09/12-grep 面/13/14 + L1/L2 + 全量测试执行 + 构建产物）/ PENDING-USER 7（TC-UI-01/03/06/07/10/11/12 目验面，用户已持新产物可自行目验）/ FAIL 0。要点：vitest 312 与 cargo 221+1 ignored 逐字核对与 coder 声明一致；tauri 产物时间戳晚于 HEAD 确认入包；TC-UI-09 六条规则 283 行逐条核对（含被顶 ambient 满队即丢/续走剩余 dwell）；TC-UI-14 panel_tab 双键钉子确认；R8 色值 36 hex+5 rgba 逐条核对 panel 面零残留（#d96c2c 判合理入例外——引 var(--accent) 会深色变项圈青违反蜜橘恒定）；测试文件 git diff 零篡改（petStore 改写属设计明示）；coder 4 项张力核实均自洽。
- R1: committer 完成（2026-08-24 23:16，reviewedSha=dc58d35）。**reviewVerdict: NEEDS_CHANGES**——无 P1；P2×2：P2-1 悬停冻结期间新气泡上屏重挂计时器→0ms setTimeout 死循环 CPU 空转（petStore.ts armForCurrent 不检查 hoverPaused；M2 无消费方不可达但 M3 悬停层直接消费，已装弹缺陷；修法：armForCurrent 加 hoverPaused guard + 回归测试）；P2-2 Todo 表单容器 .todo-form 无任何 CSS 规则→输入控件全 UA 默认渲染（32px 基线全挂 .reminder-form 下；R1-supplement-2 补的 input[type=date] 挂错容器名；深色+系统浅色时白底；修法：容器类改名 reminder-form 一行）。P3×10 记录级（过期注释 3 处/窗口标题差 · /队列合并丢 preShownMs/冻结期 dwell 溢记/atlas Clone derive 死代码/notice 重复计算/禁用语汇四套不一致/插件开关失败静默/panel://tab 冷启动竞态/Rust 命令错误串未 i18n）。需求边界问题×2（spec 措辞，不转 coder，建议 supervised-coding 落笔）：①§2.6.1 规则③/TC-UI-09-3"ambient→info 顺序驱逐"与"info 永不驱逐"自相矛盾→建议修订为"仅 ambient（自队尾优先）"②§2.5"每启用插件一行"字面歧义（禁用后行消失无法重启用，与 TC-UI-07-4 矛盾）→建议改"每个插件一行"。总体评价：语义正确性/代码质量/测试质量/项目约定/范围符合性均过关，P2 均小修。status=spec_confirm 待用户确认 spec 措辞修订。
- 用户确认 spec 修订（2026-08-25 09:09，"同意"）→ supervised-coding 已落笔：V2-DESIGN §2.6.1 规则③（仅驱逐 ambient 自队尾优先，含修订标注）+ §2.5 功能管理区（每个插件一行含已停用）；V2-TEST-CASES TC-UI-09-3 同步 + TC-UI-07-1 补"含已停用"。round 1→2，reviewedSha 置空，status=implementing，调 coder 修复 P2-1/P2-2 + 顺手清 P3-1/2/3。
- R2: coder 完成（2026-08-25 09:15，commit `cb50526` @ develop_opencode，9 文件 +69/−22）。逐条修复：P2-1 armForCurrent 加 hoverPaused guard（0ms 死循环根除；恢复分支收敛复用 armForCurrent 消除双份 remain 计算；回归测试以 vi.getTimerCount() 断言修复前红/修复后绿，advanceTimersByTime 前断言避免真死循环）；P2-2 Todo.tsx:327 容器类 todo-form→reminder-form（一行，6 输入+priority select 继承 32px 基线，产物 JS todo-form 零残留）；P3-1 三处 bridge 注释改排队语义（reminder-bridge 引 pushBubble/todo-bridge 删矛盾描述/http-bridge 删过时引用）；P3-2 i18n.rs panel_title zh/en 加「·」与页内一致 + Rust 两条逐字断言；P3-3 队列合并保留旧条目 preShownMs（重现续走剩余 dwell）+ 新测试全链。P3-4 边界语义说明（未另修）：guard 修法下冻结期新上屏条目恢复时 dwell 从恢复时刻满额起算（冻结段不计入），溢记反转为满额起算、对 M3 悬停层安全（宁可多显示不丢信息）。自测：vitest 314（+2 回归，先红后绿）/ cargo 221（含新断言）/ tsc 零错 / tauri build 28.51s 零 warning 产物 .app=09:14:38 / .dmg=09:14:58（JS 资产哈希 index-D5mssJnx.js 入包确认，CSS 未动哈希不变符合预期）。
- R2: tester 完成（2026-08-25 09:20，testedSha=cb50526）。**testVerdict: PASS**——6/6 意见全部 FIXED（P2-1 guard 位置正确+死循环推演成立+回归测试无 guard 必红/P2-2 类名改+global.css 选择器覆盖 Todo 全控件+产物佐证/P3-1 三处注释无过时残留/P3-2 两侧标题逐字一致+断言在/P3-3 preShownMs 保留+测试反推必红/P3-4 恢复满额起算语义与代码行为一致推演验证）；0 回归（vitest 314/cargo 221+1/tsc 0/git diff 9 文件 docs 未动无越界/R1 关键面仍绿）；构建产物时间戳+哈希双确认入包。
- R2: committer 复审完成（2026-08-25 09:25，reviewedSha=cb50526）。**reviewVerdict: APPROVED**——增量逐项：P2-1 guard 通用拦截（三调用点全覆盖）+ 恢复分支收敛与 R1 语义逐条等价无漂移 + 回归测试真钉子；P2-2 无连带依赖（无孤儿规则/无测试依赖类名）；P3-3 保留语义合理（显示中合并不保留符合 spec dwell 重计时）；P3-1/2 与实现一致。P3-4 语义定案：实际行为 = 满额+溢记（非纯满额），溢记上限=冻结时长、方向偏长不偏短，对 M3 安全可接受——建议 supervised-coding 在 §2.6.1 规则④或 §3.4 补一句边界声明。spec 修订两处闭环核对通过。遗留建议：①spec 补笔冻结语义 ②P3 5~10 记录在案注清理时机 ③实机 PENDING-USER 7 项待用户目验。双通过（testVerdict=PASS 且 reviewVerdict=APPROVED，reviewedSha=testedSha=HEAD=cb50526）→ status=approved。
- 交付流程执行（2026-08-25 09:37，用户批准）：①coder 提交 spec 修订 docs commit `2f3b86a`（V2-DESIGN+V2-TEST-CASES，+19/−13）+ push develop_opencode（7d77133..2f3b86a）+ 开 PR **#14**（base=develop）；②committer gh pr review——approve 被 GitHub 硬规则拒（作者 yq3 不可自批自己的 PR），降级 review comment 留痕终审 APPROVED（state=COMMENTED 已验证落库，内容含处置摘要/测试证据/范围核对/遗留说明）；③coder 把 Evidence Manifest JSON 追加进 PR #14 description（原 body 保留+追加验证）。spec 冻结语义补笔已落（§2.6.1 规则④）。**待用户：PR 页面点 approve（或跳过）+ 决定合入；实机目验 7 项（持 09:14 产物）**。检查点文件沿 M1 惯例待 PR 合入后单独提交。
- **合入完成（2026-08-25 09:45，用户指示"合入"）**：PR #14 merged（mergeCommit `84d66ba3fc4503dcf0050fb4b66b5f068c252412`，mergedAt 2026-08-25T01:45:35Z）。任务闭环：status=approved 保持，实机目验 7 项与 P3 记录项在遗留事项小节注明去向（下一任务扫描时接续）。检查点文件随收尾提交至 develop。

## 最新验证意见原文

### R1 tester 报告（2026-08-24 22:59，逐字原文）

# PulsePet v2 M2（task-pulsepet-v2-m2）R1 验收测试报告

**测试对象**：`develop_opencode` 分支 @ `dc58d35ac6f7c28fbbe2b1da5812cd7951647a7d`（R1 五 commit 合并结果）
**测试面**：单测全量（vitest 312 / cargo 221+1）+ 静态代码级核查（R8 色值、mini 猫移除、桥层、注册表、i18n）+ 构建验证

## 一、全量测试执行

| 命令 | 结果 | 与 coder 声明 |
|---|---|---|
| `npm test`（vitest run） | **26 files / 312 passed / 0 failed** | 一致 ✓ |
| `cargo test`（CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false） | **221 passed / 0 failed / 1 ignored** | 一致 ✓ |
| `npm run build`（tsc + vite build） | ✓ 372ms 零错误；CSS 哈希 `index-su_-fGYt.css` 与 coder 构建探针逐字一致 | 一致 ✓ |
| tauri build 产物抽查 | PulsePet.app 二进制 **22:51:45**、dmg **22:52:06**（晚于 HEAD commit 22:48，supplement-3/4 改动已入包） | 一致 ✓ |

1 ignored = `token_stats::tests::real_db_reconciliation_manual`（v1 既有 manual 标记，需真实 opencode.db，非 M2 引入）✓

## 二、逐 TC 勾验

### TC-UI-01 主题三档切换（实机）→ **PENDING-USER**
可代码化部分已核：`theme.ts` initThemeBridge（`ui_get_theme` 拉取 → `data-theme` 挂载 → 订阅 `ui://theme` + `prefers-color-scheme` 即时联动）、持久化 `ui.theme` 键、pet-bubble/pet-menu 全走 `--pet-world-*` 不随主题（global.css:132-203）、pet 窗 body transparent（global.css:123）。三档切换目验、重启保留实机、气泡/菜单不随主题目验 → 待用户目验。

### TC-UI-02 主题解析与持久化（单测）→ **PASS**
- `theme.test.ts`：resolveTheme 四组合（auto+系统深→dark / auto+浅→light / light、dark 手动覆盖系统）✓；parseThemePreference 非法/空→null 回退 ✓
- `theme.rs` 单测（`src-tauri/src/theme.rs:84-156`）：parse 三值+trim+大小写敏感、read_theme 缺省 None（=auto）、**非法持久化值回退 None**（:102）、write 非法拒绝不落库（:116）、命令级 mock runtime **`ui://theme` 广播断言**（:125 `commands_roundtrip_and_broadcast_via_mock_runtime`，payload `{theme:"dark"}` 经 listen 收到）✓

### TC-UI-03 面板壳与 agent 状态芯片（实机）→ **PENDING-USER**（结构面 PASS）
- Panel.tsx:13-14 两段布局注释 + 代码：标题「PulsePet · 控制面板」+ `.panel-status-chip`（含 chip-dot 圆点，等效 `● {agent} · {kind}`）；等宽字体 `var(--font-mono)`（global.css:255）
- agent/kind **字面量不翻译**（statusText 直接拼值不经过 `t()`，Panel.tsx:77）
- aria-label 走 `panel.statusAria`（Panel.tsx:85）✓；agent 空（sessions 全空）→ 仅显示 kind 优雅降级（Panel.tsx:76-77）
- Rust：`get_display_state` 返回 `{kind, agent}`（lib.rs:70）+ 单测（lib.rs:379 空 sessions→idle+空 agent / 注入后→working+claude-code）✓
- tab 栏：2px 底线 `var(--line)`（global.css:270）+ 激活 tab `2px 2px 0 var(--accent)` 硬阴影上浮（global.css:291）✓

### TC-UI-04 atlas_sheet_png 命令（作废）→ **N-A**
作废留档，不执行。命令/缓存/base64/注册/4 单测已回收（git diff + grep 确认 `atlas_sheet_png` 零残留，仅 atlas.rs:632/1277 留档注释）。

### TC-UI-05 mini 猫状态镜像（作废）→ **N-A**
作废留档，不执行。MiniCat.tsx 已删除（glob 零命中）、global.css:241 留档注释可接受。

### TC-UI-06 (kind, agent) 去重拉前（实机 + 单测）→ **PENDING-USER**（单测面 PASS）
http_server.rs:78 `if *last != Some((display.kind, display.agent.clone()))` 去重键为 (kind, agent)；单测 `notifier_dedups_on_kind_and_agent_pair`（http_server.rs:924）覆盖同 (kind,agent) 重复只发一次 + **同 kind 换 agent 仍发事件**（session 回收后归属新 agent）✓。双 agent 实机交替 → 待用户目验。

### TC-UI-07 tab 注册表与 feature flag（实机）→ **PENDING-USER**（消费链代码面 PASS）
- 核心三 tab 静态注册不可关（registry.ts + buildTabs）；插件按 name 排序插位（registry.ts:55 localeCompare）
- 禁用过滤：`enabled=false` 或无 panel_tab 声明 → 不生成（registry.ts:53）
- 当前 tab 被禁用 → `resolveTabId` 回退首个可用（registry.ts:71 + 测试）
- Settings 功能管理区：标题/hint/开关/启用停用文案（Settings.tsx:403-423）✓
- Reminders.tsx:276-278 todo 派生行「已停用（插件关闭）」徽标 `plugins.disabledBadge` ✓
- 禁用全链路实机（tab 消失/自动切走/派生停发/徽标/数据无损）→ 待用户目验

### TC-UI-08 禁用语义数据面（单测）→ **PASS**
reminder_scheduler.rs 单测（:1247-1284）：
- 禁用 → `load_active_rules` 过滤 kind='todo' 且源插件 enabled=0（2→1 行，普通行保留）✓
- `reminders_list` 照旧 `load_rules` **全量**（断言 2 行，可见但惰性）✓
- 重启用 → 恢复参与调度（2 行）✓；插件行缺失保守视为启用（:1272）✓
- `plugins_set_enabled` 触发调度器 reload：plugins.rs:343 mock runtime 测试（禁→reload→启用→reload 恢复）✓

### TC-UI-09 气泡排队模型（单测）→ **PASS**
`bubble-queue.test.ts`（283 行）六条规则逐条核对：
1. **顶替回队** ✓（:30 critical 顶 info 回队首不结案；:39 同级 FIFO；:48 critical 不被 info/ambient 顶；:57 info 顶 ambient）
2. **同源合并 10s** ✓（:67 显示中替换+dwell 重计时；:83 队列中原地替换；:92 窗口外独立入队——覆盖"已离场过期不复活"相邻语义；:99 同源不同级不合并）
3. **上限与驱逐** ✓（:110 上限 3 指 queue 不含 current；:119 驱逐序 ambient→info 从队尾；:133 critical/info 永不驱逐允许临时超 3；:145 被顶 ambient 满队即丢）
4. **分级 dwell** ✓（:158 8s/6s/4s 常量 + dwellFor；:165 expireCurrent 到期推进队首）
5. **悬停冻结** ✓（:185 冻结 dwell 不推进；:196 恢复续走剩余；:208 队列不推进）
6. **记账/净化** ✓（:220 只有最终离场才 dismissed、同级 critical FIFO 轮换；:236 被顶回队不结案；:250 重现续走剩余 dwell；:263 ackCurrent；:279 QUEUE_MAX=3 / MERGE_WINDOW_MS=10s 常量钉子）；净化空 auto 结案在 petStore.test.ts:192（pushBubble 空白文案 → 立即 reporter(9,"auto")）✓

### TC-UI-10 气泡排队实机 → **PENDING-USER**
代码面核：reminder-bridge critical 路径 + `planReminderActions` 烟花叠加编排**原样保留**（reminder-bridge.ts:4-10、56-57「特效只叠加、不替代气泡」）；todo-bridge info celebration + waving 不动（todo-bridge.ts:35-41）；http-bridge info token-report（http-bridge.ts:78）。实机全链路 → 待用户目验。

### TC-UI-11 气泡与右键菜单视觉（实机）→ **PENDING-USER**
视觉规范已核代码：暖白 `--pet-world-surface` + 2px 墨边 `--pet-world-line` + `--pet-world-shadow` 硬阴影 + 45° 旋转像素尖角（global.css:133-165）+ critical 4px 蜜橘条（:169-172）+ 菜单直角项（:187-203）。目验（含深浅主题下恒定）→ 待用户。

### TC-UI-12 设计系统落地与硬编码色清零 → **PASS**（grep 面）/ **PENDING-USER**（目验面）
- 字号阶：global.css 唯一集合 **10/11/12/13/17/22**，无 14/15/16/20 ✓
- R8 色值 grep 全量（36 hex + 5 rgba）逐条核对：
  - tokens.css 定义处（28 hex + 3 rgba 含 shadow/pet-world-shadow）→ 合法 ✓
  - `PetCanvas.tsx:16 FUR_COLOR #f4f4f7` → 宠物绒毛素材色，例外 ✓
  - `global.css:143/195 #29241d` → pet-world 墨字（气泡/菜单文字），例外域 ✓
  - `global.css:171 #d96c2c` → **气泡 critical 条色（coder 张力②）：判定合理入例外清单**——气泡属 pet-world 恒定物件，token 表无此独立 token，若引 `var(--accent)` 会在深色主题下变成项圈青 #62c6c0（违反「蜜橘恒定」§2.6.3）；以字面落 CSS 并注释"值 = 浅色主题 --accent 同源"自洽 ✓
  - `global.css:202 rgba(23,19,15,.08)` → pet-world 墨系 hover，例外域 ✓
  - `Fireworks.tsx:13/129` → 注释 + 烟花尾迹 rgba（无文案无主题），例外域 ✓
  - **panel UI 面硬编码色零残留** ✓（与 coder R8 自查一致：4 处残留全在例外域）
- 四 tab 目验 + 深色可读性目验 → 待用户

### TC-UI-13 测试迁移与既有套件不红（单测）→ **PASS**
- git diff `dc58d35~5..dc58d35` 确认 `bubble.test.ts` / `plugin-hook.test.ts`（含 pickBubble，:14/:303 仍在）/ `token-chart.test.ts` **零改动** ✓
- `petStore.test.ts` 改写为排队语义（顶替回队/分级 dwell/悬停冻结/净化空 auto 结案/记账时机，234 行变动属 §2.6.4 明示的有意取代）✓
- i18n 完备性：`i18n.test.ts:47` en/zh 键集合一致 + 无空串；新键 `settings.theme*`（5 键）/`plugins.manage*`（3 键）/`panel.statusAria` zh/en 双向存在（i18n.ts:35/226-231/254-256/278/467-472/495-497）✓

### TC-UI-14 tab 注册表纯函数（单测）→ **PASS**
registry.test.ts（128 行）四项全覆盖：
1. 核心三静态注册顺序 token→reminders→settings（:19）+ labelKey/render（:25）✓
2. 插件按 name 排序插位（:44 zeta/alpha）+ render 映射缺失不生成（:61）+ enabled=false 过滤（:70）+ panel_tab 缺失不生成（:77）✓
3. 回退：禁用/未知/null → 首个可用（:110-127）✓
4. **panel_tab 键双构造钉子**（:85-108）：含 `panel_tab` 正确生成 + 只有 camelCase `panelTab` 时缺失（反例钉住正确键名）✓

### 遗留修复验证 → **PASS**
- **L1（P2-1）**：integrations/mod.rs:1095-1098 `action_hint` 按 action 分派（install→`intg_install_hint`）；单测 :1707（安装提示含"已安装"、**不含"已卸载"**）+ i18n.rs:393-394 断言；`intg_install_hint` 独立成键（i18n.rs:253 附近）✓
- **L2（P3-1）**：integrations.test.ts:55 「v2 M2 L2：提示条语言不烘焙——渲染时以当前语言现拼」，同一 status 在 zh/en 前缀下产出不同文案 ✓

## 三、汇总

| 分类 | 数量 |
|---|---|
| PASS（单测/代码级/构建） | **12**（TC-UI-02/04 作废/05 作废/08/09/12-grep面/13/14 + L1/L2 + 全量测试执行 + 构建产物） |
| PENDING-USER（实机目验） | **7**（TC-UI-01 / 03 / 06 / 07 / 10 / 11 / 12 目验面） |
| FAIL | **0** |

**PENDING-USER 目验清单**（用户已拿到 22:52 新构建产物可自行验证）：
1. TC-UI-01：设置→外观三档切换即时生效、跟随系统联动、重启保留、气泡/菜单不随主题变
2. TC-UI-03：面板顶栏两段布局 + 芯片随状态实时更新
3. TC-UI-06：双 agent 会话同 kind 切换时芯片 agent 跟随
4. TC-UI-07：功能管理禁用 Todo 全链路（tab 消失/自动切走/停派生/徽标/重启用恢复）
5. TC-UI-10：提醒显示中收 token 汇报排队、同源合并、点宠物确认记账
6. TC-UI-11：气泡（暖白/墨边/硬阴影/尖角/critical 蜜橘条）+ 右键菜单视觉
7. TC-UI-12：四 tab 对照样例 a/b-cool 目验、深色下可读性

## 四、结论

- 单测总数与 coder 声明逐字一致（312 / 221+1 ignored）；`npm run build` 通过；tauri 产物时间戳 22:51/22:52 晚于 HEAD commit，supplement-3/4 改动确认入包
- coder 报告的 4 项设计-实现张力经核实均实现自洽：①驱逐硬约束（只驱 ambient，无 ambient 允许超 3，bubble-queue.ts 测试 :119/:133 钉住）②critical 条 #d96c2c 判合理入 R8 例外清单 ③顶栏底线统一 var(--ink)（global.css:230）④实机项已列入 PENDING-USER
- 测试文件未被篡改（git diff 核对 bubble/plugin-hook/token-chart 零改动；petStore 改写属设计明示）
- **无 FAIL 项**（含 TEST_BUG / CASE_BUG / IMPL_BUG 均零）

**testVerdict: PASS**

**testedSha**: `dc58d35ac6f7c28fbbe2b1da5812cd7951647a7d`

### R1 committer 报告（2026-08-24 23:16，逐字原文）

# PulsePet v2 M2 R1 审查报告（Committer）

**审查对象**：`develop_opencode` @ `dc58d35ac6f7c28fbbe2b1da5812cd7951647a7d`（diff 基线 = `origin/develop...HEAD`，31 文件）
**上一轮意见处置**：本轮为首轮评审（reviewedSha 曾为 null），无历史意见需核对；coder 自报 4 项张力已在本次交叉核验（①驱逐硬约束 ✓ ③顶栏底线 var(--ink) ✓，②④已由 tester 核实自洽）。

## 一、问题清单

### P2-1：悬停冻结期间新气泡到期 → 0ms 定时器死循环（M3 预留接口的接线缺陷）

**位置**：`src/pet/petStore.ts:137-144`（armForCurrent）、`:127-134`（expireTick）、`:200-202`（pushBubble 重挂条件）

**问题**：`armForCurrent` 不检查 `hoverPaused`。时序推演：`setHoverPaused(true)` → 清计时器；冻结期间到达的新气泡若**上屏**（critical 顶替 / ack 推进 / current 为空），`pushBubble`/`ackReminderBubble` 会重挂 dwell 计时器；计时器到期时 `expireCurrent` 因冻结返回 `dismissed:null`（状态引用不变），`expireTick` 随后 `armForCurrent` 重算 `remain = max(0, dwell − elapsed) = 0` → `setTimeout(expireTick, 0)` → 立即再触发 → **无限 0ms 循环，CPU 空转直至解除冻结**。M2 无消费方不可达（`setHoverPaused` 仅测试调用），但该接口是 M2 交付物、M3 §3.4 悬停层将直接消费（悬停读今日汇总 6s+ 期间来一条提醒即触发），属已装弹的潜伏缺陷。

**建议修法**：`armForCurrent` 开头加 `if (!cur || b.hoverPaused) return;`（恢复路径 `setHoverPaused(false)` 已自行重挂，不依赖它）；补一条回归测试：`setHoverPaused(true)` 后 `pushBubble`（critical）+ `advanceTimersByTime(dwell + 1)` → 断言 reporter 未被调用且无异常（钉住"冻结期间不再挂计时器"）。

### P2-2：Todo 新建/编辑表单输入控件零样式（`.todo-form` 无任何 CSS 规则）

**位置**：`src/panel/plugins/Todo.tsx:327`（容器 `className="todo-form"`）；`src/styles/global.css:1046-1071`（32px 基线仅作用 `.reminder-form input/select`）

**问题**：M2 控件规格基线（32px 高、2px 边框、token 配色、禁用态）全部挂在 `.reminder-form` 选择器下，而 Todo 表单容器是 `.todo-form`（v1 起即如此，且 v1 同样无规则）——Todo 表单的 title/dueDate/dueTime/remindBefore/tags/notes 输入框与 priority select 全部落在 **UA 默认渲染**（无 2px 边框、高度 ~24px、无 token 色）。铁证：R1-supplement-2 给基线补了 `input[type="date"]` 选择器——意图覆盖 Todo 的日期字段，却挂在了错误容器名下。影响：①TC-UI-12-1「四个 tab 页全部落新 token」在 Todo 页不成立；②深色主题下无 `color-scheme` 声明，手动深色 + 系统浅色组合时 UA 控件呈白底（R7「深色下白底刺眼」风险）；③用户两轮反馈聚焦的正是这些 tab 的控件规格，此为漏网且必然被目验发现。属 v1 存量缺口，但 Todo 轻量翻新在 M2 范围明文内，且打磨轮已宣称修复「输入框规格不统一」——此处属该修复未真正覆盖。

**建议修法**：Todo.tsx:327 容器类改名 `reminder-form`（一行；其子行本就用 `reminder-form-row`/`reminder-form-actions`，32px 基线、禁用态、主按钮规格全部自然继承），或为 `.todo-form` 补一组与基线同值规则（不推荐，双份漂移）。

### P3（记录级，不阻断）

1. **过期注释**（3 处，队列语义已取代单槽位语义）：
   - `src/lib/reminder-bridge.ts:6` 仍引用已删除的 `showReminderBubble` API；
   - `src/lib/todo-bridge.ts:13` 声称「气泡顶替旧提醒气泡时按 'auto' 回报旧 log」——排队模型下被顶者回队**不结案**，且 info 级庆祝根本无法顶 critical，描述与现状矛盾；
   - `src/lib/http-bridge.ts:9,11` 「只存不显示 V2-DESIGN §1.6」与 `showBubble` 引用已过时（M2 芯片已真实显示 agent）。
   建议顺手改为排队语义描述，防止 M3/M4 实施被误导。
2. **窗口标题与页内标题不一致**：`src-tauri/src/i18n.rs:101-104` `panel_title()` = "PulsePet 控制面板"/"PulsePet Control Panel"，页内 h1（`src/lib/i18n.ts` `panel.title`）已改为 "PulsePet · 控制面板"——窗口 chrome 与顶栏差一个「·」。建议二选一统一（同步 Rust 侧文案为最省）。
3. **队列合并丢 preShownMs**：`bubble-queue.ts:120-123` 队列中合并原地替换时，旧条目若携带 `preShownMs`（曾被顶回队）被新条目覆盖后丢失——重现时 dwell 从满额重计而非续走剩余。spec 对「队列中替换」的 dwell 语义未定义，建议替换时保留 `preShownMs` 或 spec 明示重计。
4. **冻结期状态变更的 dwell 溢记**：`bubble-queue.ts:202-218` 恢复时 `shownAt` 平移整段冻结时长；若冻结期内发生 ack/顶替/合并（新 current 中途上屏），新条目会多记冻结起点前的时长。M3 边界，与 P2-1 同源，修 P2-1 时可一并评估。
5. **死代码**：`src-tauri/src/atlas.rs:172` `#[derive(Clone)]` 在 png 缓存回收后已无消费方（无害 derive）。
6. **重复计算**：`src/panel/Settings.tsx:468-476` notice 渲染 `composeActionNotice` 计算两次（条件 + 正文各一次），可提局部变量。
7. **禁用态不一致**：`.seg:disabled`（opacity .45）vs `.intg-row-actions button:disabled`（ink-faint）vs `.panel-settings select:disabled`（cursor:wait）vs 表单禁用（cursor:not-allowed）——同页四套禁用语汇，cursor 语义（wait=加载 vs not-allowed=锁定）亦混用。纯 CSS 一致性打磨项。
8. **插件开关失败静默**：`src/panel/Settings.tsx` `onPluginToggle` 仅 console.error；`setPluginEnabled` 的 finally 重拉会使开关回弹，但无用户可见提示。可接受，记录。
9. **panel://tab 启动竞态**：Panel.tsx `useTabs` 回退 effect 在插件快照未加载（null）时会把直达 todo 的意图吞掉切到 token；仅 App 冷启动 ~100ms 窗口内可达。记录不修。
10. **Rust 命令错误串未 i18n**：`plugins.rs:179`「插件不存在：{id}」、`theme.rs:42`「theme 非法：…」会经 `settings.themeFail` 上屏，en 界面下显示中文；与既有代码库命令错误串模式一致（M8 i18n 约定未覆盖命令错误串），记录。

## 二、需求边界问题（spec 文本问题，不转 coder，建议 supervised-coding 落笔修订）

1. **§2.6.1 规则③ / TC-UI-09-3 措辞自相矛盾**：「按 ambient → info 顺序从队尾驱逐」与「critical/info 永不被驱逐（允许临时超 3）」不可同时成立。实现取硬约束解读（仅 ambient 可驱逐，coder 张力①），tester 核实自洽，M2 无 ambient 来源实际无影响。建议 spec 将「ambient → info 顺序」修订为「仅 ambient（自队尾优先）」，消除 M3 落地时的歧义空间。
2. **§2.5「每启用插件一行」措辞歧义**：字面读 = 只列启用中的插件 → 禁用后行消失、无法重启用，与 TC-UI-07-4「重启用后全恢复」矛盾。实现列出全部插件（正确，重启用路径成立）。建议 spec 改为「每(个)插件一行」或「含已停用插件」。

## 三、总体评价

- **语义正确性**：气泡排队内核六条规则实现与测试钉扎质量高（283 行逐规则覆盖、常量钉子、记账时机精确到"被顶不结案/重现续走剩余 dwell"）；P1-1 拉前（`{kind,agent}` + `(kind,agent)` 去重）含换 agent 仍发事件的钉子测试；禁用语义过滤位置（`load_active_rules`）与 `reminders_list` 全量、徽标数据源、重启用恢复均与 P2-2 定案一致；L1（action_hint 分派 + 源码钉子）与 L2（status 对象现拼 + 语言切换清空）修复到位。
- **代码质量**：模块边界清晰（纯函数内核 / store 接线 / 桥层适配三层分离）；CSS 四轮叠加后特异性推演无冲突（`.seg` 基类 (0,1,0) 被容器规则 (0,2,0)/(0,3,0) 正确覆盖，hover/active/disabled 链语义自洽）；tokens.css 与 §2.2 表逐值一致；深色覆盖块只改边框引用、零 token 变更。
- **测试质量**：无形式化走过场测试；`panel_tab` 双键反例钉子、非法主题值拒绝不落库、mock runtime 广播断言、驱逐序边界均测到点上；既有测试零篡改（tester 已核，我抽验一致）。
- **项目约定**：i18n 键集合一致性测试守护 ✓；无新 eprintln!（仅 pre-existing）✓；无新 managed state（issue #9 纪律 ✓）；数据库零迁移 ✓（db.rs 不在 diff）。
- **范围符合性**：无 M3/M4 越界；docs 修订由 supervised-coding 落工作区（未入 commit）✓；mini 猫方案 A 回收干净（`atlas_sheet_png` 零残留，仅留档注释）。
- **交付证据**：tester 已核 vitest 312 / cargo 221+1 与 tauri 产物时间戳（22:51/22:52 晚于 HEAD）双项，交叉可信。

## 四、结论

**reviewVerdict: NEEDS_CHANGES**

依据：无 P1；但两条 P2 均在 M2 交付面内且修起来极小——
- P2-1 是 M2 交付的 M3 接口内已装弹的 CPU 空转缺陷，趁文件在手修掉是最便宜时机；
- P2-2 恰好落在用户两次打回所针对的「三页控件规格」区域（Todo 表单是漏网的第四处），且与打磨轮宣称的修复直接相关，现在修可避免第三次用户目验往返。

建议处置：一个补充轮——修 P2-1（含回归测试）+ P2-2（容器类改名一行），顺手清 P3-1/2/3 注释与标题；其余 P3 记录在案可缓。两条需求边界问题由 supervised-coding 修订 spec 措辞，不转 coder。CASE_BUG 裁定请求：本轮 tester 无（FAIL/TEST_BUG/CASE_BUG/IMPL_BUG 均零），无需裁定。
