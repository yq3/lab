/**
 * bubble-queue：v2 M2 气泡排队模型（V2-DESIGN §2.6，TC-UI-09）。
 *
 * 单显示位 + 三级优先级队列（critical/info/ambient）的**纯函数内核**：
 * - `enqueue`：同源合并（10s 窗口）→ 顶替回队 → FIFO 入队 → 超限驱逐；
 * - `expireCurrent`：dwell 到期离场 + 队首推进（悬停冻结期间不推进）；
 * - `ackCurrent`：点宠物确认当前条目 + 推进；
 * - `setHoverPaused`：悬停层冻结/恢复（M3 预留接口，恢复续走剩余 dwell）。
 *
 * 全部可注入 `now`（虚拟时钟直测）；petStore 负责计时器接线与提醒记账
 * （只有 dismissed/acked 最终离场才回报——被顶回队期间不结案）。
 */

/** 气泡级别（提醒=critical / 会话汇报·庆祝=info / 工具播报=ambient）。 */
export type BubbleLevel = "critical" | "info" | "ambient";

/** 分级 dwell：critical 8s（或点宠物确认）/ info 6s / ambient 4s（§2.6.1）。 */
export const DWELL_MS: Record<BubbleLevel, number> = {
  critical: 8000,
  info: 6000,
  ambient: 4000,
};

/** 同源合并窗口（同 source + 同级别 10s 内原地替换，§2.6.1 规则②）。 */
export const MERGE_WINDOW_MS = 10_000;

/** 队列上限 = queue 数组长度（不含 current），§2.6.1 规则③。 */
export const QUEUE_MAX = 3;

export interface BubbleItem {
  id: number;
  text: string;
  level: BubbleLevel;
  /** 合并键："reminder:<logId>" | "token-report" | "celebration" | "tool:<tool>"… */
  source: string;
  /** critical 且来自提醒时携带（ack/记账，v1 字段）。 */
  reminder?: { logId: number };
  /** 入队时刻（FIFO 稳定排序 + 合并窗口判定基准）。 */
  enqueuedAt: number;
  /**
   * 被顶替回队前的已显示时长（顶替时写入；重现上屏时从 dwell 中扣除——
   * 「剩余 dwell 续走」，TC-UI-10-2）。非回队条目无此字段。
   */
  preShownMs?: number;
}

export interface BubbleState {
  /** 当前显示位。 */
  current: BubbleItem | null;
  /** 排队条目（上限 3；critical/info 永不被驱逐，允许临时超限）。 */
  queue: BubbleItem[];
  /** 悬停层暂停（true = dwell 冻结、队列不推进；M3 消费）。 */
  hoverPaused: boolean;
  /** current 开始显示的时刻（合并刷新时重置；冻结恢复时平移）。 */
  shownAt: number;
  /** 冻结起点（hoverPaused=true 时非 null）。 */
  pausedAt: number | null;
}

export function initialState(): BubbleState {
  return { current: null, queue: [], hoverPaused: false, shownAt: 0, pausedAt: null };
}

export function dwellFor(level: BubbleLevel): number {
  return DWELL_MS[level];
}

const LEVEL_RANK: Record<BubbleLevel, number> = { ambient: 0, info: 1, critical: 2 };

/** 同源合并：同 source + 同级别 + 窗口内的旧条目可被新条目原地替换。 */
function mergeable(old: BubbleItem, incoming: BubbleItem, now: number): boolean {
  return (
    old.source === incoming.source &&
    old.level === incoming.level &&
    now - old.enqueuedAt <= MERGE_WINDOW_MS
  );
}

/**
 * 超限驱逐（§2.6.1 规则③）：queue 超 QUEUE_MAX 时按 **ambient → info 顺序
 * 从队尾驱逐**；critical/info 永不被驱逐（无 ambient 可驱时允许临时超限——
 * 「提醒记账无漏账」的硬约束）。被顶回队的 ambient 遇满队自然落在驱逐序里
 * （可丢语义）。
 */
function evictOverflow(queue: BubbleItem[]): BubbleItem[] {
  let q = queue;
  while (q.length > QUEUE_MAX) {
    // 从队尾往前找第一个 ambient 驱逐（「从队尾驱逐」+ ambient 优先）；
    // 找不到 ambient（全 critical/info）→ 停止（允许临时超限）。
    let idx = -1;
    for (let i = q.length - 1; i >= 0; i--) {
      if (q[i].level === "ambient") {
        idx = i;
        break;
      }
    }
    if (idx < 0) break;
    q = [...q.slice(0, idx), ...q.slice(idx + 1)];
  }
  return q;
}

