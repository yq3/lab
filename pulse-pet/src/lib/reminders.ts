/**
 * reminders：M4 提醒的 TS 侧纯函数与 Rust 命令封装（DESIGN §5.4/§5.2，TC-RM 章节）。
 *
 * - 类型 `ReminderRule` / `ReminderStat` 与 Rust `reminder_scheduler.rs` 的 serde
 *   字段一一对应（snake_case，与 M3 TokenRow 同风格）。
 * - `sanitizeReminderText`：气泡文案净化（TC-RM-15）——在 M3 `sanitizeBubbleText`
 *   （单行 1-140）之上叠加"不展示原始路径/URL/secret 样式 token"的脱敏（DESIGN
 *   §3.1 净化策略在提醒文案上的应用）；React 纯文本渲染天然无注入执行。
 * - `parseReminderTrigger`：解析 Rust `reminder://trigger` payload（纯函数可单测）。
 * - invoke 封装走动态 import + 运行时探测（vitest/node 下不可调用，纯函数可直接测）。
 */

import { sanitizeBubbleText } from "./bubble";
import { isTauriRuntime } from "./token-stats";
import { t, type Lang } from "./i18n";
import { todoReminderText } from "./todos";

export { isTauriRuntime };

/** 面板可创建的 kind（todo 由 M7 插件派生，不在表单可选）。 */
export type ReminderKind = "hydration" | "rest" | "custom";

/** Rust 侧允许的全部 kind（读取/展示用）。 */
export type ReminderKindAll = ReminderKind | "todo";

/** v2 M4：动作类型（§4.2）。 */
export type ActionType = "notify" | "exec";

/** v2 M4：调度类型（§4.2，weekly 并入 daily 的 weekdays 过滤）。 */
export type ScheduleKind = "interval" | "daily" | "once";

export interface ReminderRule {
  id: number;
  kind: ReminderKindAll;
  label: string;
  interval_minutes: number;
  start_time: string | null;
  end_time: string | null;
  enabled: boolean;
  use_fireworks: boolean;
  last_triggered_at: string | null;
  source_todo_id: number | null;
  /** M7：todo 派生提醒的截止时刻（"YYYY-MM-DDTHH:MM"）；非 todo 为 null。 */
  todo_due_at: string | null;
  created_at: string;
  /** v2 M4：动作类型（'notify' | 'exec'）。 */
  action_type: ActionType;
  /** v2 M4：动作参数 JSON 文本（exec = {command, cwd?, timeout_minutes?, opencode_auto?}）。 */
  action_params: string | null;
  /** v2 M4：调度类型（'interval' | 'daily' | 'once'；daily/once 行 interval 恒 0）。 */
  schedule_kind: ScheduleKind;
  /** v2 M4：daily → "HH:MM"；once → "YYYY-MM-DDTHH:MM"；interval → null。 */
  schedule_at: string | null;
  /** v2 M4：daily 的星期过滤 JSON "[1,3,5]"（1=周一…7=周日；null/空 = 每天）。 */
  schedule_weekdays: string | null;
  /** v2 M4：snooze 顺延终点（RFC3339；触发时清空）。 */
  snooze_until: string | null;
  /** v2 M4：skipped 判定时刻（与 last_triggered_at 分离，P3-2）。 */
  last_skipped_at: string | null;
}

/**
 * CRUD 入参（与 Rust `ReminderInput` 对应）。v2 M4 +5 字段全可选——旧调用
 * （v1 载荷/测试 helper）不带新字段时 JSON 序列化丢弃 → Rust serde default
 * 取 notify/interval，v1 行为不变。
 */
export interface ReminderInput {
  kind: ReminderKindAll;
  label: string;
  interval_minutes: number;
  start_time: string | null;
  end_time: string | null;
  enabled: boolean;
  use_fireworks: boolean;
  /** v2 M4：缺省 notify。 */
  action_type?: ActionType;
  /** v2 M4：动作参数 JSON 文本（exec 必填）。 */
  action_params?: string | null;
  /** v2 M4：缺省 interval。 */
  schedule_kind?: ScheduleKind;
  /** v2 M4：daily → "HH:MM"；once → "YYYY-MM-DDTHH:MM"。 */
  schedule_at?: string | null;
  /** v2 M4：daily 的星期过滤 JSON 文本。 */
  schedule_weekdays?: string | null;
}

