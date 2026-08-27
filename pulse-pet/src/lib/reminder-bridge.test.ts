import { describe, expect, it } from "vitest";
import { parseTaskResult } from "./reminder-bridge";

/**
 * v2 M6（V2-DESIGN §6.2，TC-M6-03-1）：`pulsepet://task-result` payload 显式
 * `agent: "task"`（字段此前已隐含——结果气泡必然来自 task 伪 session，本
 * 里程碑显式化供前端徽标 [task] 消费）。
 * 提醒气泡（reminder://trigger 路径）不带 agent——非 agent 来源、无徽标
 * （回归项，断言在 bubble-queue.test.ts 的 bubbleAgentBadge 缺省用例）。
 */

describe("parseTaskResult：agent 字段（M6 显式化）", () => {
  it("payload 带 agent → 原样解析（Rust 恒发 \"task\"）", () => {
    const r = parseTaskResult({
      text: "例程「日报」完成",
      logId: 7,
      status: "ok",
      agent: "task",
    });
    expect(r).not.toBeNull();
    expect(r?.agent).toBe("task");
    expect(r?.text).toBe("例程「日报」完成");
    expect(r?.logId).toBe(7);
    expect(r?.status).toBe("ok");
  });

  it("payload 缺 agent（旧载荷容错）→ 默认 \"task\"（结果气泡必然来自伪 session）", () => {
    const r = parseTaskResult({ text: "t", logId: 1, status: "failed" });
    expect(r?.agent).toBe("task");
  });

  it("agent 非字符串 → 默认 \"task\"；text/logId/status 非法 → null（既有校验不回归）", () => {
    expect(parseTaskResult({ text: "t", logId: 1, status: "ok", agent: 42 })?.agent).toBe("task");
    expect(parseTaskResult({ logId: 1, status: "ok", agent: "task" })).toBeNull();
    expect(parseTaskResult({ text: "t", logId: "x", status: "ok" })).toBeNull();
    expect(parseTaskResult(null)).toBeNull();
  });
});
