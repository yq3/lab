import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePetStore, setReminderReporter, type ReminderReporter } from "./petStore";
import type { AtlasMeta, AtlasPixels } from "../lib/atlas";

describe("petStore M5 atlas 状态（热替换基础，TC-SP-11②）", () => {
  const meta = (id: string): AtlasMeta => ({
    requested: id,
    currentId: id,
    currentSource: "codex",
    cols: 8,
    rows: 9,
    frameW: 192,
    frameH: 208,
    notice: null,
  });
  const pixels = (tag: number): AtlasPixels => ({
    cols: 8,
    rows: 9,
    frameW: 192,
    frameH: 208,
    rgba: new Uint8Array(8 * 9 * 192 * 208 * 4).fill(tag),
  });

  it("setAtlas：写入 meta + pixels；切换宠物后对象身份变化（热替换信号）", () => {
    usePetStore.setState({ atlas: null, atlasMeta: null });
    const p1 = pixels(1);
    usePetStore.getState().setAtlas(meta("kitty"), p1);
    expect(usePetStore.getState().atlasMeta?.currentId).toBe("kitty");
    expect(usePetStore.getState().atlas).toBe(p1);

    // 面板切换 → 新对象身份（PetCanvas effect 依赖 atlas 身份重建离屏 sheet）
    const p2 = pixels(2);
    usePetStore.getState().setAtlas(meta("boba"), p2);
    expect(usePetStore.getState().atlas).toBe(p2);
    expect(usePetStore.getState().atlas).not.toBe(p1);
    expect(usePetStore.getState().atlasMeta?.currentId).toBe("boba");
  });

  it("setAtlas：pixels=null 表示回退占位（加载失败不崩，P2-3 兜底）", () => {
    usePetStore.getState().setAtlas(meta("broken"), null);
    expect(usePetStore.getState().atlas).toBeNull();
    expect(usePetStore.getState().atlasMeta?.notice).toBeNull();
  });

  it("atlas 模式下 setRaw/next 状态机照常（9 状态映射在渲染层，不动 store）", () => {
    usePetStore.getState().setAtlas(meta("kitty"), pixels(3));
    usePetStore.getState().setRaw("editing");
    expect(usePetStore.getState().raw).toBe("editing");
    expect(usePetStore.getState().sprite).toBe("working"); // 占位降级仍可用
    usePetStore.getState().next();
    expect(usePetStore.getState().raw).toBe("testing");
  });
});

describe("petStore M6 交互模式 / 右键菜单状态（TC-WIN-02/03/05）", () => {
  beforeEach(() => {
    usePetStore.setState({ passThrough: false, contextMenu: null });
  });

  it("默认非穿透（运行时默认可拖拽/右键，DESIGN §7.1）", () => {
    expect(usePetStore.getState().passThrough).toBe(false);
    expect(usePetStore.getState().contextMenu).toBeNull();
  });

  it("setPassThrough：热键/托盘/设置三通道共用同一状态位", () => {
    usePetStore.getState().setPassThrough(true);
    expect(usePetStore.getState().passThrough).toBe(true);
    usePetStore.getState().setPassThrough(false);
    expect(usePetStore.getState().passThrough).toBe(false);
  });

  it("openContextMenu / closeContextMenu：右键菜单坐标进出", () => {
    usePetStore.getState().openContextMenu(30, 60);
    expect(usePetStore.getState().contextMenu).toEqual({ x: 30, y: 60 });
    usePetStore.getState().closeContextMenu();
    expect(usePetStore.getState().contextMenu).toBeNull();
  });

  it("切换穿透时已打开的右键菜单自动关闭（穿透态菜单不可达，TC-WIN-04）", () => {
    usePetStore.getState().openContextMenu(10, 10);
    usePetStore.getState().setPassThrough(true);
    expect(usePetStore.getState().contextMenu).toBeNull();
  });
});

