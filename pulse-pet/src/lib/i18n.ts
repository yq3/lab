/**
 * i18n：M8 国际化（DESIGN §10 "国际化 en/zh"，v1 只双语）。
 *
 * 方案定案（轻量字典，不引 react-i18next 等依赖——v1 收尾定位 + 包体积）：
 * - `DICT`：`zh` / `en` 两个扁平字典（键点分命名空间），`t(key, params)` 做
 *   `{x}` 插值；缺键回退键名本身（可观测不静默），缺参保留占位符。
 * - 语言状态在 zustand store（pet / panel / fireworks 三窗口各持一份）；
 *   启动时 `initI18n()` 从 Rust 读持久化语言（app_state `ui.language`），
 *   无持久化则跟随系统（`zh*` → zh，其余含 zh/en 之外的回退 en）。
 * - 切换走 `changeLanguage()`：本地 store 立即生效 + invoke `ui_set_language`
 *   （Rust 持久化 + 重建托盘菜单文案 + 广播 `ui://language` 同步三窗口）。
 * - vitest / 纯浏览器 dev（非 Tauri）：默认 zh——既有断言中文文案的单测
 *   不受影响；`systemLangSafe` 为纯函数可单测。
 * - 不翻译项：宠物状态名（idle/working 等技术词）、品牌名 PulsePet、
 *   数据值（提醒 label / todo title 等用户数据）。
 */

import { create } from "zustand";

export type Lang = "zh" | "en";

/** Rust 广播语言变化的 Tauri event 名（lib.rs `ui_set_language` 下发）。 */
export const LANGUAGE_EVENT = "ui://language";

type Dict = Record<string, string>;

