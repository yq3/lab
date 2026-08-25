import { create } from "zustand";
import {
  degradeState,
  nextState,
  type NormalizedState,
  type SpriteState,
} from "../lib/state";
import { sanitizeBubbleText } from "../lib/bubble";
import {
  ackCurrent as ackCurrentQ,
  dwellFor,
  enqueue,
  expireCurrent,
  initialState as initialBubbleState,
  setHoverPaused as setHoverPausedQ,
  type BubbleItem,
  type BubbleLevel,
  type BubbleState,
} from "../lib/bubble-queue";
import type { AtlasMeta, AtlasPixels } from "../lib/atlas";

/**
 * v2 M2：气泡从单槽位（`BubbleState | null` + 恒定 8s）升级为**排队模型**
 * （V2-DESIGN §2.6）：`bubble: {current, queue, …}`（`lib/bubble-queue.ts`
 * 纯函数内核）——单显示位 + 三级优先级（critical 8s / info 6s / ambient 4s），
 * 顶替回队、同源合并 10s、上限 3、悬停冻结（M3 预留接口）。
 * 记账语义不变：只有 dismissed/acked 最终离场才回报 dismissed_via。
 */
export type { BubbleItem, BubbleLevel, BubbleState };

/**
 * M7 完成庆祝（TC-TD-04/05）：{ id, until }——PetCanvas rAF 循环按
 * `Date.now() < until` 判定生效期（到期自动失效，无需 React 重渲染），
 * 生效期间 atlas 用 waving 行（= success 行）/占位用 success 画面。
 */
export interface CelebrationState {
  id: number;
  until: number;
}

/** 庆祝动画默认时长（waving 挥手约 3s，与气泡 dwell 独立）。 */
export const CELEBRATION_DEFAULT_MS = 3000;

/**
 * 提醒气泡的消失方式回报（TC-RM-04/03）：
 * - "bubble"：用户点击宠物确认 → Rust `reminders_ack`（acked_at + dismissed_via）；
 * - "auto"：dwell 到期自动消失 → Rust `reminders_dismiss(via='auto')`；
 * - "snooze"（v2 M4，TC-M4-13）：气泡按钮「稍后 10 分钟」→ Rust
 *   `reminders_snooze`（log 结案 via='snooze' + snooze_until 写表 + 重发）。
 * 由 reminder-bridge 注册实现（petStore 不直接依赖 Tauri API，vitest 可裸跑）。
 */
export type ReminderReporter = (
  logId: number,
  via: "bubble" | "auto" | "snooze",
) => void;

