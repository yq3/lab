import { describe, expect, it, vi } from "vitest";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  Backoff,
  BUBBLE_POOL,
  bucketFor,
  buildHooks,
  classifyEvent,
  classifyToolBefore,
  createDeliverer,
  isSelfTool,
  pickBubble,
  postState,
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

describe("createDeliverer：并发投递串行化（P3-②，M2 测试缺口）", () => {
  /** 记录 post/wait 交错顺序 + 退避序列的实验装置（sleep 不真等）。
   *  退避记录点在 nextDelay（wait() 对 delay=0 不调 sleep，记录 sleep 会漏首次）。 */
  function rig(postImpls: Array<() => Promise<unknown>>) {
    const order: string[] = [];
    const delays: number[] = [];
    const backoff = new Backoff(async () => {});
    const origNext = backoff.nextDelay.bind(backoff);
    backoff.nextDelay = () => {
      const d = origNext();
      order.push(`wait${d}`);
      delays.push(d);
      return d;
    };
    let call = 0;
    const postStateImpl = vi.fn(async () => {
      order.push("post");
      const impl = postImpls[Math.min(call, postImpls.length - 1)];
      call += 1;
      return impl();
    });
    const deliverer = createDeliverer({
      throttle: { shouldSend: () => true }, // 测试关闭节流，聚焦退避行为
      backoff,
      postStateImpl: postStateImpl as never,
      killswitch: () => false,
    });
    return { deliverer, order, delays };
  }

  it("并发失败：一次只消耗一级退避（0→1000→2000，不跳级），post/wait 严格交替", async () => {
    const { deliverer, order, delays } = rig([
      () => Promise.reject(new Error("fail")),
      () => Promise.reject(new Error("fail")),
      () => Promise.reject(new Error("fail")),
    ]);
    await Promise.all([
      deliverer.deliver("working", "s1"),
      deliverer.deliver("editing", "s1"),
      deliverer.deliver("testing", "s1"),
    ]);
    // 未串行化时三个 post 会先并发执行完，再连续三次 wait（跳级/乱序）
    expect(order).toEqual(["post", "wait0", "post", "wait1000", "post", "wait2000"]);
    expect(delays).toEqual([0, 1000, 2000]);
  });

  it("失败后成功 reset：下次失败从 0 重新开始（并发下不误复位）", async () => {
    // 第 1 次失败 → 第 2 次成功（队列内 reset）→ 第 3 次失败应为 0 而非 2000
    const { deliverer, delays } = rig([
      () => Promise.reject(new Error("fail")),
      () => Promise.resolve({ status: 200 }),
      () => Promise.reject(new Error("fail")),
    ]);
    await deliverer.deliver("working", "s1");
    await deliverer.deliver("editing", "s1");
    await deliverer.deliver("testing", "s1");
    expect(delays).toEqual([0, 0]);
  });

  it("killswitch / 节流 / null kind 语义保留", async () => {
    const order: string[] = [];
    const postStateImpl = vi.fn(async () => {
      order.push("post");
      return { status: 200 };
    });
    const ks = { on: false };
    const deliverer = createDeliverer({
      throttle: { shouldSend: () => true },
      postStateImpl: postStateImpl as never,
      killswitch: () => ks.on,
    });
    await deliverer.deliver(null, "s1"); // null kind → 直接跳过
    expect(postStateImpl).not.toHaveBeenCalled();
    ks.on = true; // TC-EV-10：killswitch 整体跳过
    await deliverer.deliver("working", "s1");
    expect(postStateImpl).not.toHaveBeenCalled();
    const throttled = createDeliverer({
      throttle: { shouldSend: () => false }, // TC-EV-18：节流丢弃
      postStateImpl: postStateImpl as never,
    });
    await throttled.deliver("working", "s1");
    expect(postStateImpl).not.toHaveBeenCalled();
    expect(order).toEqual([]);
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

    // t=0：冷却中同类（同优先级）丢弃，跨类互不干扰
    expect(th.shouldSend("thinking")).toBe(false);
    expect(th.shouldSend("waiting-permission")).toBe(false);
    expect(th.shouldSend("working")).toBe(false);

    // t=3s：permission 冷却结束，speech/reaction 仍冷却
    t = 3000;
    expect(th.shouldSend("waiting-permission")).toBe(true);
    expect(th.shouldSend("thinking")).toBe(false);

    // t=10s：reaction 冷却结束，speech 仍冷却
    t = 10000;
    expect(th.shouldSend("editing")).toBe(true);
    expect(th.shouldSend("success")).toBe(false); // speech 冷却中且 2 < 已投递 thinking(3)

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

describe("插件 Throttle：同桶升级放行（DESIGN §3.1，TC-EV-18 语义扩展）", () => {
  // 优先级：error 7 > waiting-permission 6 > testing 5 > editing 4 >
  //         thinking 3 > success 2 > working 1 > idle 0（与 Rust session_state 一致）

  it("冷却内新事件优先级高于已投递 → 绕过冷却直接放行（editing(4) > working(1)）", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("working")).toBe(true); // t=0 占 reaction 桶
    t = 500; // reaction 10s 冷却内
    expect(th.shouldSend("editing")).toBe(true); // 4 > 1 → 放行
    expect(th.shouldSend("testing")).toBe(true); // 5 > 4 → 再升级仍放行
  });

  it("优先级不高于已投递 → 维持节流（working(1) ≤ editing(4)；同优先级也节流）", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("editing")).toBe(true); // 已投递 editing(4)
    t = 1000;
    expect(th.shouldSend("working")).toBe(false); // 1 < 4 → 节流
    expect(th.shouldSend("idle")).toBe(false); // 0 < 4 → 节流
    expect(th.shouldSend("editing")).toBe(false); // 4 = 4 不高于 → 节流
  });

  it("speech 桶升级：thinking(3) 后 error(7) 放行；error 后 success(2) 节流", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("thinking")).toBe(true);
    t = 100;
    expect(th.shouldSend("error")).toBe(true); // 7 > 3 → 放行
    t = 200;
    expect(th.shouldSend("success")).toBe(false); // 2 < 7 → 节流
    expect(th.shouldSend("thinking")).toBe(false); // 3 < 7 → 节流
  });

  it("permission 桶单成员（6=6）无升级空间 → 维持节流", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("waiting-permission")).toBe(true);
    t = 1000; // 3s 冷却内
    expect(th.shouldSend("waiting-permission")).toBe(false); // 6 = 6 → 节流
  });

  it("升级放行后，冷却窗以最近一次投递时刻起算（低优先级仍受节流约束）", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("working")).toBe(true); // t=0
    t = 1000;
    expect(th.shouldSend("editing")).toBe(true); // t=1s 升级放行 → last=1s
    t = 2000;
    expect(th.shouldSend("editing")).toBe(false); // 距 last 1s < 10s → 节流
    t = 11000; // 距 t=1s 已 10s → 冷却结束
    expect(th.shouldSend("working")).toBe(true);
  });

  it("背景场景：session.status busy(working) 占桶后紧随的 editing/testing 不被吞（M5 前定案动机）", () => {
    let t = 0;
    const th = new Throttle(() => t);
    expect(th.shouldSend("working")).toBe(true); // session.status busy
    t = 50;
    expect(th.shouldSend("editing")).toBe(true); // tool.execute.before edit
    t = 100;
    expect(th.shouldSend("working")).toBe(false); // tool.execute.after 复位信号被节流（App 侧 30s 超时兜底）
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

  it("总线 permission.asked → waiting-permission（A6，M2 P3-⑤ 清偿）", () => {
    // 与 permission.ask hook 通道一致（DESIGN §3.1 归一化表）；同一次询问
    // 双通道到达时 permission 桶 3s 冷却去重，无双发。
    expect(
      classifyEvent({ type: "permission.asked", properties: { sessionID: "s" } }),
    ).toBe("waiting-permission");
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

describe("插件宿主零阻塞（2026-08-22 根因修复：钩子 fire-and-forget + App 未运行快速通道）", () => {
  it("postState：runtime endpoint/token 缺失 → 返回 null 且不发请求（App 未运行 ≠ 错误）", async () => {
    const fetchImpl = vi.fn(async () => ({ status: 200 }));
    const dir = join(tmpdir(), "pulsepet-no-such-runtime");
    await expect(
      postState("working", "s1", "opencode", fetchImpl as never, dir),
    ).resolves.toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("deliver：postState → null 时静默跳过，不消耗退避等级（Backoff 序列原点不动）", async () => {
    const backoff = new Backoff(async () => {});
    const postStateImpl = vi.fn(async () => null);
    const deliverer = createDeliverer({
      throttle: { shouldSend: () => true },
      backoff,
      postStateImpl: postStateImpl as never,
      killswitch: () => false,
    });
    await deliverer.deliver("working", "s1");
    expect(postStateImpl).toHaveBeenCalledTimes(1);
    // nextDelay() 返回 0 证明 index 未被 App 未运行状态推进（真失败才退避）
    expect(backoff.nextDelay()).toBe(0);
  });

  it("钩子 fire-and-forget：deliver 永久挂起时钩子仍立即返回（绝不阻塞宿主 opencode）", async () => {
    const deliver = vi.fn(
      (_kind: string, _sessionId?: string) => new Promise<void>(() => {}),
    );
    const hooks = buildHooks({ deliver });
    await Promise.race([
      (async () => {
        await hooks["chat.message"]({ sessionID: "s1" });
        await hooks["tool.execute.before"](
          { tool: "edit", sessionID: "s1" },
          { args: { filePath: "a" } },
        );
        await hooks["tool.execute.after"]({ tool: "read", sessionID: "s1" });
        // 自忽略工具不投递（TC-EV-19）
        await hooks["tool.execute.after"]({ tool: "pulsepet_say", sessionID: "s1" });
      })(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("钩子被投递队列阻塞，宿主会卡死")), 500),
      ),
    ]);
    // fire 确实触发过（挂起 ≠ 没投递），且分类/自忽略语义与旧实现一致
    expect(deliver.mock.calls.map((c) => c[0])).toEqual(["thinking", "editing", "working"]);
  });

  it("全部 6 个钩子返回 undefined：钉住 fire-and-forget 契约（防回归为 async/await）", () => {
    // opencode 同步 await 每个钩子且无超时（pulse-pet-hook.js 头注）；任何一种
    // 回归写法（async 钩子 / return deliver(...) / return enqueue(...)）都会让
    // 返回值变成 promise → 此处立即红。宿主零阻塞的不变量由实现本身钉住，
    // 不依赖"deliver 恰好挂起"的场景构造。
    const hooks = buildHooks({ deliver: () => new Promise<void>(() => {}) });
    const results: unknown[] = [
      hooks.event({ event: { type: "session.idle", properties: {} } }),
      hooks["chat.message"]({ sessionID: "s1" }),
      hooks["permission.ask"]({ sessionID: "s1" }),
      hooks["tool.execute.before"]({ tool: "edit", sessionID: "s1" }, { args: {} }),
      hooks["tool.execute.after"]({ tool: "read", sessionID: "s1" }),
      hooks["command.execute.before"]({ command: "npm test" }),
    ];
    expect(results).toHaveLength(6);
    for (const r of results) {
      expect(r).toBeUndefined();
      expect(typeof (r as { then?: unknown })?.then).not.toBe("function");
    }
  });
});
