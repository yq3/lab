/**
 * M5 atlas 帧时长表 + 切帧逻辑（DESIGN §6.2，TC-SP-04/07/08）。
 *
 * 帧时长表照抄 petdex `sprite.zig`（crafter-station/petdex，
 * packages/petdex-desktop-native/src/sprite.zig，2026-08 抓取）：
 *   - idle 6 帧不规则眨眼（280/110/110/140/140/320ms）
 *   - 其余 uniform（末帧稍长，zig `uniform(count, dur, last)`）
 *
 * 本模块纯逻辑（无 DOM/Canvas 依赖），PetCanvas 负责 canvas 绘制。
 */

import type { NormalizedState } from "./state";

/** atlas 行名（= petdex sprite.State 枚举）。 */
export type AtlasRowName =
  | "idle"
  | "running-right"
  | "running-left"
  | "waving"
  | "jumping"
  | "failed"
  | "waiting"
  | "running"
  | "review";

export interface FrameSpec {
  /** atlas 列号。 */
  col: number;
  /** 该帧停留时长（ms）。 */
  durMs: number;
}

export interface RowDef {
  /** atlas 行号。 */
  row: number;
  frames: readonly FrameSpec[];
}

/** petdex zig `uniform(count, dur, last)`：前 count-1 帧 dur，末帧 last。 */
function uniform(count: number, dur: number, last: number): FrameSpec[] {
  return Array.from({ length: count }, (_, i) => ({
    col: i,
    durMs: i === count - 1 ? last : dur,
  }));
}

/** 9 状态帧时长表（行号与 petdex 一致；jumping 行 4 预留不驱动，TC-SP-08）。 */
export const PETDEX_ROWS: Record<AtlasRowName, RowDef> = {
  idle: {
    row: 0,
    frames: [
      { col: 0, durMs: 280 },
      { col: 1, durMs: 110 },
      { col: 2, durMs: 110 },
      { col: 3, durMs: 140 },
      { col: 4, durMs: 140 },
      { col: 5, durMs: 320 },
    ],
  },
  "running-right": { row: 1, frames: uniform(8, 120, 220) },
  "running-left": { row: 2, frames: uniform(8, 120, 220) },
  waving: { row: 3, frames: uniform(4, 140, 280) },
  jumping: { row: 4, frames: uniform(5, 140, 280) },
  failed: { row: 5, frames: uniform(8, 140, 240) },
  waiting: { row: 6, frames: uniform(6, 150, 260) },
  running: { row: 7, frames: uniform(6, 120, 220) },
  review: { row: 8, frames: uniform(6, 150, 280) },
};

/**
 * 归一化状态 → atlas 行完整映射（DESIGN §6.2 表，B17 / TC-SP-07；
 * M5 切 atlas 起启用，§6.1 占位降级映射作废）。
 * jumping 无驱动事件，不出现在此表（TC-SP-08）。
 */
export const ATLAS_ROW_FOR_STATE: Record<NormalizedState, AtlasRowName> = {
  idle: "idle", // 行 0 直映
  working: "running", // 行 7 原地踏步式跑动
  thinking: "waiting", // 行 6 待机/张望
  editing: "running-right", // 行 1 向前推进
  testing: "running-left", // 行 2 反向跑动
  "waiting-permission": "review", // 行 8 申请审批画面
  error: "failed", // 行 5 直映
  success: "waving", // 行 3 庆祝式挥手
};

export function rowForState(s: NormalizedState): RowDef {
  return PETDEX_ROWS[ATLAS_ROW_FOR_STATE[s]];
}

/** 播放头：elapsedMs 在循环时长内落在第几帧（帧边界左闭右开）。 */
export function frameIndexAt(def: RowDef, elapsedMs: number): number {
  const total = def.frames.reduce((acc, f) => acc + f.durMs, 0);
  if (total <= 0) return 0;
  let e = ((elapsedMs % total) + total) % total;
  for (let i = 0; i < def.frames.length; i++) {
    e -= def.frames[i].durMs;
    if (e < 0) return i;
  }
  return def.frames.length - 1; // 浮点兜底
}

/**
 * 切帧动画器：状态切换重置到新行第 0 帧从头播；同状态不重置。
 * 与 atlas 数据解耦（PetCanvas 拿 row/col 去切帧），atlas 热替换不影响时序状态。
 */
export class SpriteAnimator {
  private state: NormalizedState;
  private t0 = 0;

  constructor(initial: NormalizedState) {
    this.state = initial;
  }

  setState(s: NormalizedState, nowMs: number): void {
    if (s === this.state) return;
    this.state = s;
    this.t0 = nowMs;
  }

  currentFrame(nowMs: number): { row: number; col: number } {
    const def = rowForState(this.state);
    return {
      row: def.row,
      col: def.frames[frameIndexAt(def, nowMs - this.t0)].col,
    };
  }
}
