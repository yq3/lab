import { describe, expect, it, vi } from "vitest";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  Backoff,
  BUBBLE_POOL,
  bucketFor,
  buildDetail,
  buildHooks,
  classifyEvent,
  classifyToolBefore,
  createDeliverer,
  DetailThrottle,
  DETAIL_COOLDOWN_MS,
  extractDetailParam,
  isSelfTool,
  pickBubble,
  postState,
  sanitizeText,
  STICKY_MS,
  ThinkingSticky,
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

  it("bucketFor 分类正确（v0.1.3 四-3：idle 豁免 → null）", () => {
    expect(bucketFor("thinking")).toBe("speech");
    expect(bucketFor("success")).toBe("speech");
    expect(bucketFor("error")).toBe("speech");
    expect(bucketFor("waiting-permission")).toBe("permission");
    expect(bucketFor("working")).toBe("reaction");
    expect(bucketFor("editing")).toBe("reaction");
    expect(bucketFor("testing")).toBe("reaction");
    expect(bucketFor("idle")).toBeNull(); // 节流豁免：永远放行
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
    expect(th.shouldSend("editing")).toBe(false); // 4 = 4 不高于 → 节流
    // v0.1.3 四-3：idle 已豁免出桶（shouldSend 恒 true），同桶降级场景见 TC-EV-25
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
  });

  it("流式事件 → working（v0.1.3 四-4，TC-EV-26-1；TC-EV-04 修订）", () => {
    expect(
      classifyEvent({
        type: "message.part.delta",
        properties: { sessionID: "s1", delta: "x" },
      }),
    ).toBe("working");
    expect(classifyEvent({ type: "message.updated" })).toBe("working"); // v0.1.3 起不再是 null
    expect(classifyEvent({ type: "message.part.updated" })).toBe("working");
    expect(classifyEvent({ type: "plugin.added" })).toBeNull(); // 未分类事件仍忽略
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

describe("插件 ThinkingSticky + deliver 集成：thinking 粘性窗口（v0.1.3 四-2，TC-EV-24）", () => {
  function rig(clockMs: () => number) {
    const posted: Array<{ kind: string; sid: string }> = [];
    const deliverer = createDeliverer({
      throttle: new Throttle(clockMs),
      sticky: new ThinkingSticky(clockMs),
      postStateImpl: (async (kind: string, sid: string) => {
        posted.push({ kind, sid });
        return { status: 200 };
      }) as never,
      killswitch: () => false,
    });
    return { deliverer, posted };
  }

  it("STICKY_MS = 4000（定案常量，防误改）", () => {
    expect(STICKY_MS).toBe(4000);
  });

  it("窗口内 working/idle 被吞且不占节流桶（TC-EV-24-1/4）", async () => {
    let t = 0;
    const { deliverer, posted } = rig(() => t);
    await deliverer.deliver("thinking", "s1"); // t=0 置窗（speech 桶放行）
    t = 1000;
    await deliverer.deliver("working", "s1"); // 被吞
    t = 1500;
    await deliverer.deliver("idle", "s1"); // 被吞
    expect(posted).toEqual([{ kind: "thinking", sid: "s1" }]);
    // 不占桶的证明：t=4.5s 窗口过期，reaction 桶若在 t=1s 被吞事件占用则此刻
    // 仍在 10s 冷却内必被节流；实际桶空 → 放行
    t = 4500;
    await deliverer.deliver("working", "s1");
    expect(posted.map((p) => p.kind)).toEqual(["thinking", "working"]);
  });

  it("更高优先级事件窗口内照常穿透（TC-EV-24-2）", async () => {
    let t = 0;
    const { deliverer, posted } = rig(() => t);
    await deliverer.deliver("thinking", "s1");
    t = 1000;
    await deliverer.deliver("editing", "s1"); // editing(4) > thinking(3)，不吞
    t = 1200;
    await deliverer.deliver("testing", "s1"); // 升级放行
    t = 1400;
    await deliverer.deliver("waiting-permission", "s1"); // permission 桶
    expect(posted.map((p) => p.kind)).toEqual([
      "thinking",
      "editing",
      "testing",
      "waiting-permission",
    ]);
  });

  it("被 speech 节流吞掉的 thinking 仍续窗（TC-EV-24-3）", async () => {
    let t = 0;
    const { deliverer, posted } = rig(() => t);
    await deliverer.deliver("thinking", "s1"); // speech 桶占
    t = 5000;
    await deliverer.deliver("thinking", "s1"); // speech 20s 冷却内被节流
    t = 6000;
    await deliverer.deliver("working", "s1"); // 但粘性窗已续到 t=9s → 被吞
    expect(posted).toEqual([{ kind: "thinking", sid: "s1" }]);
  });

  it("多 session 隔离：A 的窗口不影响 B（TC-EV-24-5）", async () => {
    let t = 0;
    const { deliverer, posted } = rig(() => t);
    await deliverer.deliver("thinking", "A");
    t = 1000;
    await deliverer.deliver("working", "B"); // B 无窗口 → 正常投递
    expect(posted).toEqual([
      { kind: "thinking", sid: "A" },
      { kind: "working", sid: "B" },
    ]);
  });
});

describe("插件 idle 节流豁免（v0.1.3 四-3，TC-EV-25）", () => {
  function rig() {
    const posted: string[] = [];
    const deliverer = createDeliverer({
      throttle: new Throttle(() => 0), // 同一时刻：冷却语义最严格
      postStateImpl: (async (kind: string) => {
        posted.push(kind);
        return { status: 200 };
      }) as never,
      killswitch: () => false,
    });
    return { deliverer, posted };
  }

  it("reaction 桶刚投 working，紧邻 idle 立即放行（原行为缺陷回归钉子）", async () => {
    const { deliverer, posted } = rig();
    await deliverer.deliver("working", "s1"); // t=0 占 reaction 桶
    await deliverer.deliver("idle", "s1"); // 旧实现：0<1 同桶降级被吞 → 停 working 30-60s
    expect(posted).toEqual(["working", "idle"]);
  });

  it("双通道重复 idle 均放行（幂等由 App 侧覆盖兜底）", async () => {
    const { deliverer, posted } = rig();
    await deliverer.deliver("idle", "s1");
    await deliverer.deliver("idle", "s1");
    expect(posted).toEqual(["idle", "idle"]);
  });

  it("其余 reaction 类仍受 10s 冷却约束（TC-EV-18 不回归）", async () => {
    const { deliverer, posted } = rig();
    await deliverer.deliver("working", "s1");
    await deliverer.deliver("working", "s1"); // 1 = 1 不升级 → 节流
    expect(posted).toEqual(["working"]);
  });
});

describe("插件流式心跳（v0.1.3 四-4，TC-EV-26）", () => {
  it("高频 delta 经 reaction 桶节流：60s 流式恰 6 次投递（TC-EV-26-2）", async () => {
    let t = 0;
    const posted: number[] = [];
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      postStateImpl: (async () => {
        posted.push(t);
        return { status: 200 };
      }) as never,
      killswitch: () => false,
    });
    // spike 实测 ~28 次/s：250ms 一个 delta，持续 60s
    for (t = 0; t < 60000; t += 250) {
      await deliverer.deliver("working", "s1");
    }
    expect(posted).toEqual([0, 10000, 20000, 30000, 40000, 50000]);
  });

  it("缺 sessionID 的流式事件不投递（防污染 default session，TC-EV-26-3）", () => {
    const deliver = vi.fn(async () => {});
    const hooks = buildHooks({ deliver });
    hooks.event({
      event: { type: "message.part.delta", properties: { delta: "x" } }, // 无 sessionID
    });
    hooks.event({
      event: { type: "message.part.delta", properties: { sessionID: "s1", delta: "x" } },
    });
    expect(deliver).toHaveBeenCalledTimes(1);
    expect(deliver.mock.calls[0]).toEqual(["working", "s1"]);
  });

  it("零阻塞契约不回归：流式事件钩子仍返回 undefined（TC-EV-26-4）", () => {
    const hooks = buildHooks({ deliver: () => new Promise<void>(() => {}) });
    const r: unknown = hooks.event({
      event: { type: "message.part.delta", properties: { sessionID: "s1", delta: "x" } },
    });
    expect(r).toBeUndefined();
    expect(typeof (r as { then?: unknown })?.then).not.toBe("function");
  });
});

