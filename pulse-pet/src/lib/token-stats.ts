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
  /** v2 M5：来源 agent（`opencode` / `claude-code`）。 */
  agent: string;
}

/** v2 M5：agent 常量（与 Rust token_stats.rs 一致）。 */
export const AGENT_OPENCODE = "opencode";
export const AGENT_CLAUDE_CODE = "claude-code";

/**
 * v2 M6（V2-DESIGN §6.2）：agent 短名（opencode→oc / claude-code→cc /
 * task→task；未知 agent 原名兜底）。气泡徽标 `[oc]` 与今日分布行 `oc 39M`
 * 共用；技术名约定，i18n 不翻译。
 */
export function agentShortName(agent: string): string {
  switch (agent) {
    case AGENT_OPENCODE:
      return "oc";
    case AGENT_CLAUDE_CODE:
      return "cc";
    case "task":
      return "task";
    default:
      return agent;
  }
}

/** v2 M6：by_agent 行类型（与 Rust token_stats.rs AgentTodayTotal 一致）。 */
export interface AgentTodayTotal {
  agent: string;
  total: number;
}

/** v2 M3：今日 token 聚合（token_stats_today；三层快捷查看共享单一数据源）。 */
export interface TodayStats {
  input: number;
  output: number;
  cache_read: number;
  cost: number;
  /**
   * v2 M6（V2-DESIGN §6.2）：agent 分布行（有数据的 agent 按 total 降序；
   * total = 今日总量同口径 in+out+cacheRead、不含 reasoning、mock 过滤）。
   * 可选——旧序列化数据/测试夹具无此字段。
   */
  by_agent?: AgentTodayTotal[];
}

/**
 * v2 M5（C1/N-4）：双源查询返回体包装——`degraded` 仅在 opencode 源报错而
 * CC 源有数据时为非空（原始错误 "code: message"）；CC 缺席时 rows 与 M3
 * 原样一致、degraded=null（单源场景行为不变）。degraded 横幅仅 panel；
 * pet 侧（菜单/idle 追加段）静默消费合计数值、不呈现 degraded。
 */
export interface TokenQueryResult {
  rows: TokenRow[];
  degraded: string | null;
}

/** v2 M5：今日聚合返回体包装（语义同上）。 */
export interface TodayQueryResult {
  today: TodayStats;
  degraded: string | null;
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

/**
 * 调 `token_stats_query`（from/to 毫秒；group_by 维度由前端传，TC-TK-07）。
 * v2 M5：返回体为 `{rows, degraded}` 包装（C1/N-4 承载定案）。
 */
export async function fetchTokenRows(
  fromMs: number,
  toMs: number,
  groupBy: GroupBy,
): Promise<TokenQueryResult> {
  if (!isTauriRuntime()) {
    throw new StatsError("query", t("token.needApp"));
  }
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<TokenQueryResult>("token_stats_query", {
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
 * mock 过滤、reasoning 不计均在 Rust 侧）。v2 M5：双源合计，返回体
 * `{today, degraded}`；pet 侧消费方只取 today（静默呈现 CC-only 数值、
 * 不呈现 degraded——宠物不打扰原则）。错误经 parseStatsError 结构化透传
 * （no-database 等，菜单「—」态的来源；双源全缺才走错误路径）。
 */
export async function fetchTodayStats(): Promise<TodayQueryResult> {
  if (!isTauriRuntime()) {
    throw new StatsError("query", t("token.needApp"));
  }
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<TodayQueryResult>("token_stats_today");
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

/**
 * §十二 F2（2026-08-28）：查询窗口内的本地日标签全列表（含两端天）——
 * day 维度 ≤7 天窗口「补零柱」的数据源（token-chart computeStackedBars 的
 * expectedLabels）。按日期分量步进（不按 86400e3 毫秒加法，DST 安全）。
 */
export function dayLabelsBetween(fromMs: number, toMs: number): string[] {
  const out: string[] = [];
  const end = new Date(toMs);
  end.setHours(0, 0, 0, 0);
  const endMs = end.getTime();
  const cur = new Date(fromMs);
  cur.setHours(0, 0, 0, 0);
  while (cur.getTime() <= endMs && out.length < 400) {
    out.push(localDateStr(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return out;
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
