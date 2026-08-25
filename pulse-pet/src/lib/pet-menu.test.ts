import { describe, expect, it } from "vitest";
import {
  buildPetMenuItems,
  clampMenuPosition,
  todayTokenValue,
  type TodayTokenState,
} from "./pet-menu";

describe("buildPetMenuItems 右键菜单项（M6，TC-WIN-03；v2 M3 入口层 TC-M3-11）", () => {
  it("非穿透态：含「设置」与「切换交互模式」入口（TC-WIN-03 规定项）", () => {
    const items = buildPetMenuItems(false, { status: "loading" });
    const labels = items.map((i) => i.label).join("\n");
    expect(labels).toContain("设置");
    expect(labels).toContain("切换交互模式");
  });

  it("「切换交互模式」标签随穿透状态显示 开/关（双通道状态可见，TC-WIN-05）", () => {
    const off = buildPetMenuItems(false, { status: "loading" }).find(
      (i) => i.id === "toggle-pass-through",
    );
    const on = buildPetMenuItems(true, { status: "loading" }).find(
      (i) => i.id === "toggle-pass-through",
    );
    expect(off?.label).toContain("关");
    expect(on?.label).toContain("开");
  });

  it("菜单项 id 唯一且有对应动作", () => {
    const items = buildPetMenuItems(false, { status: "loading" });
    const ids = items.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const need of [
      "today-token",
      "settings",
      "toggle-pass-through",
      "hide-pet",
    ] as const) {
      expect(ids).toContain(need);
    }
  });

  it("v2 M3（N1/TC-M3-11-5）：恰 4 项、第 0 项 id=today-token 且标记 info", () => {
    const items = buildPetMenuItems(false, { status: "loading" });
    expect(items).toHaveLength(4);
    expect(items[0].id).toBe("today-token");
    expect(items[0].info, "信息项分隔线样式标记").toBe(true);
    expect(items.slice(1).every((i) => !i.info)).toBe(true);
  });

  it("v2 M3：三态 label —— … / 42M / —（formatTokens 口径由桥层生成）", () => {
    const states: TodayTokenState[] = [
      { status: "loading" },
      { status: "ok", text: "42M" },
      { status: "error" },
    ];
    const labels = states.map((s) => buildPetMenuItems(false, s)[0].label);
    expect(labels).toEqual(["今日 token：…", "今日 token：42M", "今日 token：—"]);
    // todayTokenValue 纯函数直测
    expect(todayTokenValue({ status: "loading" })).toBe("…");
    expect(todayTokenValue({ status: "ok", text: "1.2M" })).toBe("1.2M");
    expect(todayTokenValue({ status: "error" })).toBe("—");
  });
});

describe("clampMenuPosition 菜单定位（220×220 窗口内，M6）", () => {
  const W = 220;
  const MENU_W = 176;
  const MENU_H = 130; // v2 M3：4 项估值 104 → 130（§3.4 ③）

  it("光标在中上部 → 原位弹出", () => {
    const p = clampMenuPosition(10, 20, W, MENU_W, MENU_H);
    expect(p).toEqual({ x: 10, y: 20 });
  });

  it("光标近右缘 → 左移贴边不越出窗口", () => {
    const p = clampMenuPosition(215, 20, W, MENU_W, MENU_H);
    expect(p.x).toBeLessThanOrEqual(W - MENU_W - 2);
    expect(p.x).toBeGreaterThanOrEqual(2);
  });

  it("光标近底缘 → 上移贴边；两轴同时越界 → 同时 clamp", () => {
    const p = clampMenuPosition(218, 218, W, MENU_W, MENU_H);
    expect(p.y).toBeLessThanOrEqual(W - MENU_H - 2);
    expect(p.x).toBeLessThanOrEqual(W - MENU_W - 2);
  });

  it("菜单比窗口还大 → 退化为安全边距（不 panic）", () => {
    const p = clampMenuPosition(110, 110, W, 300, 300);
    expect(p.x).toBe(2);
    expect(p.y).toBe(2);
  });

  it("v2 M3：menuH=130 下光标在窗口下半部 → 上移贴边不越屏", () => {
    const p = clampMenuPosition(30, 200, W, MENU_W, MENU_H);
    expect(p.y).toBe(W - MENU_H - 2);
    expect(p.y + MENU_H).toBeLessThanOrEqual(W - 2);
  });
});

describe("M8 i18n：右键菜单文案随语言", () => {
  it("en 菜单项 + 穿透开关态", () => {
    const items = buildPetMenuItems(false, { status: "ok", text: "42M" }, "en");
    const labels = items.map((i) => i.label).join("\n");
    expect(labels).toContain("Settings…");
    expect(labels).toContain("Hide pet");
    expect(labels).toContain("pass-through: off");
    expect(labels).toContain("Today's tokens: 42M");
    const on = buildPetMenuItems(true, { status: "error" }, "en").find(
      (i) => i.id === "toggle-pass-through",
    );
    expect(on?.label).toContain("pass-through: on");
  });
});
