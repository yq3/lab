import { describe, expect, it } from "vitest";
import {
  buildTabs,
  normalizeTabId,
  resolveTabId,
  type PluginTabSource,
} from "./registry";
import type { ComponentType } from "react";

/** 构造 plugins_list 返回形状的插件行（render 映射表测试注入）。 */
function plugin(p: Partial<PluginTabSource> & { id: string }): PluginTabSource {
  const base: PluginTabSource = {
    id: p.id,
    name: p.name ?? "Plugin",
    enabled: p.enabled ?? true,
    panel_tab: "panel_tab" in p ? (p.panel_tab ?? null) : { title: p.name ?? "Plugin" },
  };
  return { ...base, ...p } as PluginTabSource;
}

const noop = (() => null) as unknown as ComponentType<unknown>;

describe("registry TC-UI-14 ①核心三 tab 静态注册、顺序固定", () => {
  it("无插件时 = token → tasks → settings", () => {
    const tabs = buildTabs([], {});
    expect(tabs.map((t) => t.id)).toEqual(["token", "tasks", "settings"]);
    expect(tabs.every((t) => t.kind === "core")).toBe(true);
  });

  it("核心 tab 有 i18n labelKey + render（v2 M4：tasks 键）", () => {
    const tabs = buildTabs([], {});
    expect(tabs[0].labelKey).toBe("panel.tab.token");
    expect(tabs[1].labelKey).toBe("panel.tab.tasks");
    expect(tabs[2].labelKey).toBe("panel.tab.settings");
    for (const t of tabs) expect(typeof t.render).toBe("function");
  });
});

describe("registry TC-UI-14 ①插件插位（按 name 排序，插在 tasks 与 settings 之间）", () => {
  it("单个插件 tab 插位", () => {
    const tabs = buildTabs([plugin({ id: "built-in-todo", name: "Todo" })], {
      "built-in-todo": noop,
    });
    expect(tabs.map((t) => t.id)).toEqual(["token", "tasks", "built-in-todo", "settings"]);
    expect(tabs[2].kind).toBe("plugin");
    expect(tabs[2].label).toBe("Todo");
  });

  it("多插件按 name 排序（zeta/alpha → alpha 在前）", () => {
    const tabs = buildTabs(
      [
        plugin({ id: "p-zeta", name: "Zeta" }),
        plugin({ id: "p-alpha", name: "Alpha" }),
      ],
      { "p-zeta": noop, "p-alpha": noop },
    );
    expect(tabs.map((t) => t.id)).toEqual([
      "token",
      "tasks",
      "p-alpha",
      "p-zeta",
      "settings",
    ]);
  });

  it("render 映射表缺插件的静态绑定 → 该插件 tab 不生成（无动态代码加载）", () => {
    const tabs = buildTabs([plugin({ id: "unknown-plugin", name: "X" })], {
      "built-in-todo": noop,
    });
    expect(tabs.map((t) => t.id)).toEqual(["token", "tasks", "settings"]);
  });
});

describe("registry TC-UI-14 ②禁用过滤", () => {
  it("enabled=false 的插件 tab 不出现在注册表", () => {
    const tabs = buildTabs([plugin({ id: "built-in-todo", enabled: false })], {
      "built-in-todo": noop,
    });
    expect(tabs.map((t) => t.id)).toEqual(["token", "tasks", "settings"]);
  });

  it("panel_tab 缺失（无 tab 声明）→ 不生成 tab", () => {
    const tabs = buildTabs([plugin({ id: "headless", panel_tab: null })], {
      headless: noop,
    });
    expect(tabs.map((t) => t.id)).toEqual(["token", "tasks", "settings"]);
  });
});

describe("registry TC-UI-14 ④ panel_tab 键名钉子（P3-③ 回归陷阱）", () => {
  it("mock 数据含 panel_tab（Rust 序列化键，无 serde rename）→ 正确生成 tab", () => {
    const tabs = buildTabs(
      [plugin({ id: "built-in-todo", panel_tab: { title: "Todo" } })],
      { "built-in-todo": noop },
    );
    expect(tabs.map((t) => t.id)).toContain("built-in-todo");
  });

  it("读错键（panelTab camelCase）→ 插件 tab 缺失（钉住正确键名为 panel_tab）", () => {
    // 模拟「前端读错键」的反例：payload 只有 camelCase panelTab 字段，
    // panel_tab 为空 → 不应生成 tab。
    const wrong = {
      id: "built-in-todo",
      name: "Todo",
      version: "0.1.0",
      enabled: true,
      panelTab: { title: "Todo" },
      panel_tab: null,
    } as unknown as PluginTabSource;
    const tabs = buildTabs([wrong], { "built-in-todo": noop });
    expect(tabs.map((t) => t.id)).not.toContain("built-in-todo");
  });
});

describe("registry TC-UI-14 ③回退（当前 tab 被禁用 → 首个可用）", () => {
  const coreTabs = buildTabs([], {});

  it("目标在列表中 → 直达", () => {
    expect(resolveTabId("tasks", coreTabs)).toBe("tasks");
  });

  it("目标为禁用 tab / 未知值 → 回退首个可用 tab", () => {
    const tabs = buildTabs([plugin({ id: "built-in-todo", enabled: false })], {
      "built-in-todo": noop,
    });
    expect(resolveTabId("built-in-todo", tabs)).toBe("token");
    expect(resolveTabId("no-such-tab", tabs)).toBe("token");
  });

  it("目标为 null（panel://tab 无效载荷）→ 首个可用", () => {
    expect(resolveTabId(null, coreTabs)).toBe("token");
  });
});

describe("v2 M4（TC-M4-02-1）：tab id reminders → tasks + 旧值兼容", () => {
  it("normalizeTabId：旧值 reminders 映射 tasks；其余原样", () => {
    expect(normalizeTabId("reminders")).toBe("tasks");
    expect(normalizeTabId("tasks")).toBe("tasks");
    expect(normalizeTabId("token")).toBe("token");
    expect(normalizeTabId("settings")).toBe("settings");
  });

  it("resolveTabId：panel://tab 直达旧值 reminders → tasks（映射后直达）", () => {
    expect(resolveTabId("reminders", buildTabs([], {}))).toBe("tasks");
  });

  it("旧 id 已不在注册表（防双 tab）", () => {
    const tabs = buildTabs([], {});
    expect(tabs.some((t) => t.id === "reminders")).toBe(false);
    expect(tabs.some((t) => t.id === "tasks")).toBe(true);
  });
});
