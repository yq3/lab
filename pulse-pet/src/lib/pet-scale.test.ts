/**
 * §十一归一化纯函数单测（V2-OPEN-ITEMS §11.2 / docs/v2/pet-size.md）。
 *
 * 四素材 idle 帧内并集为 **2026-08-28 PIL 实测值**（blinking-kitty /
 * wagging-doggy 内置 PNG + kun-like / line-puppy petdex webp），钉住：
 * - 同档位各素材 idle 视觉高度一致（"内置猫现状 = 中档、petdex 靠过来"）；
 * - 帧尺寸上限（防裁剪安全网）对极小内容素材生效；
 * - 缺失/非法度量 → null（回退全帧适配）。
 */
import { describe, expect, it } from "vitest";
import { IDLE_ANCHOR, computePetScale, frameRectAtScale } from "./pet-scale";
import type { IdleRect } from "./atlas";
import { PET_SIZES } from "./size-bridge";

const rect = (x: number, y: number, w: number, h: number): IdleRect => ({ x, y, w, h });

/** 四素材实测 idle 帧内并集（帧内局部坐标，192×208 帧）。 */
const ASSETS = {
  kitty: rect(56, 48, 88, 108), // 内置：填高 52%（锚定来源）
  doggy: rect(52, 48, 96, 112), // 内置：填高 54%
  kun: rect(36, 5, 119, 198), // petdex：填高 95%
  puppy: rect(18, 5, 155, 198), // petdex：填高 95%
};

/** idle 视觉高度（逻辑 px）：h × s。 */
const idleDisplayH = (canvas: number, idle: IdleRect) =>
  idle.h * (computePetScale(canvas, 192, 208, idle) as number);

describe("computePetScale 归一化（§11.2）", () => {
  it("锚定比率 = 内置猫 idle 填高（108/208）", () => {
    expect(IDLE_ANCHOR).toBeCloseTo(108 / 208, 10);
  });

  it.each(["small", "medium", "large"] as const)(
    "%s 档：四素材 idle 视觉高度一致（残差 < 0.5px）",
    (tier) => {
      const canvas = PET_SIZES[tier];
      const target = canvas * IDLE_ANCHOR;
      for (const idle of Object.values(ASSETS)) {
        expect(idleDisplayH(canvas, idle)).toBeCloseTo(target, 5);
      }
    },
  );

  it("中档：kitty 缩放比 = 220/208（锚定项恰等于帧高上限，视觉与档位化前一致）", () => {
    expect(computePetScale(220, 192, 208, ASSETS.kitty)).toBeCloseTo(220 / 208, 10);
  });

  it("中档：petdex 满帧素材缩到 ~0.577（idle 高 210 → 114，向内置靠拢）", () => {
    expect(computePetScale(220, 192, 208, ASSETS.kun)).toBeCloseTo(
      (220 * IDLE_ANCHOR) / 198,
      10,
    );
  });

  it("帧尺寸上限生效：极小内容素材不越帧放大（s 封顶 canvas/frameH）", () => {
    const tiny = rect(90, 90, 10, 20); // 假想素材：idle 只占 20px 高
    expect(computePetScale(220, 192, 208, tiny)).toBeCloseTo(220 / 208, 10);
    // idle 显示高 = 20 × 220/208 ≈ 21px——安全网兜住，不无限放大
  });

  it("缺失 / 非法度量 → null（回退全帧适配）", () => {
    expect(computePetScale(220, 192, 208, null)).toBeNull();
    expect(computePetScale(220, 192, 208, rect(0, 0, 10, 0))).toBeNull();
    expect(computePetScale(0, 192, 208, ASSETS.kitty)).toBeNull();
  });
});

describe("frameRectAtScale 居中几何", () => {
  it("物理像素口径：2× 屏 220 逻辑画布、kitty s → 帧居中且恰好铺满高度", () => {
    const s = (computePetScale(220, 192, 208, ASSETS.kitty) as number) * 2;
    const r = frameRectAtScale(440, 440, 192, 208, s);
    expect(r.dw).toBeCloseTo(192 * s, 8);
    expect(r.dh).toBeCloseTo(440, 6); // 208 × 220/208 × 2 = 440（贴边不裁）
    expect(r.dy).toBeCloseTo(0, 6);
    expect(r.dx).toBeCloseTo((440 - r.dw) / 2, 8);
  });
});