export interface ReminderStat {
  kind: string;
  today: number;
  total: number;
}

/** `reminder://trigger` payload（Rust `TriggerPayload`）。 */
export interface ReminderTrigger {
  id: number;
  kind: string;
  label: string;
  use_fireworks: boolean;
  fireworks_global: boolean;
  log_id: number;
  /** M7（TC-TD-03）：kind='todo' 时为截止时刻 epoch ms（前端算"还有 X 分钟"）。 */
  todo_due_ms: number | null;
}

/** 内置模板（DESIGN §5.2 默认文案；面板一键套用）。 */
export const REMINDER_TEMPLATES: readonly {
  kind: ReminderKind;
  label: string;
  interval_minutes: number;
}[] = [
  { kind: "hydration", label: "该喝水啦 💧", interval_minutes: 30 },
  { kind: "rest", label: "休息一下 ☕", interval_minutes: 60 },
  { kind: "rest", label: "站起来走走 🚶", interval_minutes: 90 },
];

const KIND_LABEL_KEYS: Record<string, string> = {
  hydration: "reminders.kind.hydration",
  rest: "reminders.kind.rest",
  custom: "reminders.kind.custom",
  todo: "reminders.kind.todo",
};

/** kind 人读名（M8 i18n：随当前语言；未知 kind 原样返回）。 */
export function kindLabel(kind: string, lang?: Lang): string {
  const key = KIND_LABEL_KEYS[kind];
  return key ? t(key, undefined, lang) : kind;
}

export function kindEmoji(kind: string): string {
  if (kind === "hydration") return "💧";
  if (kind === "rest") return "☕";
  if (kind === "todo") return "📋";
  return "⭐";
}

// ---- 净化（TC-RM-15） ----

/** 路径样式 token：`/usr/...`、`~/...`、`C:\...`（行首或空白后起头）。 */
const RE_PATH = /(^|\s)(?:[A-Za-z]:\\|\/|~\/)\S*/g;
/** URL：`http(s)://...`、`www.` 开头（不吞尾部闭合标点；`?` 属查询串保留）。 */
const RE_URL = /\b(?:https?:\/\/|www\.)[^\s)\]。，,；;！？]*/gi;
/** secret 样式 token：OpenAI/Anthropic sk-、GitHub ghp_/pat、AWS AKIA、Slack xox。 */
const RE_SECRET =
  /\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{8,})/g;

/**
 * 提醒文案净化：URL/路径/secret 样式 token 置换为占位符，再走 M3 基础净化
 * （单行化 + trim + 1-140 截断；空 → 空串即丢弃不出气泡）。
 * `<script>` / markdown 链接等标记不做任何解释——React 纯文本渲染即无注入。
 */
export function sanitizeReminderText(text: unknown): string {
  if (typeof text !== "string") return "";
  return sanitizeBubbleText(
    text.replace(RE_URL, "［链接］").replace(RE_SECRET, "［密钥］").replace(RE_PATH, "$1［路径］"),
  );
}

// ---- 校验（与 Rust validate_input 同口径；返回错误文案，null = 通过） ----

export const MAX_INTERVAL_MINUTES = 1440;

/**
 * 规则行 → 表单值（M4 P2 ②，M7 清偿）：**保留原始 kind**（todo 派生规则不再
 * 降级为 custom——快捷开关/编辑不得改写 kind，source_todo_id 在 Rust update
 * 不触碰该列天然保留）；interval=0（todo 单次）原样带回由校验放行。
 * v2 M4：动作/调度新字段一并带回（快捷开关路径不丢 exec/定点语义）。
 */
export function ruleToForm(r: ReminderRule): ReminderInput {
  return {
    kind: r.kind,
    label: r.label,
    interval_minutes: r.interval_minutes,
    start_time: r.start_time,
    end_time: r.end_time,
    enabled: r.enabled,
    use_fireworks: r.use_fireworks,
    action_type: r.action_type,
    action_params: r.action_params,
    schedule_kind: r.schedule_kind,
    schedule_at: r.schedule_at,
    schedule_weekdays: r.schedule_weekdays,
  };
}