describe("插件三机制联动时间线（v0.1.3 四-2/3/4 集成，TC-EV-27）", () => {
  it("thinking 稳定 4s → 心跳续活 → editing 穿透 → 长流式无 >30s 静默 → idle 即时收尾", async () => {
    let t = 0;
    const posted: Array<{ t: number; kind: string }> = [];
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      sticky: new ThinkingSticky(() => t),
      postStateImpl: (async (kind: string) => {
        posted.push({ t, kind });
        return { status: 200 };
      }) as never,
      killswitch: () => false,
    });

    await deliverer.deliver("thinking", "s1"); // chat.message → thinking（t=0）
    for (t = 500; t < 4000; t += 500) {
      await deliverer.deliver("working", "s1"); // 0-4s delta 心跳被粘性吞
    }
    t = 4500;
    await deliverer.deliver("working", "s1"); // 窗口过期，首个心跳放行
    t = 5000;
    await deliverer.deliver("editing", "s1"); // tool.execute.before(edit) 穿透
    for (t = 6000; t < 64000; t += 2000) {
      await deliverer.deliver("working", "s1"); // 60s+ 纯文本生成 delta 心跳
    }
    t = 65000;
    await deliverer.deliver("idle", "s1"); // session.idle 豁免放行，即时收尾

    expect(posted.map((p) => p.kind)).toEqual([
      "thinking",
      "working",
      "editing",
      "working",
      "working",
      "working",
      "working",
      "working",
      "idle",
    ]);
    // 心跳间隔（含编辑期跨桶）无 >30s 静默：idle_timeout 不可能误触
    const times = posted.map((p) => p.t);
    for (let i = 1; i < times.length; i++) {
      expect(times[i] - times[i - 1]).toBeLessThan(30000);
    }
  });
});

