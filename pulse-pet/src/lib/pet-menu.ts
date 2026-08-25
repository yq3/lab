/**
 * pet-menu：M6 宠物右键菜单（PetMenu.tsx）的纯逻辑（TC-WIN-03）。
 *
 * pet 窗口只有 220×220：菜单是窗口内 DOM 浮层，必须 clamp 在窗口可视区内。
 * 菜单项与定位计算抽成纯函数供 vitest（node 环境，无 DOM）单测。
 *
 * M8 i18n：菜单文案经 `t()` 取当前语言（默认 zh；vitest 断言不受影响），
 * `lang` 可显式传入供测试。
 *
 * v2 M3（§3.4 ③）：入口层「今日 token」信息项——第 0 项三态（loading … /
 * ok 42M / error —），点击 → `openPanel("token")`（默认即今日，无缝衔接）。
 */

import { t, type Lang } from "./i18n";

export type PetMenuAction =
  | "today-token"
  | "settings"
  | "toggle-pass-through"
  | "hide-pet";

/** 「今日 token」信息项三态（数据来自 token_stats_today 的 30s 缓存）。 */
export type TodayTokenState =
  | { status: "loading" }
  | { status: "ok"; text: string }
  | { status: "error" };

export interface PetMenuItem {
  id: PetMenuAction;
  label: string;
  /** v2 M3：信息项（今日 token）与行为项分隔线样式区分（§3.4 ③）。 */
  info?: boolean;
}

/** 三态 → label 插值 v（… / 42M / —）。 */
export function todayTokenValue(state: TodayTokenState): string {
  switch (state.status) {
    case "loading":
      return "…";
    case "ok":
      return state.text;
    case "error":
      return "—";
  }
}

/**
 * 菜单项（非穿透态弹出；穿透态下 contextmenu 事件透出，本菜单不可达，
 * TC-WIN-04）：
 * - 今日 token（v2 M3 入口层）：三态信息项，点击 → openPanel("token")；
 * - 设置：打开控制面板设置页（panel://tab 事件）；
 * - 切换交互模式：穿透开/关（与热键 ⌘/Ctrl+Shift+Alt+P、托盘菜单同一 Rust
 *   状态，三通道同步，TC-WIN-05）；
 * - 隐藏宠物：与托盘左键同一 toggle（TC-APP-03 语义）。
 */
export function buildPetMenuItems(
  passThrough: boolean,
  todayToken: TodayTokenState,
  lang?: Lang,
): PetMenuItem[] {
  return [
    {
      id: "today-token",
      label: t("menu.todayToken", { v: todayTokenValue(todayToken) }, lang),
      info: true,
    },
    { id: "settings", label: t("menu.settings", undefined, lang) },
    {
      id: "toggle-pass-through",
      label: t(
        "menu.togglePass",
        { state: t(passThrough ? "menu.passOn" : "menu.passOff", undefined, lang) },
        lang,
      ),
    },
    { id: "hide-pet", label: t("menu.hidePet", undefined, lang) },
  ];
}

/**
 * 把菜单左上角 clamp 到窗口内（留 2px 安全边距）。菜单比窗口大时退化为
 * 贴左上角安全边距，不 panic。
 */
export function clampMenuPosition(
  x: number,
  y: number,
  windowSize: number,
  menuW: number,
  menuH: number,
): { x: number; y: number } {
  const pad = 2;
  const maxX = windowSize - menuW - pad;
  const maxY = windowSize - menuH - pad;
  return {
    x: Math.max(pad, Math.min(x, Math.max(pad, maxX))),
    y: Math.max(pad, Math.min(y, Math.max(pad, maxY))),
  };
}
