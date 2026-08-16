import { describe, expect, it } from "vitest";
import {
  formatCost,
  formatTokens,
  localDayEndMs,
  localDayStartMs,
  rangeForPreset,
  sumRows,
  type TokenRow,
} from "./token-stats";

function row(overrides: Partial<TokenRow> = {}): TokenRow {
  return {
    session_id: "s",
    project_id: "p",
    day: null,
    cost: 0,
    tokens_input: 0,
    tokens_output: 0,
    tokens_reasoning: 0,
    tokens_cache_read: 0,
    tokens_cache_write: 0,
    time_created: null,
    time_updated: null,
    ...overrides,
  };
}

describe("formatTokens：Xk / M 格式化", () => {
  it("千位以下原样", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(910)).toBe("910");
  });
  it("千位以上 1 位小数 k", () => {
    expect(formatTokens(1000)).toBe("1.0k");
    expect(formatTokens(58263)).toBe("58.3k");
  });
  it("百万以上 M", () => {
    expect(formatTokens(1234567)).toBe("1.2M");
  });
});

describe("formatCost：USD 格式化（与 Rust format_cost_usd 口径一致）", () => {
  it("0 → $0；<0.01 用 4 位；其余 2 位", () => {
    expect(formatCost(0)).toBe("$0");
    expect(formatCost(0.0031)).toBe("$0.0031");
    expect(formatCost(0.0103)).toBe("$0.01");
    expect(formatCost(0.526)).toBe("$0.53");
    expect(formatCost(12.3)).toBe("$12.30");
  });
});

describe("rangeForPreset：时间跨度（含当天，TC-TK-08）", () => {
  it("7d = 今天 0 点往前 6 天起，至当前时刻（今天整天包含在内）", () => {
    // 2026-08-16 12:34:56.789 本地
    const now = new Date(2026, 7, 16, 12, 34, 56, 789);
    const { fromMs, toMs } = rangeForPreset("7d", now);
    expect(toMs).toBe(now.getTime());
    const from = new Date(fromMs);
    expect(from.getFullYear()).toBe(2026);
    expect(from.getMonth()).toBe(7);
    expect(from.getDate()).toBe(10); // 16 - 6 = 10（含当天共 7 天）
    expect(from.getHours()).toBe(0);
    expect(from.getMinutes()).toBe(0);
    expect(from.getSeconds()).toBe(0);
    expect(from.getMilliseconds()).toBe(0);
  });

  it("30d = 今天 0 点往前 29 天起", () => {
    const now = new Date(2026, 7, 16, 23, 59, 59);
    const { fromMs, toMs } = rangeForPreset("30d", now);
    expect(toMs).toBe(now.getTime());
    const from = new Date(fromMs);
    expect(from.getDate()).toBe(18); // 跨月由 Date 自行回退（7-18）
  });
});

describe("localDayStartMs / localDayEndMs：自定义跨度边界", () => {
  it("yyyy-mm-dd → 本地 [0 点, 23:59:59.999]", () => {
    const start = localDayStartMs("2026-08-01");
    const d = new Date(start);
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 7, 1]);
    expect([d.getHours(), d.getMinutes()]).toEqual([0, 0]);
    const end = localDayEndMs("2026-08-01");
    const e = new Date(end);
    expect([e.getHours(), e.getMinutes(), e.getSeconds(), e.getMilliseconds()]).toEqual([
      23, 59, 59, 999,
    ]);
    // 单日跨度 = end - start + 1ms 恰好一整天
    expect(end - start + 1).toBe(24 * 3600 * 1000);
  });
});

describe("sumRows：KPI 汇总", () => {
  it("累计 input/output/cache_read/cost", () => {
    const rows = [
      row({ cost: 0.1, tokens_input: 100, tokens_output: 10, tokens_cache_read: 5 }),
      row({ cost: 0.2, tokens_input: 200, tokens_output: 20, tokens_cache_read: 6 }),
      row({ cost: 0.3, tokens_input: 300, tokens_output: 30, tokens_cache_write: 7 }),
    ];
    const kpi = sumRows(rows);
    expect(kpi.input).toBe(600);
    expect(kpi.output).toBe(60);
    expect(kpi.cacheRead).toBe(11);
    expect(kpi.cost).toBeCloseTo(0.6, 9);
  });

  it("空列表全 0", () => {
    expect(sumRows([])).toEqual({ input: 0, output: 0, cacheRead: 0, cost: 0 });
  });
});
