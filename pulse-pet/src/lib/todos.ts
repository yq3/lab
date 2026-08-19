/**
 * todos：M7 Todo 插件 TS 侧类型、纯函数与 Rust 命令封装（DESIGN §8，TC-TD 章节）。
 *
 * - 类型 `TodoItem` / `TodoInput` / `TodoCompleteResult` 与 Rust `todos.rs` 的
 *   serde 字段一一对应（snake_case，与 reminders.ts 同风格）。
 * - `validateTodoInput`：表单校验（与 Rust validate_todo_input 同口径）。
 * - `dueHasTime` / `composeDue` / `splitDue`：due_date 两种形态
 *   （"YYYY-MM-DD" / "YYYY-MM-DDTHH:MM"）与表单 date/time 输入的互转。
 * - `todoReminderText`：到点气泡文案"还有 X 分钟要完成「任务名」"
 *   （X = 触发时刻距 due 的剩余分钟数，TC-TD-03）。
 * - `parseTodoCompleted`：Rust `todo://completed` 事件 payload 解析
 *   （完成联动 waving + 气泡，TC-TD-04/05）。
 * - invoke 封装走动态 import + 运行时探测（vitest/node 下不可调用）。
 */

import { isTauriRuntime } from "./token-stats";

export { isTauriRuntime };

export interface TodoItem {
  id: number;
  title: string;
  notes: string | null;
  priority: number;
  due_date: string | null;
  remind_before_minutes: number;
  /** 保留字段 v1 不写入不读取（防重唯一来源在 reminders 侧，TC-TD-06）。 */
  remind_last_triggered_at: string | null;
  completed_at: string | null;
  sort_order: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface TodoInput {
  title: string;
  notes: string | null;
  priority: number;
  due_date: string | null;
  remind_before_minutes: number;
  sort_order: number;
  tags: string[];
}

export interface TodoCompleteResult {
  todo: TodoItem;
  completed_today: number;
  all_today_done: boolean;
  was_due_today: boolean;
}

export const MAX_TITLE_CHARS = 140;
export const MAX_REMIND_BEFORE_MINUTES = 10080;
export const MAX_TAGS = 20;

// ---- 校验（与 Rust validate_todo_input 同口径；返回错误文案，null = 通过） ----

export function validateTodoInput(input: TodoInput): string | null {
  const title = input.title.trim();
  if (!title) return "标题不能为空";
  if (title.length > MAX_TITLE_CHARS) return `标题超长（≤${MAX_TITLE_CHARS} 字符）`;
  if (input.priority < 0 || input.priority > 3) return "优先级应为 0-3";
  if (
    input.remind_before_minutes < 0 ||
    input.remind_before_minutes > MAX_REMIND_BEFORE_MINUTES
  ) {
    return `提前提醒非法（0-${MAX_REMIND_BEFORE_MINUTES} 分钟）`;
  }
  const due = input.due_date?.trim() ?? "";
  // 形状 + 范围（月/日/时分）与 Rust chrono 解析同口径
  const RE_DUE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(T([01]\d|2[0-3]):[0-5]\d)?$/;
  if (due && !RE_DUE.test(due)) {
    return "截止格式应为 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM";
  }
  const tags = input.tags.map((t) => t.trim()).filter(Boolean);
  if (tags.length > MAX_TAGS) return `标签数量超限（≤${MAX_TAGS} 个）`;
  if (tags.some((t) => t.length > 40)) return "单个标签 ≤40 字符";
  return null;
}

// ---- due_date 形态（纯函数） ----

/** due 是否带时间（派生提醒前提，TC-TD-03/08）。 */
export function dueHasTime(due: string | null): boolean {
  return !!due && due.includes("T");
}

/** date 输入 + 可选 time 输入 → 库格式 due（date 为空 → null）。 */
export function composeDue(date: string, time: string): string | null {
  const d = date.trim();
  if (!d) return null;
  const t = time.trim();
  return t ? `${d}T${t}` : d;
}

/** 库格式 due → 表单 date/time（null → 双空串）。 */
export function splitDue(due: string | null): { date: string; time: string } {
  if (!due) return { date: "", time: "" };
  const i = due.indexOf("T");
  if (i < 0) return { date: due, time: "" };
  return { date: due.slice(0, i), time: due.slice(i + 1) };
}

// ---- 到点气泡文案（TC-TD-03） ----

/**
 * "还有 X 分钟要完成「任务名」"：X = 触发时刻（nowMs）距 due（dueMs）的
 * 剩余分钟数（四舍五入，已过期 → 0）；due 缺失/非法 → null（回退纯 label）。
 */
export function todoReminderText(label: string, dueMs: number | null, nowMs: number): string | null {
  if (typeof dueMs !== "number" || !Number.isFinite(dueMs)) return null;
  const minutes = Math.round((dueMs - nowMs) / 60_000);
  const x = Math.max(0, minutes);
  return `还有 ${x} 分钟要完成「${label}」`;
}

// ---- 完成联动事件解析（TC-TD-04/05） ----

export interface TodoCompletedEvent {
  title: string;
  completed_today: number;
  all_today_done: boolean;
}

/** 解析 `todo://completed` payload；字段缺失/类型不对 → null（静默忽略）。 */
export function parseTodoCompleted(payload: unknown): TodoCompletedEvent | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as Record<string, unknown>;
  if (typeof p.title !== "string" || !p.title) return null;
  const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
  if (!num(p.completed_today)) return null;
  if (typeof p.all_today_done !== "boolean") return null;
  return {
    title: p.title,
    completed_today: p.completed_today,
    all_today_done: p.all_today_done,
  };
}

