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
 * M1 阶段没有 HTTP 事件源（M2 引入），通过 `setRaw` / `next` 驱动状态，
 * 供占位精灵渲染与降级映射验证（TC-SP-01 / TC-SP-01b）。
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
