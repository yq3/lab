/**
 * ClaudeCodeAdapter（v2 M1，V2-DESIGN §1.6，TC-INT-01 前端兜底层）。
 *
 * `normalizeRawEvent` 与 `opencode-plugin/claude-code-hook.js` 的 classify 逻辑
 * 一一对应（CC hook input JSON 的前端兜底归一化——主链路在 hook 脚本侧完成，
 * 此层仅测试/兜底用，与 OpenCodeAdapter 同模式）。
 * `tokenSource: "transcript-incremental"`（M5 transcript 增量解析兑现）。
 */

import type { AgentAdapter, NormalizedEvent } from "../agent-adapter";
import type { NormalizedState } from "../state";

// 与 claude-code-hook.js 逐字一致（TC-INT-01-1 防两处漂移）
const TEST_CMD_RE = /(test|vitest|jest|pytest|npm\s+test|pnpm\s+test|yarn\s+test)/i;
const EDIT_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

type RawInput = Record<string, unknown>;

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** CC 侧编辑工具分类（§1.3.1 映射）。 */
export function classifyToolUse(
  toolName: string,
  toolInput: RawInput | undefined,
): NormalizedState {
  if (EDIT_TOOLS.has(toolName)) return "editing";
  if (toolName === "Bash") {
    const cmd = str(toolInput?.command);
    return TEST_CMD_RE.test(cmd) ? "testing" : "working";
  }
  return "working";
}

/**
 * 归一化 CC hook input（stdin JSON）→ kind（返回 null 表示不注册/忽略）。
 * 与 claude-code-hook.js 的 classifyHookInput 一一对应。
 */
export function normalizeRawKind(raw: unknown): NormalizedState | null {
  if (typeof raw !== "object" || raw === null) return null;
  const input = raw as RawInput;
  switch (str(input.hook_event_name)) {
    case "SessionStart":
      return "idle";
    case "UserPromptSubmit":
      return "thinking";
    case "PreToolUse":
      return classifyToolUse(
        str(input.tool_name),
        input.tool_input as RawInput | undefined,
      );
    case "PostToolUse":
      return "working";
    case "PostToolUseFailure":
      return "error";
    case "PermissionRequest":
      return "waiting-permission";
    case "Stop":
      return "idle";
    case "StopFailure":
      return "error";
    default:
      return null;
  }
}

export const ClaudeCodeAdapter: AgentAdapter = {
  id: "claude-code",
  normalizeRawEvent(raw: unknown): NormalizedEvent | null {
    const kind = normalizeRawKind(raw);
    if (!kind) return null;
    // CC 侧全事件缺 session_id 丢弃（§1.3.2，较 opencode 侧更严，不落 default）
    const sid =
      typeof raw === "object" && raw !== null
        ? str((raw as RawInput).session_id)
        : "";
    if (!sid) return null;
    return { sessionId: sid, kind, agent: "claude-code" };
  },
  tokenSource: "transcript-incremental",
  iconSet: "claude-code",
};
