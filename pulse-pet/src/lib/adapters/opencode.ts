/**
 * OpenCodeAdapter（DESIGN §3.4，v1 唯一实现，TC-EV-04 归一化映射 / TC-EV-23）。
 *
 * `normalizeRawEvent` 与插件 `opencode-plugin/pulse-pet-hook.js` 的 classify* 逻辑
 * 一一对应，用于前端兜底归一化（插件侧已归一化，主链路不走这里）。
 */

import type { AgentAdapter, NormalizedEvent } from "../agent-adapter";
import type { NormalizedState } from "../state";

const EDIT_TOOLS = new Set(["edit", "write", "patch", "apply_patch"]);
const SHELL_TOOLS = new Set(["bash", "shell", "terminal"]);
const SELF_TOOL_RE = /pulsepet_(status|say|react)/;
const TEST_CMD_RE =
  /(test|vitest|jest|pytest|npm\s+test|pnpm\s+test|yarn\s+test)/i;

type RawEvent = Record<string, unknown>;

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** 从原始事件尽力提取 sessionId。 */
function sessionIdOf(raw: RawEvent): string {
  const props = raw.properties as RawEvent | undefined;
  const fromProps = props?.sessionID ?? props?.sessionId;
  const direct = raw.sessionID ?? raw.sessionId;
  return str(fromProps ?? direct) || "default";
}

/**
 * 归一化原始 opencode 事件 → kind（返回 null 表示忽略/无法分类）。
 * 与插件侧分类保持一致（TC-EV-04）。
 */
export function normalizeRawKind(raw: unknown): NormalizedState | null {
  if (typeof raw !== "object" || raw === null) return null;
  const ev = raw as RawEvent;
  const type = str(ev.type);
  const tool = str(ev.tool);
  const args = ev.args as RawEvent | undefined;

  switch (type) {
    case "session.status": {
      const props = ev.properties as RawEvent | undefined;
      const status = props?.status as RawEvent | undefined;
      return status?.type === "idle" ? "idle" : "working";
    }
    case "session.idle":
      return "idle";
    case "session.error":
      return "error";
    case "chat.message":
      return "thinking";
    case "permission.ask":
    case "permission.asked":
      return "waiting-permission";
    case "tool.execute.before": {
      if (!tool || SELF_TOOL_RE.test(tool)) return null; // 自忽略（防回环）
      if (EDIT_TOOLS.has(tool)) return "editing";
      if (SHELL_TOOLS.has(tool)) {
        const cmd = str(args?.command ?? args?.cmd ?? ev.command);
        return TEST_CMD_RE.test(cmd) ? "testing" : "working";
      }
      return "working";
    }
    case "tool.execute.after":
      return "working"; // 复位主信号
    default:
      return null;
  }
}

export const OpenCodeAdapter: AgentAdapter = {
  id: "opencode",
  normalizeRawEvent(raw: unknown): NormalizedEvent | null {
    const kind = normalizeRawKind(raw);
    if (!kind) return null;
    const ev = (raw ?? {}) as RawEvent;
    return {
      sessionId: sessionIdOf(ev),
      kind,
      agent: "opencode",
    };
  },
  tokenSource: "opencode-sqlite",
  iconSet: "opencode",
};
