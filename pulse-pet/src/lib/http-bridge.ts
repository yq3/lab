/**
 * http-bridge：收来自 Rust 的 Tauri event（事件 → petStore），DESIGN §9 / §3.3。
 *
 * Rust 侧 `session_state` 已做多 session 优先级合并，经 Tauri event `pulsepet://state`
 * 下发合并后的显示状态（payload = `{kind}`）。本模块：
 *   1. 初始化时查一次 `get_display_state`（避免启动时错过已发生的状态）；
 *   2. 监听 `pulsepet://state`，把 `kind` 写入 petStore。
 *
 * 与 @tauri-apps/api 的交互用动态 import + 运行时探测，使纯函数（parseDisplayKind /
 * applyStatePayload）可在 vitest(node) 下直接单测。
 */

import { ALL_STATES, type NormalizedState } from "./state";
import { usePetStore } from "../pet/petStore";

/** 从 Tauri event payload 解析合并后的显示状态 kind（非法返回 null）。 */
export function parseDisplayKind(payload: unknown): NormalizedState | null {
  if (typeof payload !== "object" || payload === null) return null;
  const kind = (payload as { kind?: unknown }).kind;
  if (typeof kind !== "string") return null;
  return ALL_STATES.includes(kind as NormalizedState)
    ? (kind as NormalizedState)
    : null;
}

/** 把 payload 应用到 petStore（含 8→5 降级映射）。 */
export function applyStatePayload(payload: unknown): void {
  const kind = parseDisplayKind(payload);
  if (kind) usePetStore.getState().setRaw(kind);
}

/**
 * 初始化 bridge（仅在 Tauri 运行时执行；vitest/node 下直接返回）。
 * 由 `main.tsx` 启动时调用一次。
 */
export async function initHttpBridge(): Promise<void> {
  // Tauri 运行时探测（非 Tauri 环境如 vitest 不执行）
  if (typeof window === "undefined") return;
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return;
  }
  const [{ listen }, { invoke }] = await Promise.all([
    import("@tauri-apps/api/event"),
    import("@tauri-apps/api/core"),
  ]);

  // 初始查询当前显示状态
  try {
    const kind = await invoke<string>("get_display_state");
    if (typeof kind === "string") {
      const parsed = ALL_STATES.includes(kind as NormalizedState)
        ? (kind as NormalizedState)
        : null;
      if (parsed) usePetStore.getState().setRaw(parsed);
    }
  } catch {
    // App 侧命令不可用时静默（不影响事件监听）
  }

  await listen("pulsepet://state", (event) => {
    applyStatePayload(event.payload);
  });
}