export function validateReminderInput(input: ReminderInput, lang?: Lang): string | null {
  const label = input.label.trim();
  if (!label) return t("reminders.validation.labelEmpty", undefined, lang);
  if (label.length > 140) return t("reminders.validation.labelLong", undefined, lang);
  if (!["hydration", "rest", "custom", "todo"].includes(input.kind)) {
    return t("reminders.validation.kindBad", { kind: input.kind }, lang);
  }
  // M4 P2 ③（M7 清偿）：todo kind 恒 interval=0（一次性）；非 todo 至少 1 分钟。
  // 新建表单只提供 hydration/rest/custom（todo 由 Todo 插件派生），此处放行
  // 仅为编辑/快捷开关已有 todo 规则时不再破坏其 kind 与 interval。
  // P2-2（R1 审查）：字段名（起始/结束）随语言本地化，en 不再中英混搭。
  const whatStart = () => t("reminders.field.start", undefined, lang);
  const whatEnd = () => t("reminders.field.end", undefined, lang);
  if (input.kind === "todo") {
    if (input.interval_minutes !== 0) {
      return t("reminders.validation.todoInterval", undefined, lang);
    }
    const checkAbs = (s: string | null | undefined, what: string): string | null => {
      if (!s) return null;
      return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s)
        ? null
        : t("reminders.validation.absFormat", { what }, lang);
    };
    return checkAbs(input.start_time, whatStart()) ?? checkAbs(input.end_time, whatEnd());
  }

  // ---- v2 M4：动作/调度泛化校验（与 Rust normalize_input 同规则；Rust 为权威） ----

  const actionType = input.action_type ?? "notify";
  if (actionType !== "notify" && actionType !== "exec") {
    return t("tasks.validation.actionBad", undefined, lang);
  }
  const scheduleKind = input.schedule_kind ?? "interval";
  if (scheduleKind !== "interval" && scheduleKind !== "daily" && scheduleKind !== "once") {
    return t("tasks.validation.scheduleBad", undefined, lang);
  }

  // exec：action_params JSON 解析 + 执行器校验（TC-M4-01-4/07）
  if (actionType === "exec") {
    const text = (input.action_params ?? "").trim();
    if (!text) return t("tasks.validation.paramsMissing", undefined, lang);
    let params: unknown;
    try {
      params = JSON.parse(text);
    } catch {
      return t("tasks.validation.paramsMissing", undefined, lang);
    }
    const err = validateExecParams(params as Record<string, unknown>, lang);
    if (err) return err;
  }

  if (scheduleKind === "daily") {
    const at = (input.schedule_at ?? "").trim();
    if (!at) return t("tasks.validation.atRequired", undefined, lang);
    if (!/^\d{2}:\d{2}$/.test(at) || !hhmmOk(at)) {
      return t("tasks.validation.atFormat", undefined, lang);
    }
    const wdErr = validateWeekdays(input.schedule_weekdays, lang);
    if (wdErr) return wdErr;
    return null; // daily：interval/窗口字段由 Rust normalize 重置（前端不校验）
  }
  if (scheduleKind === "once") {
    const at = (input.schedule_at ?? "").trim();
    if (!at) return t("tasks.validation.atRequired", undefined, lang);
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(at)) {
      return t("tasks.validation.dtFormat", undefined, lang);
    }
    const ms = Date.parse(at); // 本地时区解析（无 Z 后缀）
    if (Number.isNaN(ms)) return t("tasks.validation.dtFormat", undefined, lang);
    if (ms <= Date.now()) return t("tasks.validation.dtPast", undefined, lang);
    return null;
  }

  // interval：v1 语义（1-1440；HH:MM 窗口；exec 行不消费窗口——由 Rust 重置）
  if (input.interval_minutes < 1 || input.interval_minutes > MAX_INTERVAL_MINUTES) {
    return t("reminders.validation.intervalBad", { max: MAX_INTERVAL_MINUTES }, lang);
  }
  const checkHhmm = (s: string | null | undefined, what: string): string | null => {
    if (!s) return null;
    const m = /^(\d{1,2}):(\d{2})$/.exec(s);
    if (!m) return t("reminders.validation.timeFormat", { what }, lang);
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) return t("reminders.validation.timeRange", { what }, lang);
    return null;
  };
  if (actionType === "exec") return null; // exec+interval：窗口不校验（Rust 清空）
  const startErr = checkHhmm(input.start_time, whatStart());
  if (startErr) return startErr;
  const endErr = checkHhmm(input.end_time, whatEnd());
  if (endErr) return endErr;
  return null;
}

