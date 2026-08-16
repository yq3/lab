import { create } from "zustand";
import {
  degradeState,
  nextState,
  type NormalizedState,
  type SpriteState,
} from "../lib/state";
import { BUBBLE_AUTO_HIDE_MS, sanitizeBubbleText } from "../lib/bubble";

/** 当前展示的气泡（M3：token 会话汇报等；null = 无气泡）。 */
export interface BubbleState {
  text: string;
  /** 自增序号，供 React key 重建（重置自动隐藏计时）。 */
  id: number;
}

interface PetState {
  /** 归一化原始状态（8 种）。 */
  raw: NormalizedState;
  /** 占位精灵状态（5 种，经 8→5 降级映射）。 */
  sprite: SpriteState;
  /** 气泡（null = 不显示）。 */
  bubble: BubbleState | null;
  setRaw: (raw: NormalizedState) => void;
  next: () => void;
  /** 展示气泡（净化约束：单行 1-140；非法输入丢弃；8s 自动消失，DESIGN §5.2）。 */
  showBubble: (text: string) => void;
  hideBubble: () => void;
}

/** 气泡自动隐藏定时器（store 外置，避免进入响应式状态）。 */
let bubbleTimer: ReturnType<typeof setTimeout> | null = null;
let bubbleSeq = 0;

/**
 * 宠物状态 store。
 *
 * M2 起主事件源：`src/lib/http-bridge.ts` 监听 Rust 下发的合并显示状态
 * （`pulsepet://state` event）→ 调 `setRaw` 更新。`setRaw` / `next` 仍保留，
 * 供占位精灵渲染、降级映射验证（TC-SP-01/01b）与测试 / CDP 手动驱动。
 *
 * M3 起 `pulsepet://bubble` event（token 会话汇报等）→ `showBubble`。
 */
export const usePetStore = create<PetState>((set) => ({
  raw: "idle",
  sprite: "idle",
  bubble: null,
  setRaw: (raw) => set({ raw, sprite: degradeState(raw) }),
  next: () =>
    set((s) => {
      const raw = nextState(s.raw);
      return { raw, sprite: degradeState(raw) };
    }),
  showBubble: (text) => {
    const clean = sanitizeBubbleText(text);
    if (!clean) return; // 净化后为空 → 不出气泡（TC-TK-12：无内容不显示 0/陈旧）
    bubbleSeq += 1;
    set({ bubble: { text: clean, id: bubbleSeq } });
    if (bubbleTimer) clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(() => {
      bubbleTimer = null;
      set({ bubble: null });
    }, BUBBLE_AUTO_HIDE_MS);
  },
  hideBubble: () => {
    if (bubbleTimer) {
      clearTimeout(bubbleTimer);
      bubbleTimer = null;
    }
    set({ bubble: null });
  },
}));
