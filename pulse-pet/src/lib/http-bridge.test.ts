import { describe, expect, it } from "vitest";
import { applyStatePayload, parseDisplayKind } from "./http-bridge";
import { usePetStore } from "../pet/petStore";
import { ALL_STATES } from "./state";

describe("parseDisplayKind：解析 Rust 下发的合并显示状态", () => {
  it("解析合法 kind", () => {
    expect(parseDisplayKind({ kind: "working" })).toBe("working");
    expect(parseDisplayKind({ kind: "waiting-permission" })).toBe("waiting-permission");
  });

  it("非法 payload 返回 null", () => {
    expect(parseDisplayKind(null)).toBeNull();
    expect(parseDisplayKind(undefined)).toBeNull();
    expect(parseDisplayKind({ kind: "sprinting" })).toBeNull();
    expect(parseDisplayKind({ kind: 123 })).toBeNull();
    expect(parseDisplayKind("working")).toBeNull();
  });
});

describe("applyStatePayload：event → petStore（含 8→5 降级）", () => {
  it("写入 store 的 raw 与 sprite", () => {
    applyStatePayload({ kind: "testing" });
    const s = usePetStore.getState();
    expect(s.raw).toBe("testing");
    expect(s.sprite).toBe("working"); // testing → working 降级

    applyStatePayload({ kind: "error" });
    expect(usePetStore.getState().sprite).toBe("error");

    // 复位回 idle，避免影响其它测试
    applyStatePayload({ kind: "idle" });
    expect(usePetStore.getState().raw).toBe("idle");
  });

  it("非法 payload 不改变 store 状态", () => {
    applyStatePayload({ kind: "idle" });
    applyStatePayload({ kind: "bogus" });
    expect(usePetStore.getState().raw).toBe("idle");
  });

  it("8 种归一化状态均可被 bridge 接收", () => {
    for (const kind of ALL_STATES) {
      applyStatePayload({ kind });
      expect(usePetStore.getState().raw).toBe(kind);
    }
    applyStatePayload({ kind: "idle" });
  });
});