function hhmmOk(s: string): boolean {
  const m = /^(\d{2}):(\d{2})$/.exec(s);
  if (!m) return false;
  return Number(m[1]) <= 23 && Number(m[2]) <= 59;
}

/** exec action_params 校验（与 Rust ExecExecutor::validate_params 同规则）。 */
export function validateExecParams(
  params: Record<string, unknown>,
  lang?: Lang,
): string | null {
  const command = typeof params.command === "string" ? params.command : "";
  if (!command.trim()) return t("tasks.validation.commandEmpty", undefined, lang);
  if (command.length > 2000) return t("tasks.validation.commandLong", undefined, lang);
  if (params.cwd != null && typeof params.cwd === "string" && params.cwd.trim()) {
    // 存在性/目录性只做宽松提示（Rust 权威校验；浏览器端无法同步判定）
    void 0;
  }
  if (params.timeout_minutes != null) {
    const v = params.timeout_minutes;
    if (typeof v !== "number" || !Number.isInteger(v) || v < 1 || v > 120) {
      return t("tasks.validation.timeoutBad", undefined, lang);
    }
  }
  if (params.opencode_auto != null && typeof params.opencode_auto !== "boolean") {
    return t("tasks.validation.autoBad", undefined, lang);
  }
  return null;
}

/** weekdays JSON 文本校验（1-7、合法数组）。 */
export function validateWeekdays(s: string | null | undefined, lang?: Lang): string | null {
  const text = (s ?? "").trim();
  if (!text) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return t("tasks.validation.weekdaysBad", undefined, lang);
  }
  if (!Array.isArray(parsed) || !parsed.every((d) => typeof d === "number" && d >= 1 && d <= 7 && Number.isInteger(d))) {
    return t("tasks.validation.weekdaysBad", undefined, lang);
  }
  return null;
}

// ---- 展示辅助（纯函数） ----

/** "09:00"-"18:00" → "09:00-18:00（跨午夜）" 之类的窗口描述。 */
export function isCrossMidnight(start: string | null, end: string | null): boolean {
  if (!start || !end) return false;
  return start > end;
}

export function formatWindow(start: string | null, end: string | null, lang?: Lang): string {
  if (start && end) {
    return t(
      "reminders.window.range",
      {
        start,
        end,
        cross: isCrossMidnight(start, end)
          ? t("reminders.window.cross", undefined, lang)
          : "",
      },
      lang,
    );
  }
  if (start) return t("reminders.window.from", { start }, lang);
  if (end) return t("reminders.window.until", { end }, lang);
  return t("reminders.window.allDay", undefined, lang);
}

export function formatInterval(minutes: number, lang?: Lang): string {
  if (minutes === 0) return t("reminders.interval.once", undefined, lang);
  if (minutes % 60 === 0) {
    return t("reminders.interval.hours", { n: minutes / 60 }, lang);
  }
  return t("reminders.interval.minutes", { n: minutes }, lang);
}