/** 完成气泡文案：全清 → "今日完成 N 项"（TC-TD-05）；否则 "干得漂亮 🎉"（TC-TD-04）。 */
export function celebrationText(e: TodoCompletedEvent): string {
  return e.all_today_done ? `今日完成 ${e.completed_today} 项` : "干得漂亮 🎉";
}

// ---- 展示辅助（纯函数） ----

const PRIORITY_LABELS = ["无", "低", "中", "高"];

export function priorityLabel(p: number): string {
  return PRIORITY_LABELS[p] ?? String(p);
}

/** RFC3339 → 本地展示（复用 reminders formatLogTime 风格，独立实现避免循环依赖）。 */
export function formatTodoTime(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** due 展示：带时间 → "2026-08-18 15:30"；纯日期 → "2026-08-18"。 */
export function formatDue(due: string | null): string {
  if (!due) return "无";
  return due.replace("T", " ");
}

// ---- Rust 命令封装（非 Tauri 环境抛错，与 reminders.ts 风格一致） ----

function notInApp(): Error {
  return new Error("Todo 需要在 PulsePet App（Tauri）内使用");
}

export async function fetchTodos(): Promise<TodoItem[]> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TodoItem[]>("todo_list");
}

export async function upsertTodo(id: number | null, input: TodoInput): Promise<TodoItem> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TodoItem>("todo_upsert", { id, input });
}

export async function deleteTodo(id: number): Promise<void> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("todo_delete", { id });
}

export async function completeTodo(id: number, completed: boolean): Promise<TodoCompleteResult> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TodoCompleteResult>("todo_complete", { id, completed });
}

export async function reorderTodos(orderedIds: number[]): Promise<TodoItem[]> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TodoItem[]>("todo_reorder", { orderedIds });
}

// ---- 插件 manifest（TC-TD-01：面板核对入口） ----

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  manifest_version: number;
  enabled: boolean;
  permissions: string[];
  panel_tab: { title?: unknown; icon?: unknown } | null;
  manifest_path: string;
}

export async function fetchPlugins(): Promise<PluginInfo[]> {
  if (!isTauriRuntime()) throw notInApp();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PluginInfo[]>("plugins_list");
}
