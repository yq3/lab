/**
 * interaction：M6 交互模式（穿透开/关）TS 侧封装（DESIGN §6.3/§7.1，TC-APP-07/12）。
 *
 * 穿透状态唯一权威在 Rust（`src-tauri/src/interaction.rs`，持久化 app_state
 * `pet.pass_through`）；本模块提供：
 * - 事件名常量 + 载荷解析（`pulsepet://pass-through`，热键/托盘/设置三通道
 *   切换后 Rust 广播，TC-WIN-05 状态同步）；
 * - invoke 封装（动态 import + isTauriRuntime 守卫，vitest/node 可裸跑）；
 * - `initInteractionBridge`：启动查询 + 事件订阅 → petStore（pet/panel 都跑，
 *   panel 的设置开关依赖同一 store 位）。
 */

import { isTauriRuntime } from "./token-stats";
import { usePetStore } from "../pet/petStore";

/** Rust 广播穿透状态变化的 Tauri event 名。 */
export const PASS_THROUGH_EVENT = "pulsepet://pass-through";

/** Rust `panel_open(tab)` 打开面板后通知面板切 tab 的 event 名。 */
export const PANEL_TAB_EVENT = "panel://tab";

/** 解析 `pulsepet://pass-through` 载荷；非法 → null（不误更新状态）。 */
export function parsePassThroughEnabled(payload: unknown): boolean | null {
  if (typeof payload === "object" && payload !== null && "enabled" in payload) {
    const v = (payload as { enabled: unknown }).enabled;
    if (typeof v === "boolean") return v;
  }
  return null;
}

/** 穿透状态人读描述（设置页提示/测试断言用）。 */
export function describePassThrough(passThrough: boolean): string {
  return passThrough
    ? "穿透开：纯展示（鼠标穿透，不可拖拽/右键）"
    : "穿透关：可交互（可拖拽/右键）";
}

/** Panel tab 白名单（PetMenu「设置…」→ panel 设置页；todo M7 前不存在）。 */
export type PanelTab = "token" | "reminders" | "settings";

/** 校验 tab 字符串；非法（含 M7 前不存在的 todo）→ null。 */
export function normalizeTab(tab: unknown): PanelTab | null {
  if (tab === "token" || tab === "reminders" || tab === "settings") return tab;
  return null;
}

/** 查询当前穿透状态（Rust 唯一权威）。 */
export async function fetchPassThrough(): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("pet_get_pass_through");
}

/** 设置穿透状态（Rust 侧应用窗口 + 持久化 + 广播事件 + 同步托盘勾选）。 */
export async function setPassThrough(enabled: boolean): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("pet_set_pass_through", { enabled });
}

/** 开始原生窗口拖拽（pet 窗口；超过拖拽阈值时由 PetCanvas 调用）。 */
export async function startPetDrag(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("pet_start_drag");
}

/** 切换宠物可见性（PetMenu「隐藏宠物」；与托盘左键同语义）。 */
export async function togglePetVisible(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("pet_toggle_visible");
}

/** 打开控制面板（可选直达 tab；PetMenu「设置…」→ settings）。 */
export async function openPanel(tab?: PanelTab): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("panel_open", { tab: tab ?? null });
}

/**
 * 启动桥接：查询当前穿透状态 + 订阅变化事件 → petStore。
 * pet / panel 路由都初始化（panel 设置页开关依赖同一状态位）。
 * 非 Tauri 环境（vitest / 纯浏览器 dev）直接返回。
 */
export async function initInteractionBridge(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!isTauriRuntime()) return;
  try {
    const enabled = await fetchPassThrough();
    usePetStore.getState().setPassThrough(enabled);
  } catch (e) {
    console.error("[pulsepet] pass-through state query failed:", e);
  }
  const { listen } = await import("@tauri-apps/api/event");
  await listen(PASS_THROUGH_EVENT, (event) => {
    const v = parsePassThroughEnabled(event.payload);
    if (v !== null) usePetStore.getState().setPassThrough(v);
  });
}