interface PetState {
  /** 归一化原始状态（8 种）。 */
  raw: NormalizedState;
  /** 占位精灵状态（5 种，经 8→5 降级映射）。 */
  sprite: SpriteState;
  /**
   * v2 M1：当前显示状态的归属 agent（"opencode" / "claude-code"；默认
   * "opencode"）。panel 状态芯片消费（M2）；M6 抢镜在此基础上扩展。
   */
  displayAgent: string;
  /** 气泡排队状态（v2 M2；纯函数内核在 lib/bubble-queue.ts）。 */
  bubble: BubbleState;
  /** M5：当前 atlas RGBA 图块（null = 无 atlas，占位 PNG 渲染）。 */
  atlas: AtlasPixels | null;
  /** M5：当前 atlas 元数据（含回退 notice；null = 未加载/非 Tauri）。 */
  atlasMeta: AtlasMeta | null;
  /** M6：穿透模式（true = 纯展示：鼠标穿透，不可拖拽/右键；Rust 为唯一权威）。 */
  passThrough: boolean;
  /** M6：右键菜单坐标（null = 关闭；穿透态恒 null，TC-WIN-04）。 */
  contextMenu: { x: number; y: number } | null;
  /** M7：完成庆祝（waving 挥手覆盖期；null = 无）。 */
  celebration: CelebrationState | null;
  setRaw: (raw: NormalizedState) => void;
  /** v2 M1：更新显示状态归属 agent（http-bridge 解析 payload.agent 后调用）。 */
  setDisplayAgent: (agent: string) => void;
  next: () => void;
  /** M5：atlas 加载/热替换（atlas-bridge 调用；对象身份变化驱动 canvas 重建）。 */
  setAtlas: (meta: AtlasMeta, pixels: AtlasPixels | null) => void;
  /** M6：更新穿透状态（interaction-bridge 订阅 Rust 广播后调用）。 */
  setPassThrough: (enabled: boolean) => void;
  /** M6：打开右键菜单（PetCanvas contextmenu 事件）。 */
  openContextMenu: (x: number, y: number) => void;
  /** M6：关闭右键菜单（菜单项动作 / 点击外部 / 窗口失焦）。 */
  closeContextMenu: () => void;
  /** M7：开始完成庆祝（todo 完成 → waving + 气泡，TC-TD-04/05）。 */
  startCelebration: (durationMs?: number) => void;
  /**
   * v2 M2：入队气泡（桥层构造 level/source/reminder；净化约束：单行 1-140，
   * 净化后为空的提醒条目按 auto 结案——§2.6.1 规则⑤）。
   */
  pushBubble: (item: Omit<BubbleItem, "id" | "enqueuedAt">) => void;
  /** v2 M2：悬停层冻结/恢复（M3 预留接口；冻结 dwell、恢复续走剩余）。 */
  setHoverPaused: (paused: boolean) => void;
  /** v2 M2：清空气泡并取消计时（测试 / 诊断用）。 */
  resetBubbles: () => void;
  /** M4：点击宠物"已确认"（TC-RM-04）；非提醒气泡时返回 false（交回状态轮换）。 */
  ackReminderBubble: () => boolean;
  /**
   * v2 M4（TC-M4-13）：snooze 当前提醒气泡——离场 + 结案 via='snooze'
   * （Rust 侧写 snooze_until + next_due 置为重发）；非提醒气泡返回 false。
   */
  snoozeReminderBubble: () => boolean;
}

/** 气泡 dwell 计时器（store 外置，避免进入响应式状态）。 */
let bubbleTimer: ReturnType<typeof setTimeout> | null = null;
let bubbleSeq = 0;
let celebrationSeq = 0;
/** 提醒回报回调（reminder-bridge 注册；null = 无人在意，如 vitest/纯前端 dev）。 */
let reminderReporter: ReminderReporter | null = null;

/** 注册/清空提醒消失回报（reminder-bridge 初始化时调用一次）。 */
export function setReminderReporter(fn: ReminderReporter | null): void {
  reminderReporter = fn;
}

function reportReminder(b: BubbleItem | null | undefined, via: "bubble" | "auto" | "snooze"): void {
  if (b?.reminder) {
    reminderReporter?.(b.reminder.logId, via);
  }
}

function clearBubbleTimer(): void {
  if (bubbleTimer) {
    clearTimeout(bubbleTimer);
    bubbleTimer = null;
  }
}

/** 到期 tick：expireCurrent（记账）→ 推进 → 按新 current 的分级 dwell 重挂。 */
function expireTick(): void {
  bubbleTimer = null;
  const { bubble } = usePetStore.getState();
  const { state, dismissed } = expireCurrent(bubble, Date.now());
  reportReminder(dismissed, "auto");
  usePetStore.setState({ bubble: state });
  armForCurrent(state);
}

/** 为 current 挂 dwell 计时（null 则不挂）。
 * R2 P2-1：悬停冻结期间不挂——冻结中到达/顶替上屏的新条目若挂上计时器，
 * 到期时 expireCurrent 因冻结返回 dismissed:null，remain 重算为 0 →
 * setTimeout(0) 无限循环（CPU 空转直至解除冻结）。恢复路径
 * setHoverPaused(false) 自行重挂，不依赖本函数。 */
function armForCurrent(b: BubbleState): void {
  clearBubbleTimer();
  const cur = b.current;
  if (!cur || b.hoverPaused) return;
  const elapsed = Date.now() - b.shownAt;
  const remain = Math.max(0, dwellFor(cur.level) - elapsed);
  bubbleTimer = setTimeout(expireTick, remain);
}

