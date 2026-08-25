/**
 * pet/todayToken：今日 token 的 pet 桥层 30s 缓存（v2 M3 §3.4，R3/TC-M3-10-7）。
 *
 * 悬停卡（HoverToday）与右键菜单（PetMenu）共享 `token_stats_today` 单一
 * 数据源——高频悬停下最坏 2 次查询/分钟。菜单信息项文案由既有 `formatTokens`
 * 生成（与 idle 追加段 Rust `format_tokens_k` 同口径，N11）。
 */

import { formatTokens, fetchTodayStats, type TodayStats } from "../lib/token-stats";
import type { TodayTokenState } from "../lib/pet-menu";

/** 缓存新鲜度窗口（§3.4：30s）。 */
export const TODAY_CACHE_MS = 30_000;

let cache: { at: number; data: TodayStats } | null = null;

/** 清空缓存（测试用）。 */
export function resetTodayCache(): void {
  cache = null;
}

/** 今日聚合（30s 缓存内直接复用；错误结构化透传——菜单/卡片错误态来源）。 */
export async function fetchTodayStatsCached(now = Date.now()): Promise<TodayStats> {
  if (cache && now - cache.at < TODAY_CACHE_MS) {
    return cache.data;
  }
  const data = await fetchTodayStats();
  cache = { at: now, data };
  return data;
}

/** TodayStats → 菜单信息项三态文案（total = in+out+cache_read，reasoning 不计）。 */
export function todayTokenStateOf(s: TodayStats): TodayTokenState {
  return {
    status: "ok",
    text: formatTokens(s.input + s.output + s.cache_read),
  };
}