// ===========================================================================
// v2 M3 工具级气泡：extractDetailParam 提取净化 + detail 独立 20s 节流桶
//（V2-DESIGN §3.7.1，TC-M3-13；P1-4 bash 净化强化钉子）
// ===========================================================================

describe("M3 extractDetailParam：各工具族 param 提取（TC-M3-13-1）", () => {
  it("read/edit：file path → basename（绝不携带路径原文）", () => {
    expect(extractDetailParam("read", { filePath: "/Users/x/lab/V2-DESIGN.md" })).toBe(
      "V2-DESIGN.md",
    );
    expect(extractDetailParam("edit", { filePath: "src/lib/bubble.ts" })).toBe("bubble.ts");
    expect(extractDetailParam("write", { path: "/tmp/a b.md" })).toBe("a b.md");
    expect(extractDetailParam("listfile", { path: "/Users/x/lab" })).toBe("lab");
    // Windows 分隔符
    expect(extractDetailParam("read", { filePath: "C:\\dev\\repo\\AGENTS.md" })).toBe("AGENTS.md");
  });

  it("bash：剥离行首 KEY=value 段后取首词；首词含 / 或 \\ 取 basename（P1-4）", () => {
    expect(extractDetailParam("bash", { command: "npm test" })).toBe("npm");
    // 绝对路径命令 → basename（不泄漏路径）
    expect(extractDetailParam("bash", { command: "/opt/homebrew/bin/npm test" })).toBe("npm");
    expect(extractDetailParam("bash", { command: "/usr/local/bin/rg pattern" })).toBe("rg");
    // env 赋值命令（单个/连续）→ 剥离后首词
    expect(extractDetailParam("bash", { command: "FOO=secret npm test" })).toBe("npm");
    expect(extractDetailParam("bash", { command: "A=1 B=2 C=3 cargo build --release" })).toBe(
      "cargo",
    );
    // 混合：env 前缀 + 绝对路径命令
    expect(extractDetailParam("bash", { command: "PATH=/x:/y /opt/bin/node server.js" })).toBe(
      "node",
    );
    // cmd 别名字段
    expect(extractDetailParam("bash", { cmd: "git status" })).toBe("git");
  });

  it("search：pattern 净化后原样 ≤40 字符（含 / 或 \\ 取末段）", () => {
    expect(extractDetailParam("grep", { pattern: "TODO|FIXME" })).toBe("TODO|FIXME");
    expect(extractDetailParam("glob", { pattern: "src/lib/*.ts" })).toBe("*.ts");
    expect(extractDetailParam("grep", { pattern: "a/b/c/needle" })).toBe("needle");
    expect(extractDetailParam("grep", { pattern: "x".repeat(60) })).toHaveLength(40);
  });

  it("web：URL → hostname（不携带 URL 全文）", () => {
    expect(extractDetailParam("webfetch", { url: "https://maven.aliyun.com/x?y=1" })).toBe(
      "maven.aliyun.com",
    );
    expect(extractDetailParam("webfetch", { url: "http://localhost:1430/#/panel" })).toBe(
      "localhost",
    );
    // websearch 无 url：query 按 search 同款净化
    expect(extractDetailParam("websearch", { query: "tauri 2 docs" })).toBe("tauri 2 docs");
  });

  it("无参 / 提取失败 / 白名单外工具 / 自忽略工具 → null（不携带）", () => {
    expect(extractDetailParam("read", {})).toBeNull();
    expect(extractDetailParam("read", { filePath: "" })).toBeNull();
    expect(extractDetailParam("bash", {})).toBeNull();
    expect(extractDetailParam("bash", { command: "   " })).toBeNull();
    expect(extractDetailParam(null, {})).toBeNull();
    expect(extractDetailParam("unknown-tool", { filePath: "/x/y.md" })).toBeNull();
    expect(extractDetailParam("pulsepet_say", { text: "hi" })).toBeNull();
    expect(extractDetailParam(undefined, undefined)).toBeNull();
  });

  it("buildDetail：'<tplId>:<param>' 组装（TC-M3-13-4）", () => {
    expect(buildDetail("edit", { filePath: "/x/V2-SCOPE.md" })).toBe("edit:V2-SCOPE.md");
    expect(buildDetail("bash", { command: "FOO=x npm test" })).toBe("bash:npm");
    expect(buildDetail("read", {})).toBeNull();
  });

  it("TC-SEC 口径：detail 不含路径原文 / 参数原文 / URL 全文", () => {
    const cases = [
      ["read", { filePath: "/Users/secret/path/token.txt" }, "token.txt"],
      ["bash", { command: "/usr/local/bin/secret-cmd --password hunter2" }, "secret-cmd"],
      ["webfetch", { url: "https://evil.example.com/a/b/c?token=xyz" }, "evil.example.com"],
    ] as const;
    for (const [tool, args, expectIncluded] of cases) {
      const d = buildDetail(tool, args);
      expect(d).toBeTruthy();
      expect(d).toContain(expectIncluded);
      // 原文中的敏感片段不出现在 detail
      expect(d).not.toContain("/Users/secret");
      expect(d).not.toContain("--password");
      expect(d).not.toContain("token=xyz");
    }
  });
});

