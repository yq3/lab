/**
 * pet-drag：M6 宠物窗口拖拽的阈值判定（TC-WIN-01，DESIGN §6.3）。
 *
 * 策略：mousedown 只记录起点，移动超过阈值才调 `startDragging()`（Rust 命令
 * `pet_start_drag` → `WebviewWindow::start_dragging()`，走 OS 原生窗口拖拽，
 * 跨显示器由系统处理、不被单屏边缘卡住，TC-APP-11）。阈值判定独立成纯函数：
 * - 未超过阈值 = 点击（保留 M1 点击轮换状态 + TC-RM-04 点击确认气泡语义）；
 * - 超过阈值 = 拖拽（原生 drag loop 接管，松开即停，TC-WIN-01）。
 *
 * 穿透态（pass-through）下 webview 收不到任何鼠标事件（DESIGN §6.3：穿透态
 * 收不到 mousedown，"临时关穿透再拖"不成立）——调用方无需也不应再防御。
 */

/** 拖拽启动阈值（逻辑像素）：超过才视为拖拽，避免点击误触发。 */
export const DRAG_THRESHOLD_PX = 4;

/**
 * 是否达到拖拽启动条件：水平或垂直任一轴位移 ≥ 阈值（按轴判定，斜向轻移
 * 两轴各 3px 不叠加触发）。
 */
export function shouldStartDrag(
  startX: number,
  startY: number,
  x: number,
  y: number,
  threshold: number = DRAG_THRESHOLD_PX,
): boolean {
  return Math.abs(x - startX) >= threshold || Math.abs(y - startY) >= threshold;
}
