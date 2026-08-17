/**
 * pet-menu：M6 宠物右键菜单（PetMenu.tsx）的纯逻辑（TC-WIN-03）。
 *
 * pet 窗口只有 220×220：菜单是窗口内 DOM 浮层，必须 clamp 在窗口可视区内。
 * 菜单项与定位计算抽成纯函数供 vitest（node 环境，无 DOM）单测。
 */

export type PetMenuAction = "settings" | "toggle-pass-through" | "hide-pet";

export interface PetMenuItem {
  id: PetMenuAction;
  label: string;
}

/**
 * 菜单项（非穿透态弹出；穿透态下 contextmenu 事件透出，本菜单不可达，
 * TC-WIN-04）：
 * - 设置：打开控制面板设置页（panel://tab 事件）；
 * - 切换交互模式：穿透开/关（与热键 ⌘/Ctrl+Shift+Alt+P、托盘菜单同一 Rust
 *   状态，三通道同步，TC-WIN-05）；
 * - 隐藏宠物：与托盘左键同一 toggle（TC-APP-03 语义）。
 */
export function buildPetMenuItems(passThrough: boolean): PetMenuItem[] {
  return [
    { id: "settings", label: "设置…" },
    {
      id: "toggle-pass-through",
      label: `切换交互模式（穿透：${passThrough ? "开" : "关"}）`,
    },
    { id: "hide-pet", label: "隐藏宠物" },
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
