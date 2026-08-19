import { describe, expect, it } from "vitest";
import {
  PASS_THROUGH_EVENT,
  PANEL_TAB_EVENT,
  describePassThrough,
  parsePassThroughEnabled,
  normalizeTab,
} from "./interaction";

describe("parsePassThroughEnabled 事件载荷解析（M6，TC-WIN-05 状态同步）", () => {
  it("合法载荷 { enabled: boolean } → 解析出布尔值", () => {
    expect(parsePassThroughEnabled({ enabled: true })).toBe(true);
    expect(parsePassThroughEnabled({ enabled: false })).toBe(false);
  });

  it("非法载荷 → null（不误更新状态）", () => {
    expect(parsePassThroughEnabled(null)).toBeNull();
    expect(parsePassThroughEnabled(undefined)).toBeNull();
    expect(parsePassThroughEnabled("true")).toBeNull();
    expect(parsePassThroughEnabled({ enabled: "yes" })).toBeNull();
    expect(parsePassThroughEnabled({})).toBeNull();
  });
});

describe("事件名常量与文档口径一致（DESIGN §6.3/§7.3）", () => {
  it("穿透状态事件 = pulsepet://pass-through", () => {
    expect(PASS_THROUGH_EVENT).toBe("pulsepet://pass-through");
  });
  it("面板 tab 事件 = panel://tab", () => {
    expect(PANEL_TAB_EVENT).toBe("panel://tab");
  });
});

describe("describePassThrough 人读描述", () => {
  it("开 = 纯展示（鼠标穿透）；关 = 可交互（可拖拽/右键）", () => {
    expect(describePassThrough(true)).toContain("纯展示");
    expect(describePassThrough(false)).toContain("可拖拽");
  });
});

describe("normalizeTab 面板 tab 白名单（PetMenu 设置入口 → panel 设置页）", () => {
  it("合法 tab 原样返回；非法 → null", () => {
    expect(normalizeTab("settings")).toBe("settings");
    expect(normalizeTab("token")).toBe("token");
    expect(normalizeTab("reminders")).toBe("reminders");
    expect(normalizeTab("todo")).toBe("todo"); // M7 起存在（TC-TD-01）
    expect(normalizeTab("about")).toBeNull();
    expect(normalizeTab(42 as unknown as string)).toBeNull();
    expect(normalizeTab(null as unknown as string)).toBeNull();
  });
});
