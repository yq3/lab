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

/**
 * 拖拽/点击判定状态机（R2 修复，用户反馈：拖拽结束后附加了一次左键单击效果）。
 *
 * 根因：超阈值启动 `start_dragging()`（OS 原生窗口拖拽）后，松开鼠标时 macOS
 * WKWebView 的 pointer 流不会被取消（无 pointercancel），浏览器把该按下-抬起
 * 序列补发成完整 `pointerup` + `click`——若不区分，`onClick` 的状态轮换
 *（M1 单击语义）会在每次拖拽后误触发一次。
 *
 * 本类把"本轮按下是否发生过拖拽"独立成可单测的纯逻辑：
 * - `onPointerDown(x, y)` 记录起点并重置抑制标志（兜底：平台不补发 click 时
 *   标志不残留到下一次真实单击）；
 * - `onPointerMove(x, y)` 首次超阈值返回 true（调用方启动原生拖拽，只此一次），
 *   并置抑制标志；
 * - `onPointerUp()` 结束本轮；
 * - `shouldSuppressClick()` 读一次即消费：拖拽尾巴的 click 吞掉一次，之后的
 *   真实单击正常放行。
 *
 * 仅主键（button 0）路径使用；右键（contextmenu，无 click）与穿透态（收不到
 * 事件）不受影响。
 */
export class DragClickGuard {
  private start: { x: number; y: number } | null = null;
  private dragging = false;
  private suppressClick = false;

  onPointerDown(x: number, y: number): void {
    this.start = { x, y };
    this.dragging = false;
    this.suppressClick = false;
  }

  /** 返回 true = 应启动原生窗口拖拽（每轮按下至多一次）。 */
  onPointerMove(x: number, y: number): boolean {
    const start = this.start;
    if (!start || this.dragging) return false;
    if (shouldStartDrag(start.x, start.y, x, y)) {
      this.dragging = true;
      this.suppressClick = true;
      return true;
    }
    return false;
  }

  onPointerUp(): void {
    this.start = null;
    this.dragging = false;
  }

  /** 本次 click 是否应被吞掉（拖拽尾巴）；读一次即消费。 */
  shouldSuppressClick(): boolean {
    const s = this.suppressClick;
    this.suppressClick = false;
    return s;
  }
}

/**
 * 点击 → 状态轮换 的总判定（R3 P1，纯函数供单测）。
 *
 * P1 根因：PetMenu 曾以 document **capture** 阶段监听 pointerdown 先关菜单，
 * click 时读实时 `contextMenu` 恒为 null → "菜单开时点画布仅关菜单"防线失效，
 * 每次关菜单误轮换一次（气泡时还会误 ack）。
 *
 * 修复后的时序约定（组件层保证）：
 * - PetMenu 的 document pointerdown 监听走**冒泡**阶段（React root 在 #root、
 *   document 之下，canvas 的 React onPointerDown 先于 PetMenu 关菜单执行）；
 * - canvas `onPointerDown` 快照菜单开态（PetMenu 关闭前读到 true）；
 * - `onClick` 用本函数判定：拖拽尾巴（R2）或快照菜单开 → 不轮换。
 */
export interface ClickGateInput {
  /** R2：DragClickGuard.shouldSuppressClick() 的返回值（已消费）。 */
  dragTail: boolean;
  /** R3：本次按下的 pointerdown 时刻（PetMenu 关菜单前）菜单是否打开。 */
  menuOpenAtPointerDown: boolean;
}

/** 返回 true = 本次 click 应执行状态轮换（无提醒气泡时）语义。 */
export function shouldRotateOnClick(gate: ClickGateInput): boolean {
  return !gate.dragTail && !gate.menuOpenAtPointerDown;
}
