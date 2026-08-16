import { create } from "zustand";
import {
  degradeState,
  nextState,
  type NormalizedState,
  type SpriteState,
} from "../lib/state";
import { BUBBLE_AUTO_HIDE_MS, sanitizeBubbleText } from "../lib/bubble";
import type { AtlasMeta, AtlasPixels } from "../lib/atlas";

/** 当前展示的气泡（M3：token 会话汇报；M4 起复用于提醒文案）。 */
export interface BubbleState {
  text: string;
  /** 自增序号，供 React key 重建（重置自动隐藏计时）。 */
  id: number;
  /** M4：本气泡来自一条提醒时携带 reminder_log id（点击确认/自动消失回报用）。 */
  reminder?: { logId: number };
}

/**
 * 提醒气泡的消失方式回报（TC-RM-04/03）：
 * - "bubble"：用户点击宠物确认 → Rust `reminders_ack`（acked_at + dismissed_via）；
 * - "auto"：8s 自动消失（含被新气泡顶替）→ Rust `reminders_dismiss(via='auto')`。
 * 由 reminder-bridge 注册实现（petStore 不直接依赖 Tauri API，vitest 可裸跑）。
 */
export type ReminderReporter = (logId: number, via: "bubble" | "auto") => void;

interface PetState {
  /** 归一化原始状态（8 种）。 */
  raw: NormalizedState;
  /** 占位精灵状态（5 种，经 8→5 降级映射）。 */
  sprite: SpriteState;
  /** 气泡（null = 不显示）。 */
  bubble: BubbleState | null;
  /** M5：当前 atlas RGBA 图块（null = 无 atlas，占位 PNG 渲染）。 */
  atlas: AtlasPixels | null;
  /** M5：当前 atlas 元数据（含回退 notice；null = 未加载/非 Tauri）。 */
  atlasMeta: AtlasMeta | null;
  setRaw: (raw: NormalizedState) => void;
  next: () => void;
  /** M5：atlas 加载/热替换（atlas-bridge 调用；对象身份变化驱动 canvas 重建）。 */
  setAtlas: (meta: AtlasMeta, pixels: AtlasPixels | null) => void;
  /** 展示气泡（净化约束：单行 1-140；非法输入丢弃；8s 自动消失，DESIGN §5.2）。 */
  showBubble: (text: string) => void;
  hideBubble: () => void;
  /** M4：展示提醒气泡并挂 log_id（8s 自动消失回报 'auto'）。 */
  showReminderBubble: (text: string, logId: number) => void;
  /** M4：点击宠物"已确认"（TC-RM-04）；非提醒气泡时返回 false（交回状态轮换）。 */
  ackReminderBubble: () => boolean;
}

/** 气泡自动隐藏定时器（store 外置，避免进入响应式状态）。 */
let bubbleTimer: ReturnType<typeof setTimeout> | null = null;
let bubbleSeq = 0;
/** 提醒回报回调（reminder-bridge 注册；null = 无人在意，如 vitest/纯前端 dev）。 */
let reminderReporter: ReminderReporter | null = null;

/** 注册/清空提醒消失回报（reminder-bridge 初始化时调用一次）。 */
export function setReminderReporter(fn: ReminderReporter | null): void {
  reminderReporter = fn;
}

function reportReminder(b: BubbleState | null, via: "bubble" | "auto"): void {
  if (b?.reminder) {
    reminderReporter?.(b.reminder.logId, via);
  }
}

function clearBubbleTimer(): void {
  if (bubbleTimer) {
    clearTimeout(bubbleTimer);
    bubbleTimer = null;
  }
}

function armBubbleTimer(): void {
  clearBubbleTimer();
  bubbleTimer = setTimeout(() => {
    bubbleTimer = null;
    // 8s 自动消失：提醒气泡回报 dismissed_via='auto'（TC-RM-03）
    const cur = usePetStore.getState().bubble;
    reportReminder(cur, "auto");
    usePetStore.setState({ bubble: null });
  }, BUBBLE_AUTO_HIDE_MS);
}

/**
 * 宠物状态 store。
 *
 * M2 起主事件源：`src/lib/http-bridge.ts` 监听 Rust 下发的合并显示状态
 * （`pulsepet://state` event）→ 调 `setRaw` 更新。`setRaw` / `next` 仍保留，
 * 供占位精灵渲染、降级映射验证（TC-SP-01/01b）与测试 / CDP 手动驱动。
 *
 * M3 起 `pulsepet://bubble` event（token 会话汇报等）→ `showBubble`；
 * M4 起 `reminder://trigger` → `showReminderBubble`（经 reminder-bridge）。
 */
export const usePetStore = create<PetState>((set, get) => ({
  raw: "idle",
  sprite: "idle",
  bubble: null,
  atlas: null,
  atlasMeta: null,
  setAtlas: (meta, pixels) => set({ atlasMeta: meta, atlas: pixels }),
  setRaw: (raw) => set({ raw, sprite: degradeState(raw) }),
  next: () =>
    set((s) => {
      const raw = nextState(s.raw);
      return { raw, sprite: degradeState(raw) };
    }),
  showBubble: (text) => {
    const clean = sanitizeBubbleText(text);
    if (!clean) return; // 净化后为空 → 不出气泡（TC-TK-12：无内容不显示 0/陈旧）
    // 顶替提醒气泡时，旧的按自动消失回报（未确认）
    reportReminder(get().bubble, "auto");
    bubbleSeq += 1;
    set({ bubble: { text: clean, id: bubbleSeq } });
    armBubbleTimer();
  },
  hideBubble: () => {
    clearBubbleTimer();
    set({ bubble: null });
  },
  showReminderBubble: (text, logId) => {
    const clean = sanitizeBubbleText(text);
    if (!clean) {
      // 净化后无内容：不出气泡，直接按自动消失结案（不留无主日志行）
      reminderReporter?.(logId, "auto");
      return;
    }
    reportReminder(get().bubble, "auto");
    bubbleSeq += 1;
    set({ bubble: { text: clean, id: bubbleSeq, reminder: { logId } } });
    armBubbleTimer();
  },
  ackReminderBubble: () => {
    const cur = get().bubble;
    if (!cur?.reminder) return false;
    clearBubbleTimer();
    set({ bubble: null });
    reportReminder(cur, "bubble"); // TC-RM-04：acked_at + dismissed_via='bubble'
    return true;
  },
}));
