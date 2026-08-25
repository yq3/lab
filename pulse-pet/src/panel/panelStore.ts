/**
 * panelStore：v2 M2 面板壳状态（V2-DESIGN §2.4）。
 *
 * `{kind, agent}`——panel 初始化时 `get_display_state` 查询（返回
 * `{kind, agent}`——M1 前置拉前至 M2，TC-UI-03-3）+ 监听 `pulsepet://state`
 * （payload 含 agent）。agent 为空（sessions 全空）时为 null——状态芯片
 * 优雅降级（TC-UI-03-4，不显示错误值）。
 */

import { create } from "zustand";
import { ALL_STATES, type NormalizedState } from "../lib/state";
import type { StatePayload } from "../lib/http-bridge";

interface PanelState {
  /** 当前合并显示状态（默认 idle）。 */
  kind: NormalizedState;
  /** 归属 agent；null = 未知/全空（芯片降级）。 */
  agent: string | null;
  set: (kind: NormalizedState, agent: string | null) => void;
}

export const usePanelStore = create<PanelState>((set) => ({
  kind: "idle",
  agent: null,
  set: (kind, agent) => set({ kind, agent }),
}));

function applyPayload(p: StatePayload): void {
  usePanelStore.getState().set(p.kind, p.agent);
}

/**
 * panel 窗初始化（Panel.tsx 挂载时调用一次；非 Tauri 环境静默）：
 * 初始查询 + 订阅 `pulsepet://state` 实时跟随（TC-UI-03-2/TC-UI-06）。
 */
export async function initPanelStore(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    const dto = await invoke<unknown>("get_display_state");
    const kind = (dto as { kind?: unknown } | null)?.kind;
    const agent = (dto as { agent?: unknown } | null)?.agent;
    if (
      typeof kind === "string" &&
      ALL_STATES.includes(kind as NormalizedState)
    ) {
      applyPayload({
        kind: kind as NormalizedState,
        agent: typeof agent === "string" && agent ? agent : null,
      });
    }
  } catch {
    // 命令不可用时静默（事件监听照常）
  }
  const { listen } = await import("@tauri-apps/api/event");
  await listen("pulsepet://state", (event) => {
    const p = event.payload as { kind?: unknown; agent?: unknown } | null;
    const kind = p?.kind;
    if (
      typeof kind === "string" &&
      ALL_STATES.includes(kind as NormalizedState)
    ) {
      applyPayload({
        kind: kind as NormalizedState,
        agent:
          typeof p?.agent === "string" && p.agent ? (p.agent as string) : null,
      });
    }
  });
}
