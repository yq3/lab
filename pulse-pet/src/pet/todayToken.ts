/**
 * pet/todayToken：今日 token 的 pet 桥层 30s 缓存（v2 M3 §3.4，TC-M3-11-4）。
 *
 * 右键菜单（PetMenu「今日 token」三态信息项）消费 `token_stats_today` 单一
 * 数据源；30s 缓存防高频开关菜单打查询。（主动层悬停卡已按用户 2026-08-25
 * 裁定移除，缓存改由菜单独享。）菜单信息项文案由既有 `formatTokens` 生成
 *（与 idle 追加段 Rust `format_tokens_k` 同口径，N11）。
 */

import { formatTokens, fetchTodayStats, type TodayStats } from "../lib/token-stats";
import { todayByAgentText, type TodayTokenState } from "../lib/pet-menu";

/** 缓存新鲜度窗口（§3.4：30s）。 */
export const TODAY_CACHE_MS = 30_000;

let cache: { at: number; data: TodayStats } | null = null;

/** 今日聚合（30s 缓存内直接复用；错误结构化透传——菜单/卡片错误态来源）。 */
export async function fetchTodayStatsCached(now = Date.now()): Promise<TodayStats> {
  if (cache && now - cache.at < TODAY_CACHE_MS) {
    return cache.data;
  }
  // v2 M5：双源合计（opencode + CC）；pet 侧静默消费数值、不呈现 degraded
  // （宠物不打扰原则——C1/N-4 定案：degraded 横幅仅 panel）
  const { today } = await fetchTodayStats();
  cache = { at: now, data: today };
  return today;
}

/**
 * TodayStats → 菜单信息项三态文案（total = in+out+cache_read，reasoning 不计）。
 * v2 M6（V2-DESIGN §6.2，TC-M6-04）：+agent 分布行 byAgent（双 agent 有数据
 * 才显示；呈现面随 M3 悬停卡移除落在本菜单信息项子行——任务裁定点）。
 */
export function todayTokenStateOf(s: TodayStats): TodayTokenState {
  const byAgent = todayByAgentText(s) ?? undefined;
  return {
    status: "ok",
    text: formatTokens(s.input + s.output + s.cache_read),
    ...(byAgent ? { byAgent } : {}),
  };
}
