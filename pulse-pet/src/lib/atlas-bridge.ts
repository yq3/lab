/**
 * atlas-bridge：M5 atlas 的 Tauri 链路（DESIGN §6.2 / §9）。
 *
 * 1. pet 路由启动时拉取 `atlas_meta` + `atlas_pixels` → petStore（atlas 模式渲染）；
 *    拉取失败 → atlas 置 null，回退占位 PNG 路径（P2-3 兜底语义），不崩。
 * 2. 监听 `atlas://changed`（panel 切换宠物后 Rust 下发）→ 重新拉取 → 热替换
 *    webview 帧（TC-SP-11②，无需重启）。
 * 3. panel / fireworks 路由不拉 pixels（11MB 级数据只在 pet 窗口持有）。
 *
 * 非 Tauri 环境（vitest / 浏览器 dev）直接返回，保持纯前端可跑。
 */

import { usePetStore } from "../pet/petStore";
import { fetchAtlasMeta, fetchAtlasPixels } from "./atlas";
import { isTauriRuntime } from "./token-stats";

function isPetRoute(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hash.replace(/^#\/?/, "");
  return !h.startsWith("panel") && !h.startsWith("fireworks");
}

/** 拉取当前 atlas → store（任何失败静默回退占位，不影响主链路）。 */
async function loadAtlasIntoStore(): Promise<void> {
  try {
    const meta = await fetchAtlasMeta();
    try {
      const pixels = await fetchAtlasPixels(meta);
      usePetStore.getState().setAtlas(meta, pixels);
    } catch (e) {
      console.error("[pulsepet] atlas pixels load failed:", e);
      usePetStore.getState().setAtlas(meta, null);
    }
  } catch (e) {
    console.error("[pulsepet] atlas meta load failed:", e);
  }
}

export async function initAtlasBridge(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!isTauriRuntime()) return;

  if (isPetRoute()) {
    await loadAtlasIntoStore();
  }

  const { listen } = await import("@tauri-apps/api/event");
  await listen("atlas://changed", () => {
    if (isPetRoute()) void loadAtlasIntoStore();
  });
}
