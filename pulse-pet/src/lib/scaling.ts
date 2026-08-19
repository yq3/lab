/**
 * canvas 缩放与尺寸策略（DESIGN §6.1 / TC-SP-02 / TC-SP-03）。
 *
 * - canvas 内部分辨率 = 逻辑尺寸 × devicePixelRatio（HiDPI 2× → 440）
 * - CSS 尺寸固定为逻辑尺寸（220×220）
 * - 帧图按 min(canvasW/frameW, canvasH/frameH) 居中绘制，保持比例不裁剪
 */

/** 帧图缩放系数：保持比例、不裁剪、可完整放进 canvas。 */
export function computeScale(
  canvasW: number,
  canvasH: number,
  frameW: number,
  frameH: number,
): number {
  return Math.min(canvasW / frameW, canvasH / frameH);
}

/** canvas 内部分辨率（物理像素） = 逻辑尺寸 × dpr。 */
export function computeCanvasSize(cssSize: number, dpr: number): number {
  return Math.round(cssSize * dpr);
}

/** 帧图居中绘制的目标矩形（物理像素坐标）。 */
export function computeFrameRect(
  canvasW: number,
  canvasH: number,
  frameW: number,
  frameH: number,
): { dx: number; dy: number; dw: number; dh: number } {
  const scale = computeScale(canvasW, canvasH, frameW, frameH);
  const dw = frameW * scale;
  const dh = frameH * scale;
  const dx = (canvasW - dw) / 2;
  const dy = (canvasH - dh) / 2;
  return { dx, dy, dw, dh };
}
