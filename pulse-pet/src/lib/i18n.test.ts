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

  // v2 M3（§3.9 键名清单 + 实施细项增补，TC-M3-17）：新键双语齐备
  it("M3 新键 zh/en 均存在（含实施细项微调键）", async () => {
    const { DICT } = await import("./i18n");
    const m3Keys = [
      "token.preset.today",
      "token.kpi.total",
      "token.col.model",
      "token.model.unknown",
      "token.project.global",
      "token.project.unknown",
      "token.chart.tip",
      "token.chart.tipRow",
      "token.chart.noModels",
      "menu.todayToken",
      "toolb.read",
      "toolb.edit",
      "toolb.bash",
      "toolb.search",
      "toolb.web",
      "settings.sectionPet",
      "settings.toolBroadcast",
      "settings.toolBroadcastFail",
    ];
    for (const k of m3Keys) {
      expect(DICT.zh[k], `zh 缺键 ${k}`).toBeTruthy();
      expect(DICT.en[k], `en 缺键 ${k}`).toBeTruthy();
    }
  });

  // 用户 2026-08-25 裁定修订：cache read 升独立第二卡（总量/cache read/input/
  // output），首卡「含 cache read X」副行随之取消——totalSub 键清退
  it("token.kpi.totalSub 已清退（cache read 独立卡取代副行小字）", async () => {
    const { DICT } = await import("./i18n");
    expect(!("token.kpi.totalSub" in DICT.zh), "zh 应无 totalSub").toBe(true);
    expect(!("token.kpi.totalSub" in DICT.en), "en 应无 totalSub").toBe(true);
  });

  // 用户 2026-08-25 14:05 裁定：移除主动层悬停卡（三层降两层）——悬停卡错误态
  // 专用键 todayUnavailable 清退（TC-M3-17 清退断言）
  it("token.todayUnavailable 已清退（悬停卡移除，无消费方）", async () => {
    const { DICT } = await import("./i18n");
    expect(!("token.todayUnavailable" in DICT.zh), "zh 应无 todayUnavailable").toBe(true);
    expect(!("token.todayUnavailable" in DICT.en), "en 应无 todayUnavailable").toBe(true);
  });

  // v2 M4 R1 补充（用户 2026-08-25 五点 UI 裁定）：tab/表单 zh 显示名改「例程」
  // 「待办」——钉住键值防回退（en：Routines / Todo）
  it("M4 R1 补充改名键：tasks 例程 / todo 待办（zh）+ Routines / Todo（en）", async () => {
    const { DICT } = await import("./i18n");
    expect(DICT.zh["panel.tab.tasks"]).toBe("例程");
    expect(DICT.en["panel.tab.tasks"]).toBe("Routines");
    expect(DICT.zh["panel.tab.todo"]).toBe("待办");
    expect(DICT.en["panel.tab.todo"]).toBe("Todo");
    expect(DICT.zh["reminders.form.newTitle"]).toBe("新建例程");
    expect(DICT.en["reminders.form.newTitle"]).toBe("New routine");
    expect(DICT.zh["reminders.form.editTitle"]).toBe("编辑例程 #{n}");
    expect(DICT.zh["tasks.rules.title"]).toBe("例程（{n}）");
    expect(DICT.en["tasks.rules.title"]).toBe("Routines ({n})");
  });

  // v2 M4 R1 补充 2（用户 2026-08-25 二次裁定）：状态芯片 agentTask 同步例程
  it("M4 R1 补充 2：panel.agentTask 例程（zh）/ Routine（en）", async () => {
    const { DICT } = await import("./i18n");
    expect(DICT.zh["panel.agentTask"]).toBe("例程");
    expect(DICT.en["panel.agentTask"]).toBe("Routine");
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
