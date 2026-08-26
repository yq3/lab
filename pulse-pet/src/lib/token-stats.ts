/**
 * token-stats：Rust token_stats 命令的 TS 侧封装（DESIGN §4.2/§4.3，TC-TK-01~09）。
 *
 * - 类型 `TokenRow` 与 Rust 侧 `token_stats.rs` 的 serde 序列化字段一一对应。
 * - Rust 命令错误序列化为 `"code: message"`，`parseStatsError` 拆出结构化 code：
 *   no-database（数据库未运行/未初始化）/ legacy-storage（请升级 opencode）/
 *   schema-mismatch（请升级 pulse-pet）/ query（其它）。
 * - 纯函数（format / range / sumRows 族）可在 vitest(node) 下直接单测。
 */

import { t } from "./i18n";

export interface TokenRow {
  session_id: string | null;
  project_id: string | null;
  /** 分组标签：day=`2026-08-16`，week=`2026-W33`；session/range 为 null。 */
  day: string | null;
  cost: number;
  tokens_input: number;
  tokens_output: number;
  tokens_reasoning: number;
  tokens_cache_read: number;
  tokens_cache_write: number;
  time_created: number | null;
  time_updated: number | null;
  /** v2 M3：`json_extract(model,'$.id')`（仅按 id 归并）；NULL/损坏 → null（「未知模型」合并）。 */
  model_id: string | null;
  /** v2 M3：basename(project.worktree)；global（"/"）或 JOIN 未命中 → null（前端回退标签）。 */
  project_name: string | null;
  /** v2 M3：会话标题（by-session 独有；聚合行 null）。 */
  title: string | null;
}

/** v2 M3：今日 token 聚合（token_stats_today；三层快捷查看共享单一数据源）。 */
export interface TodayStats {
  input: number;
  output: number;
  cache_read: number;
  cost: number;
}

export type GroupBy = "session" | "day" | "week" | "range";

export type StatsErrorCode =
  | "no-database"
  | "legacy-storage"
  | "schema-mismatch"
  | "query";

const CODES: StatsErrorCode[] = [
  "no-database",
  "legacy-storage",
  "schema-mismatch",
  "query",
];

export class StatsError extends Error {
  readonly code: StatsErrorCode;
  constructor(code: StatsErrorCode, message: string) {
    super(message);
    this.name = "StatsError";
    this.code = code;
  }
}

/** 把 Rust 侧 `"code: message"` 错误串拆成结构化错误；未知格式归入 query。 */
export function parseStatsError(raw: unknown): StatsError {
  const text =
    typeof raw === "string"
      ? raw
      : raw instanceof Error
        ? raw.message
        : String(raw ?? "");
  const sep = text.indexOf(":");
  const head = sep >= 0 ? text.slice(0, sep) : text;
  const rest = sep >= 0 ? text.slice(sep + 1).trim() : text;
  const code = (CODES as string[]).includes(head)
    ? (head as StatsErrorCode)
    : "query";
  return new StatsError(code, rest || text);
}

/** 是否在 Tauri 运行时内（非 Tauri 环境如浏览器 dev / vitest 直接判定不可用）。 */
export function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as unknown as Record<string, unknown>)
  );
}

/** 调 `token_stats_query`（from/to 毫秒；group_by 维度由前端传，TC-TK-07）。 */
export async function fetchTokenRows(
  fromMs: number,
  toMs: number,
  groupBy: GroupBy,
): Promise<TokenRow[]> {
  if (!isTauriRuntime()) {
    throw new StatsError("query", t("token.needApp"));
  }
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<TokenRow[]>("token_stats_query", {
      fromMs,
      toMs,
      groupBy,
    });
  } catch (e) {
    throw parseStatsError(e);
  }
}

/**
 * v2 M3（§3.2/§3.4）：今日 token 聚合（`token_stats_today`——from=本地今天 0 点、
 * mock 过滤、reasoning 不计均在 Rust 侧）。错误经 parseStatsError 结构化透传
 * （no-database 等，悬停卡「暂无数据」/菜单「—」态的来源）。
 */
