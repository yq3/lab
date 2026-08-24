import { describe, expect, it } from "vitest";
import { ClaudeCodeAdapter, normalizeRawKind } from "./claude-code";

/** CC hook input 构造。 */
function cc(event: string, extra: Record<string, unknown> = {}) {
  return { hook_event_name: event, session_id: "uuid-1", ...extra };
}

describe("ClaudeCodeAdapter（V2-DESIGN §1.6，与 claude-code-hook.js 一一对应）", () => {
  it("八事件映射 + PreToolUse 工具分类与 hook 脚本一致（TC-INT-01 前端兜底）", () => {
    expect(normalizeRawKind(cc("SessionStart"))).toBe("idle");
    expect(normalizeRawKind(cc("UserPromptSubmit"))).toBe("thinking");
    expect(normalizeRawKind(cc("PreToolUse", { tool_name: "Edit" }))).toBe("editing");
    expect(normalizeRawKind(cc("PreToolUse", { tool_name: "NotebookEdit" }))).toBe("editing");
    expect(
      normalizeRawKind(cc("PreToolUse", { tool_name: "Bash", tool_input: { command: "cargo test" } })),
    ).toBe("testing");
    expect(
      normalizeRawKind(cc("PreToolUse", { tool_name: "Bash", tool_input: { command: "ls" } })),
    ).toBe("working");
    expect(normalizeRawKind(cc("PreToolUse", { tool_name: "Read" }))).toBe("working");
    expect(normalizeRawKind(cc("PostToolUse"))).toBe("working");
    expect(normalizeRawKind(cc("PostToolUseFailure"))).toBe("error");
    expect(normalizeRawKind(cc("PermissionRequest"))).toBe("waiting-permission");
    expect(normalizeRawKind(cc("Stop"))).toBe("idle");
    expect(normalizeRawKind(cc("StopFailure"))).toBe("error");
    // 不注册的事件
    expect(normalizeRawKind(cc("Notification"))).toBeNull();
    expect(normalizeRawKind(cc("SubagentStart"))).toBeNull();
    expect(normalizeRawKind(cc("SessionEnd"))).toBeNull();
    expect(normalizeRawKind({ session_id: "x" })).toBeNull();
  });

  it("normalizeRawEvent：缺 session_id 丢弃（不落 default）；完整事件带 agent", () => {
    expect(ClaudeCodeAdapter.normalizeRawEvent({ hook_event_name: "Stop" })).toBeNull();
    expect(ClaudeCodeAdapter.normalizeRawEvent(cc("Stop", { session_id: "" }))).toBeNull();
    expect(ClaudeCodeAdapter.normalizeRawEvent(cc("UserPromptSubmit"))).toEqual({
      sessionId: "uuid-1",
      kind: "thinking",
      agent: "claude-code",
    });
  });

  it("adapter 元数据（tokenSource M5 兑现、iconSet）", () => {
    expect(ClaudeCodeAdapter.id).toBe("claude-code");
    expect(ClaudeCodeAdapter.tokenSource).toBe("transcript-incremental");
    expect(ClaudeCodeAdapter.iconSet).toBe("claude-code");
  });
});
