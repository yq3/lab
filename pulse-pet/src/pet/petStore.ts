import { create } from "zustand";
import {
  degradeState,
  nextState,
  type NormalizedState,
  type SpriteState,
} from "../lib/state";

interface PetState {
  /** 归一化原始状态（8 种）。 */
  raw: NormalizedState;
  /** 占位精灵状态（5 种，经 8→5 降级映射）。 */
  sprite: SpriteState;
  setRaw: (raw: NormalizedState) => void;
  next: () => void;
}

/**
 * 宠物状态 store。
 *
 * M2 起主事件源：`src/lib/http-bridge.ts` 监听 Rust 下发的合并显示状态
 * （`pulsepet://state` event）→ 调 `setRaw` 更新。`setRaw` / `next` 仍保留，
 * 供占位精灵渲染、降级映射验证（TC-SP-01/01b）与测试 / CDP 手动驱动。
 */
export const usePetStore = create<PetState>((set) => ({
  raw: "idle",
  sprite: "idle",
  setRaw: (raw) => set({ raw, sprite: degradeState(raw) }),
  next: () =>
    set((s) => {
      const raw = nextState(s.raw);
      return { raw, sprite: degradeState(raw) };
    }),
}));
