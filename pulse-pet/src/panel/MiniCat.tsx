import { useEffect, useRef, useState } from "react";
import { usePanelStore } from "./panelStore";
import { ATLAS_ROW_FOR_STATE, PETDEX_ROWS } from "../lib/sprite";
import { isTauriRuntime } from "../lib/token-stats";

/**
 * mini 猫状态镜像（v2 M2 面板壳签名元素，V2-DESIGN §2.4 / TC-UI-05）：
 * - 顶栏 24×26 像素猫（`image-rendering: pixelated`），用当前 atlas 真实帧
 *   镜像 agent 状态（working→running 行跑动帧、error→failed 行等）；
 * - 帧行映射复用 `lib/sprite.ts`；**120ms 固定步进取帧**（不复用帧时长表的
 *   不规则节拍——迷你尺寸只需示意性律动），rAF 循环按步进节流重绘；
 * - atlas 数据源 = Rust `atlas_sheet_png`（PNG dataURL，AtlasState 缓存，
 *   热替换失效重建）+ 监听 `atlas://changed` 同步换装（TC-UI-05-2）；
 * - atlas 缺失 / 命令失败 / 图解码失败 → 渲染占位方块（不崩，优雅降级，
 *   TC-UI-05-3）。
 */

const CSS_W = 24;
const CSS_H = 26;
/** 固定步进（每 120ms 前进一帧）。 */
const FRAME_STEP_MS = 120;

/** 状态 → (row, 该行帧数)。 */
function rowOf(kind: keyof typeof ATLAS_ROW_FOR_STATE): { row: number; frames: number } {
  const def = PETDEX_ROWS[ATLAS_ROW_FOR_STATE[kind]];
  return { row: def.row, frames: def.frames.length };
}

export default function MiniCat() {
  const kind = usePanelStore((s) => s.kind);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  /** 已解码的 atlas sheet 图（null = 未就绪/失败 → 占位）。 */
  const [sheet, setSheet] = useState<HTMLImageElement | null>(null);
  const [failed, setFailed] = useState(false);

  // 拉取 atlas PNG dataURL（热替换事件重拉）
  useEffect(() => {
    if (!isTauriRuntime()) {
      setFailed(true);
      return;
    }
    let alive = true;
    const load = async () => {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const url = await invoke<string | null>("atlas_sheet_png");
        if (!alive || !url) {
          if (!alive) return;
          setFailed(true);
          return;
        }
        const img = new Image();
        img.onload = () => {
          if (!alive) return;
          setFailed(false);
          setSheet(img);
        };
        img.onerror = () => {
          if (!alive) return;
          setFailed(true);
        };
        img.src = url;
      } catch {
        if (alive) setFailed(true);
      }
    };
    void load();
    void (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      const un = await listen("atlas://changed", () => void load());
      if (!alive) un();
    })();
    return () => {
      alive = false;
    };
  }, []);

  // rAF 绘制（120ms 步进节流：col 变化才重绘）
  useEffect(() => {
    if (!sheet) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(CSS_W * dpr);
    canvas.height = Math.round(CSS_H * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false; // 像素风：放大不插值

    let rafId = 0;
    let disposed = false;
    let lastCol = -1;
    let lastRow = -1;
    const t0 = performance.now();

    const loop = (now: number) => {
      if (disposed) return;
      const { row, frames } = rowOf(kind);
      const col = Math.floor((now - t0) / FRAME_STEP_MS) % Math.max(1, frames);
      if (col !== lastCol || row !== lastRow) {
        lastCol = col;
        lastRow = row;
        // sheet 网格：8 列；帧高按 192:208 = 12:13 比例由帧宽推导（干净缩放同口径）
        const fw = sheet.width / 8;
        const fh = (fw / 12) * 13;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(
          sheet,
          col * fw,
          row * fh,
          fw,
          fh,
          0,
          0,
          canvas.width,
          canvas.height,
        );
      }
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
    };
  }, [sheet, kind]);

  if (!sheet || failed) {
    // 占位方块：宠物世界固定色（墨边 + 暖白面），优雅降级不崩（TC-UI-05-3）
    return <span className="mini-cat mini-cat-fallback" aria-hidden="true" />;
  }
  return <canvas ref={canvasRef} className="mini-cat" width={CSS_W} height={CSS_H} />;
}