/**
 * 入队（含同源合并 / 顶替回队 / FIFO / 上限驱逐）：
 * 1. 同源合并：显示中或队列中的同 source+级别 且 10s 内的旧条目被新条目
 *    原地替换（显示中的文案刷新 + dwell 重计时 shownAt=now；队列中的位置
 *    不变）——不产生第二条；
 * 2. 顶替：高优先级立即顶掉显示中的低优先级（被顶者回**队首**，不丢失、
 *    不结案；critical 只被同级 critical 以 FIFO/合并轮换）；
 * 3. 同级/低级到达 → FIFO 入队尾；
 * 4. 入队/回队导致 queue 超限 → evictOverflow。
 */
export function enqueue(state: BubbleState, item: BubbleItem, now: number): BubbleState {
  // ① 显示中条目合并（文案刷新 + dwell 重计时）
  if (state.current && mergeable(state.current, item, now)) {
    return { ...state, current: { ...item, enqueuedAt: now }, shownAt: now };
  }
  // ② 队列中条目合并（原地替换，位置不变）
  const qIdx = state.queue.findIndex((q) => mergeable(q, item, now));
  if (qIdx >= 0) {
    const queue = [...state.queue];
    queue[qIdx] = { ...item, enqueuedAt: now };
    return { ...state, queue };
  }
  // ③ 顶替：高优先级顶掉显示中的低优先级（被顶者回**队首**，不丢失、
  //    不结案；已显示时长记入 preShownMs——重现时续走剩余 dwell）
  if (
    state.current &&
    LEVEL_RANK[item.level] > LEVEL_RANK[state.current.level]
  ) {
    const evicted: BubbleItem = {
      ...state.current,
      preShownMs: now - state.shownAt,
    };
    const queue = evictOverflow([evicted, ...state.queue]);
    return { ...state, current: { ...item, enqueuedAt: now }, shownAt: now, queue };
  }
  // ④ FIFO 入队尾（current 空则直接上屏）
  if (!state.current) {
    return { ...state, current: { ...item, enqueuedAt: now }, shownAt: now };
  }
  return { ...state, queue: evictOverflow([...state.queue, { ...item, enqueuedAt: now }]) };
}

/**
 * dwell 到期离场：返回 `{state, dismissed}`——`dismissed` 为最终离开显示的
 * 条目（记账唯一来源，petStore 据此回报 dismissed_via='auto'），未到期或
 * 悬停冻结期间为 null（队列不推进）。
 */
export function expireCurrent(
  state: BubbleState,
  now: number,
): { state: BubbleState; dismissed: BubbleItem | null } {
  if (!state.current) return { state, dismissed: null };
  if (state.hoverPaused) return { state, dismissed: null };
  if (now - state.shownAt < dwellFor(state.current.level)) {
    return { state, dismissed: null };
  }
  return advance(state, now);
}

/**
 * 确认当前条目（点宠物）：返回 `{state, acked}`——`acked` 为被确认的条目
 * （记账 dismissed_via='bubble'）。
 */
export function ackCurrent(
  state: BubbleState,
  now: number = Date.now(),
): { state: BubbleState; acked: BubbleItem | null } {
  if (!state.current) return { state, acked: null };
  const { state: next, dismissed } = advance(state, now);
  return { state: next, acked: dismissed };
}

/** current 离场 + 队首推进（ack 不受冻结限制——确认即离场）。 */
function advance(
  state: BubbleState,
  now: number,
): { state: BubbleState; dismissed: BubbleItem | null } {
  const dismissed = state.current as BubbleItem;
  const [head, ...rest] = state.queue;
  const next = head
    ? { ...head, preShownMs: undefined }
    : null;
  return {
    state: {
      ...state,
      current: next,
      queue: rest,
      // 回队重现的条目续走剩余 dwell（TC-UI-10-2）；新上屏条目从头计时
      shownAt: next ? now - (head?.preShownMs ?? 0) : now,
    },
    dismissed,
  };
}

/**
 * 悬停层暂停/恢复（M3 预留接口，测试钉住）：
 * - paused=true：记录冻结起点（expireCurrent 不再推进）；
 * - paused=false：shownAt 平移冻结时长——恢复后续走**剩余 dwell**。
 */
export function setHoverPaused(
  state: BubbleState,
  paused: boolean,
  now: number = Date.now(),
): BubbleState {
  if (paused) {
    if (state.hoverPaused) return state;
    return { ...state, hoverPaused: true, pausedAt: now };
  }
  if (!state.hoverPaused) return state;
  const frozen = state.pausedAt !== null ? Math.max(0, now - state.pausedAt) : 0;
  return {
    ...state,
    hoverPaused: false,
    pausedAt: null,
    shownAt: state.current ? state.shownAt + frozen : state.shownAt,
  };
}
