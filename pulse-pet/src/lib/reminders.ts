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
  created_at: string;
}

/** CRUD 入参（与 Rust `ReminderInput` 对应）。 */
export interface ReminderInput {
  kind: ReminderKind;
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

const KIND_LABELS: Record<string, string> = {
  hydration: "喝水",
  rest: "休息",
  custom: "自定义",
  todo: "待办",
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
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

export function validateReminderInput(input: ReminderInput): string | null {
  const label = input.label.trim();
  if (!label) return "文案不能为空";
  if (label.length > 140) return "文案超长（≤140 字符）";
  if (!["hydration", "rest", "custom"].includes(input.kind)) {
    return `类型非法：${input.kind}`;
  }
  // 面板只创建 hydration/rest/custom（todo 由 M7 插件派生，Rust 侧另校验）
  if (input.interval_minutes < 1 || input.interval_minutes > MAX_INTERVAL_MINUTES) {
    return `间隔非法（1-${MAX_INTERVAL_MINUTES} 分钟）`;
  }
  const checkHhmm = (s: string | null | undefined, what: string): string | null => {
    if (!s) return null;
    const m = /^(\d{1,2}):(\d{2})$/.exec(s);
    if (!m) return `${what}时间格式应为 HH:MM`;
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) return `${what}时间越界（00:00-23:59）`;
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

export function formatWindow(start: string | null, end: string | null): string {
  if (!start && !end) return "全天";
  if (!end) return `${start} 起`;
  if (!start) return `至 ${end}`;
  return `${start}-${end}${isCrossMidnight(start, end) ? "（跨午夜）" : ""}`;
}

export function formatInterval(minutes: number): string {
  if (minutes === 0) return "单次";
  if (minutes % 60 === 0) return `每 ${minutes / 60} 小时`;
  return `每 ${minutes} 分钟`;
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
  };
}

/** 烟花判定：单条 use_fireworks 覆盖（升级）全局开关（TC-RM-11，OR 语义）。 */
export function usesFireworks(t: Pick<ReminderTrigger, "use_fireworks" | "fireworks_global">): boolean {
  return t.use_fireworks || t.fireworks_global;
}

// ---- Rust 命令封装（非 Tauri 环境抛错/返回空，与 token-stats 风格一致） ----

function notInApp(): Error {
  return new Error("提醒配置需要在 PulsePet App（Tauri）内使用");
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