const zh: Dict = {
  // ---- panel 骨架 ----
  "panel.title": "PulsePet · 控制面板",
  "panel.tab.token": "Token",
  "panel.tab.reminders": "提醒",
  "panel.tab.todo": "待办",
  "panel.tab.settings": "设置",
  // v2 M2：顶栏 agent 状态芯片 aria-label（agent/kind 字面量不翻译）
  "panel.statusAria": "当前 agent 状态：{text}",

  // ---- token 统计页 ----
  "token.preset.today": "今日",
  "token.preset.7d": "近 7 天",
  "token.preset.30d": "近 30 天",
  "token.preset.custom": "自定义",
  "token.dim.day": "按天",
  "token.dim.week": "按周",
  "token.dim.range": "整段",
  "token.refresh": "刷新",
  "token.loading": "查询中…",
  "token.aria.range": "时间跨度",
  "token.aria.from": "起始日期",
  "token.aria.to": "结束日期",
  "token.aria.dim": "统计维度",
  "token.aria.agent": "agent 维度",
  "token.chart.title": "Token 时序（{dim}）",
  "token.chart.aria": "token 时序柱状图",
  // v2 M3：堆叠柱图 HTML tooltip（日期 + 三值 + 占比 + 总量）
  "token.chart.tip": "{label}：共 {total}",
  "token.chart.tipRow": "{name}：{n}（{pct}%）",
  // v2 M3：模型筛选
  "token.chart.noModels": "未勾选任何模型，柱图为空。",
  "token.col.model": "模型",
  "token.model.unknown": "未知模型",
  "token.kpi.total": "总量",
  "token.sessions.title": "会话（{n}）",
  "token.sessions.empty": "跨度内无会话记录。",
  "token.sessions.updated": "更新时间",
  "token.project.global": "全局",
  "token.project.unknown": "（未知项目）",
  "token.error.noDatabase": "数据库未运行/未初始化：未检测到 opencode 数据库（opencode.db / opencode-canary.db）。",
  "token.error.legacyStorage": "检测到旧版 opencode 存储格式（storage/session/*.json）：请升级 opencode 后使用。",
  "token.error.schemaMismatch": "opencode.db schema 不兼容（{msg}）",
  "token.error.query": "查询失败：{msg}",
  "token.needApp": "Token 统计需要在 PulsePet App（Tauri）内查看",
  // v2 M5（§5.6，TC-M5-04/10）：agent 筛选 chip + 会话列表徽标全名
  "token.agent.opencode": "opencode",
  "token.agent.claudeCode": "Claude Code",
  // v2 M5 R2（TC-M5-04-1）：agent tab「全部」项（恒显，默认选中）
  "token.agent.all": "全部",
  // v2 M5：费用口径标注（CC 恒 0——第三方 key 下单价表不可信，S4 裁定）
  "token.costOpencodeOnly": "费用仅统计 opencode（Claude Code 无可靠费用数据）",
  // v2 M5（TC-M5-07）：例程会话 ⚡ 徽标 title 提示（零 schema 改动）
  "token.taskBadge": "定时任务例程",
  // v2 M5（C1/N-4）：degraded 细横幅（仅 panel；opencode 源不可用 × CC 有数据）
  "token.degraded": "opencode 源不可用：仅显示 Claude Code 数据",
  "token.hoverAgent": "今日 agent 分布",

  // ---- 提醒页 ----
  "reminders.needApp": "提醒配置需要在 PulsePet App（Tauri）内使用",
  "reminders.loadFail": "读取提醒配置失败：{msg}",
  "reminders.loading": "读取提醒配置…",
  "reminders.fwGlobal": "全局烟花模式（未单独勾选的提醒也升级为烟花）",
  "reminders.pausedBadge": "已暂停所有提醒（托盘可恢复）",
  "reminders.rules.title": "提醒规则（{n}）",
  "reminders.rules.empty": "还没有例程，从下方模板或表单新建一条吧。",
  "reminders.kind.hydration": "喝水",
  "reminders.kind.rest": "休息",
  "reminders.kind.custom": "自定义",
  "reminders.kind.todo": "待办",
  "reminders.kind.todoDerived": "待办（派生）",
  "reminders.field.start": "起始",
  "reminders.field.end": "结束",
  "reminders.interval.once": "单次",
  "reminders.interval.hours": "每 {n} 小时",
  "reminders.interval.minutes": "每 {n} 分钟",
  "reminders.window.allDay": "全天",
  "reminders.window.from": "{start} 起",
  "reminders.window.until": "至 {end}",
  "reminders.window.range": "{start}-{end}{cross}",
  "reminders.window.cross": "（跨午夜）",
  "reminders.due": "截止 {ts}",
  "reminders.dueNone": "—",
  "reminders.last": "上次 {ts}",
  "reminders.lastNever": "从未触发",
  "reminders.enabled": "启用",
  "reminders.enabledOn": "启用中",
  "reminders.enabledOff": "已停用",
  "reminders.fireworks": "烟花",
  "reminders.fireworksOverride": "单条烟花覆盖（TC-RM-11）",
  "reminders.test": "试一试",
  "reminders.edit": "编辑",
  "reminders.delete": "删除",
  "reminders.deleteConfirm": "确认删除？",
  "reminders.deleteHint": "再次点击确认删除",
  "reminders.form.newTitle": "新建例程",
  "reminders.form.editTitle": "编辑例程 #{n}",
  "reminders.form.todoHint":
    "📋 Todo 派生提醒（单次，由 Todo 插件管理类型/间隔/时刻——在 Todo 页改任务的截止或提前提醒即可）。此处仅可调整文案、启用与烟花；改动会随任务下次保存被任务标题覆盖。",
  "reminders.form.type": "类型",
  "reminders.form.label": "文案（气泡显示，纯文本 1-140 字符）",
  "reminders.form.labelPlaceholder": "如：该喝水啦 💧",
  "reminders.form.interval": "间隔（分钟，1-1440）",
  "reminders.form.start": "起始（留空 = 全天）",
  "reminders.form.end": "结束（留空 = 全天）",
  "reminders.form.crossMidnight":
    "跨午夜窗口：仅在 [{start}, 24:00) ∪ [00:00, {end}) 内触发（TC-RM-06）",
  "reminders.form.fireworksMode": "烟花模式",
  "reminders.form.save": "保存修改",
  "reminders.form.create": "新建",
  "reminders.form.cancel": "取消编辑",
  "reminders.stats.title": "历史统计（reminder_logs）",
  "reminders.stats.empty": "暂无提醒记录。",
  "reminders.stats.today": "今日 {n} 次",
  "reminders.stats.total": "累计 {n} 次",
  "reminders.toast.fired": "已触发「{label}」",
  "reminders.toast.dedup": "3 分钟内已触发过，去重拦截（TC-RM-05）",
  "reminders.toast.paused": "所有提醒已暂停（托盘「暂停所有提醒」），恢复后再试",
  "reminders.toast.triggerFail": "触发失败：{msg}",
  "reminders.toast.deleteFail": "删除失败：{msg}",
  "reminders.toast.updateFail": "更新失败：{msg}",
  "reminders.toast.fwGlobalFail": "全局烟花开关保存失败：{msg}",
  "reminders.tpl.hydration": "该喝水啦 💧",
  "reminders.tpl.rest1": "休息一下 ☕",
  "reminders.tpl.rest2": "站起来走走 🚶",
  "reminders.validation.labelEmpty": "文案不能为空",
  "reminders.validation.labelLong": "文案超长（≤140 字符）",
  "reminders.validation.kindBad": "类型非法：{kind}",
  "reminders.validation.todoInterval": "todo 派生提醒间隔恒为 0（单次）",
  "reminders.validation.absFormat": "{what}应为 YYYY-MM-DDTHH:MM（todo 派生）",
  "reminders.validation.intervalBad": "间隔非法（1-{max} 分钟）",
  "reminders.validation.timeFormat": "{what}时间格式应为 HH:MM",
  "reminders.validation.timeRange": "{what}时间越界（00:00-23:59）",

  // ---- v2 M4：定时任务（tasks.*，V2-DESIGN §4.7）----
  "panel.tab.tasks": "例程",
  "panel.agentTask": "例程",
  "tasks.rules.title": "例程（{n}）",
  "tasks.actionType": "动作类型",
  "tasks.action.notify": "提醒",
  "tasks.action.exec": "执行命令",
  "tasks.badge.notify": "提醒（气泡 + 烟花）",
  "tasks.badge.exec": "执行命令（后台进程 + 历史）",
  "tasks.schedule.interval": "间隔",
  "tasks.schedule.daily": "每天",
  "tasks.schedule.once": "一次",
  "tasks.schedule.at": "时刻（HH:MM）",
  "tasks.schedule.datetime": "日期时间",
  "tasks.schedule.weekdays": "星期（不勾 = 每天）",
  "tasks.weekday.1": "一",
  "tasks.weekday.2": "二",
  "tasks.weekday.3": "三",
  "tasks.weekday.4": "四",
  "tasks.weekday.5": "五",
  "tasks.weekday.6": "六",
  "tasks.weekday.7": "日",
  "tasks.summary.daily": "每天 {at}",
  "tasks.summary.dailyDays": "周{days} {at}",
  "tasks.summary.once": "一次 · {at}",
  "tasks.form.name": "任务名",
  "tasks.form.namePlaceholder": "如：数 md 文件",
  "tasks.form.command": "命令（sh -c 执行，≤2000 字符）",
  "tasks.form.cwd": "工作目录（可选）",
  "tasks.form.timeout": "超时（分钟，1-120）",
  "tasks.form.instruction": "指令",
  "tasks.tpl.title": "opencode 例程",
  "tasks.tpl.hint": "一键填充：opencode run --title \"pulsepet 例程: <任务名>\" \"<指令>\"（可再改）",
  "tasks.tpl.auto": "自动放行权限（--auto，危险）",
  "tasks.tpl.autoHint": "勾选后例程的权限请求自动放行——无人值守执行副作用命令，请谨慎",
  "tasks.skip": "跳过本次",
  "tasks.skipDone": "已跳过本周期",
  "tasks.skipFail": "跳过失败：{msg}",
  "tasks.snooze": "稍后 10 分钟",
  "tasks.history.title": "执行历史",
  "tasks.history.empty": "暂无执行记录。",
  "tasks.history.loadFail": "读取执行历史失败：{msg}",
  "tasks.history.page": "第 {page}/{pages} 页 · 共 {total} 条",
  "tasks.history.prev": "上一页",
  "tasks.history.next": "下一页",
  "tasks.history.expand": "展开输出",
  "tasks.history.collapse": "收起",
  "tasks.history.delay": "补跑延迟 {sec} 秒",
  "tasks.history.output": "输出尾部（≤2KB）",
  "tasks.history.filterAll": "全部任务",
  "tasks.status.ok": "ok",
  "tasks.status.failed": "failed",
  "tasks.status.skipped": "skipped",
  "tasks.status.running": "running",
  "task.summary.ok": "任务完成",
  "task.summary.failed": "失败（退出码 {n}）",
  "task.summary.failedNoCode": "失败",
  "task.summary.timeout": "超时（{n} 分钟）被终止",
  "task.summary.missed": "错过补跑窗（15 分钟）",
  "task.summary.paused": "暂停期间跳过",
  "task.summary.interrupted": "App 退出中断",
  "task.summary.stale": "上次运行未完结（启动清理）",
  "tasks.validation.actionBad": "动作类型非法（应为 notify/exec）",
  "tasks.validation.scheduleBad": "调度类型非法（应为 interval/daily/once）",
  "tasks.validation.atRequired": "时刻不能为空",
  "tasks.validation.atFormat": "时刻应为 HH:MM",
  "tasks.validation.dtFormat": "日期时间应为 YYYY-MM-DDTHH:MM",
  "tasks.validation.dtPast": "须为未来时刻（防创建即意外执行）",
  "tasks.validation.weekdaysBad": "星期过滤非法（1-7）",
  "tasks.validation.paramsMissing": "执行命令需要 action_params（JSON 对象）",
  "tasks.validation.commandEmpty": "命令不能为空",
  "tasks.validation.commandLong": "命令超长（≤2000 字符）",
  "tasks.validation.cwdNotDir": "工作目录不存在或不是目录",
  "tasks.validation.timeoutBad": "超时非法（1-120 分钟，缺省 10）",
  "tasks.validation.autoBad": "opencode_auto 应为布尔值",

  // ---- todo 插件页 ----
  "todo.needApp": "Todo 需要在 PulsePet App（Tauri）内使用",
  "todo.loadFail": "读取 Todo 失败：{msg}",
  "todo.loading": "读取 Todo…",
  "todo.plugin.prefix": "插件",
  "todo.plugin.enabled": "已启用",
  "todo.plugin.disabled": "已停用",
  "todo.plugin.permissions": "权限",
  "todo.plugin.loading": "内置 Todo 插件（manifest 读取中…）",
  "todo.tasks.title": "任务（未完成 {open} · 今日已完成 {done}）",
  "todo.tasks.empty": "还没有任务，从下方表单新建一个吧。",
  "todo.form.title": "标题（必填，1-140 字符）",
  "todo.form.titlePlaceholder": "如：交周报",
  "todo.form.priority": "优先级",
  "todo.priority.0": "无",
  "todo.priority.1": "低",
  "todo.priority.2": "中",
  "todo.priority.3": "高",
  "todo.form.dueDate": "截止日期",
  "todo.form.dueTime": "截止时间（可选；带时间才派生提醒）",
  "todo.form.dueTimeTitle": "截止（带时间，可派生提醒）",
  "todo.form.dueTitle": "截止",
  "todo.form.remindBefore": "提前提醒（分钟，0 = 完全无提醒）",
  "todo.form.remindBeforeNote": "🔔 提前 {n} 分钟",
  "todo.form.remindBeforeTitle": "到点前 N 分钟宠物气泡提醒（reminders kind='todo' 单次）",
  "todo.form.tags": "标签（逗号分隔）",
  "todo.form.tagsPlaceholder": "如：work, 紧急",
  "todo.form.notes": "备注",
  "todo.form.notesPlaceholder": "可选",
  "todo.form.newTitle": "新建任务",
  "todo.form.editTitle": "编辑任务 #{n}",
  "todo.form.hint":
    "带时间的截止 + 提前提醒 > 0 → 到点前宠物气泡「还有 X 分钟要完成「任务名」」（reminders 派生单次行，TC-TD-03）；提前提醒 = 0 → 完全无提醒（TC-TD-08）。",
  "todo.form.save": "保存修改",
  "todo.form.create": "新建",
  "todo.form.cancel": "取消编辑",
  "todo.moveUp": "上移（sort_order 重排立即生效）",
  "todo.moveDown": "下移",
  "todo.complete": "完成",
  "todo.uncomplete": "取消完成",
  "todo.edit": "编辑",
  "todo.delete": "删除",
  "todo.deleteConfirm": "确认删除？",
  "todo.deleteHint": "再次点击确认删除",
  "todo.dueNone": "无",
  "todo.toast.deleteFail": "删除失败：{msg}",
  "todo.toast.updateFail": "更新失败：{msg}",
  "todo.toast.reorderFail": "重排失败：{msg}",
  "todo.text.minutesLeft": "还有 {n} 分钟要完成「{label}」",
  "todo.celebration.normal": "干得漂亮 🎉",
  "todo.celebration.allDone": "今日完成 {n} 项",
  "todo.validation.titleEmpty": "标题不能为空",
  "todo.validation.titleLong": "标题超长（≤{max} 字符）",
  "todo.validation.priority": "优先级应为 0-3",
  "todo.validation.remindBefore": "提前提醒非法（0-{max} 分钟）",
  "todo.validation.dueFormat": "截止格式应为 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM",
  "todo.validation.tagsTooMany": "标签数量超限（≤{max} 个）",
  "todo.validation.tagLong": "单个标签 ≤40 字符",

  // ---- 设置页 ----
  "settings.needApp": "设置需要在 PulsePet App（Tauri）内使用",
  "settings.loadFail": "读取宠物列表失败：{msg}",
  "settings.switchFail": "切换宠物失败：{msg}",
  "settings.passFail": "切换穿透失败：{msg}",
  "settings.languageFail": "切换语言失败：{msg}",
  "settings.pet": "宠物",
  "settings.petLabel": "选择宠物（切换立即生效；重启保留）",
  "settings.autoOption": "自动（默认 blinking-kitty）",
  "settings.source.builtin": "内置",
  "settings.missingOption": "{id} — 素材损坏或不存在，已回退",
  "settings.brokenOption": " — 素材损坏/非标准，不可选",
  "settings.current": "当前渲染：{id}（来源 {source}，{cols}×{rows} 网格，单帧 {fw}×{fh}）",
  "settings.fellBack": "，已从「{id}」回退",
  "settings.interaction": "交互",
  "settings.passThrough":
    "点击穿透（纯展示模式）：开启后鼠标事件透出——宠物不可拖拽、右键菜单不可达，动画照常播放；可经全局热键 ⌘/Ctrl+Shift+Alt+P 或托盘菜单「切换交互模式」切回。",
  // v2 M3（§3.7.2，P2-4）：「宠物与播报」区（工具播报开关；不放「功能管理」区）
  "settings.sectionPet": "宠物与播报",
  "settings.toolBroadcast":
    "工具播报：agent 使用工具时宠物气泡播报（如「正在编辑 X.md」）；关闭立即静默，插件照常上报。",
  "settings.toolBroadcastFail": "工具播报开关保存失败：{msg}",
  "settings.hotkeys": "全局热键：⌘/Ctrl+Shift+P 唤起/隐藏面板；⌘/Ctrl+Shift+Alt+P 切换穿透；",
  "settings.hotkeys.debug": " ⌘/Ctrl+Shift+Alt+F 调试烟花（仅开发构建）。",
  "settings.language": "语言",
  "settings.languageHint": "界面语言（三窗口 + 托盘菜单立即生效；重启保留）",
  "settings.languageZh": "中文",
  "settings.languageEn": "English",

  // ---- v2 M2 外观（主题三档，V2-DESIGN §2.3）----
  "settings.theme": "外观",
  "settings.themeHint": "面板主题（跟随系统或固定浅色/深色；重启保留；气泡与右键菜单不随主题变）",
  "settings.themeAuto": "跟随系统",
  "settings.themeLight": "浅色",
  "settings.themeDark": "深色",
  "settings.themeFail": "切换主题失败：{msg}",

  // ---- v2 M1 接入管理（V2-DESIGN §1.7/§1.8）----
  "integrations.title": "接入管理",
  "integrations.installed": "已安装",
  "integrations.notInstalled": "未安装",
  "integrations.stale": "需更新",
  "integrations.error": "检测失败",
  "integrations.install": "安装",
  "integrations.reinstall": "重新安装",
  "integrations.uninstall": "卸载",
  "integrations.installing": "安装中…",
  "integrations.nodeMissing": "未检测到 node（CC 接入需要）",
  "integrations.nodeReady": "node 已就绪",
  "integrations.lastEvent": "事件正常",
  "integrations.noEvent": "最近无事件",
  "integrations.backupNote": "修改前自动备份",
  "integrations.opencodeDesc": "opencode 插件",
  "integrations.claudeDesc": "Claude Code hooks",
  "integrations.fail": "操作失败：{msg}",
  "integrations.actionDone": "操作完成：",

  // ---- v2 M2 功能管理（feature flag，V2-DESIGN §2.5）----
  "plugins.manage": "功能管理",
  "plugins.manageHint": "关闭插件将隐藏其面板页并停用其派生提醒（数据保留，重新启用即恢复）",
  "plugins.manageToggle": "启用 {name}",
  "plugins.disabledBadge": "已停用（插件关闭）",

  // ---- 宠物右键菜单 ----
  "menu.settings": "设置…",
  "menu.togglePass": "切换交互模式（穿透：{state}）",
  "menu.passOn": "开",
  "menu.passOff": "关",
  "menu.hidePet": "隐藏宠物",
  // v2 M3：入口层「今日 token」信息项（{v} = … / 42M / — 三态）
  "menu.todayToken": "今日 token：{v}",

  // ---- v2 M3 工具级气泡（模板 ID 协议，§3.7.1；{p} = 净化后的 param）----
  "toolb.read": "正在读 {p}",
  "toolb.edit": "正在编辑 {p}",
  "toolb.bash": "正在跑 {p}",
  "toolb.search": "搜索 {p}",
  "toolb.web": "访问 {p}",

  // ---- 通用 ----
  "pass.on": "穿透开：纯展示（鼠标穿透，不可拖拽/右键）",
  "pass.off": "穿透关：可交互（可拖拽/右键）",
  "atlas.needApp": "atlas 需要在 PulsePet App（Tauri）内使用",
};

