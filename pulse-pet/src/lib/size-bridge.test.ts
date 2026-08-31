/**
 * size-bridge 纯函数单测（§十一档位）：载荷解析 + 档位表锁步。
 * 桥接初始化（initSizeBridge）依赖 Tauri 运行时，不在 vitest 覆盖
 * （照 interaction.test.ts 口径，只测纯函数面）。
 */
import { describe, expect, it } from "vitest";
import { PET_SIZES, isPetSize, parseSizePayload } from "./size-bridge";
import { usePetStore } from "../pet/petStore";

describe("parseSizePayload（pet://size 载荷）", () => {
  it("合法档位 → 原样返回", () => {
    expect(parseSizePayload({ size: "small", logical: 184 })).toBe("small");
    expect(parseSizePayload({ size: "medium", logical: 220 })).toBe("medium");
    expect(parseSizePayload({ size: "large", logical: 280 })).toBe("large");
  });

  it("非法值 → null（不误更新状态）", () => {
    expect(parseSizePayload({ size: "giant", logical: 999 })).toBeNull();
    expect(parseSizePayload({ size: 220 })).toBeNull();
    expect(parseSizePayload({})).toBeNull();
    expect(parseSizePayload(null)).toBeNull();
    expect(parseSizePayload("large")).toBeNull();
  });
});

describe("PET_SIZES 档位表（与 Rust pet_size.rs logical_of 锁步）", () => {
  it("三档数值钉死（184 = 菜单外宽 176 不裁剪下限，§11.4）", () => {
    expect(PET_SIZES).toEqual({ small: 184, medium: 220, large: 280 });
  });

  it("isPetSize 白名单", () => {
    expect(isPetSize("small")).toBe(true);
    expect(isPetSize("medium")).toBe(true);
    expect(isPetSize("large")).toBe(true);
    expect(isPetSize("Medium")).toBe(false);
    expect(isPetSize(undefined)).toBe(false);
  });
});

describe("petStore.setSize（档位状态位）", () => {
  it("默认 medium；setSize 更新", () => {
    usePetStore.setState({ size: "medium" });
    expect(usePetStore.getState().size).toBe("medium");
    usePetStore.getState().setSize("large");
    expect(usePetStore.getState().size).toBe("large");
    usePetStore.setState({ size: "medium" }); // 复位，不影响其它用例
  });
});
