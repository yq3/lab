/**
 * token-stats：Rust token_stats 命令的 TS 侧封装（DESIGN §4.2/§4.3，TC-TK-01~09）。
 *
 * - 类型 `TokenRow` 与 Rust 侧 `token_stats.rs` 的 serde 序列化字段一一对应。
 * - Rust 命令错误序列化为 `"code: message"`，`parseStatsError` 拆出结构化 code：
 *   no-database（数据库未运行/未初始化）/ legacy-storage（请升级 opencode）/
 *   schema-mismatch（请升级 pulse-pet）/ query（其它）。
 * - 纯函数（format / range / sumRows 族）可在 vitest(node) 下直接单测。
 */

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
    throw new StatsError("query", "Token 统计需要在 PulsePet App（Tauri）内查看");
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

/** 调 `token_stats_current_session`（TC-TK-10/12：无记录返回 null）。 */
export async function fetchCurrentSession(
  sessionId: string,
): Promise<TokenRow | null> {
  if (!isTauriRuntime()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<TokenRow | null>("token_stats_current_session", {
      sessionId,
    });
  } catch {
    return null; // 查询失败视同无记录（不出气泡）
  }
}

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

// ---- 时间跨度（TC-TK-08：边界含当天） ----

export type RangePreset = "7d" | "30d";

export interface TimeRange {
  fromMs: number;
  toMs: number;
}

/** 7d/30d：from = 本地今天 0 点往前 N-1 天（含当天共 N 天），to = 当前时刻。 */
export function rangeForPreset(preset: RangePreset, now = new Date()): TimeRange {
  const days = preset === "7d" ? 7 : 30;
  const toMs = now.getTime();
  const from = new Date(now);
  from.setHours(0, 0, 0, 0);
  from.setDate(from.getDate() - (days - 1));
  return { fromMs: from.getTime(), toMs };
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
  input: number;
  output: number;
  cacheRead: number;
  cost: number;
}

/** 跨度内总 input/output/cache_read/cost（TC-TK-09 ①）。 */
export function sumRows(rows: TokenRow[]): KpiTotals {
  return rows.reduce<KpiTotals>(
    (acc, r) => ({
      input: acc.input + r.tokens_input,
      output: acc.output + r.tokens_output,
      cacheRead: acc.cacheRead + r.tokens_cache_read,
      cost: acc.cost + r.cost,
    }),
    { input: 0, output: 0, cacheRead: 0, cost: 0 },
  );
}
