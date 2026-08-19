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

export { isTauriRuntime };

/** 面板可创建的 kind（todo 由 M7 插件派生，不在表单可选）。 */
export type ReminderKind = "hydration" | "rest" | "custom";

/** Rust 侧允许的全部 kind（读取/展示用）。 */
export type ReminderKindAll = ReminderKind | "todo";

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
}

/** CRUD 入参（与 Rust `ReminderInput` 对应；kind=todo 仅出现在编辑派生规则时）。 */
export interface ReminderInput {
  kind: ReminderKindAll;
  label: string;
  interval_minutes: number;
  start_time: string | null;
  end_time: string | null;
  enabled: boolean;
  use_fireworks: boolean;
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
    return checkAbs(input.start_time, "起始") ?? checkAbs(input.end_time, "结束");
  }
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
  const startErr = checkHhmm(input.start_time, "起始");
  if (startErr) return startErr;
  const endErr = checkHhmm(input.end_time, "结束");
  if (endErr) return endErr;
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
