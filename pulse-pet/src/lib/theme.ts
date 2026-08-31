/**
 * theme：v2 M2 主题机制前端（V2-DESIGN §2.3，TC-UI-01/02）。
 *
 * - `resolveTheme(preference, systemDark)` 纯函数：手动选择 > 系统偏好；
 *   auto → `prefers-color-scheme`（监听即时联动）；
 * - `<html data-theme="light|dark">` 挂载（tokens.css 的 `[data-theme="dark"]`
 *   覆盖块；无属性 = 浅色默认）；**主题只作用 panel 窗**（pet 窗气泡/菜单走
 *   `--pet-world-*` 固定色，不随主题）；
 * - 持久化在 Rust（app_state `ui.theme`，缺省 auto）：`initThemeBridge` 拉取
 *   + 订阅 `ui://theme`；`setThemePreference` 本地立即生效 + invoke 持久化
 *   （失败回滚，与 changeLanguage 同纪律）；
 * - 已知边界（R9）：深色用户冷加载先闪一帧浅色（FOUC）——接受不修。
 */

import { create } from "zustand";

export type ThemePreference = "auto" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

/** Rust 广播主题偏好变化的 Tauri event 名（theme.rs `ui_set_theme` 下发）。 */
export const THEME_EVENT = "ui://theme";

/** 解析实际主题：auto 跟随系统；手动选择覆盖系统偏好。 */
export function resolveTheme(
  preference: ThemePreference,
  systemDark: boolean,
): ResolvedTheme {
  if (preference === "light") return "light";
  if (preference === "dark") return "dark";
  return systemDark ? "dark" : "light";
}

/** 解析偏好值（非法/空 → null，回退 auto；与 Rust parse_theme 同口径）。 */
export function parseThemePreference(v: unknown): ThemePreference | null {
  return v === "auto" || v === "light" || v === "dark" ? v : null;
}

/** 应用主题到 <html data-theme>（非 DOM 环境 no-op，vitest/node 可裸跑）。 */
export function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined" || !document.documentElement) return;
  document.documentElement.dataset.theme = resolved;
}

function systemDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

interface ThemeState {
  preference: ThemePreference;
  setPreference: (p: ThemePreference) => void;
}

/** 偏好 store（默认 auto；initThemeBridge 以持久化值覆盖）。 */
export const useThemeStore = create<ThemeState>((set) => ({
  preference: "auto",
  setPreference: (p) => set({ preference: p }),
}));

/** 按当前偏好 + 系统偏好重算并应用（preference/system 变化时调用）。 */
function reapply(pref: ThemePreference): void {
  applyTheme(resolveTheme(pref, systemDark()));
}

function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as unknown as Record<string, unknown>)
  );
}

/**
 * panel 窗初始化：读持久化偏好（`ui_get_theme`，None → auto）→ 应用；
 * 订阅 `ui://theme`（设置页切换 → Rust 广播）与 `prefers-color-scheme`
 * （auto 时系统切换即时联动）。非 Tauri 环境静默返回。
 */
export async function initThemeBridge(): Promise<void> {
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    const persisted = await invoke<string | null>("ui_get_theme");
    const pref = parseThemePreference(persisted) ?? "auto";
    useThemeStore.getState().setPreference(pref);
    reapply(pref);
  } catch (e) {
    console.error("[pulsepet] load persisted theme failed:", e);
  }
  const { listen } = await import("@tauri-apps/api/event");
  await listen(THEME_EVENT, (event) => {
    const v = (event.payload as { theme?: unknown } | null)?.theme;
    const pref = parseThemePreference(v) ?? "auto";
    useThemeStore.getState().setPreference(pref);
    reapply(pref);
  });
  // auto 时系统深浅切换即时联动（手动 light/dark 不受影响）
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const pref = useThemeStore.getState().preference;
      if (pref === "auto") reapply(pref);
    };
    mq.addEventListener?.("change", onChange);
  }
}

/**
 * 设置页切换偏好：本地立即生效 → invoke `ui_set_theme`（Rust 持久化 + 广播）。
 * invoke 失败回滚本地 store（写失败不静默——与 changeLanguage 同纪律）。
 */
export async function setThemePreference(pref: ThemePreference): Promise<void> {
  const prev = useThemeStore.getState().preference;
  useThemeStore.getState().setPreference(pref);
  reapply(pref);
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    await invoke("ui_set_theme", { theme: pref });
  } catch (e) {
    console.error("[pulsepet] set theme failed:", e);
    useThemeStore.getState().setPreference(prev);
    reapply(prev);
    throw e;
  }
}
