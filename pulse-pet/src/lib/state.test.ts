import { describe, expect, it } from "vitest";
import {
  ALL_STATES,
  degradeState,
  nextState,
  type NormalizedState,
} from "./state";

describe("degradeState：占位阶段 8→5 降级映射（TC-SP-01b）", () => {
  it("5 个直映状态保持原样", () => {
    expect(degradeState("idle")).toBe("idle");
    expect(degradeState("thinking")).toBe("thinking");
    expect(degradeState("working")).toBe("working");
    expect(degradeState("success")).toBe("success");
    expect(degradeState("error")).toBe("error");
  });

  it("3 个未覆盖状态降级到最近同类", () => {
    expect(degradeState("waiting-permission")).toBe("thinking");
    expect(degradeState("testing")).toBe("working");
    expect(degradeState("editing")).toBe("working");
  });

  it("8 种归一化状态全部可映射，无 undefined（无空白画面）", () => {
    for (const s of ALL_STATES) {
      const out = degradeState(s);
      expect(["idle", "thinking", "working", "success", "error"]).toContain(out);
    }
    expect(ALL_STATES).toHaveLength(8);
  });
});

describe("nextState：状态循环驱动（M1 手动验证用）", () => {
  it("按 8 状态顺序循环", () => {
    expect(nextState("idle")).toBe("thinking");
    expect(nextState("thinking")).toBe("working");
    expect(nextState("error")).toBe("idle");
  });

  it("覆盖全部 8 状态", () => {
    const seen = new Set<NormalizedState>();
    let cur: NormalizedState = "idle";
    for (let i = 0; i < 8; i++) {
      seen.add(cur);
      cur = nextState(cur);
    }
    expect(cur).toBe("idle");
    expect(seen.size).toBe(8);
  });
});