const en: Dict = {
  "panel.title": "PulsePet · Control Panel",
  "panel.tab.token": "Token",
  "panel.tab.reminders": "Reminders",
  "panel.tab.todo": "Todo",
  "panel.tab.settings": "Settings",
  "panel.statusAria": "Current agent state: {text}",

  "token.preset.today": "Today",
  "token.preset.7d": "Last 7 days",
  "token.preset.30d": "Last 30 days",
  "token.preset.custom": "Custom",
  "token.dim.day": "By day",
  "token.dim.week": "By week",
  "token.dim.range": "Whole range",
  "token.refresh": "Refresh",
  "token.loading": "Querying…",
  "token.aria.range": "Time range",
  "token.aria.from": "Start date",
  "token.aria.to": "End date",
  "token.aria.dim": "Dimension",
  "token.aria.agent": "Agent dimension",
  "token.chart.title": "Token timeline ({dim})",
  "token.chart.aria": "Token bar chart",
  "token.chart.tip": "{label}: total {total}",
  "token.chart.tipRow": "{name}: {n} ({pct}%)",
  "token.chart.noModels": "No models selected — the chart is empty.",
  "token.col.model": "Model",
  "token.model.unknown": "Unknown model",
  "token.kpi.total": "Total",
  "token.sessions.title": "Sessions ({n})",
  "token.sessions.empty": "No sessions in this range.",
  "token.sessions.updated": "Updated",
  "token.project.global": "Global",
  "token.project.unknown": "(unknown project)",
  "token.error.noDatabase":
    "opencode database not running/initialized: opencode.db / opencode-canary.db not found.",
  "token.error.legacyStorage":
    "Legacy opencode storage detected (storage/session/*.json): please upgrade opencode.",
  "token.error.schemaMismatch": "opencode.db schema incompatible ({msg})",
  "token.error.query": "Query failed: {msg}",
  "token.needApp": "Token stats are only available inside the PulsePet app (Tauri)",
  // v2 M5（§5.6，TC-M5-04/10）：agent 筛选 chip + 会话列表徽标全名
  "token.agent.opencode": "opencode",
  "token.agent.claudeCode": "Claude Code",
  "token.agent.all": "All",
  // v2 M5：费用口径标注（CC 恒 0——第三方 key 下单价表不可信，S4 裁定）
  "token.costOpencodeOnly": "Cost covers opencode only (no reliable Claude Code cost)",
  // v2 M5（TC-M5-07）：例程会话 ⚡ 徽标 title 提示（零 schema 改动）
  "token.taskBadge": "Scheduled routine",
  // v2 M5（C1/N-4）：degraded 细横幅（仅 panel；opencode 源不可用 × CC 有数据）
  "token.degraded": "opencode source unavailable: showing Claude Code data only",
  "token.hoverAgent": "Today's tokens by agent",

  "reminders.needApp": "Reminders are only available inside the PulsePet app (Tauri)",
  "reminders.loadFail": "Failed to load reminders: {msg}",
  "reminders.loading": "Loading reminders…",
  "reminders.fwGlobal": "Global fireworks mode (reminders without per-rule opt-in are upgraded to fireworks)",
  "reminders.pausedBadge": "All reminders paused (resume from tray)",
  "reminders.rules.title": "Reminder rules ({n})",
  "reminders.rules.empty":
    "No routines yet — create one from the templates or the form below.",
  "reminders.kind.hydration": "Hydration",
  "reminders.kind.rest": "Rest",
  "reminders.kind.custom": "Custom",
  "reminders.kind.todo": "Todo",
  "reminders.kind.todoDerived": "Todo (derived)",
  "reminders.field.start": "start",
  "reminders.field.end": "end",
  "reminders.interval.once": "Once",
  "reminders.interval.hours": "Every {n} h",
  "reminders.interval.minutes": "Every {n} min",
  "reminders.window.allDay": "All day",
  "reminders.window.from": "From {start}",
  "reminders.window.until": "Until {end}",
  "reminders.window.range": "{start}-{end}{cross}",
  "reminders.window.cross": " (cross-midnight)",
  "reminders.due": "Due {ts}",
  "reminders.dueNone": "—",
  "reminders.last": "Last {ts}",
  "reminders.lastNever": "Never triggered",
  "reminders.enabled": "Enabled",
  "reminders.enabledOn": "Enabled",
  "reminders.enabledOff": "Disabled",
  "reminders.fireworks": "Fireworks",
  "reminders.fireworksOverride": "Per-rule fireworks override (TC-RM-11)",
  "reminders.test": "Test",
  "reminders.edit": "Edit",
  "reminders.delete": "Delete",
  "reminders.deleteConfirm": "Confirm delete?",
  "reminders.deleteHint": "Click again to confirm delete",
  "reminders.form.newTitle": "New routine",
  "reminders.form.editTitle": "Edit routine #{n}",
  "reminders.form.todoHint":
    "📋 Derived todo reminder (one-shot; type/interval/time are managed by the Todo plugin — change the task's due or lead time on the Todo page). Only text, enabled and fireworks can be adjusted here; edits will be overwritten by the task title on its next save.",
  "reminders.form.type": "Type",
  "reminders.form.label": "Text (shown in bubble, plain text, 1-140 chars)",
  "reminders.form.labelPlaceholder": "e.g. Drink some water 💧",
  "reminders.form.interval": "Interval (minutes, 1-1440)",
  "reminders.form.start": "Start (empty = all day)",
  "reminders.form.end": "End (empty = all day)",
  "reminders.form.crossMidnight":
    "Cross-midnight window: fires only within [{start}, 24:00) ∪ [00:00, {end}) (TC-RM-06)",
  "reminders.form.fireworksMode": "Fireworks mode",
  "reminders.form.save": "Save changes",
  "reminders.form.create": "Create",
  "reminders.form.cancel": "Cancel editing",
  "reminders.stats.title": "History (reminder_logs)",
  "reminders.stats.empty": "No reminder records yet.",
  "reminders.stats.today": "Today: {n}",
  "reminders.stats.total": "Total: {n}",
  "reminders.toast.fired": "Fired “{label}”",
  "reminders.toast.dedup": "Already fired within 3 minutes, deduplicated (TC-RM-05)",
  "reminders.toast.paused": "All reminders are paused (tray “Pause all reminders”) — resume first",
  "reminders.toast.triggerFail": "Trigger failed: {msg}",
  "reminders.toast.deleteFail": "Delete failed: {msg}",
  "reminders.toast.updateFail": "Update failed: {msg}",
  "reminders.toast.fwGlobalFail": "Failed to save global fireworks switch: {msg}",
  "reminders.tpl.hydration": "Drink some water 💧",
  "reminders.tpl.rest1": "Take a break ☕",
  "reminders.tpl.rest2": "Stand up and walk 🚶",
  "reminders.validation.labelEmpty": "Text must not be empty",
  "reminders.validation.labelLong": "Text too long (≤140 chars)",
  "reminders.validation.kindBad": "Invalid type: {kind}",
  "reminders.validation.todoInterval": "Derived todo reminder interval is always 0 (one-shot)",
  "reminders.validation.absFormat": "{what} should be YYYY-MM-DDTHH:MM (derived todo)",
  "reminders.validation.intervalBad": "Invalid interval (1-{max} minutes)",
  "reminders.validation.timeFormat": "{what} time should be HH:MM",
  "reminders.validation.timeRange": "{what} time out of range (00:00-23:59)",

  // ---- v2 M4: scheduled tasks (tasks.*, V2-DESIGN §4.7) ----
  "panel.tab.tasks": "Routines",
  "panel.agentTask": "Routine",
  "tasks.rules.title": "Routines ({n})",
  "tasks.actionType": "Action",
  "tasks.action.notify": "Notify",
  "tasks.action.exec": "Run command",
  "tasks.badge.notify": "Notify (bubble + fireworks)",
  "tasks.badge.exec": "Run command (background process + history)",
  "tasks.schedule.interval": "Interval",
  "tasks.schedule.daily": "Daily",
  "tasks.schedule.once": "Once",
  "tasks.schedule.at": "Time (HH:MM)",
  "tasks.schedule.datetime": "Date & time",
  "tasks.schedule.weekdays": "Weekdays (none = every day)",
  "tasks.weekday.1": "Mon",
  "tasks.weekday.2": "Tue",
  "tasks.weekday.3": "Wed",
  "tasks.weekday.4": "Thu",
  "tasks.weekday.5": "Fri",
  "tasks.weekday.6": "Sat",
  "tasks.weekday.7": "Sun",
  "tasks.summary.daily": "Daily {at}",
  "tasks.summary.dailyDays": "{days} {at}",
  "tasks.summary.once": "Once · {at}",
  "tasks.form.name": "Task name",
  "tasks.form.namePlaceholder": "e.g. count md files",
  "tasks.form.command": "Command (runs via sh -c, ≤2000 chars)",
  "tasks.form.cwd": "Working directory (optional)",
  "tasks.form.timeout": "Timeout (minutes, 1-120)",
  "tasks.form.instruction": "Instruction",
  "tasks.tpl.title": "opencode routine",
  "tasks.tpl.hint": "One-click fill: opencode run --title \"pulsepet 例程: <task name>\" \"<instruction>\" (editable)",
  "tasks.tpl.auto": "Auto-approve permissions (--auto, dangerous)",
  "tasks.tpl.autoHint": "Permission requests are auto-approved — unattended side-effect commands, use with care",
  "tasks.skip": "Skip once",
  "tasks.skipDone": "Skipped this cycle",
  "tasks.skipFail": "Skip failed: {msg}",
  "tasks.snooze": "Snooze 10 min",
  "tasks.history.title": "Run history",
  "tasks.history.empty": "No runs yet.",
  "tasks.history.loadFail": "Failed to load history: {msg}",
  "tasks.history.page": "Page {page}/{pages} · {total} runs",
  "tasks.history.prev": "Previous",
  "tasks.history.next": "Next",
  "tasks.history.expand": "Show output",
  "tasks.history.collapse": "Collapse",
  "tasks.history.delay": "Catch-up delay {sec}s",
  "tasks.history.output": "Output tail (≤2KB)",
  "tasks.history.filterAll": "All tasks",
  "tasks.status.ok": "ok",
  "tasks.status.failed": "failed",
  "tasks.status.skipped": "skipped",
  "tasks.status.running": "running",
  "task.summary.ok": "Task finished",
  "task.summary.failed": "Failed (exit code {n})",
  "task.summary.failedNoCode": "Failed",
  "task.summary.timeout": "Timed out (terminated after {n} min)",
  "task.summary.missed": "Missed catch-up window (15 min)",
  "task.summary.paused": "Skipped while paused",
  "task.summary.interrupted": "Interrupted on app exit",
  "task.summary.stale": "Unfinished run from last session (cleaned)",
  "tasks.validation.actionBad": "Invalid action type (notify/exec)",
  "tasks.validation.scheduleBad": "Invalid schedule kind (interval/daily/once)",
  "tasks.validation.atRequired": "Time is required",
  "tasks.validation.atFormat": "Time should be HH:MM",
  "tasks.validation.dtFormat": "Date & time should be YYYY-MM-DDTHH:MM",
  "tasks.validation.dtPast": "Must be in the future (no accidental run on create)",
  "tasks.validation.weekdaysBad": "Invalid weekdays (1-7)",
  "tasks.validation.paramsMissing": "Run-command needs action_params (JSON object)",
  "tasks.validation.commandEmpty": "Command cannot be empty",
  "tasks.validation.commandLong": "Command too long (≤2000 chars)",
  "tasks.validation.cwdNotDir": "Working directory missing or not a directory",
  "tasks.validation.timeoutBad": "Invalid timeout (1-120 minutes, default 10)",
  "tasks.validation.autoBad": "opencode_auto should be a boolean",

  "todo.needApp": "Todo is only available inside the PulsePet app (Tauri)",
  "todo.loadFail": "Failed to load Todo: {msg}",
  "todo.loading": "Loading Todo…",
  "todo.plugin.prefix": "Plugin",
  "todo.plugin.enabled": "enabled",
  "todo.plugin.disabled": "disabled",
  "todo.plugin.permissions": "Permissions",
  "todo.plugin.loading": "Built-in Todo plugin (loading manifest…)",
  "todo.tasks.title": "Tasks (open {open} · done today {done})",
  "todo.tasks.empty": "No tasks yet — create one from the form below.",
  "todo.form.title": "Title (required, 1-140 chars)",
  "todo.form.titlePlaceholder": "e.g. Submit weekly report",
  "todo.form.priority": "Priority",
  "todo.priority.0": "None",
  "todo.priority.1": "Low",
  "todo.priority.2": "Medium",
  "todo.priority.3": "High",
  "todo.form.dueDate": "Due date",
  "todo.form.dueTime": "Due time (optional; only with a time can it derive a reminder)",
  "todo.form.dueTimeTitle": "Due (with time, can derive a reminder)",
  "todo.form.dueTitle": "Due",
  "todo.form.remindBefore": "Lead time (minutes, 0 = no reminder at all)",
  "todo.form.remindBeforeNote": "🔔 {n} min ahead",
  "todo.form.remindBeforeTitle": "Pet bubble reminder N minutes before the deadline (reminders kind='todo' one-shot)",
  "todo.form.tags": "Tags (comma-separated)",
  "todo.form.tagsPlaceholder": "e.g. work, urgent",
  "todo.form.notes": "Notes",
  "todo.form.notesPlaceholder": "Optional",
  "todo.form.newTitle": "New task",
  "todo.form.editTitle": "Edit task #{n}",
  "todo.form.hint":
    "Timed due + lead time > 0 → pet bubble “X min left to finish ‘task’” before the deadline (derived one-shot reminders row, TC-TD-03); lead time = 0 → no reminder at all (TC-TD-08).",
  "todo.form.save": "Save changes",
  "todo.form.create": "Create",
  "todo.form.cancel": "Cancel editing",
  "todo.moveUp": "Move up (sort_order re-applies immediately)",
  "todo.moveDown": "Move down",
  "todo.complete": "Complete",
  "todo.uncomplete": "Uncomplete",
  "todo.edit": "Edit",
  "todo.delete": "Delete",
  "todo.deleteConfirm": "Confirm delete?",
  "todo.deleteHint": "Click again to confirm delete",
  "todo.dueNone": "None",
  "todo.toast.deleteFail": "Delete failed: {msg}",
  "todo.toast.updateFail": "Update failed: {msg}",
  "todo.toast.reorderFail": "Reorder failed: {msg}",
  "todo.text.minutesLeft": "{n} min left to finish “{label}”",
  "todo.celebration.normal": "Well done 🎉",
  "todo.celebration.allDone": "{n} tasks done today",
  "todo.validation.titleEmpty": "Title must not be empty",
  "todo.validation.titleLong": "Title too long (≤{max} chars)",
  "todo.validation.priority": "Priority should be 0-3",
  "todo.validation.remindBefore": "Invalid lead time (0-{max} minutes)",
  "todo.validation.dueFormat": "Due should be YYYY-MM-DD or YYYY-MM-DDTHH:MM",
  "todo.validation.tagsTooMany": "Too many tags (≤{max})",
  "todo.validation.tagLong": "Each tag ≤40 chars",

  "settings.needApp": "Settings are only available inside the PulsePet app (Tauri)",
  "settings.loadFail": "Failed to load pet list: {msg}",
  "settings.switchFail": "Failed to switch pet: {msg}",
  "settings.passFail": "Failed to toggle pass-through: {msg}",
  "settings.languageFail": "Failed to switch language: {msg}",
  "settings.pet": "Pet",
  "settings.petLabel": "Select pet (applies immediately; persisted across restarts)",
  "settings.autoOption": "Auto (default blinking-kitty)",
  "settings.source.builtin": "Built-in",
  "settings.missingOption": "{id} — broken or missing, fell back",
  "settings.brokenOption": " — broken/non-standard, not selectable",
  "settings.current": "Now rendering: {id} (source {source}, {cols}×{rows} grid, frame {fw}×{fh})",
  "settings.fellBack": ", fell back from “{id}”",
  "settings.interaction": "Interaction",
  "settings.passThrough":
    "Click-through (display-only mode): when on, mouse events pass through — the pet cannot be dragged and the right-click menu is unavailable, while animations keep playing; toggle back via global hotkey ⌘/Ctrl+Shift+Alt+P or the tray menu “Toggle interaction mode”.",
  "settings.sectionPet": "Pet & Broadcast",
  "settings.toolBroadcast":
    "Tool broadcast: the pet bubble reports tool usage (e.g. “Editing X.md”); turning it off silences immediately while the plugin keeps reporting.",
  "settings.toolBroadcastFail": "Failed to save tool broadcast switch: {msg}",
  "settings.hotkeys": "Global hotkeys: ⌘/Ctrl+Shift+P show/hide panel; ⌘/Ctrl+Shift+Alt+P toggle pass-through;",
  "settings.hotkeys.debug": " ⌘/Ctrl+Shift+Alt+F debug fireworks (dev builds only).",
  "settings.language": "Language",
  "settings.languageHint": "UI language (all three windows + tray menu apply immediately; persisted)",
  "settings.languageZh": "中文",
  "settings.languageEn": "English",

  // ---- v2 M2 appearance (theme, V2-DESIGN §2.3) ----
  "settings.theme": "Appearance",
  "settings.themeHint": "Panel theme (follow system or fixed light/dark; persisted; bubble and right-click menu keep their pet-world look)",
  "settings.themeAuto": "Follow system",
  "settings.themeLight": "Light",
  "settings.themeDark": "Dark",
  "settings.themeFail": "Failed to switch theme: {msg}",

  // ---- v2 M1 接入管理（V2-DESIGN §1.7/§1.8）----
  "integrations.title": "Integrations",
  "integrations.installed": "Installed",
  "integrations.notInstalled": "Not installed",
  "integrations.stale": "Needs update",
  "integrations.error": "Check failed",
  "integrations.install": "Install",
  "integrations.reinstall": "Reinstall",
  "integrations.uninstall": "Uninstall",
  "integrations.installing": "Installing…",
  "integrations.nodeMissing": "node not found (required for claude-code)",
  "integrations.nodeReady": "node ready",
  "integrations.lastEvent": "Receiving events",
  "integrations.noEvent": "No recent events",
  "integrations.backupNote": "Changes are backed up automatically",
  "integrations.opencodeDesc": "opencode plugin",
  "integrations.claudeDesc": "Claude Code hooks",
  "integrations.fail": "Operation failed: {msg}",
  "integrations.actionDone": "Done: ",

  // ---- v2 M2 features (feature flag, V2-DESIGN §2.5) ----
  "plugins.manage": "Features",
  "plugins.manageHint": "Disabling a plugin hides its panel tab and stops its derived reminders (data is kept; re-enable to restore)",
  "plugins.manageToggle": "Enable {name}",
  "plugins.disabledBadge": "Disabled (plugin off)",

  "menu.settings": "Settings…",
  "menu.togglePass": "Toggle interaction mode (pass-through: {state})",
  "menu.passOn": "on",
  "menu.passOff": "off",
  "menu.hidePet": "Hide pet",
  "menu.todayToken": "Today's tokens: {v}",

  // ---- v2 M3 tool-level bubbles (template ID protocol, §3.7.1) ----
  "toolb.read": "Reading {p}",
  "toolb.edit": "Editing {p}",
  "toolb.bash": "Running {p}",
  "toolb.search": "Searching {p}",
  "toolb.web": "Fetching {p}",

  "pass.on": "Pass-through on: display-only (mouse passes through, no drag/right-click)",
  "pass.off": "Pass-through off: interactive (draggable / right-clickable)",
  "atlas.needApp": "atlas is only available inside the PulsePet app (Tauri)",
};

