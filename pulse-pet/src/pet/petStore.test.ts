import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePetStore } from "./petStore";
import { BUBBLE_AUTO_HIDE_MS } from "../lib/bubble";

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
