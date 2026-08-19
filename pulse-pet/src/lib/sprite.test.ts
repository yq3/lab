import { describe, expect, it } from "vitest";

import {
  ATLAS_ROW_FOR_STATE,
  PETDEX_ROWS,
  SpriteAnimator,
  frameIndexAt,
  rowForState,
} from "./sprite";
import { ALL_STATES, type NormalizedState } from "./state";

/**
 * M5 前端 sprite 帧时长表 + 9 状态映射（DESIGN §6.2，TC-SP-04/07/08）。
 * 帧时长数据照抄 petdex `sprite.zig`（crafter-station/petdex，
 * packages/petdex-desktop-native/src/sprite.zig，2026-08 抓取）。
 */

describe("PETDEX_ROWS 帧时长表（照抄 petdex sprite.zig）", () => {
  it("idle：6 帧不规则眨眼 [280,110,110,140,140,320]，行 0", () => {
    const idle = PETDEX_ROWS.idle;
    expect(idle.row).toBe(0);
    expect(idle.frames.map((f) => f.durMs)).toEqual([280, 110, 110, 140, 140, 320]);
    expect(idle.frames.map((f) => f.col)).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("running-right / running-left：uniform(8, 120, 220)，行 1/2", () => {
    for (const [name, row] of [
      ["running-right", 1],
      ["running-left", 2],
    ] as const) {
      const def = PETDEX_ROWS[name];
      expect(def.row).toBe(row);
      expect(def.frames).toHaveLength(8);
      expect(def.frames.slice(0, 7).every((f) => f.durMs === 120)).toBe(true);
      expect(def.frames[7].durMs).toBe(220);
      expect(def.frames.map((f) => f.col)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    }
  });

  it("waving uniform(4,140,280) / jumping uniform(5,140,280)，行 3/4", () => {
    expect(PETDEX_ROWS.waving.row).toBe(3);
    expect(PETDEX_ROWS.waving.frames.map((f) => f.durMs)).toEqual([140, 140, 140, 280]);
    expect(PETDEX_ROWS.jumping.row).toBe(4);
    expect(PETDEX_ROWS.jumping.frames.map((f) => f.durMs)).toEqual([140, 140, 140, 140, 280]);
  });

  it("failed uniform(8,140,240) / waiting uniform(6,150,260) / running uniform(6,120,220) / review uniform(6,150,280)", () => {
    expect(PETDEX_ROWS.failed.row).toBe(5);
    expect(PETDEX_ROWS.failed.frames.map((f) => f.durMs)).toEqual([
      140, 140, 140, 140, 140, 140, 140, 240,
    ]);
    expect(PETDEX_ROWS.waiting.row).toBe(6);
    expect(PETDEX_ROWS.waiting.frames.map((f) => f.durMs)).toEqual([150, 150, 150, 150, 150, 260]);
    expect(PETDEX_ROWS.running.row).toBe(7);
    expect(PETDEX_ROWS.running.frames.map((f) => f.durMs)).toEqual([120, 120, 120, 120, 120, 220]);
    expect(PETDEX_ROWS.review.row).toBe(8);
    expect(PETDEX_ROWS.review.frames.map((f) => f.durMs)).toEqual([150, 150, 150, 150, 150, 280]);
  });

  it("9 行行号 0-8 各占一行（无冲突）", () => {
    const rows = Object.values(PETDEX_ROWS).map((d) => d.row);
    expect(new Set(rows).size).toBe(9);
    expect([...rows].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
  });
});

describe("9 状态映射（TC-SP-07 / TC-SP-08）", () => {
  it("8 种归一化状态 → DESIGN §6.2 映射表", () => {
    const expected: Record<NormalizedState, number> = {
      idle: 0,
      working: 7,
      thinking: 6,
      editing: 1,
      testing: 2,
      "waiting-permission": 8,
      error: 5,
      success: 3,
    };
    for (const s of ALL_STATES) {
      expect(rowForState(s).row).toBe(expected[s]);
    }
  });

  it("jumping（行 4）无驱动事件，不被任何状态引用（TC-SP-08）", () => {
    for (const s of ALL_STATES) {
      expect(rowForState(s).row).not.toBe(4);
    }
    // 映射表也不含 jumping 键
    expect(Object.values(ATLAS_ROW_FOR_STATE)).not.toContain("jumping");
  });
});

describe("frameIndexAt：帧时长推进 + 循环", () => {
  it("idle 不规则序列边界", () => {
    const def = PETDEX_ROWS.idle; // 累计 [280,390,500,640,780,1100]
    expect(frameIndexAt(def, 0)).toBe(0);
    expect(frameIndexAt(def, 279)).toBe(0);
    expect(frameIndexAt(def, 280)).toBe(1); // 110ms 短帧（眨眼）
    expect(frameIndexAt(def, 390)).toBe(2);
    expect(frameIndexAt(def, 500)).toBe(3);
    expect(frameIndexAt(def, 640)).toBe(4);
    expect(frameIndexAt(def, 780)).toBe(5); // 320ms 长帧
    expect(frameIndexAt(def, 1100)).toBe(0); // 循环回第一帧
    expect(frameIndexAt(def, 1100 + 280)).toBe(1);
  });

  it("running uniform 序列边界与循环", () => {
    const def = PETDEX_ROWS.running; // [120×5, 220] 总 820
    expect(frameIndexAt(def, 0)).toBe(0);
    expect(frameIndexAt(def, 120)).toBe(1);
    expect(frameIndexAt(def, 600)).toBe(5);
    expect(frameIndexAt(def, 820)).toBe(0);
  });

  it("单帧行不越界", () => {
    const single = { row: 0, frames: [{ col: 0, durMs: 100 }] };
    expect(frameIndexAt(single, 0)).toBe(0);
    expect(frameIndexAt(single, 99)).toBe(0);
    expect(frameIndexAt(single, 100)).toBe(0); // 循环
  });
});

describe("SpriteAnimator：状态切换重置 + 帧推进（热替换基础）", () => {
  it("初始 idle，按时间推进", () => {
    const a = new SpriteAnimator("idle");
    expect(a.currentFrame(0)).toEqual({ row: 0, col: 0 });
    expect(a.currentFrame(300)).toEqual({ row: 0, col: 1 }); // ≥280ms 进第 2 帧
  });

  it("状态切换 → 立即回到新行第 0 帧（切行动画从头播）", () => {
    const a = new SpriteAnimator("idle");
    a.currentFrame(1000); // 深入 idle 序列
    a.setState("error", 1000);
    expect(a.currentFrame(1000)).toEqual({ row: 5, col: 0 });
    expect(a.currentFrame(1000 + 141)).toEqual({ row: 5, col: 1 }); // failed 140ms/帧
  });

  it("全部 8 种状态切换后行号正确", () => {
    const a = new SpriteAnimator("idle");
    const rows: Record<NormalizedState, number> = {
      idle: 0,
      working: 7,
      thinking: 6,
      editing: 1,
      testing: 2,
      "waiting-permission": 8,
      error: 5,
      success: 3,
    };
    let t = 0;
    for (const s of ALL_STATES) {
      a.setState(s, t);
      expect(a.currentFrame(t).row).toBe(rows[s]);
      t += 5000;
    }
  });

  it("同状态重复 setState 不重置动画", () => {
    const a = new SpriteAnimator("idle");
    a.currentFrame(1000); // col 5（idle 累计 [280,390,500,640,780,1100]，1000∈[780,1100)）
    a.setState("idle", 1000);
    expect(a.currentFrame(1000).col).toBe(5);
  });
});