/** RFC3339 → 展示用本地时间（解析失败原样返回）。 */
export function formatLogTime(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// ---- v2 M4：动作徽标 + 调度摘要 + opencode 模板（§4.6/§4.7） ----

/** 动作徽标：💧 notify / ⚡ exec（todo 派生行 📋 保持 M2 展示）。 */
export function actionBadge(rule: Pick<ReminderRule, "kind" | "action_type">): string {
  if (rule.kind === "todo") return "📋";
  return rule.action_type === "exec" ? "⚡" : "💧";
}

/** 动作徽标 title 说明（悬停提示）。 */
export function actionBadgeTitle(rule: Pick<ReminderRule, "kind" | "action_type">, lang?: Lang): string {
  if (rule.kind === "todo") return t("reminders.kind.todoDerived", undefined, lang);
  return t(
    rule.action_type === "exec" ? "tasks.badge.exec" : "tasks.badge.notify",
    undefined,
    lang,
  );
}

/** weekdays JSON → 数字数组（空/解析失败 = 每天空数组）。 */
export function parseWeekdays(s: string | null | undefined): number[] {
  if (!s) return [];
  try {
    const arr = JSON.parse(s);
    if (!Array.isArray(arr)) return [];
    return arr.filter((d) => typeof d === "number" && d >= 1 && d <= 7);
  } catch {
    return [];
  }
}

/** weekdays 数字数组 → 规范 JSON 文本（空数组 = null = 每天）。 */
export function weekdaysToJson(days: number[]): string | null {
  const uniq = [...new Set(days)].filter((d) => d >= 1 && d <= 7).sort((a, b) => a - b);
  return uniq.length ? JSON.stringify(uniq) : null;
}

/**
 * 调度摘要（列表行 · §4.7）：「每 30 分钟 · 09:00-18:00」/「每天 09:00」/
 * 「周三、五 09:00」/「一次 · 08-25 21:00」；todo 派生行走既有截止展示。
 */
export function scheduleSummary(
  rule: Pick<
    ReminderRule,
    "kind" | "interval_minutes" | "start_time" | "end_time" | "schedule_kind" |
    "schedule_at" | "schedule_weekdays"
  >,
  lang?: Lang,
): string {
  const wdNames = parseWeekdays(rule.schedule_weekdays).map(
    (d) => t(`tasks.weekday.${d}`, undefined, lang),
  );
  switch (rule.schedule_kind) {
    case "daily": {
      const at = rule.schedule_at ?? "";
      if (!wdNames.length) return t("tasks.summary.daily", { at }, lang);
      return t("tasks.summary.dailyDays", { days: wdNames.join("、"), at }, lang);
    }
    case "once": {
      // "YYYY-MM-DDTHH:MM" → "MM-DD HH:MM"（就近可读）
      const at = (rule.schedule_at ?? "").replace(/^(\d{4})-(\d{2}-\d{2})T/, "$2 ");
      return t("tasks.summary.once", { at }, lang);
    }
    default: {
      // interval + 可选时间窗
      const base = formatInterval(rule.interval_minutes, lang);
      const win = formatWindow(rule.start_time, rule.end_time, lang);
      if (rule.start_time || rule.end_time) {
        return `${base} · ${win}`;
      }
      return base;
    }
  }
}

/**
 * opencode 例程模板拼接（§4.6，纯填表辅助——执行层不感知 opencode）：
 * `opencode run --title "pulsepet 例程: <任务名>" [--auto] "<指令>"`；
 * 不用 --dir（cwd 字段即工作目录）。
 */
export function buildOpencodeCommand(
  taskName: string,
  instruction: string,
  auto: boolean,
): string {
  const title = `pulsepet 例程: ${taskName.trim()}`;
  const instr = instruction.trim();
  const autoFlag = auto ? " --auto" : "";
  return `opencode run --title ${shellQuote(title)}${autoFlag} ${shellQuote(instr)}`;
}

/** POSIX 单引号安全引用（sh -c 双层语义下最稳的引用形态）。 */
export function shellQuote(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

/**
 * action_logs.summary 模板键 → 当前语言渲染（与 Rust i18n::render_task_summary
 * 同口径；参数化键 `task.summary.timeout:N`）。
 */
export function renderTaskSummary(
  stored: string,
  exitCode?: number | null,
  lang?: Lang,
): string {
  const timeoutMatch = /^task\.summary\.timeout:(\d+)$/.exec(stored);
  if (timeoutMatch) {
    return t("task.summary.timeout", { n: timeoutMatch[1] }, lang);
  }
  switch (stored) {
    case "task.summary.ok":
      return t("task.summary.ok", undefined, lang);
    case "task.summary.failed":
      return exitCode != null
        ? t("task.summary.failed", { n: exitCode }, lang)
        : t("task.summary.failedNoCode", undefined, lang);
    case "task.summary.missed":
      return t("task.summary.missed", undefined, lang);
    case "task.summary.paused":
      return t("task.summary.paused", undefined, lang);
    case "task.summary.interrupted":
      return t("task.summary.interrupted", undefined, lang);
    case "task.summary.stale":
      return t("task.summary.stale", undefined, lang);
    default:
      return stored; // 未知键原样（可观测不静默）
  }
}

/** action_logs 行（Rust ActionLog serde 同名字段）。 */
export interface ActionLog {
  id: number;
  reminder_id: number;
  action_type: string;
  status: string;
  summary: string;
  output_tail: string | null;
  exit_code: number | null;
  started_at: string;
  finished_at: string | null;
  scheduled_at: string | null;
}

/** action_logs_list 分页返回（Rust ActionLogPage）。 */
export interface ActionLogPage {
  rows: ActionLog[];
  total: number;
  page: number;
  page_size: number;
}

// ---- 触发事件解析（纯函数，供 bridge/单测） ----

/** 解析 `reminder://trigger` payload；字段缺失/类型不对 → null（静默忽略）。 */
export function parseReminderTrigger(payload: unknown): ReminderTrigger | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as Record<string, unknown>;
  const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
  if (!num(p.id) || !num(p.log_id)) return null;
  if (typeof p.kind !== "string" || typeof p.label !== "string") return null;
  if (typeof p.use_fireworks !== "boolean" || typeof p.fireworks_global !== "boolean") {
    return null;
  }
  return {
    id: p.id,
    kind: p.kind,
    label: p.label,
    use_fireworks: p.use_fireworks,
    fireworks_global: p.fireworks_global,
    log_id: p.log_id,
    // M7：todo_due_ms 可选（非 todo 提醒不带；缺省 → null）
    todo_due_ms: num(p.todo_due_ms) ? p.todo_due_ms : null,
  };
}

/** 烟花判定：单条 use_fireworks 覆盖（升级）全局开关（TC-RM-11，OR 语义）。 */
export function usesFireworks(t: Pick<ReminderTrigger, "use_fireworks" | "fireworks_global">): boolean {
  return t.use_fireworks || t.fireworks_global;
}

/** 触发编排计划（v0.1.3 四-5，TC-RM-17）。 */
export interface ReminderPlan {
  /** 净化后的气泡文案（气泡无条件展示，特效只叠加不替代）。 */
  bubbleText: string;
  /** 是否额外放烟花。 */
  fireworks: boolean;
}

/**
 * 提醒触发编排（纯函数，v0.1.3 四-5 定案）：原 reminder-bridge 的 if/else
 * 二选一重构——气泡路径无条件执行（todo 派生文案构造 + 净化内聚于此），
 * `usesFireworks(t)` 时**额外**放烟花。原则：特效只叠加、不替代气泡。
 */
export function planReminderActions(t: ReminderTrigger, nowMs: number): ReminderPlan {
  const raw =
    t.kind === "todo"
      ? (todoReminderText(t.label, t.todo_due_ms, nowMs) ?? t.label)
      : t.label;
  return { bubbleText: sanitizeReminderText(raw), fireworks: usesFireworks(t) };
}

// ---- Rust 命令封装（非 Tauri 环境抛错/返回空，与 token-stats 风格一致） ----

function notInApp(): Error {
  return new Error(t("reminders.needApp"));
}

export async function fetchReminders(): Promise<ReminderRule[]> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ReminderRule[]>("reminders_list");
}

