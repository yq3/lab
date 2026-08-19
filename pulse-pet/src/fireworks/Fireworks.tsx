import { useEffect, useRef } from "react";
import {
  FIREWORKS_HARD_CAP_MS,
  FireworksEngine,
  parseFireworksPlay,
  type Particle,
} from "./engine";

/**
 * 烟花窗口（DESIGN §5.3 / §2.3；TC-RM-09/10/16）。
 *
 * - 窗口：M1 已配置全屏（maximized）、透明（transparent + backgroundColor
 *   #00000000，macOS 经 macOSPrivateApi）、置顶、无边框、无任务栏项；
 *   本组件只负责内容渲染。Windows 兼容（TC-RM-16，实机 M8）：若
 *   `maximized + transparent + alwaysOnTop` 组合渲染异常，回退方案见 DESIGN
 *   §12（窗口不透明 + 近桌面深色背景），macOS 侧已在 M4 实测透明 + 内容渲染。
 * - 播放编排：挂载后 `fireworks_ready`（Rust 侧 pending 补发握手）→ 收
 *   `fireworks://play`（Rust emit_to 本窗口；origin 为宠物位置换算的逻辑像素）
 *   → rAF 60fps 渲染 → 引擎完成（~3.8s，硬上限 5s）后 `fireworks_finished`
 *   → Rust hide 窗口。播放中再次收到 play 直接重置引擎重播（TC-RM-10）。
 * - 拖尾：每帧 `destination-out` 半透明擦除（对透明窗口安全，不留残帧），
 *   粒子用 `lighter` 叠加出流光质感；结束后 clearRect 全清（无残留帧）。
 */

function drawParticle(
  ctx: CanvasRenderingContext2D,
  p: Particle,
  dpr: number,
): void {
  const life = Math.max(0, 1 - p.age / p.maxAge); // alpha fade
  if (life <= 0) return;
  const x = p.x * dpr;
  const y = p.y * dpr;
  const size = p.size * dpr;
  const hue = ((p.hue % 360) + 360) % 360;
  // 外层辉光（大而淡）
  ctx.fillStyle = `hsla(${hue}, 95%, 62%, ${0.30 * life})`;
  ctx.beginPath();
  ctx.arc(x, y, size * 2.6, 0, Math.PI * 2);
  ctx.fill();
  // 内核（亮）
  ctx.fillStyle = `hsla(${hue}, 100%, ${72 + 18 * life}%, ${life})`;
  ctx.beginPath();
  ctx.arc(x, y, size, 0, Math.PI * 2);
  ctx.fill();
  // 花瓣拖线（沿速度方向短线，"流光花瓣"）
  if (p.type === "petal") {
    const vlen = Math.hypot(p.vx, p.vy) || 1;
    const len = Math.min(10, 2 + vlen * 1.2) * dpr;
    ctx.strokeStyle = `hsla(${hue}, 100%, 78%, ${0.55 * life})`;
    ctx.lineWidth = Math.max(1, size * 0.6);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - (p.vx / vlen) * len, y - (p.vy / vlen) * len);
    ctx.stroke();
  }
}

export default function Fireworks() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // 引擎/循环句柄挂在 ref 上：跨 effect 存活、二次播放复用（TC-RM-10）
  const engineRef = useRef<FireworksEngine | null>(null);
  const rafRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runningRef = useRef(false);

  useEffect(() => {
    // 非 Tauri 运行时（浏览器 dev / vitest）无事件可听，渲染占位即可
    if (
      typeof window === "undefined" ||
      !(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
    ) {
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let disposed = false;
    let last = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
    };
    resize();
    window.addEventListener("resize", resize);

    const stopLoop = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = 0;
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      runningRef.current = false;
      // 无残留帧：整幅清空（TC-RM-09 ③）
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };

    const finish = (logId: number) => {
      stopLoop();
      void (async () => {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          await invoke("fireworks_finished", { logId }); // Rust hide + 记 'fireworks'
        } catch (e) {
          console.error("[pulsepet] fireworks_finished failed:", e);
        }
      })();
    };

    const frame = (now: number) => {
      const engine = engineRef.current;
      if (!engine) return stopLoop();
      const dt = last ? now - last : 1000 / 60;
      last = now;
      engine.step(dt);
      const dpr = window.devicePixelRatio || 1;
      // 拖尾：半透明擦除上一帧（destination-out 对透明窗口安全）
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0, 0, 0, 0.22)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      // 粒子叠加发光
      ctx.globalCompositeOperation = "lighter";
      for (const p of engine.getParticles()) {
        drawParticle(ctx, p, dpr);
      }
      if (engine.isDone()) {
        finish(engine.getPlayLogId());
        return;
      }
      rafRef.current = requestAnimationFrame(frame);
    };

    const startPlay = (logId: number, originX: number, originY: number, targetX: number, targetY: number) => {
      const play = {
        log_id: logId,
        origin_x: originX,
        origin_y: originY,
        target_x: targetX,
        target_y: targetY,
      };
      stopLoop(); // 复用：先清上一场（TC-RM-10）
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!engineRef.current) {
        engineRef.current = new FireworksEngine(play);
      } else {
        engineRef.current.reset(play);
      }
      runningRef.current = true;
      last = 0;
      rafRef.current = requestAnimationFrame(frame);
      // 硬上限保险（rAF 被节流时兜底结束，窗口 3-5s 内必 hide）
      timerRef.current = setTimeout(() => {
        if (runningRef.current && engineRef.current) {
          finish(engineRef.current.getPlayLogId());
        }
      }, FIREWORKS_HARD_CAP_MS + 250);
    };

    void (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        await listen("fireworks://play", (event) => {
          const p = parseFireworksPlay(event.payload);
          if (!p) return;
          startPlay(p.log_id, p.origin_x, p.origin_y, p.target_x, p.target_y);
        });
        if (disposed) return;
        // ready 握手：Rust 侧若有 pending play 会立即补发
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("fireworks_ready");
        console.log("[pulsepet] fireworks window ready");
      } catch (e) {
        console.error("[pulsepet] fireworks bridge failed:", e);
      }
    })();

    return () => {
      disposed = true;
      stopLoop();
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="fireworks-canvas" />;
}
