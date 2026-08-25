import { useEffect, useRef } from "react";
import { computeCanvasSize, computeFrameRect } from "../lib/scaling";
import { SpriteAnimator } from "../lib/sprite";
import { DragClickGuard, shouldRotateOnClick } from "../lib/pet-drag";
import { startPetDrag } from "../lib/interaction";
import type { NormalizedState } from "../lib/state";
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

/** M7：庆祝期判定（TC-TD-04/05 waving 覆盖；到期自动失效）。 */
function celebrationActive(c: { id: number; until: number } | null): boolean {
  return !!c && Date.now() < c.until;
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

  // M6 拖拽/点击判定状态机（R2：拖拽尾巴的补发 click 不再触发状态轮换；
  // 纯逻辑在 lib/pet-drag.ts，单测覆盖拖拽/纯点击/平台差异兜底路径）
  const dragGuardRef = useRef(new DragClickGuard());
  // R3 P1：pointerdown 时刻的菜单开态快照——PetMenu 在 document 冒泡阶段关菜单
  //（晚于本组件的 React onPointerDown），click 时读实时状态恒为 null，会误轮换
  const menuOpenAtPointerDownRef = useRef(false);
  const passThroughRef = useRef(passThrough);
  passThroughRef.current = passThrough;

  // rAF 循环读取最新的 sprite/raw，避免每帧重建 effect
  const spriteRef = useRef(sprite);
  spriteRef.current = sprite;
  const rawRef = useRef(raw);
  rawRef.current = raw;
  // M7：完成庆祝（waving 覆盖期）；rAF 内按 Date.now < until 自过期
  const celebration = usePetStore((s) => s.celebration);
  const celebrationRef = useRef(celebration);
  celebrationRef.current = celebration;

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
      // M7：庆祝期占位画面切到 success（挥手语义最贴近；TC-TD-04）
      const celebrating = celebrationActive(celebrationRef.current);
      const sprite = celebrating ? "success" : spriteRef.current;
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

      // idle 眨眼动画（闭合睁开的左眼；庆祝期不眨眼）
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
      // 9 状态映射（TC-SP-07）：raw → atlas 行；切帧时序由 SpriteAnimator 驱动。
      // M7：庆祝期覆盖为 success（atlas 行 3 = waving 挥手，TC-TD-04）
      const effective: NormalizedState = celebrationActive(celebrationRef.current)
        ? "success"
        : rawRef.current;
      animator.setState(effective, now);
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
  // 点击语义保留：未超阈值的按下-抬起仍是 click（M1 状态轮换 + TC-RM-04 确认）；
  // 拖拽结束后 OS/WKWebView 可能补发一次 click（R2 实测），由 DragClickGuard
  // 识别并吞掉——拖拽绝不附加单击效果，真实单击不受影响。
  // v2 M3（§3.4 ②）：pointerenter/leave 写 hoverEntered——HoverToday 500ms
  // 防抖驱动（穿透态守卫，TC-M3-10-5）。
  const setHoverEntered = usePetStore((s) => s.setHoverEntered);
  const onPointerEnter = () => {
    if (passThroughRef.current) return;
    setHoverEntered(true);
  };
  const onPointerLeave = () => {
    setHoverEntered(false); // 离开即时（幂等；未悬停时 no-op）
    dragGuardRef.current.onPointerUp();
  };
  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 || passThroughRef.current) return;
    // R3 P1：先快照菜单开态（此刻 PetMenu 的冒泡关闭尚未执行）
    menuOpenAtPointerDownRef.current = usePetStore.getState().contextMenu !== null;
    dragGuardRef.current.onPointerDown(e.clientX, e.clientY);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (passThroughRef.current) return;
    if (dragGuardRef.current.onPointerMove(e.clientX, e.clientY)) {
      startPetDrag().catch((err) => console.error("[pulsepet] start_drag failed:", err));
    }
  };
  const endDragTrack = () => {
    dragGuardRef.current.onPointerUp();
  };  const onContextMenu = (e: React.MouseEvent<HTMLCanvasElement>) => {
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
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onContextMenu={onContextMenu}
      onClick={() => {
        // R2：拖拽结束后系统补发的尾巴 click；R3 P1：pointerdown 时菜单开着
        //（= 本次按下用于点外部关菜单）——两者都不轮换，不触碰气泡 ack
        const rotate = shouldRotateOnClick({
          dragTail: dragGuardRef.current.shouldSuppressClick(),
          menuOpenAtPointerDown: menuOpenAtPointerDownRef.current,
        });
        menuOpenAtPointerDownRef.current = false; // 快照一次即消费
        closeContextMenu(); // 幂等（PetMenu 已关时 no-op）
        if (!rotate) return;
        if (!ackReminder()) next();
      }}
    />
  );
}
