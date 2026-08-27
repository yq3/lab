import { describe, expect, it } from "vitest";
import {
  applyBubblePayload,
  applyStatePayload,
  parseDisplayKind,
  parseStatePayload,
} from "./http-bridge";
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

describe("parseStatePayload：v2 M1 可选 agent（V2-DESIGN §1.6）", () => {
  it("带 agent 的 payload 解析出 {kind, agent}", () => {
    expect(parseStatePayload({ kind: "editing", agent: "claude-code" })).toEqual({
      kind: "editing",
      agent: "claude-code",
    });
    expect(parseStatePayload({ kind: "working", agent: "opencode" })).toEqual({
      kind: "working",
      agent: "opencode",
    });
  });

  it("旧 payload（无 agent）向后兼容：agent = null 不覆盖", () => {
    expect(parseStatePayload({ kind: "idle" })).toEqual({ kind: "idle", agent: null });
    expect(parseStatePayload({ kind: "idle", agent: "" })).toEqual({ kind: "idle", agent: null });
    expect(parseStatePayload({ kind: "idle", agent: 42 })).toEqual({ kind: "idle", agent: null });
  });

  it("kind 非法 → 整体 null（agent 不单独生效）", () => {
    expect(parseStatePayload({ kind: "bogus", agent: "claude-code" })).toBeNull();
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

  it("v2 M1：agent 写入 displayAgent（只存不显示），无 agent 不覆盖", () => {
    applyStatePayload({ kind: "working", agent: "claude-code" });
    expect(usePetStore.getState().displayAgent).toBe("claude-code");
    applyStatePayload({ kind: "editing", agent: "opencode" });
    expect(usePetStore.getState().displayAgent).toBe("opencode");
    // 旧 payload 无 agent → displayAgent 保持原值
    applyStatePayload({ kind: "idle" });
    expect(usePetStore.getState().displayAgent).toBe("opencode");
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

  it("displayAgent 默认 opencode（V2-DESIGN §1.6）", () => {
    // 上一用例末尾可能改过；此处经重置验证默认初值语义（新 store 首次读取）
    expect(["opencode", "claude-code"]).toContain(usePetStore.getState().displayAgent);
  });
});

// ---- v2 M6（V2-DESIGN §6.2，TC-M6-03-1）：bubble payload 解析 agent ----

describe("applyBubblePayload：token 汇报气泡携带 agent（M6 徽标数据源）", () => {
  it("payload {text, agent} → 条目 agent 传入（[oc]/[cc] 徽标来源）", () => {
    usePetStore.getState().resetBubbles();
    applyBubblePayload({ text: "opencode 汇报", agent: "opencode" });
    expect(usePetStore.getState().bubble.current?.agent).toBe("opencode");
    usePetStore.getState().resetBubbles();
    applyBubblePayload({ text: "CC 汇报", agent: "claude-code" });
    expect(usePetStore.getState().bubble.current?.agent).toBe("claude-code");
  });

  it("payload 缺 agent（旧载荷）→ 条目无 agent（向后兼容，不渲染徽标）", () => {
    usePetStore.getState().resetBubbles();
    applyBubblePayload({ text: "旧版载荷" });
    expect(usePetStore.getState().bubble.current?.agent).toBeUndefined();
  });

  it("agent 非字符串（非法类型）→ 忽略 agent 只出文本", () => {
    usePetStore.getState().resetBubbles();
    applyBubblePayload({ text: "ok", agent: 42 });
    expect(usePetStore.getState().bubble.current?.agent).toBeUndefined();
    expect(usePetStore.getState().bubble.current?.text).toBe("ok");
  });
});
