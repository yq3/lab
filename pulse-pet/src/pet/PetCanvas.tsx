import { useEffect, useRef } from "react";
import { computeCanvasSize, computeFrameRect } from "../lib/scaling";
import { SpriteAnimator } from "../lib/sprite";
import { shouldStartDrag } from "../lib/pet-drag";
import { startPetDrag } from "../lib/interaction";
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

/**
 * M5：把 atlas RGBA 整块画进离屏 canvas（一次 putImageData），此后每帧
 * drawImage 源矩形切帧（192×208 单帧），不做前端解码（TC-SP-04）。
 * 失败返回 null（调用方回退占位 PNG 路径）。
 */
function buildSheetCanvas(
  cols: number,
  rows: number,
  frameW: number,
  frameH: number,
  rgba: Uint8Array,
): HTMLCanvasElement | null {
  const w = cols * frameW;
  const h = rows * frameH;
  const sheet = document.createElement("canvas");
  sheet.width = w;
  sheet.height = h;
  const ctx = sheet.getContext("2d");
  if (!ctx) return null;
  try {
    // ImageData 需要 Uint8ClampedArray 视图（共享同一 buffer，无拷贝）
    const clamped = new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, rgba.length);
    ctx.putImageData(new ImageData(clamped, w, h), 0, 0);
  } catch {
    return null;
  }
  return sheet;
}

export default function PetCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sprite = usePetStore((s) => s.sprite);
  const next = usePetStore((s) => s.next);
  const ackReminder = usePetStore((s) => s.ackReminderBubble);
  const raw = usePetStore((s) => s.raw);
  const atlas = usePetStore((s) => s.atlas);
  const passThrough = usePetStore((s) => s.passThrough);
  const openContextMenu = usePetStore((s) => s.openContextMenu);
  const closeContextMenu = usePetStore((s) => s.closeContextMenu);

  // M6 拖拽起点（pointerdown 记录、move 超阈值启动原生拖拽、up/cancel/leave 清除）
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const passThroughRef = useRef(passThrough);
  passThroughRef.current = passThrough;

  // rAF 循环读取最新的 sprite/raw，避免每帧重建 effect
  const spriteRef = useRef(sprite);
  spriteRef.current = sprite;
  const rawRef = useRef(raw);
  rawRef.current = raw;

  // M5：atlas 离屏 sheet（atlas 对象身份变化 = 热替换，重建一次）
  const sheetRef = useRef<HTMLCanvasElement | null>(null);
  const atlasSizeRef = useRef<{ fw: number; fh: number } | null>(null);
  useEffect(() => {
    if (!atlas) {
      sheetRef.current = null;
      atlasSizeRef.current = null;
      return;
    }
    const sheet = buildSheetCanvas(
      atlas.cols,
      atlas.rows,
      atlas.frameW,
      atlas.frameH,
      atlas.rgba,
    );
    if (!sheet) {
      console.error("[pulsepet] atlas sheet build failed, fallback to placeholder");
      sheetRef.current = null;
      atlasSizeRef.current = null;
      return;
    }
    sheetRef.current = sheet;
    atlasSizeRef.current = { fw: atlas.frameW, fh: atlas.frameH };
  }, [atlas]);

  // 占位 PNG（无 atlas 时的兜底渲染，P2-3）
  const imgRef = useRef<HTMLImageElement | null>(null);
  useEffect(() => {
    if (atlas) return; // atlas 模式不需要占位图
    let alive = true;
    loadCatImage()
      .then((img) => {
        if (alive) imgRef.current = img;
      })
      .catch((err) => {
        // P2-3：加载失败用纯色兜底（img 置 null 后 draw 走纯色分支）
        console.error("[pulsepet] placeholder image load failed:", err);
        imgRef.current = null;
      });
    return () => {
      alive = false;
    };
  }, [atlas]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let rafId = 0;
    let disposed = false;
    let media: MediaQueryList | null = null;
    const animator = new SpriteAnimator("idle");

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

    const drawPlaceholder = (now: number) => {
      const dpr = window.devicePixelRatio || 1;
      const canvasW = computeCanvasSize(CSS_SIZE, dpr);
      const canvasH = canvasW;
      const img = imgRef.current;
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
      if (spriteRef.current === "idle" && isBlinking(now)) {
        const scale = dw / FRAME_W;
        ctx.fillStyle = FUR_COLOR;
        ctx.fillRect(
          dx + EYE_LEFT.x * scale,
          dy + EYE_LEFT.y * scale,
          EYE_LEFT.w * scale,
          EYE_LEFT.h * scale,
        );
      }
    };

    const drawAtlas = (now: number) => {
      const dpr = window.devicePixelRatio || 1;
      const canvasW = computeCanvasSize(CSS_SIZE, dpr);
      const canvasH = canvasW;
      ctx.clearRect(0, 0, canvasW, canvasH);

      const sheet = sheetRef.current;
      const size = atlasSizeRef.current;
      if (!sheet || !size) {
        drawPlaceholder(now); // sheet 构建失败兜底
        return;
      }
      // 9 状态映射（TC-SP-07）：raw → atlas 行；切帧时序由 SpriteAnimator 驱动
      animator.setState(rawRef.current, now);
      const { row, col } = animator.currentFrame(now);
      const { dx, dy, dw, dh } = computeFrameRect(canvasW, canvasH, size.fw, size.fh);
      ctx.drawImage(
        sheet,
        col * size.fw,
        row * size.fh,
        size.fw,
        size.fh,
        dx,
        dy,
        dw,
        dh,
      );
    };

    const loop = (now: number) => {
      if (disposed) return;
      if (sheetRef.current) drawAtlas(now);
      else drawPlaceholder(now);
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      if (media) media.removeEventListener("change", onDprChange);
      window.removeEventListener("resize", onDprChange);
    };
  }, []);

  // M6 交互（TC-WIN-01/02/03）：主键按下记录起点，位移超阈值 → 原生窗口拖拽
  // （跨屏由系统处理，TC-APP-11）；右键弹 PetMenu。穿透态下 webview 收不到
  // 事件（DESIGN §6.3），passThroughRef 双保险不触发任何交互。
  // 点击语义保留：未超阈值的按下-抬起仍是 click（M1 状态轮换 + TC-RM-04 确认）。
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 || passThroughRef.current) return;
    dragStartRef.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const start = dragStartRef.current;
    if (!start || passThroughRef.current) return;
    if (shouldStartDrag(start.x, start.y, e.clientX, e.clientY)) {
      dragStartRef.current = null; // 只启动一次，此后 OS drag loop 接管
      startPetDrag().catch((err) => console.error("[pulsepet] start_drag failed:", err));
    }
  };
  const endDragTrack = () => {
    dragStartRef.current = null;
  };
  const onContextMenu = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (passThroughRef.current) return; // 正常不会发生（穿透收不到事件）
    e.preventDefault();
    openContextMenu(e.clientX, e.clientY);
  };

  // 点击宠物：有提醒气泡时视为"已确认"（TC-RM-04，提前消失 + 记 acked_at）；
  // 否则沿用 M1 的状态轮换（占位阶段的手动驱动）。
  return (
    <canvas
      ref={canvasRef}
      className="pet-canvas"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDragTrack}
      onPointerCancel={endDragTrack}
      onPointerLeave={endDragTrack}
      onContextMenu={onContextMenu}
      onClick={() => {
        // 菜单打开时点击画布 = 点外部：仅关菜单，不触发状态轮换
        const hadMenu = usePetStore.getState().contextMenu !== null;
        closeContextMenu();
        if (hadMenu) return;
        if (!ackReminder()) next();
      }}
    />
  );
}
