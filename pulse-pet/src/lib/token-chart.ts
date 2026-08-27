/**
 * token-chart：堆叠柱状图纯计算（v2 M3 §3.5，TC-M3-05；取代 v1 computeBars/
 * pieSlices——柱图/饼图唯一消费方均在 Token 页，随饼图砍除一并清退，R6）。
 *
 * 输入 day/week 聚合行（含 model_id）+ 勾选模型集合，输出每日一柱、柱内三段
 * 自底向上 **output → input → cache read**（SCOPE D 裁定；reasoning 不参与
 * 任何汇总口径）。与 React 组件解耦便于 vitest(node) 单测。
 */

import type { TokenRow } from "./token-stats";

/** 模型勾选键：model_id；NULL 模型行以 null 为键（chip 显示「未知模型」）。 */
export type ModelKey = string | null;

/** 柱内一段（自底向上顺序：output → input → cacheRead）。 */
export interface StackedSegment {
  /** 段语义键（渲染色与图例共用：--chart-output/input/cache）。 */
  key: "output" | "input" | "cacheRead";
  /** 数值（tooltip/占比用）。 */
  value: number;
  /** 段顶 y 坐标（SVG 坐标系，值越大越靠上）。 */
  y: number;
  /** 段高（0 值段高度 0）。 */
  h: number;
}

/** 一根堆叠柱（一天）。 */
export interface StackedBar {
  /** 分组标签（day=`2026-08-16` / week=`2026-W33`）。 */
  label: string;
  /** 三值（勾选剔除后聚合；tooltip/图例用）。 */
  output: number;
  input: number;
  cacheRead: number;
  /** 柱总量 = output + input + cacheRead。 */
  total: number;
  x: number;
  w: number;
  /** 三段自底向上排列（segs[0] = 最底段 output）。 */
  segs: StackedSegment[];
}

export interface StackedBarOptions {
  width: number;
  height: number;
  pad: number;
  /** 柱宽占每格宽度的比例（0-1，默认 0.6）。 */
  fill?: number;
  /**
   * **M5（V2-DESIGN §5.6，TC-M5-04）**：agent 筛选——作用域仅柱图（与模型
   * 筛选一致，M3 E 口径）；「不传 = 不过滤」（等价全量）由钉子单测守住。
   * 传入即按 `row.agent ∈ agentFilter` 过滤后聚合（勾选剔除）。
   */
  agentFilter?: ReadonlySet<string>;
}

/**
 * 堆叠柱计算：
 * 1. 行按 `row.model_id`（null 为「未知模型」桶）过滤——未勾选的模型剔除后聚合；
 *    M5：行再按 agentFilter 过滤（未勾选的 agent 剔除，作用域仅柱图）；
 * 2. 按行 day 标签分组 SUM（多模型行合并为一柱）；
 * 3. 柱按标签升序排列；柱高与最大 total 成比例，三段自底向上 output → input
 *    → cache read；全零/空输入不产生 NaN。
 */
export function computeStackedBars(
  rows: TokenRow[],
  selectedModels: ReadonlySet<ModelKey>,
  opts: StackedBarOptions,
): StackedBar[] {
  const { width, height, pad } = opts;
  const fill = opts.fill ?? 0.6;
  // 勾选剔除（模型筛选 + M5 agent 筛选；不传 agentFilter = 不过滤，N12）
  const kept = rows.filter((r) => {
    if (opts.agentFilter && !opts.agentFilter.has(r.agent)) return false;
    return selectedModels.has(r.model_id ?? null);
  });
  // 按 day 标签聚合（null 标签归 "—"，正常 grouped 行恒有 day）
  const map = new Map<string, { output: number; input: number; cacheRead: number }>();
  for (const r of kept) {
    const k = r.day ?? "—";
    const cur = map.get(k) ?? { output: 0, input: 0, cacheRead: 0 };
    cur.output += r.tokens_output;
    cur.input += r.tokens_input;
    cur.cacheRead += r.tokens_cache_read;
    map.set(k, cur);
  }
  const entries = [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const n = entries.length;
  if (n === 0) return [];
  const plotW = Math.max(width - 2 * pad, 0);
  const plotH = Math.max(height - 2 * pad, 0);
  const max = Math.max(...entries.map(([, v]) => v.output + v.input + v.cacheRead), 0);
  const slot = plotW / n;
  const barW = slot * fill;
  const baseline = pad + plotH;
  return entries.map(([label, v], i) => {
    const total = v.output + v.input + v.cacheRead;
    const hOf = (x: number) => (max > 0 ? (Math.max(x, 0) / max) * plotH : 0);
    const hOut = hOf(v.output);
    const hIn = hOf(v.input);
    const hCache = hOf(v.cacheRead);
    // 自底向上：output 贴基线 → input 叠上 → cache read 顶段
    const yOut = baseline - hOut;
    const yIn = yOut - hIn;
    const yCache = yIn - hCache;
    return {
      label,
      output: v.output,
      input: v.input,
      cacheRead: v.cacheRead,
      total,
      x: pad + i * slot + (slot - barW) / 2,
      w: barW,
      segs: [
        { key: "output", value: v.output, y: yOut, h: hOut },
        { key: "input", value: v.input, y: yIn, h: hIn },
        { key: "cacheRead", value: v.cacheRead, y: yCache, h: hCache },
      ],
    };
  });
}

/** 模型 chip 列表项：跨度内 distinct model_id 按总量（in+out+cache_read）降序。 */
export interface ModelChip {
  key: ModelKey;
  /** 勾选状态由调用方持有，这里只出清单。 */
  total: number;
}

/**
 * tooltip 三项数值行的显示顺序（自上而下）：**cache read → input → output**
 * （用户 2026-08-25 裁定修订，TC-M3-05-2）。与柱内三段堆叠顺序（自底向上
 * output → input → cache read，SCOPE D 不变）**独立**——两序互为逆序。
 */
export const TOOLTIP_ROW_ORDER = ["cacheRead", "input", "output"] as const;

/** 聚合行 → 模型 chip 清单（§3.5：distinct model_id、按总量降序、默认全勾）。 */
export function computeModelChips(
  rows: TokenRow[],
  /**
   * **M5 R2（TC-M5-04-2）**：agent 维度联动收窄——选中具体 agent 时传单元素集，
   * chip 清单收窄为该 agent 有数据的模型；「全部」不传（双源模型并集）或传
   * 全量集（等价）。语义与 `computeStackedBars.agentFilter` 对齐（N12：不传 =
   * 不过滤）。
   */
  agentFilter?: ReadonlySet<string>,
): ModelChip[] {
  const map = new Map<ModelKey, number>();
  for (const r of rows) {
    if (agentFilter && !agentFilter.has(r.agent)) continue;
    const k: ModelKey = r.model_id ?? null;
    map.set(k, (map.get(k) ?? 0) + r.tokens_input + r.tokens_output + r.tokens_cache_read);
  }
  return [...map.entries()]
    .map(([key, total]) => ({ key, total }))
    .sort((a, b) => b.total - a.total);
}

/**
 * 聚合行 → 有数据的 agent 清单（M5 R2，TC-M5-04-1：agent tab 选项来源——
 * 无数据的 agent 不渲染；distinct + 字典序稳定排列）。「全部」项由组件层
 * 恒显并列补上（纯数据函数不含 UI 哨兵）。
 */
export function agentsWithRows(rows: TokenRow[]): string[] {
  const set = new Set<string>();
  for (const r of rows) {
    if (r.agent) set.add(r.agent);
  }
  return [...set].sort();
}
