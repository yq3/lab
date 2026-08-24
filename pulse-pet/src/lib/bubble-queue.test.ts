import { describe, expect, it } from "vitest";
import {
  DWELL_MS,
  MERGE_WINDOW_MS,
  QUEUE_MAX,
  ackCurrent,
  dwellFor,
  enqueue,
  expireCurrent,
  initialState,
  setHoverPaused,
  type BubbleItem,
  type BubbleLevel,
} from "./bubble-queue";

/** 构造测试条目（id 递增由调用方控制，便于断言替换/驱逐目标）。 */
function item(
  id: number,
  level: BubbleLevel,
  source: string,
  text = "",
  extra: Partial<BubbleItem> = {},
): BubbleItem {
  return { id, level, source, text: text || `text-${id}`, enqueuedAt: 0, ...extra };
}

const T0 = 1_000_000;

describe("bubble-queue TC-UI-09 ①顶替回队 / 同级 FIFO", () => {
  it("critical 到达时 info 显示中 → info 立即被顶回队首（不丢失、不结案）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "token-report"), T0);
    expect(s.current?.id).toBe(1);
    s = enqueue(s, item(2, "critical", "reminder:1"), T0 + 100);
    expect(s.current?.id).toBe(2); // critical 立即上屏
    expect(s.queue.map((q) => q.id)).toEqual([1]); // 被顶的 info 回队首
  });

  it("同级新条目按 FIFO 排队（不顶替显示中条目）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "a"), T0);
    s = enqueue(s, item(2, "info", "b"), T0 + 100);
    s = enqueue(s, item(3, "info", "c"), T0 + 200);
    expect(s.current?.id).toBe(1);
    expect(s.queue.map((q) => q.id)).toEqual([2, 3]);
  });

  it("低优先级到达不顶替高优先级（critical 不被 info/ambient 顶，规则⑥）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "reminder:1"), T0);
    s = enqueue(s, item(2, "info", "token-report"), T0 + 100);
    s = enqueue(s, item(3, "ambient", "tool:edit"), T0 + 200);
    expect(s.current?.id).toBe(1); // critical 稳坐显示位
    expect(s.queue.map((q) => q.id)).toEqual([2, 3]);
  });

  it("info 顶替 ambient（高顶低通用规则）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "ambient", "tool:edit"), T0);
    s = enqueue(s, item(2, "info", "token-report"), T0 + 100);
    expect(s.current?.id).toBe(2);
    expect(s.queue.map((q) => q.id)).toEqual([1]);
  });
});

describe("bubble-queue TC-UI-09 ②同源合并 10s", () => {
  it("显示中的同源同级 10s 内替换：文案刷新 + dwell 重计时", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "token-report", "第一条"), T0);
    // 6s dwell 走到 5.9s 时合并刷新 → dwell 必须重计时（否则 0.1s 后就到期）
    const t1 = T0 + 5_900;
    s = enqueue(s, item(2, "info", "token-report", "第二条"), t1);
    expect(s.current?.id).toBe(2); // 原地替换显示中条目
    expect(s.current?.text).toBe("第二条");
    expect(s.queue).toHaveLength(0); // 不产生第二条排队
    // 替换后 5.9s 内不应到期（dwell 从 t1 重算）
    const r = expireCurrent(s, t1 + DWELL_MS.info - 1);
    expect(r.dismissed).toBeNull();
    const r2 = expireCurrent(s, t1 + DWELL_MS.info);
    expect(r2.dismissed?.id).toBe(2);
  });

  it("队列中的同源同级也替换（位置不变）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "reminder:1"), T0);
    s = enqueue(s, item(2, "info", "token-report", "旧"), T0 + 100);
    s = enqueue(s, item(3, "info", "token-report", "新"), T0 + 2_000);
    expect(s.queue.map((q) => q.id)).toEqual([3]); // 队列中原地替换（不追加）
    expect(s.queue[0].text).toBe("新");
  });

  it("合并窗口外（>10s）→ 独立入队，不合并", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "a"), T0);
    s = enqueue(s, item(2, "info", "a"), T0 + MERGE_WINDOW_MS + 1);
    expect(s.queue.map((q) => q.id)).toEqual([2]); // 窗口外新条目独立排队
  });

  it("同源不同级不合并", () => {
    // current info + 到达 ambient（同 source）→ 走顶替判断（低不顶高）入队，不合
    let s = initialState();
    s = enqueue(s, item(10, "info", "x"), T0);
    s = enqueue(s, item(11, "ambient", "x"), T0 + 100);
    expect(s.current?.id).toBe(10);
    expect(s.queue.map((q) => q.id)).toEqual([11]); // 同 source 不同 level 不合并
  });
});

