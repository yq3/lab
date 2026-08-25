import { describe, expect, it } from "vitest";
import {
  computeModelChips,
  computeStackedBars,
  TOOLTIP_ROW_ORDER,
  type ModelKey,
} from "./token-chart";
import type { TokenRow } from "./token-stats";

function gRow(
  day: string,
  model: string | null,
  v: { i?: number; o?: number; c?: number; r?: number },
): TokenRow {
  return {
    session_id: null,
    project_id: null,
    day,
    cost: 0,
    tokens_input: v.i ?? 0,
    tokens_output: v.o ?? 0,
    tokens_reasoning: v.r ?? 0,
    tokens_cache_read: v.c ?? 0,
    tokens_cache_write: 0,
    time_created: null,
    time_updated: null,
    model_id: model,
    project_name: null,
    title: null,
  };
}

const OPTS = { width: 200, height: 100, pad: 10 };

describe("computeStackedBars：三段堆叠柱（v2 M3 §3.5，TC-M3-05）", () => {
  const rows = [
    gRow("2026-08-24", "glm", { i: 30, o: 10, c: 60 }),
    gRow("2026-08-25", "glm", { i: 15, o: 5, c: 30 }),
    gRow("2026-08-25", "kimi", { i: 10, o: 10, c: 10 }),
  ];
  const all = new Set<ModelKey>(["glm", "kimi"]);

  it("三段自底向上 output → input → cache read；段序与叠放顺序钉住", () => {
    const bars = computeStackedBars(rows, all, OPTS);
    expect(bars.map((b) => b.label), "标签升序").toEqual(["2026-08-24", "2026-08-25"]);
    const d25 = bars[1];
    // 同日两模型聚合：i=25 o=15 c=40（勾选全量）
    expect(d25.input).toBe(25);
    expect(d25.output).toBe(15);
    expect(d25.cacheRead).toBe(40);
    expect(d25.total).toBe(80);
    // 段序：output 最底、input 中段、cacheRead 顶段
    expect(d25.segs.map((s) => s.key)).toEqual(["output", "input", "cacheRead"]);
    // 自底向上：output 贴基线（y + h = baseline），input 底接 output 顶，cache 顶接 input 顶
    const [out, input, cache] = d25.segs;
    const baseline = OPTS.height - OPTS.pad;
    expect(out.y + out.h).toBeCloseTo(baseline, 6);
    expect(input.y + input.h).toBeCloseTo(out.y, 6);
    expect(cache.y + cache.h).toBeCloseTo(input.y, 6);
    // 段高与值成比例（比例分母 = 全局最大柱 total=100，非柱内 total）
    expect(out.h).toBeCloseTo((15 / 100) * (OPTS.height - 2 * OPTS.pad), 6);
  });

  it("最大总量柱占满可用高度", () => {
    const bars = computeStackedBars(rows, all, OPTS);
    const d24 = bars[0]; // total 100 = 最大
    const top = d24.segs[2].y;
    expect(top, "顶段 y = pad（占满）").toBeCloseTo(OPTS.pad, 6);
  });

  it("勾选剔除后重新聚合（SCOPE E：仅柱图口径）", () => {
    const bars = computeStackedBars(rows, new Set<ModelKey>(["kimi"]), OPTS);
    expect(bars.length, "glm 剔除后 08-24 无数据").toBe(1);
    expect(bars[0].input).toBe(10);
    expect(bars[0].total).toBe(30);
  });

  it("selectedModels 空集 → 空数组（空态文案，不渲染柱）", () => {
    expect(computeStackedBars(rows, new Set<ModelKey>(), OPTS)).toEqual([]);
  });

  it("空行输入 → 空数组；全零行不产生 NaN", () => {
    expect(computeStackedBars([], all, OPTS)).toEqual([]);
    const bars = computeStackedBars([gRow("d", "glm", {})], all, OPTS);
    expect(bars).toHaveLength(1);
    expect(bars[0].total).toBe(0);
    for (const s of bars[0].segs) {
      expect(Number.isFinite(s.y)).toBe(true);
      expect(s.h).toBe(0);
    }
  });

  it("NULL model_id 行进入 null 桶，可单独勾选", () => {
    const rows2 = [
      gRow("d1", "glm", { i: 10 }),
      gRow("d1", null, { i: 5 }),
    ];
    const onlyUnknown = computeStackedBars(rows2, new Set<ModelKey>([null]), OPTS);
    expect(onlyUnknown[0].input).toBe(5);
    const both = computeStackedBars(rows2, new Set<ModelKey>([null, "glm"]), OPTS);
    expect(both[0].input).toBe(15);
  });

  it("N12 钉子：不传 agentFilter 时行为 = 不过滤（等价全量，M5 预留参数位）", () => {
    const withOpt = computeStackedBars(rows, all, { ...OPTS, agentFilter: undefined });
    const withoutOpt = computeStackedBars(rows, all, OPTS);
    expect(withOpt).toEqual(withoutOpt);
  });

  it("reasoning 不参与任何段（注入非零 reasoning 段高不变）", () => {
    const withR = [gRow("d", "glm", { i: 10, o: 10, c: 10, r: 999 })];
    const bars = computeStackedBars(withR, all, OPTS);
    expect(bars[0].total).toBe(30);
    expect(bars[0].segs.reduce((acc, s) => acc + s.value, 0)).toBe(30);
  });
});

describe("computeModelChips：模型 chip 清单（§3.5）", () => {
  it("distinct model_id 按总量降序；null 为未知模型桶", () => {
    const rows = [
      gRow("d1", "glm", { i: 100 }),
      gRow("d1", "kimi", { i: 50 }),
      gRow("d2", "glm", { o: 50 }),
      gRow("d2", null, { i: 1 }),
    ];
    expect(computeModelChips(rows)).toEqual([
      { key: "glm", total: 150 },
      { key: "kimi", total: 50 },
      { key: null, total: 1 },
    ]);
  });
});

describe("TOOLTIP_ROW_ORDER：tooltip 行序（用户 2026-08-25 裁定修订，TC-M3-05-2）", () => {
  it("三项数值行自上而下 cache read → input → output（与柱内堆叠顺序独立）", () => {
    expect(TOOLTIP_ROW_ORDER).toEqual(["cacheRead", "input", "output"]);
    // 与柱内堆叠序（自底向上 output → input → cache read，SCOPE D 不变）互为逆序——
    // 两序独立钉住，防一处改动波及另一处
    expect([...TOOLTIP_ROW_ORDER].reverse()).toEqual(["output", "input", "cacheRead"]);
  });
});