/** 双语字典（导出供字典完备性测试遍历）。 */
export const DICT: Record<Lang, Dict> = { zh, en };

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

/**
 * 语言 store：默认 zh（测试/未初始化环境的确定性行为）；`initI18n()` 在
 * Tauri 运行时内以「持久化值 → 系统语言」顺序覆盖。
 */
export const useLangStore = create<LangState>((set) => ({
  lang: "zh",
  setLang: (lang) => set({ lang }),
}));

/** 取当前语言（纯函数场景 / 非 React 调用方使用）。 */
export function currentLang(): Lang {
  return useLangStore.getState().lang;
}

/** 查字典 + `{x}` 插值；缺键回退键名、缺参保留占位符（均可观测不静默）。 */
export function t(
  key: string,
  params?: Record<string, string | number>,
  lang: Lang = currentLang(),
): string {
  const tpl = DICT[lang][key] ?? DICT.zh[key] ?? key;
  if (!params) return tpl;
  return tpl.replace(/\{(\w+)\}/g, (m, k: string) =>
    k in params ? String(params[k]) : m,
  );
}

/** 语言标签（`zh*` → zh；其余含 zh/en 之外的一律回退 en）。 */
export function systemLangSafe(language: string | undefined): Lang {
  return (language ?? "").toLowerCase().startsWith("zh") ? "zh" : "en";
}

