/**
 * 归一化状态与占位精灵状态的映射（DESIGN §6.1）。
 *
 * 归一化事件有 8 种状态（DESIGN §3.1），占位精灵只有 5 张画面（§6.1）：
 *   idle / thinking / working / success / error
 * 未覆盖的 3 个状态降级到最近同类：
 *   waiting-permission → thinking
 *   testing            → working
 *   editing            → working
 *
 * 该映射为纯函数，便于单测（TC-SP-01b）。
 */

export type NormalizedState =
  | "idle"
  | "thinking"
  | "working"
  | "editing"
  | "testing"
  | "waiting-permission"
  | "success"
  | "error";

export type SpriteState = "idle" | "thinking" | "working" | "success" | "error";

export const ALL_STATES: NormalizedState[] = [
  "idle",
  "thinking",
  "working",
  "editing",
  "testing",
  "waiting-permission",
  "success",
  "error",
];

const DEGRADE: Record<NormalizedState, SpriteState> = {
  idle: "idle",
  thinking: "thinking",
  working: "working",
  editing: "working",
  testing: "working",
  "waiting-permission": "thinking",
  success: "success",
  error: "error",
};

export function degradeState(raw: NormalizedState): SpriteState {
  return DEGRADE[raw];
}

export function nextState(current: NormalizedState): NormalizedState {
  const i = ALL_STATES.indexOf(current);
  return ALL_STATES[(i + 1) % ALL_STATES.length];
}
