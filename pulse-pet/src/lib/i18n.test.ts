import { beforeEach, describe, expect, it } from "vitest";
import { changeLanguage, systemLangSafe, t, useLangStore } from "./i18n";

/**
 * i18n（M8，DESIGN §10 "国际化 en/zh"）：
 * - 轻量字典方案（无第三方 i18n 依赖，v1 只双语）；
 * - `t(key, params)` 从当前语言字典取模板并做 `{x}` 插值；
 * - 语言状态在 zustand store（各窗口独立持有，经 `ui://language` 事件同步）；
 * - vitest（非 Tauri）环境默认 zh——既有断言中文文案的单测不受语言切换影响；
 * - 字典完备性：en 与 zh 键集合一致（防漏译静默回退）。
 */

describe("t()：模板查找与插值", () => {
  beforeEach(() => {
    useLangStore.getState().setLang("zh");
  });

  it("zh 默认语言取 zh 模板", () => {
    expect(t("panel.tab.settings")).toBe("设置");
  });

  it("params 做 {x} 插值", () => {
    expect(t("reminders.rules.title", { n: 3 })).toBe("提醒规则（3）");
  });

  it("切换 en 后取 en 模板（含插值）", () => {
    useLangStore.getState().setLang("en");
    expect(t("panel.tab.settings")).toBe("Settings");
    expect(t("reminders.rules.title", { n: 3 })).toBe("Reminder rules (3)");
  });

  it("缺失键回退键名本身（可观测，不静默）", () => {
    expect(t("no.such.key")).toBe("no.such.key");
  });

  it("缺失参数保留占位符", () => {
    expect(t("reminders.rules.title")).toBe("提醒规则（{n}）");
  });

  it("技术词不翻译：状态名 / 品牌名保持原文", () => {
    expect(t("panel.tab.token")).toBe("Token");
    useLangStore.getState().setLang("en");
    expect(t("panel.tab.token")).toBe("Token");
  });
});

describe("字典完备性", () => {
  it("en 与 zh 键集合一致（防漏译）", async () => {
    const { DICT } = await import("./i18n");
    const zhKeys = Object.keys(DICT.zh).sort();
    const enKeys = Object.keys(DICT.en).sort();
    expect(enKeys).toEqual(zhKeys);
  });

  it("两语言均无空串模板", async () => {
    const { DICT } = await import("./i18n");
    for (const [lang, dict] of Object.entries(DICT)) {
      for (const [k, v] of Object.entries(dict)) {
        expect(v.length > 0, `${lang}.${k} 不应为空串`).toBe(true);
      }
    }
  });
});

describe("systemLangSafe：默认语言跟随系统", () => {
  it("zh 开头 → zh；en / 其它 → en（zh/en 之外回退 en）", () => {
    expect(systemLangSafe("zh-CN")).toBe("zh");
    expect(systemLangSafe("zh")).toBe("zh");
    expect(systemLangSafe("en-US")).toBe("en");
    expect(systemLangSafe("ja-JP")).toBe("en"); // 非双语 → 回退 en
    expect(systemLangSafe(undefined)).toBe("en");
    expect(systemLangSafe("")).toBe("en");
  });
});

describe("changeLanguage：非 Tauri 环境仅更新本地 store", () => {
  it("切换后 store 语言变化且不抛错", async () => {
    useLangStore.getState().setLang("zh");
    await changeLanguage("en");
    expect(useLangStore.getState().lang).toBe("en");
    await changeLanguage("zh");
    expect(useLangStore.getState().lang).toBe("zh");
  });
});
