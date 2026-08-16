import { describe, expect, it, vi } from "vitest";

import {
  Backoff,
  BUBBLE_POOL,
  bucketFor,
  classifyEvent,
  classifyToolBefore,
  isSelfTool,
  pickBubble,
  sanitizeText,
  Throttle,
} from "../../opencode-plugin/pulse-pet-hook.js";

describe("插件 Backoff：指数退避序列（TC-EV-07）", () => {
  it("退避序列 0→1s→2s→5s→30s 封顶", () => {
    const b = new Backoff();
    expect(b.nextDelay()).toBe(0); // 首次立即重试
    expect(b.nextDelay()).toBe(1000);
    expect(b.nextDelay()).toBe(2000);
    expect(b.nextDelay()).toBe(5000);
    expect(b.nextDelay()).toBe(30000); // 封顶
    expect(b.nextDelay()).toBe(30000); // 封顶持续
  });

  it("mock 时间断言 wait() 实际 sleep 1s→2s→5s→30s", async () => {
    const slept: number[] = [];
    const sleep = vi.fn((ms: number) => {
      slept.push(ms);
      return Promise.resolve();
    });
    const b = new Backoff(sleep);
    await b.wait(); // 0ms → 不 sleep
    await b.wait(); // 1000
    await b.wait(); // 2000
    await b.wait(); // 5000
    await b.wait(); // 30000
    expect(slept).toEqual([1000, 2000, 5000, 30000]);
  });

  it("恢复后 reset → 下次立即投递", () => {
    const b = new Backoff();
    b.nextDelay();
    b.nextDelay();
    b.nextDelay(); // 推进到 2000
    b.reset();
    expect(b.nextDelay()).toBe(0);
  });
});

describe("插件 Throttle：三类冷却互不干扰（TC-EV-18）", () => {
  it("speech 20s / permission 3s / reaction 10s 独立生效", () => {
    let t = 0;
    const th = new Throttle(() => t);

    // t=0：三类各放行一次
    expect(th.shouldSend("thinking")).toBe(true); // speech
    expect(th.shouldSend("waiting-permission")).toBe(true); // permission
    expect(th.shouldSend("working")).toBe(true); // reaction

    // t=0：同类冷却中丢弃，跨类互不干扰
    expect(th.shouldSend("thinking")).toBe(false);
    expect(th.shouldSend("error")).toBe(false); // 与 thinking 同 speech 桶
    expect(th.shouldSend("waiting-permission")).toBe(false);
    expect(th.shouldSend("working")).toBe(false);

    // t=3s：permission 冷却结束，speech/reaction 仍冷却
    t = 3000;
    expect(th.shouldSend("waiting-permission")).toBe(true);
    expect(th.shouldSend("thinking")).toBe(false);

    // t=10s：reaction 冷却结束，speech 仍冷却
    t = 10000;
    expect(th.shouldSend("editing")).toBe(true);
    expect(th.shouldSend("success")).toBe(false);

    // t=20s：speech 冷却结束
    t = 20000;
    expect(th.shouldSend("thinking")).toBe(true);
  });

  it("bucketFor 分类正确", () => {
    expect(bucketFor("thinking")).toBe("speech");
    expect(bucketFor("success")).toBe("speech");
    expect(bucketFor("error")).toBe("speech");
    expect(bucketFor("waiting-permission")).toBe("permission");
    expect(bucketFor("working")).toBe("reaction");
    expect(bucketFor("editing")).toBe("reaction");
    expect(bucketFor("testing")).toBe("reaction");
    expect(bucketFor("idle")).toBe("reaction");
  });
});

describe("插件 classifyEvent / classifyToolBefore：归一化（TC-EV-04）", () => {
  it("session.status / session.idle / session.error", () => {
    expect(
      classifyEvent({ type: "session.status", properties: { status: { type: "idle" } } }),
    ).toBe("idle");
    expect(
      classifyEvent({ type: "session.status", properties: { status: { type: "busy" } } }),
    ).toBe("working");
    expect(classifyEvent({ type: "session.idle" })).toBe("idle");
    expect(classifyEvent({ type: "session.error" })).toBe("error");
    expect(classifyEvent({ type: "message.updated" })).toBeNull();
  });

  it("工具分类 + 测试命令检测", () => {
    expect(classifyToolBefore("edit")).toBe("editing");
    expect(classifyToolBefore("apply_patch")).toBe("editing");
    expect(classifyToolBefore("bash", { command: "npm test" })).toBe("testing");
    expect(classifyToolBefore("bash", { command: "pytest -q" })).toBe("testing");
    expect(classifyToolBefore("bash", { command: "ls" })).toBe("working");
    expect(classifyToolBefore("read")).toBe("working");
  });

  it("自忽略工具（TC-EV-19）", () => {
    expect(isSelfTool("pulsepet_say")).toBe(true);
    expect(isSelfTool("pulsepet_status")).toBe(true);
    expect(isSelfTool("pulsepet_react")).toBe(true);
    expect(isSelfTool("read")).toBe(false);
    expect(classifyToolBefore("pulsepet_say")).toBeNull();
  });
});

describe("插件消息净化（TC-EV-20/21）", () => {
  it("气泡只来自白名单池，不含原始内容", () => {
    const t = pickBubble("thinking");
    expect(BUBBLE_POOL.thinking).toContain(t);
    // 即使传了原始文本，pickBubble 也只从池里取（不接收原始内容参数）
  });

  it("反应类状态不出气泡", () => {
    expect(pickBubble("working")).toBe("");
    expect(pickBubble("editing")).toBe("");
    expect(pickBubble("idle")).toBe("");
  });

  it("全部白名单模板：单行、1-140 字符", () => {
    for (const cat of Object.keys(BUBBLE_POOL) as (keyof typeof BUBBLE_POOL)[]) {
      for (const tpl of BUBBLE_POOL[cat]) {
        expect(tpl.length).toBeGreaterThanOrEqual(1);
        expect(tpl.length).toBeLessThanOrEqual(140);
        expect(tpl).not.toMatch(/[\r\n]/);
      }
    }
  });

  it("sanitizeText 单行化 + 截断 + 空串丢弃", () => {
    expect(sanitizeText("a\nb\r\nc")).toBe("a b c");
    expect(sanitizeText("x".repeat(200)).length).toBe(140);
    expect(sanitizeText("   ")).toBe("");
  });
});
