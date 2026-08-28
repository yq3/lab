/**
 * pet-scale：§十一视觉归一化（V2-OPEN-ITEMS §11.2，纯函数）。
 *
 * 问题：192×208 的帧是"舞台"，各素材填帧率差异悬殊（实测内置 kitty idle
 * 高 52% vs petdex 素材 95%）→ 同档位视觉大小差 1.8×。
 *
 * 锚定（用户裁定 2026-08-28）："内置猫现状就是中档、petdex 靠过来"——
 * 目标 idle 高 = canvas × 108/208（blinking-kitty 的 idle 帧内填高）。
 *
 * 防裁剪上限 = **帧尺寸本身**（s ≤ canvas/frameW, canvas/frameH）：内容
 * ⊆ 帧、帧按 s 缩放后恰好放进画布（居中）→ 任何素材任何动画帧永不裁剪。
 * 不用整表内容包围盒做上限——奔跑行会让内容遍布整帧宽，全表 bbox ≈ 整张
 * sheet（实测 kitty 1520×1772），作上限会把宠物压扁。
 *
 * 绘制几何 = 帧居中（与现行 computeFrameRect 同构，仅 scale 来源不同）：
 * 帧内相对位置保持 → 奔跑帧的帧内位移语义不被破坏，帧间无抖动。
 *
 * 基准数据来源：Rust `atlas.rs` 的 `frame_union_at_origin(row 0)`（idle 行
 * 逐帧原点并集，帧内局部坐标），经 AtlasMetaDto.idle 下发。
 */

import type { IdleRect } from "./atlas";

/** 锚定比率：目标 idle 高 / 画布（= 108/208，内置猫 idle 帧内填高）。 */
export const IDLE_ANCHOR = 108 / 208;

/**
 * 归一化缩放系数（逻辑像素比：帧原生 px → 画布逻辑 px；物理像素 = ×dpr）。
 *
 * `idle` 为 null / 非法（h ≤ 0）时由调用方回退全帧适配（computeFrameRect）。
 */
export function computePetScale(
  canvas: number,
  frameW: number,
  frameH: number,
  idle: IdleRect | null,
): number | null {
  if (!idle || idle.h <= 0 || frameW <= 0 || frameH <= 0 || canvas <= 0) return null;
  return Math.min((canvas * IDLE_ANCHOR) / idle.h, canvas / frameW, canvas / frameH);
}

/**
 * 按给定缩放系数计算帧的居中目标矩形（canvasW/H 与 s 同口径——物理像素
 * 时传物理画布与 s×dpr；与 scaling.ts 的 computeFrameRect 同构，仅 scale
 * 外部给定而非 min 适配）。
 */
export function frameRectAtScale(
  canvasW: number,
  canvasH: number,
  frameW: number,
  frameH: number,
  s: number,
): { dx: number; dy: number; dw: number; dh: number } {
  const dw = frameW * s;
  const dh = frameH * s;
  return { dx: (canvasW - dw) / 2, dy: (canvasH - dh) / 2, dw, dh };
}