export async function upsertReminder(
  id: number | null,
  input: ReminderInput,
): Promise<ReminderRule> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ReminderRule>("reminders_upsert", { id, input });
}

export async function deleteReminder(id: number): Promise<void> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("reminders_delete", { id });
}

export async function fetchReminderStats(): Promise<ReminderStat[]> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ReminderStat[]>("reminders_stats");
}

export async function fetchFireworksGlobal(): Promise<boolean> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("reminders_get_fireworks_global");
}

export async function setFireworksGlobal(enabled: boolean): Promise<void> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("reminders_set_fireworks_global", { enabled });
}

export async function fetchPaused(): Promise<boolean> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("reminders_get_paused");
}

/** 手动触发（面板"试一试"）："fired" | "dedup" | "paused"。 */
export async function triggerReminderNow(id: number): Promise<string> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("reminders_trigger_now", { id });
}

/** v2 M4：snooze「稍后 10 分钟」（仅 notify；气泡按钮 invoke）。 */
export async function snoozeReminder(logId: number): Promise<void> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("reminders_snooze", { logId });
}

/** v2 M4：「跳过本次」（行操作；不触发不记录）。 */
export async function skipTaskOnce(id: number): Promise<void> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("tasks_skip_once", { id });
}

/** v2 M4：执行历史分页查询（倒序 50 条/页；reminderId 可选过滤）。 */
export async function fetchActionLogs(
  reminderId: number | null,
  page: number,
): Promise<ActionLogPage> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ActionLogPage>("action_logs_list", {
    reminderId,
    page: page ?? 1,
  });
}