describe("M3 DetailThrottle：独立 20s 单桶（TC-M3-13-3）", () => {
  it("首条放行；冷却期内拦截；20s 后恢复", () => {
    let t = 0;
    const dt = new DetailThrottle(() => t);
    expect(dt.shouldSend()).toBe(true);
    t = 10_000;
    expect(dt.shouldSend(), "20s 冷却期内").toBe(false);
    t = 20_000;
    expect(dt.shouldSend(), "冷却窗结束").toBe(true);
    expect(DETAIL_COOLDOWN_MS).toBe(20000);
  });
});

describe("M3 deliver：detail 桶语义四条（reaction 后判定，TC-M3-13-3）", () => {
  function makeRecorder() {
    const posted: { kind: string; detail: string | null }[] = [];
    const postStateImpl = (
      kind: string,
      _sid: string,
      _agent?: string,
      _f?: unknown,
      _d?: unknown,
      detail?: string | null,
    ): Promise<{ ok: boolean }> => {
      posted.push({ kind, detail: detail ?? null });
      return Promise.resolve({ ok: true });
    };
    return { posted, postStateImpl };
  }

  it("冷却期内状态事件照发、detail 省略；detail 桶恢复后再携带", async () => {
    let t = 0;
    const rec = makeRecorder();
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      detailThrottle: new DetailThrottle(() => t),
      postStateImpl: rec.postStateImpl,
      killswitch: () => false,
    });
    await deliverer.deliver("editing", "s1", "edit:a.md"); // 两桶均消耗
    t = 5_000;
    // speech 桶独立（error 不受 reaction 冷却约束）→ 状态照发；detail 桶冷却 → 省略
    await deliverer.deliver("error", "s1", "bash:npm");
    t = 21_000; // 两桶均出窗
    await deliverer.deliver("editing", "s1", "edit:c.md");
    expect(rec.posted).toEqual([
      { kind: "editing", detail: "edit:a.md" },
      { kind: "error", detail: null },
      { kind: "editing", detail: "edit:c.md" },
    ]);
  });

  it("状态事件被 reaction 桶吞掉时 detail 桶不消耗", async () => {
    let t = 0;
    const rec = makeRecorder();
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      detailThrottle: new DetailThrottle(() => t),
      postStateImpl: rec.postStateImpl,
      killswitch: () => false,
    });
    // 先发 working 占 reaction 桶（不带 detail）
    await deliverer.deliver("working", "s1");
    t = 1_000;
    // 同桶低优先级（working ≤ working）被节流吞 → 状态不发、detail 桶不消耗
    await deliverer.deliver("working", "s1", "bash:npm");
    expect(rec.posted.length, "状态被吞 → 无投递").toBe(1);
    t = 11_000; // reaction 10s 冷却已过（1s → 11s）
    await deliverer.deliver("working", "s1", "bash:npm"); // 状态放行；detail 桶从未消耗 → 携带
    expect(rec.posted[1]).toEqual({ kind: "working", detail: "bash:npm" });
  });

  it("detail 不影响状态节流桶（状态照常按自身冷却）", async () => {
    let t = 0;
    const rec = makeRecorder();
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      detailThrottle: new DetailThrottle(() => t),
      postStateImpl: rec.postStateImpl,
      killswitch: () => false,
    });
    await deliverer.deliver("editing", "s1", "edit:a.md");
    t = 5_000;
    // editing(4) ≤ editing(4)：reaction 维持节流——状态与 detail 都不发
    await deliverer.deliver("editing", "s1", "edit:b.md");
    t = 8_000;
    // error 走 speech 桶（独立）：状态照发；detail 桶仍在冷却（首条 0s 起 20s）→ 省略
    await deliverer.deliver("error", "s1", "bash:x");
    expect(rec.posted).toEqual([
      { kind: "editing", detail: "edit:a.md" },
      { kind: "error", detail: null },
    ]);
  });

  it("detail 冷却消耗不因网络失败回滚（N7）", async () => {
    let t = 0;
    const calls: (string | null)[] = [];
    let failFirst = true;
    const deliverer = createDeliverer({
      throttle: new Throttle(() => t),
      detailThrottle: new DetailThrottle(() => t),
      postStateImpl: (_k, _s, _a, _f, _d, detail) => {
        calls.push(detail ?? null);
        if (failFirst) {
          failFirst = false;
          return Promise.reject(new Error("network down"));
        }
        return Promise.resolve({ ok: true });
      },
      killswitch: () => false,
      backoff: new Backoff(async () => 0), // 失败不真 sleep（测试加速）
    });
    await deliverer.deliver("editing", "s1", "edit:a.md"); // 网络失败
    t = 1_000;
    await deliverer.deliver("editing", "s1", "edit:b.md"); // 升级？同级被节流……
    t = 15_000;
    await deliverer.deliver("error", "s1", "edit:c.md"); // speech 桶放行；detail 仍冷却 → 省略
    expect(calls, "失败后 20s 内不重发 detail（不回滚）").toEqual(["edit:a.md", null]);
  });
});