/**
 * 宠物状态 store。
 *
 * M2 起主事件源：`src/lib/http-bridge.ts` 监听 Rust 下发的合并显示状态
 * （`pulsepet://state` event）→ 调 `setRaw` 更新。`setRaw` / `next` 仍保留，
 * 供占位精灵渲染、降级映射验证（TC-SP-01/01b）与测试 / CDP 手动驱动。
 *
 * M3 起 `pulsepet://bubble` event（token 会话汇报等）→ `pushBubble`（info 级）；
 * M4 起 `reminder://trigger` → `pushBubble`（critical 级，经 reminder-bridge）；
 * v2 M2 起多来源经排队模型合并展示（V2-DESIGN §2.6）。
 */
export const usePetStore = create<PetState>((set, get) => ({
  raw: "idle",
  sprite: "idle",
  displayAgent: "opencode",
  bubble: initialBubbleState(),
  atlas: null,
  atlasMeta: null,
  passThrough: false,
  contextMenu: null,
  celebration: null,
  setAtlas: (meta, pixels) => set({ atlasMeta: meta, atlas: pixels }),
  setPassThrough: (enabled) =>
    // 切到穿透时已打开的右键菜单一并关闭（穿透态菜单不可达，TC-WIN-04）
    set((s) => ({
      passThrough: enabled,
      contextMenu: enabled ? null : s.contextMenu,
    })),
  openContextMenu: (x, y) => set({ contextMenu: { x, y } }),
  closeContextMenu: () => set({ contextMenu: null }),
  startCelebration: (durationMs = CELEBRATION_DEFAULT_MS) => {
    celebrationSeq += 1;
    set({ celebration: { id: celebrationSeq, until: Date.now() + durationMs } });
  },
  setRaw: (raw) => set({ raw, sprite: degradeState(raw) }),
  setDisplayAgent: (agent) => set({ displayAgent: agent }),
  next: () =>
    set((s) => {
      const raw = nextState(s.raw);
      return { raw, sprite: degradeState(raw) };
    }),
  pushBubble: (item) => {
    const clean = sanitizeBubbleText(item.text);
    if (!clean) {
      // 净化后为空：不出气泡；提醒条目按 auto 结案（不留无主日志行，规则⑤）
      if (item.reminder) reminderReporter?.(item.reminder.logId, "auto");
      return;
    }
    const now = Date.now();
    const prev = get().bubble;
    const next = enqueue(
      prev,
      { ...item, text: clean, id: ++bubbleSeq, enqueuedAt: now },
      now,
    );
    set({ bubble: next });
    // current 变化（新上屏 / 顶替 / 合并刷新重计时）→ 重挂 dwell
    if (next.current?.id !== prev.current?.id || next.shownAt !== prev.shownAt) {
      armForCurrent(next);
    }
  },
  setHoverPaused: (paused) => {
    const prev = get().bubble;
    const next = setHoverPausedQ(prev, paused, Date.now());
    set({ bubble: next });
    if (paused) {
      clearBubbleTimer(); // 冻结：dwell 停走（恢复时续走剩余）
    } else {
      armForCurrent(next); // 恢复：续走剩余 dwell（内部含清挂 + 冻结 guard 不触发）
    }
  },
  resetBubbles: () => {
    clearBubbleTimer();
    set({ bubble: initialBubbleState() });
  },
  ackReminderBubble: () => {
    const prev = get().bubble;
    if (!prev.current?.reminder) return false;
    const now = Date.now();
    const { state, acked } = ackCurrentQ(prev, now);
    set({ bubble: state });
    reportReminder(acked, "bubble"); // TC-RM-04：acked_at + dismissed_via='bubble'
    armForCurrent(state);
    return true;
  },
  snoozeReminderBubble: () => {
    // v2 M4（TC-M4-13）：与 ack 同一离场语义，结案 via='snooze'（重发编排全在
    // Rust 侧——snooze_until 写表 + 内存 next_due 置为）
    const prev = get().bubble;
    if (!prev.current?.reminder) return false;
    const now = Date.now();
    const { state, acked } = ackCurrentQ(prev, now);
    set({ bubble: state });
    reportReminder(acked, "snooze");
    armForCurrent(state);
    return true;
  },
}));