/** 浏览器默认语言（无 navigator 环境回退 en）。 */
function systemLang(): Lang {
  const nav =
    typeof navigator !== "undefined"
      ? (navigator as { language?: string }).language
      : undefined;
  return systemLangSafe(nav);
}

/** Tauri 运行时探测（与 token-stats.isTauriRuntime 同实现；此处内联避免
 * i18n ↔ token-stats 循环 import——token-stats 的错误文案反过来依赖 t()）。 */
function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as unknown as Record<string, unknown>)
  );
}

/**
 * 各窗口启动初始化：读持久化语言（app_state `ui.language`，经 Rust
 * `ui_get_language`）→ 无持久化跟随系统；随后订阅 `ui://language`
 * （设置页切换 → Rust 广播 → 三窗口同步）。
 */
export async function initI18n(): Promise<void> {
  if (!isTauriRuntime()) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const persisted = await invoke<string | null>("ui_get_language");
    const lang = persisted === "zh" || persisted === "en" ? persisted : systemLang();
    useLangStore.getState().setLang(lang);
  } catch (e) {
    console.error("[pulsepet] load persisted language failed:", e);
    useLangStore.getState().setLang(systemLang());
  }
  try {
    const { listen } = await import("@tauri-apps/api/event");
    await listen(LANGUAGE_EVENT, (event) => {
      const v = (event.payload as { lang?: unknown } | null)?.lang;
      if (v === "zh" || v === "en") useLangStore.getState().setLang(v);
    });
  } catch (e) {
    console.error("[pulsepet] language event listen failed:", e);
  }
}

/**
 * 设置页切换语言：本地 store 立即生效 → invoke `ui_set_language`（Rust：
 * 持久化 app_state + 全局语言位 + 重建托盘菜单 + panel 标题 + 广播三窗口）。
 */
export async function changeLanguage(lang: Lang): Promise<void> {
  useLangStore.getState().setLang(lang);
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("ui_set_language", { lang });
}
