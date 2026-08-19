import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePetStore, setReminderReporter, type ReminderReporter } from "./petStore";
import { BUBBLE_AUTO_HIDE_MS } from "../lib/bubble";
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

describe("petStore 气泡状态（M3 token 汇报，TC-TK-10/12）", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    usePetStore.getState().hideBubble();
    usePetStore.getState().setRaw("idle");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("showBubble：合法文本入列，8s 后自动消失", () => {
    usePetStore.getState().showBubble("本期用了 58.3k input / 910 output / $0.05");
    expect(usePetStore.getState().bubble?.text).toBe(
      "本期用了 58.3k input / 910 output / $0.05",
    );
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS - 1);
    expect(usePetStore.getState().bubble).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble).toBeNull();
  });

  it("showBubble：净化约束生效（多行单行化、超长截断、非法输入丢弃）", () => {
    usePetStore.getState().showBubble("a\nb");
    expect(usePetStore.getState().bubble?.text).toBe("a b");
    usePetStore.getState().showBubble("x".repeat(200));
    expect(usePetStore.getState().bubble?.text?.length).toBe(140);
    // 空串/非字符串 → 不出气泡（TC-TK-12 精神：无内容不显示）
    usePetStore.getState().hideBubble();
    usePetStore.getState().showBubble("");
    expect(usePetStore.getState().bubble).toBeNull();
    usePetStore.getState().showBubble(123 as unknown as string);
    expect(usePetStore.getState().bubble).toBeNull();
  });

  it("showBubble：新气泡重置自动隐藏计时", () => {
    usePetStore.getState().showBubble("第一条");
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS - 1);
    usePetStore.getState().showBubble("第二条");
    // 再走满 8s：从第二条出现时刻起算
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS);
    expect(usePetStore.getState().bubble).toBeNull();
  });

  it("hideBubble：手动清除并取消定时器", () => {
    usePetStore.getState().showBubble("马上消失");
    usePetStore.getState().hideBubble();
    expect(usePetStore.getState().bubble).toBeNull();
    // 定时器已被取消：走到 8s 后不应有残留副作用（保持 null）
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS + 1000);
    expect(usePetStore.getState().bubble).toBeNull();
  });

  it("气泡与精灵状态互不影响", () => {
    usePetStore.getState().setRaw("success");
    usePetStore.getState().showBubble("汇报");
    expect(usePetStore.getState().sprite).toBe("success");
    expect(usePetStore.getState().raw).toBe("success");
    expect(usePetStore.getState().bubble?.text).toBe("汇报");
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
    usePetStore.getState().showBubble("干得漂亮 🎉");
    usePetStore.getState().startCelebration();
    expect(usePetStore.getState().raw).toBe("working");
    expect(usePetStore.getState().bubble?.text).toBe("干得漂亮 🎉");
    expect(usePetStore.getState().celebration).not.toBeNull();
  });
});

describe("petStore 提醒气泡（M4，TC-RM-03/04/05）", () => {
  let reporter: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    usePetStore.getState().hideBubble();
    usePetStore.getState().setRaw("idle");
    reporter = vi.fn();
    setReminderReporter(reporter as unknown as ReminderReporter);
  });

  afterEach(() => {
    setReminderReporter(null); // 不污染其它用例
    vi.useRealTimers();
  });

  it("showReminderBubble：携带 logId，8s 自动消失回报 auto（TC-RM-03）", () => {
    usePetStore.getState().showReminderBubble("该喝水啦 💧", 42);
    expect(usePetStore.getState().bubble?.text).toBe("该喝水啦 💧");
    expect(usePetStore.getState().bubble?.reminder).toEqual({ logId: 42 });
    expect(reporter).not.toHaveBeenCalled();
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS - 1);
    expect(usePetStore.getState().bubble).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(usePetStore.getState().bubble).toBeNull();
    expect(reporter).toHaveBeenCalledWith(42, "auto");
  });

  it("ackReminderBubble：提前确认 → 立即消失并回报 bubble（TC-RM-04）", () => {
    usePetStore.getState().showReminderBubble("休息一下 ☕", 7);
    vi.advanceTimersByTime(2000); // 触发 2s 时点击
    const done = usePetStore.getState().ackReminderBubble();
    expect(done).toBe(true);
    expect(usePetStore.getState().bubble).toBeNull();
    expect(reporter).toHaveBeenCalledWith(7, "bubble");
    expect(reporter).not.toHaveBeenCalledWith(7, "auto");
    // 确认后定时器已取消：走到 8s 不再触发 auto 回报
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS);
    expect(reporter).toHaveBeenCalledTimes(1);
  });

  it("ackReminderBubble：非提醒气泡返回 false（点击交回状态轮换）", () => {
    usePetStore.getState().showBubble("普通气泡");
    expect(usePetStore.getState().ackReminderBubble()).toBe(false);
    expect(usePetStore.getState().bubble).not.toBeNull();
  });

  it("净化后为空的提醒文案：不出气泡，立即按 auto 结案", () => {
    usePetStore.getState().showReminderBubble("   ", 9);
    expect(usePetStore.getState().bubble).toBeNull();
    expect(reporter).toHaveBeenCalledWith(9, "auto");
  });

  it("提醒气泡被新气泡顶替：旧的按 auto 回报", () => {
    usePetStore.getState().showReminderBubble("第一条", 1);
    usePetStore.getState().showReminderBubble("第二条", 2);
    expect(reporter).toHaveBeenCalledWith(1, "auto");
    expect(usePetStore.getState().bubble?.reminder).toEqual({ logId: 2 });
    vi.advanceTimersByTime(BUBBLE_AUTO_HIDE_MS);
    expect(reporter).toHaveBeenCalledWith(2, "auto");
  });
});