describe("bubble-queue TC-UI-09 ③队列上限与驱逐", () => {
  it("上限 3 指 queue 长度（不含 current）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "r:1"), T0);
    s = enqueue(s, item(2, "critical", "r:2"), T0 + 1);
    s = enqueue(s, item(3, "critical", "r:3"), T0 + 2);
    s = enqueue(s, item(4, "critical", "r:4"), T0 + 3);
    expect(s.queue).toHaveLength(3);
  });

  it("超限按 ambient → info 顺序从队尾驱逐：ambient 先逐出", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "r:1"), T0); // current
    s = enqueue(s, item(2, "info", "i-2"), T0 + 1);
    s = enqueue(s, item(3, "ambient", "a-3"), T0 + 2);
    s = enqueue(s, item(4, "ambient", "a-4"), T0 + 3); // queue: [2,3,4] 满
    // 新 ambient 入队超限 → 队尾（新入者）被驱逐
    s = enqueue(s, item(5, "ambient", "a-5"), T0 + 4);
    expect(s.queue.map((q) => q.id)).toEqual([2, 3, 4]); // 队尾 ambient（新 a-5）被驱逐
    // 新 info 入队超限 → 驱逐队尾起第一个 ambient（a-4），新条目保留
    s = enqueue(s, item(6, "info", "i-6"), T0 + 5);
    expect(s.queue.map((q) => q.id)).toEqual([2, 3, 6]); // a-4 逐出、i-6 保留
  });

  it("critical / info 永不被驱逐：全 critical/info 队列允许临时超 3", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "r:1"), T0); // current
    s = enqueue(s, item(2, "info", "i-2"), T0 + 1);
    s = enqueue(s, item(3, "info", "i-3"), T0 + 2);
    s = enqueue(s, item(4, "info", "i-4"), T0 + 3); // queue 恰满 [2,3,4]
    s = enqueue(s, item(5, "info", "i-5"), T0 + 4); // 超限但无可驱逐的 ambient
    expect(s.queue.map((q) => q.id)).toEqual([2, 3, 4, 5]); // 允许临时超 3，info 保留
    s = enqueue(s, item(6, "critical", "r:6"), T0 + 5);
    expect(s.queue).toHaveLength(5); // critical 同样不驱逐
  });

  it("被顶替回队的 ambient 遇满队驱逐即丢弃（ambient 可丢语义）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "ambient", "a-1"), T0); // current ambient
    s = enqueue(s, item(2, "info", "i-2"), T0 + 1);
    s = enqueue(s, item(3, "info", "i-3"), T0 + 2);
    s = enqueue(s, item(4, "info", "i-4"), T0 + 3); // queue: [2,3,4] 满（info 不驱逐）
    s = enqueue(s, item(5, "critical", "r-5"), T0 + 4); // critical 顶掉 ambient a-1 回队
    expect(s.current?.id).toBe(5);
    expect(s.queue.map((q) => q.id)).toEqual([2, 3, 4]); // 回队的 a-1 遇满队即丢
  });
});

describe("bubble-queue TC-UI-09 ④分级 dwell", () => {
  it("critical 8s / info 6s / ambient 4s；dwellFor 常量一致", () => {
    expect(DWELL_MS).toEqual({ critical: 8000, info: 6000, ambient: 4000 });
    expect(dwellFor("critical")).toBe(8000);
    expect(dwellFor("info")).toBe(6000);
    expect(dwellFor("ambient")).toBe(4000);
  });

  it("expireCurrent 到期离场并推进队首", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "a"), T0);
    s = enqueue(s, item(2, "ambient", "b"), T0 + 1); // 低优先级不顶 info，排队
    expect(expireCurrent(s, T0 + DWELL_MS.info - 1).dismissed).toBeNull();
    const { state: s2, dismissed } = expireCurrent(s, T0 + DWELL_MS.info);
    expect(dismissed?.id).toBe(1);
    expect(s2.current?.id).toBe(2); // 队首推进上屏
    expect(s2.queue).toHaveLength(0);
  });

  it("current 为 null 时 expireCurrent 是 no-op", () => {
    const s = initialState();
    const r = expireCurrent(s, T0);
    expect(r.dismissed).toBeNull();
    expect(r.state.current).toBeNull();
  });
});

