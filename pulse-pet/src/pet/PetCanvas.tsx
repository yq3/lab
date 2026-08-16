import { useEffect, useRef } from "react";
import type { SpriteState } from "../lib/state";
import { computeCanvasSize, computeFrameRect } from "../lib/scaling";
import { usePetStore } from "./petStore";

const CSS_SIZE = 220;
const FRAME_W = 128;
const FRAME_H = 128;

/** 占位精灵中左眼（睁开的那只）在 128×128 图内的像素块，用于眨眼动画。 */
const EYE_LEFT = { x: 44, y: 40, w: 8, h: 8 };

const FUR_COLOR = "#f4f4f7";

let catImage: HTMLImageElement | null = null;
let catImagePromise: Promise<HTMLImageElement> | null = null;

function loadCatImage(): Promise<HTMLImageElement> {
  if (catImage) return Promise.resolve(catImage);
  if (catImagePromise) return catImagePromise;
  catImagePromise = new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      catImage = img;
      resolve(img);
    };
    img.onerror = () => reject(new Error("failed to load placeholder-cat.png"));
    img.src = "/placeholder-cat.png";
  });
  return catImagePromise;
}

/** 眨眼：每 3s 闭眼一次，持续 150ms（仅 idle 状态）。 */
function isBlinking(now: number): boolean {
  const period = 3000;
  const blinkDuration = 150;
  return now % period < blinkDuration;
}

function draw(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement | null,
  sprite: SpriteState,
  now: number,
): void {
  const dpr = window.devicePixelRatio || 1;
  const canvasW = computeCanvasSize(CSS_SIZE, dpr);
  const canvasH = canvasW;
  ctx.clearRect(0, 0, canvasW, canvasH);

  if (!img) {
    // P2-3：素材缺失时的纯色兜底——画一个居中圆（宠物轮廓占位），不崩、不白屏。
    ctx.fillStyle = FUR_COLOR;
    ctx.beginPath();
    ctx.arc(canvasW / 2, canvasH / 2, canvasW / 2.6, 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  // 帧图按 min(canvasW/frameW, canvasH/frameH) 居中绘制，保持比例不裁剪
  const { dx, dy, dw, dh } = computeFrameRect(canvasW, canvasH, FRAME_W, FRAME_H);
  ctx.drawImage(img, dx, dy, dw, dh);

  // idle 眨眼动画（闭合睁开的左眼）
  if (sprite === "idle" && isBlinking(now)) {
    const scale = dw / FRAME_W;
    ctx.fillStyle = FUR_COLOR;
    ctx.fillRect(
      dx + EYE_LEFT.x * scale,
      dy + EYE_LEFT.y * scale,
      EYE_LEFT.w * scale,
      EYE_LEFT.h * scale,
    );
  }
}

export default function PetCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sprite = usePetStore((s) => s.sprite);
  const next = usePetStore((s) => s.next);
  const ackReminder = usePetStore((s) => s.ackReminderBubble);

  // rAF 循环读取最新的 sprite，避免每帧重建 effect
  const spriteRef = useRef(sprite);
  spriteRef.current = sprite;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let rafId = 0;
    let disposed = false;
    let media: MediaQueryList | null = null;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const size = computeCanvasSize(CSS_SIZE, dpr);
      canvas.width = size;
      canvas.height = size;
      canvas.style.width = `${CSS_SIZE}px`;
      canvas.style.height = `${CSS_SIZE}px`;
    };

    // 监听 dpr 变化（拖到不同缩放比的屏幕）重设画布尺寸（TC-SP-03）。
    // P2-4：rAF 延迟一帧再 resize，防 dpr 回落竞态（matchMedia 触发时
    // window.devicePixelRatio 可能仍是旧值，等一帧让其稳定）。
    const onDprChange = () => {
      requestAnimationFrame(resize);
      if (media) media.removeEventListener("change", onDprChange);
      media = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
      media.addEventListener("change", onDprChange);
    };

    resize();
    media = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    media.addEventListener("change", onDprChange);
    window.addEventListener("resize", onDprChange);

    // P2-3：加载失败时 console.error 并用纯色兜底（img 置 null 后 draw 走纯色分支），
    // 不再产生 unhandled rejection。
    loadCatImage()
      .catch((err) => {
        console.error("[pulsepet] placeholder image load failed:", err);
        return null;
      })
      .then((img) => {
        const loop = (now: number) => {
          if (disposed) return;
          draw(ctx, img, spriteRef.current, now);
          rafId = requestAnimationFrame(loop);
        };
        rafId = requestAnimationFrame(loop);
      });

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      if (media) media.removeEventListener("change", onDprChange);
      window.removeEventListener("resize", onDprChange);
    };
  }, []);

  // 点击宠物：有提醒气泡时视为"已确认"（TC-RM-04，提前消失 + 记 acked_at）；
  // 否则沿用 M1 的状态轮换（占位阶段的手动驱动）。
  return (
    <canvas
      ref={canvasRef}
      className="pet-canvas"
      onClick={() => {
        if (!ackReminder()) next();
      }}
    />
  );
}