describe("petStore 气泡排队（v2 M2，TC-UI-09/13-3：单槽位断言有意改写为排队语义）", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    usePetStore.getState().resetBubbles();
    usePetStore.getState().setRaw("idle");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("pushBubble(info)：分级 dwell 6s 后自动消失（不再恒定 8s）", () => {
    usePetStore.getState().pushBubble({ text: "本期用了 58.3k input", level: "info", source: "token-report" });
    expect(usePetStore.getState().bubble.current?.text).toBe("本期用了 58.3k input");
    vi.advanceTimersByTime(5999);
    expect(usePetStore.getState().bubble.current).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble.current).toBeNull();
  });

  it("pushBubble 净化约束（多行单行化、超长截断）；空/非法输入丢弃", () => {
    usePetStore.getState().pushBubble({ text: "a\nb", level: "info", source: "x" });
    expect(usePetStore.getState().bubble.current?.text).toBe("a b");
    usePetStore.getState().pushBubble({ text: "x".repeat(200), level: "info", source: "x" });
    expect(usePetStore.getState().bubble.current?.text?.length).toBe(140);
    usePetStore.getState().resetBubbles();
    usePetStore.getState().pushBubble({ text: "", level: "info", source: "x" });
    expect(usePetStore.getState().bubble.current).toBeNull();
    usePetStore.getState().pushBubble({ text: 123 as unknown as string, level: "info", source: "x" });
    expect(usePetStore.getState().bubble.current).toBeNull();
  });

  it("critical 顶替 info：info 回队首、critical 到期后 info 重现（续走剩余 dwell）", () => {
    usePetStore.getState().pushBubble({ text: "汇报", level: "info", source: "token-report" });
    vi.advanceTimersByTime(3000); // info 已显示 3s
    usePetStore.getState().pushBubble({ text: "该喝水啦 💧", level: "critical", source: "reminder:1", reminder: { logId: 1 } });
    expect(usePetStore.getState().bubble.current?.level).toBe("critical");
    expect(usePetStore.getState().bubble.queue.map((q) => q.text)).toEqual(["汇报"]);
    // critical 8s 到期 → info 重现；剩余 dwell 3s（冻结语义外的续走由 shownAt 推进保证）
    vi.advanceTimersByTime(8000);
    expect(usePetStore.getState().bubble.current?.text).toBe("汇报");
    vi.advanceTimersByTime(2999);
    expect(usePetStore.getState().bubble.current?.text).toBe("汇报");
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble.current).toBeNull();
  });

  it("悬停冻结（M3 预留接口）：setHoverPaused(true) 冻结 dwell，恢复续走剩余", () => {
    usePetStore.getState().pushBubble({ text: "a", level: "info", source: "x" });
    vi.advanceTimersByTime(3000);
    usePetStore.getState().setHoverPaused(true);
    vi.advanceTimersByTime(60000); // 冻结期间不走
    expect(usePetStore.getState().bubble.current).not.toBeNull();
    usePetStore.getState().setHoverPaused(false);
    vi.advanceTimersByTime(2999); // 剩余 3s
    expect(usePetStore.getState().bubble.current).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble.current).toBeNull();
  });

  it("R2 P2-1：冻结期间新上屏气泡不挂 dwell 计时器（防 0ms 定时器死循环）", () => {
    usePetStore.getState().pushBubble({ text: "a", level: "info", source: "x" });
    usePetStore.getState().setHoverPaused(true); // 冻结 → 清计时器
    expect(vi.getTimerCount()).toBe(0);
    // 冻结期间 critical 到达（顶替上屏）：修复前 pushBubble 会经
    // armForCurrent 挂 dwell 计时器 → 到期时 expireCurrent 因冻结返回
    // dismissed:null → remain=max(0, dwell-elapsed)=0 → setTimeout(0) 无限循环
    usePetStore.getState().pushBubble({
      text: "r", level: "critical", source: "reminder:1", reminder: { logId: 1 },
    });
    expect(usePetStore.getState().bubble.current?.level).toBe("critical");
    expect(vi.getTimerCount()).toBe(0); // 冻结期间不得挂 dwell 计时器（0ms 死循环根因）
    // 走过 dwell+1：无计时器 → 无 tick → 不结案、不空转
    vi.advanceTimersByTime(10_000);
    expect(usePetStore.getState().bubble.current?.text).toBe("r");
  });
});

