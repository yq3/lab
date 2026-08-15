import { describe, expect, it } from "vitest";
import { OpenCodeAdapter, normalizeRawKind } from "./opencode";
import { ALL_STATES } from "../state";

describe("OpenCodeAdapter.normalizeRawKind：归一化映射（TC-EV-04）", () => {
  it("session.status idle → idle（状态复位主信号）", () => {
    expect(
      normalizeRawKind({ type: "session.status", properties: { status: { type: "idle" } } }),
    ).toBe("idle");
  });

  it("session.status 其它（busy/retry）→ working", () => {
    expect(
      normalizeRawKind({ type: "session.status", properties: { status: { type: "busy" } } }),
    ).toBe("working");
    expect(
      normalizeRawKind({ type: "session.status", properties: { status: { type: "retry" } } }),
    ).toBe("working");
  });

  it("session.idle → idle；session.error → error", () => {
    expect(normalizeRawKind({ type: "session.idle" })).toBe("idle");
    expect(normalizeRawKind({ type: "session.error" })).toBe("error");
  });

  it("chat.message → thinking；permission.ask → waiting-permission", () => {
    expect(normalizeRawKind({ type: "chat.message" })).toBe("thinking");
    expect(normalizeRawKind({ type: "permission.ask" })).toBe("waiting-permission");
  });

  it("编辑类工具 → editing", () => {
    for (const tool of ["edit", "write", "patch", "apply_patch"]) {
      expect(normalizeRawKind({ type: "tool.execute.before", tool })).toBe("editing");
    }
  });

  it("bash 类工具 + 测试命令 → testing；非测试命令 → working", () => {
    expect(
      normalizeRawKind({ type: "tool.execute.before", tool: "bash", args: { command: "npm test" } }),
    ).toBe("testing");
    expect(
      normalizeRawKind({ type: "tool.execute.before", tool: "bash", args: { command: "ls -la" } }),
    ).toBe("working");
  });

  it("其它工具 → working；tool.execute.after → working（复位）", () => {
    expect(normalizeRawKind({ type: "tool.execute.before", tool: "read" })).toBe("working");
    expect(normalizeRawKind({ type: "tool.execute.after", tool: "edit" })).toBe("working");
  });

  it("自忽略工具被跳过（防回环，TC-EV-19）", () => {
    expect(
      normalizeRawKind({ type: "tool.execute.before", tool: "pulsepet_say" }),
    ).toBeNull();
    expect(
      normalizeRawKind({ type: "tool.execute.before", tool: "pulsepet_status" }),
    ).toBeNull();
    expect(
      normalizeRawKind({ type: "tool.execute.before", tool: "pulsepet_react" }),
    ).toBeNull();
  });
});

describe("OpenCodeAdapter 抽象存在性（TC-EV-23）", () => {
  it("接口字段齐全", () => {
    expect(OpenCodeAdapter.id).toBe("opencode");
    expect(OpenCodeAdapter.tokenSource).toBe("opencode-sqlite");
    expect(OpenCodeAdapter.iconSet).toBe("opencode");
    expect(typeof OpenCodeAdapter.normalizeRawEvent).toBe("function");
  });

  it("normalizeRawEvent 返回 NormalizedEvent，kind 全部在 8 状态内", () => {
    const ev = OpenCodeAdapter.normalizeRawEvent({
      type: "tool.execute.before",
      tool: "edit",
      sessionID: "abc123",
    });
    expect(ev).not.toBeNull();
    expect(ev!.sessionId).toBe("abc123");
    expect(ev!.kind).toBe("editing");
    expect(ALL_STATES).toContain(ev!.kind);
  });

  it("不可分类的原始事件返回 null", () => {
    expect(OpenCodeAdapter.normalizeRawEvent({ type: "unknown.thing" })).toBeNull();
    expect(OpenCodeAdapter.normalizeRawEvent(null)).toBeNull();
  });
});