export async function fetchTodayStats(): Promise<TodayStats> {
  if (!isTauriRuntime()) {
    throw new StatsError("query", t("token.needApp"));
  }
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<TodayStats>("token_stats_today");
  } catch (e) {
    throw parseStatsError(e);
  }
}

// 注：M3 曾有 `fetchCurrentSession`（token_stats_current_session 的 TS 封装），前端无
// 调用方（当前会话气泡汇报由 Rust 侧 idle hook 直接下发），按 M4 清偿 P3-② 删除；
// Rust command 按 spec §4.2 保留注册，供后续里程碑接入。

// ---- 数字格式化（与 Rust format_tokens_k / format_cost_usd 口径一致） ----

export function formatTokens(n: number): string {
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (a >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function formatCost(usd: number): string {
  if (usd <= 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

// ---- 时间跨度（TC-TK-08：边界含当天；v2 M3 增 today preset） ----

export type RangePreset = "today" | "7d" | "30d";

export interface TimeRange {
  fromMs: number;
  toMs: number;
}

/**
 * today：from = 本地今天 0 点、to = 当前时刻（§3.3）；
 * 7d/30d：from = 本地今天 0 点往前 N-1 天（含当天共 N 天），to = 当前时刻。
 */
export function rangeForPreset(preset: RangePreset, now = new Date()): TimeRange {
  const toMs = now.getTime();
  const from = new Date(now);
  from.setHours(0, 0, 0, 0);
  if (preset !== "today") {
    const days = preset === "7d" ? 7 : 30;
    from.setDate(from.getDate() - (days - 1));
  }
  return { fromMs: from.getTime(), toMs };
}

/**
 * v2 M4 R3（tester R2 P2 修复）：查询窗口解析——**每次调用以传入 now 重算**。
 *
 * - preset（today/7d/30d）：to = 调用时刻（面板窗口 hide/show 不重挂载组件，
 *   若 range 在挂载时 useMemo 定格，活跃会话 time_updated 越过定格 toMs 后
 *   被整体排除且 Refresh 不可追回——TokenStats 的 load/focus 刷新每次调用
 *   本函数，窗口随之前进）；
 * - custom：用户指定区间语义不变——from/to 恒为所选日的整天边界（含当天），
 *   与调用时刻无关；从/至倒填经 min/max 归位。
 */
export function resolveQueryRange(
  preset: RangePreset | "custom",
  fromStr: string,
  toStr: string,
  now = new Date(),
): TimeRange {
  if (preset === "custom") {
    const fromMs = Math.min(localDayStartMs(fromStr), localDayStartMs(toStr));
    const toMs = Math.max(localDayEndMs(fromStr), localDayEndMs(toStr));
    return { fromMs, toMs };
  }
  return rangeForPreset(preset, now);
}

/** `yyyy-mm-dd` → 本地当天 0 点毫秒。 */
export function localDayStartMs(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1, 0, 0, 0, 0).getTime();
}

/** `yyyy-mm-dd` → 本地当天 23:59:59.999 毫秒（自定义跨度「含当天」）。 */
export function localDayEndMs(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1, 23, 59, 59, 999).getTime();
}

/** 今天 `yyyy-mm-dd`（本地）。 */
export function localDateStr(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// ---- KPI 汇总 ----

export interface KpiTotals {
  /** v2 M3（§3.5）：总量 = input + output + cache_read（reasoning 不计，SCOPE D）。 */
  total: number;
  input: number;
  output: number;
  cacheRead: number;
  cost: number;
}

/** 跨度内 total/input/output/cache_read/cost（TC-TK-09 ①；M3 增 total）。 */
export function sumRows(rows: TokenRow[]): KpiTotals {
  return rows.reduce<KpiTotals>(
    (acc, r) => ({
      total: acc.total + r.tokens_input + r.tokens_output + r.tokens_cache_read,
      input: acc.input + r.tokens_input,
      output: acc.output + r.tokens_output,
      cacheRead: acc.cacheRead + r.tokens_cache_read,
      cost: acc.cost + r.cost,
    }),
    { total: 0, input: 0, output: 0, cacheRead: 0, cost: 0 },
  );
}