describe("petStore 提醒气泡排队 + 记账（M4 语义在排队模型下的延续，TC-UI-09-6/TC-UI-10）", () => {
  let reporter: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    usePetStore.getState().resetBubbles();
    usePetStore.getState().setRaw("idle");
    reporter = vi.fn();
    setReminderReporter(reporter as unknown as ReminderReporter);
  });

  afterEach(() => {
    setReminderReporter(null); // 不污染其它用例
    vi.useRealTimers();
  });

  it("critical 携带 logId：8s 自动消失回报 auto（TC-RM-03 语义在分级 dwell 下）", () => {
    usePetStore.getState().pushBubble({ text: "该喝水啦 💧", level: "critical", source: "reminder:42", reminder: { logId: 42 } });
    expect(usePetStore.getState().bubble.current?.reminder).toEqual({ logId: 42 });
    expect(reporter).not.toHaveBeenCalled();
    vi.advanceTimersByTime(7999);
    expect(usePetStore.getState().bubble.current).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble.current).toBeNull();
    expect(reporter).toHaveBeenCalledWith(42, "auto");
  });

  it("ackReminderBubble：提前确认 → 立即消失回报 bubble（TC-RM-04）", () => {
    usePetStore.getState().pushBubble({ text: "休息一下 ☕", level: "critical", source: "reminder:7", reminder: { logId: 7 } });
    vi.advanceTimersByTime(2000);
    const done = usePetStore.getState().ackReminderBubble();
    expect(done).toBe(true);
    expect(usePetStore.getState().bubble.current).toBeNull();
    expect(reporter).toHaveBeenCalledWith(7, "bubble");
    expect(reporter).not.toHaveBeenCalledWith(7, "auto");
    vi.advanceTimersByTime(10000);
    expect(reporter).toHaveBeenCalledTimes(1); // 确认后计时器不再触发 auto
  });

  it("ackReminderBubble：非提醒气泡返回 false（点击交回状态轮换）", () => {
    usePetStore.getState().pushBubble({ text: "普通气泡", level: "info", source: "x" });
    expect(usePetStore.getState().ackReminderBubble()).toBe(false);
    expect(usePetStore.getState().bubble.current).not.toBeNull();
  });

  // ---- v2 M4（TC-M4-13）：snooze 按钮 —— 与 ack 同一离场语义，via='snooze' ----

  it("snoozeReminderBubble：气泡即消回报 snooze；确认后不再触发 auto", () => {
    usePetStore.getState().pushBubble({ text: "休息一下 ☕", level: "critical", source: "reminder:11", reminder: { logId: 11 } });
    vi.advanceTimersByTime(1000);
    const done = usePetStore.getState().snoozeReminderBubble();
    expect(done).toBe(true);
    expect(usePetStore.getState().bubble.current).toBeNull();
    expect(reporter).toHaveBeenCalledWith(11, "snooze");
    expect(reporter).not.toHaveBeenCalledWith(11, "auto");
    expect(reporter).not.toHaveBeenCalledWith(11, "bubble");
    vi.advanceTimersByTime(10000);
    expect(reporter).toHaveBeenCalledTimes(1); // snooze 离场后计时器不再触发 auto
  });

  it("snoozeReminderBubble：exec 结果气泡（无 reminder 载荷）返回 false——永不 snooze", () => {
    usePetStore.getState().pushBubble({ text: "任务：任务完成", level: "critical", source: "task:3" });
    expect(usePetStore.getState().snoozeReminderBubble()).toBe(false);
    expect(usePetStore.getState().bubble.current).not.toBeNull();
    expect(reporter).not.toHaveBeenCalled();
  });

  it("净化后为空的提醒文案：不出气泡，立即按 auto 结案（§2.6.1 规则⑤）", () => {
    usePetStore.getState().pushBubble({ text: "   ", level: "critical", source: "reminder:9", reminder: { logId: 9 } });
    expect(usePetStore.getState().bubble.current).toBeNull();
    expect(reporter).toHaveBeenCalledWith(9, "auto");
  });

  it("critical 显示中 info 排队：critical 到期才记账，info 随后上屏（规则⑥）", () => {
    usePetStore.getState().pushBubble({ text: "第一条", level: "critical", source: "reminder:1", reminder: { logId: 1 } });
    // token 汇报（info）不会顶 critical：排队
    usePetStore.getState().pushBubble({ text: "汇报", level: "info", source: "token-report" });
    expect(usePetStore.getState().bubble.current?.reminder).toEqual({ logId: 1 });
    expect(usePetStore.getState().bubble.queue).toHaveLength(1);
    // 第一条 8s 到期 → 汇报上屏；第一条此时才结案 auto
    vi.advanceTimersByTime(8000);
    expect(reporter).toHaveBeenCalledTimes(1);
    expect(reporter).toHaveBeenCalledWith(1, "auto");
    expect(usePetStore.getState().bubble.current?.text).toBe("汇报");
    // 汇报 6s 到期消失（从其上屏时刻起算）
    vi.advanceTimersByTime(6000);
    expect(usePetStore.getState().bubble.current).toBeNull();
    expect(reporter).toHaveBeenCalledTimes(1); // info 气泡无记账
  });
});

describe("petStore M7 完成庆祝（TC-TD-04/05 waving 覆盖）", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-17T12:00:00"));
    usePetStore.setState({ celebration: null });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("startCelebration：写入 { id, until }，默认约 3s 生效期", () => {
    usePetStore.getState().startCelebration();
    const c = usePetStore.getState().celebration;
    expect(c).not.toBeNull();
    expect(c?.id).toBeGreaterThan(0);
    expect(c?.until).toBe(Date.now() + 3000);
  });

  it("startCelebration：可自定义时长；再次调用刷新 until（新 id）", () => {
    usePetStore.getState().startCelebration(8000);
    const first = usePetStore.getState().celebration;
    expect(first?.until).toBe(Date.now() + 8000);
    vi.advanceTimersByTime(1000);
    usePetStore.getState().startCelebration(3000);
    const second = usePetStore.getState().celebration;
    expect(second?.id).not.toBe(first?.id);
    expect(second?.until).toBe(Date.now() + 3000);
  });

  it("庆祝与气泡/精灵状态互不影响（渲染层按 until 覆盖行，不改 raw）", () => {
    usePetStore.getState().setRaw("working");
    usePetStore.getState().pushBubble({ text: "干得漂亮 🎉", level: "info", source: "celebration" });
    usePetStore.getState().startCelebration();
    expect(usePetStore.getState().raw).toBe("working");
    expect(usePetStore.getState().bubble.current?.text).toBe("干得漂亮 🎉");
    expect(usePetStore.getState().celebration).not.toBeNull();
  });
});
