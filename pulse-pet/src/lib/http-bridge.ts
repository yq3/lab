/**
 * http-bridge：收来自 Rust 的 Tauri event（事件 → petStore），DESIGN §9 / §3.3。
 *
 * Rust 侧 `session_state` 已做多 session 优先级合并，经 Tauri event `pulsepet://state`
 * 下发合并后的显示状态（payload = `{kind, agent?}`；v2 M1 起携带归属 agent，
 * 向后兼容旧 payload 只读 kind）。本模块：
 *   1. 初始化时查一次 `get_display_state`（避免启动时错过已发生的状态）；
 *   2. 监听 `pulsepet://state`，把 `kind` 写入 petStore、可选 `agent` 写入
 *      `petStore.displayAgent`（只存不显示，V2-DESIGN §1.6）；
 *   3. M3：监听 `pulsepet://bubble`（token 会话汇报等，payload = `{text}`）→
 *      `showBubble`（内部做单行 1-140 净化）。
 *
 * 与 @tauri-apps/api 的交互用动态 import + 运行时探测，使纯函数（parseDisplayKind /
 * parseStatePayload / applyStatePayload / parseBubblePayload）可在 vitest(node) 下直接单测。
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

/** 解析后的显示状态（agent 可选——v2 M1 payload 变更，缺省 null 不覆盖）。 */
export interface StatePayload {
  kind: NormalizedState;
  agent: string | null;
}

/** 解析 `pulsepet://state` payload：`{kind, agent?}`（kind 非法 → null）。 */
export function parseStatePayload(payload: unknown): StatePayload | null {
  const kind = parseDisplayKind(payload);
  if (!kind) return null;
  const agent =
    typeof payload === "object" && payload !== null
      ? (payload as { agent?: unknown }).agent
      : undefined;
  return { kind, agent: typeof agent === "string" && agent ? agent : null };
}

/** 解析后的启动查询结果（get_display_state 返回 `{kind, agent}`——v2 M2 拉前）。 */
export function parseDisplayStatePayload(payload: unknown): StatePayload | null {
  return parseStatePayload(payload);
}

/** 把 payload 应用到 petStore（含 8→5 降级映射；agent 只存不显示）。 */
export function applyStatePayload(payload: unknown): void {
  const parsed = parseStatePayload(payload);
  if (!parsed) return;
  const store = usePetStore.getState();
  store.setRaw(parsed.kind);
  if (parsed.agent) store.setDisplayAgent(parsed.agent);
}

/** 从 `pulsepet://bubble` payload 提取气泡文案（非字符串 → null，不出气泡）。 */
export function parseBubblePayload(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const text = (payload as { text?: unknown }).text;
  return typeof text === "string" && text.length > 0 ? text : null;
}

/**
 * 把气泡 payload 应用到 petStore（v2 M2：token 会话汇报 = **info 级**、
 * source="token-report"，经排队模型合并展示——§2.6.2；pushBubble 内部净化，
 * 空文案丢弃）。
 */
export function applyBubblePayload(payload: unknown): void {
  const text = parseBubblePayload(payload);
  if (text) {
    usePetStore
      .getState()
      .pushBubble({ text, level: "info", source: "token-report" });
  }
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

  // 初始查询当前显示状态（v2 M2：返回 {kind, agent}——面板芯片/宠物初开即正确）
  try {
    const dto = await invoke<unknown>("get_display_state");
    const parsed = parseDisplayStatePayload(dto);
    if (parsed) {
      const store = usePetStore.getState();
      store.setRaw(parsed.kind);
      if (parsed.agent) store.setDisplayAgent(parsed.agent);
    }
  } catch {
    // App 侧命令不可用时静默（不影响事件监听）
  }

  await listen("pulsepet://state", (event) => {
    applyStatePayload(event.payload);
  });

  // M3：token 会话汇报气泡（idle + 有用量时 Rust 侧下发）
  await listen("pulsepet://bubble", (event) => {
    applyBubblePayload(event.payload);
  });
}