describe("bubble-queue TC-UI-09 ⑤悬停层冻结（M3 预留接口）", () => {
  it("setHoverPaused(true) 冻结 dwell：expireCurrent 不推进", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "a"), T0);
    const frozenAt = T0 + 3_000;
    s = setHoverPaused(s, true, frozenAt);
    // 冻结 60s 后仍不应到期
    const r = expireCurrent(s, frozenAt + 60_000);
    expect(r.dismissed).toBeNull();
    expect(r.state.current?.id).toBe(1);
  });

  it("恢复后续走剩余 dwell（冻结期不计入显示时长）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "a"), T0); // dwell 6s
    const frozenAt = T0 + 3_000; // 已显示 3s
    s = setHoverPaused(s, true, frozenAt);
    const resumedAt = frozenAt + 60_000;
    s = setHoverPaused(s, false, resumedAt);
    // 剩余 3s：resumedAt + 3s - 1 未到期，+3s 到期
    expect(expireCurrent(s, resumedAt + 2_999).dismissed).toBeNull();
    expect(expireCurrent(s, resumedAt + 3_000).dismissed?.id).toBe(1);
  });

  it("队列不推进：current 空且队列有货时冻结期间 expire 不推进队首", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "r:1"), T0);
    s = enqueue(s, item(2, "info", "i"), T0 + 1);
    s = setHoverPaused(s, true, T0 + 10);
    const r = expireCurrent(s, T0 + DWELL_MS.critical + 5_000);
    expect(r.dismissed).toBeNull(); // 冻结期间不结案
    expect(r.state.current?.id).toBe(1); // 队列不推进
  });
});

describe("bubble-queue TC-UI-09 ⑥记账时机 / ack", () => {
  it("只有最终离开显示才 dismissed：同级 critical 间 FIFO 轮换（不顶替）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "reminder:1", "第一条", { reminder: { logId: 1 } }), T0);
    // 同级新 critical（不同 source）→ FIFO 排队，不顶显示中的
    s = enqueue(s, item(2, "critical", "reminder:2"), T0 + 100);
    expect(s.current?.id).toBe(1); // 同级 critical FIFO（不顶替）
    expect(s.queue.map((q) => q.id)).toEqual([2]);
    // 1 到期 → 2 上屏（1 最终离场才结案，reminder 记账信息完整）
    const r = expireCurrent(s, T0 + DWELL_MS.critical);
    expect(r.dismissed?.id).toBe(1);
    expect(r.dismissed?.reminder).toEqual({ logId: 1 }); // 记账信息完整保留到最终离场
    expect(r.state.current?.id).toBe(2); // 队首轮换上屏
    const r2 = expireCurrent(r.state, T0 + DWELL_MS.critical * 2 + 100);
    expect(r2.dismissed?.id).toBe(2);
  });

  it("高优先级顶替：被顶者回队首不结案，随后重现（顶替回队路径的记账）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "token-report", "汇报"), T0);
    // critical 到达 → info(1) 被顶回队首
    s = enqueue(s, item(2, "critical", "reminder:9", "r", { reminder: { logId: 9 } }), T0 + 100);
    expect(s.current?.id).toBe(2);
    expect(s.queue.map((q) => q.id)).toEqual([1]); // 被顶的 info 回队首未结案
    // critical 确认（ack）→ info 重现
    const { state: s2, acked } = ackCurrent(s, T0 + 500);
    expect(acked?.reminder).toEqual({ logId: 9 });
    expect(s2.current?.id).toBe(1); // 被顶者随后重现
    expect(s2.queue).toHaveLength(0);
  });

  it("被顶者重现续走剩余 dwell（TC-UI-10-2：已显示时长从 dwell 中扣除）", () => {
    let s = initialState();
    s = enqueue(s, item(1, "info", "token-report"), T0); // info dwell 6s
    // 显示 4s 后被 critical 顶掉 → 剩余 dwell 2s
    s = enqueue(s, item(2, "critical", "reminder:9"), T0 + 4_000);
    // critical 1s 后被确认 → info 重现
    const { state: s2 } = ackCurrent(s, T0 + 5_000);
    expect(s2.current?.id).toBe(1);
    // 重现后 2s - 1ms 不应到期（续走剩余而非从头 6s）
    expect(expireCurrent(s2, T0 + 5_000 + 2_000 - 1).dismissed).toBeNull();
    expect(expireCurrent(s2, T0 + 5_000 + 2_000).dismissed?.id).toBe(1);
  });

  it("ackCurrent：确认当前条目并推进队列", () => {
    let s = initialState();
    s = enqueue(s, item(1, "critical", "reminder:1", "r", { reminder: { logId: 7 } }), T0);
    s = enqueue(s, item(2, "info", "i"), T0 + 1);
    const { state: s2, acked } = ackCurrent(s, T0 + 500);
    expect(acked?.id).toBe(1);
    expect(acked?.reminder).toEqual({ logId: 7 });
    expect(s2.current?.id).toBe(2); // 确认后队首推进
  });

  it("ackCurrent：无 current 时 no-op", () => {
    const { state, acked } = ackCurrent(initialState(), T0);
    expect(acked).toBeNull();
    expect(state.current).toBeNull();
  });

  it("QUEUE_MAX = 3、MERGE_WINDOW_MS = 10s 常量钉子", () => {
    expect(QUEUE_MAX).toBe(3);
    expect(MERGE_WINDOW_MS).toBe(10_000);
  });
});