describe("M3 buildHooks：仅 tool.execute.before 携带 detail（TC-M3-13-2）", () => {
  it("before 的 args 提取 detail；after / command.execute.before / 其它钩子不带", async () => {
    const posted: { kind: string; detail: string | null }[] = [];
    const deliverer = {
      deliver: (kind: string, _sid: string | null, detail: string | null = null) => {
        posted.push({ kind, detail: detail ?? null });
        return Promise.resolve();
      },
    };
    const hooks = buildHooks(deliverer as never);
    // before：edit 工具 → editing + detail
    hooks["tool.execute.before"](
      { tool: "edit", sessionID: "s1" },
      { args: { filePath: "/x/pulse-pet-hook.js" } },
    );
    // after：working 复位，无 detail
    hooks["tool.execute.after"]({ tool: "edit", sessionID: "s1" });
    // command.execute.before：testing，无 detail
    hooks["command.execute.before"]({ command: "npm test", sessionID: "s1" });
    // chat.message：thinking，无 detail
    hooks["chat.message"]({ sessionID: "s1" });
    // 无 args 的 before（detail=null 不携带，状态照发）
    hooks["tool.execute.before"]({ tool: "read", sessionID: "s1" }, {});
    await Promise.resolve();
    expect(posted).toEqual([
      { kind: "editing", detail: "edit:pulse-pet-hook.js" },
      { kind: "working", detail: null },
      { kind: "testing", detail: null },
      { kind: "thinking", detail: null },
      { kind: "working", detail: null },
    ]);
  });

  it("全部钩子仍返回 undefined：零阻塞契约不回归（fire-and-forget）", () => {
    const hooks = buildHooks();
    expect(hooks["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "/x/a.md" } })).toBeUndefined();
    expect(hooks["tool.execute.after"]({ tool: "edit" })).toBeUndefined();
    expect(hooks["command.execute.before"]({ command: "npm test" })).toBeUndefined();
  });
});
