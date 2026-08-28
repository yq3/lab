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
      "settings.toolBroadcast",
      "settings.toolBroadcastFail",
    ];
    for (const k of m3Keys) {
      expect(DICT.zh[k], `zh 缺键 ${k}`).toBeTruthy();
      expect(DICT.en[k], `en 缺键 ${k}`).toBeTruthy();
    }
  });

  // §十二 F6（2026-08-28）：交互与播报合并区——旧区名键清退 + 新键齐备
  // 二轮微调：sectionInteraction 改值「交互管理」；卡片文案拆 name + Desc 两键；
  // 「当前渲染」行移除 → current/fellBack 清退。
  // 审查 P3-6：themeLabel 不入清退清单——该键 F6 增、F16 删同批净零（HEAD 无此键），
  // 断言恒真无防护力；真实清退面 = interaction/sectionPet/current/fellBack
  it("F6+二轮：interaction/sectionPet/current/fellBack 已清退，合并区与拆分键齐备", async () => {
    const { DICT } = await import("./i18n");
    for (const k of [
      "settings.interaction",
      "settings.sectionPet",
      "settings.current",
      "settings.fellBack",
    ]) {
      expect(!(`${k}` in DICT.zh), `zh 应无 ${k}`).toBe(true);
      expect(!(`${k}` in DICT.en), `en 应无 ${k}`).toBe(true);
    }
    for (const k of [
      "settings.sectionInteraction",
      "settings.passThrough",
      "settings.passThroughDesc",
      "settings.toolBroadcast",
      "settings.toolBroadcastDesc",
      "settings.size",
    ]) {
      expect(DICT.zh[k], `zh 缺键 ${k}`).toBeTruthy();
      expect(DICT.en[k], `en 缺键 ${k}`).toBeTruthy();
    }
    // 二轮微调钉值：区名 + 大小 label
    expect(DICT.zh["settings.sectionInteraction"]).toBe("交互管理");
    expect(DICT.en["settings.sectionInteraction"]).toBe("Interaction");
    expect(DICT.zh["settings.size"]).toBe("宠物大小");
    expect(DICT.en["settings.size"]).toBe("Pet size");
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

  // v2 M5（TC-M5-10）：新键 zh/en 集合一致 + 关键键值钉住
  // R2（2026-08-27）：token.agent.all 新增（agent tab「全部」项）；
  // token.chart.noAgents 随单选交互清退（始终恰有一项选中，空态不可达）
  it("M5 新键 zh/en 均存在（token.agent.* / taskBadge / degraded）", async () => {
    const { DICT } = await import("./i18n");
    const m5Keys = [
      "token.agent.opencode",
      "token.agent.claudeCode",
      "token.agent.all",
      "token.taskBadge",
      "token.degraded",
      "token.aria.agent",
    ];
    for (const k of m5Keys) {
      expect(DICT.zh[k], `zh 缺键 ${k}`).toBeTruthy();
      expect(DICT.en[k], `en 缺键 ${k}`).toBeTruthy();
      expect(DICT.zh[k].length > 0 && DICT.en[k].length > 0, `${k} 两语言非空`).toBe(true);
    }
    // 徽标全名（品牌名不翻译——zh/en 同值合法）
    expect(DICT.zh["token.agent.claudeCode"]).toBe("Claude Code");
    expect(DICT.en["token.agent.claudeCode"]).toBe("Claude Code");
    // R2：agent tab「全部」项文案钉住（zh/en 互异，防粘贴错语言）
    expect(DICT.zh["token.agent.all"]).toBe("全部");
    expect(DICT.en["token.agent.all"]).toBe("All");
    // R2：agent tab 组 aria-label（维度单选，非复选筛选）
    expect(DICT.zh["token.aria.agent"]).toBe("agent 维度");
    expect(DICT.en["token.aria.agent"]).toBe("Agent dimension");
    // 可翻译键 zh/en 互异（防粘贴错语言）
    for (const k of ["token.taskBadge", "token.degraded"]) {
      expect(DICT.zh[k], `${k} zh/en 应互异`).not.toBe(DICT.en[k]);
    }
    expect(DICT.zh["token.taskBadge"]).toBe("定时任务例程");
    expect(DICT.en["token.taskBadge"]).toBe("Scheduled routine");
  });

  // §十二 F3（2026-08-28）：费用口径标注随 UI 移除，键清退（仿 noAgents 先例）
  it("token.costOpencodeOnly 已清退（费用口径标注移除，F3）", async () => {
    const { DICT } = await import("./i18n");
    expect(!("token.costOpencodeOnly" in DICT.zh), "zh 应无 costOpencodeOnly").toBe(true);
    expect(!("token.costOpencodeOnly" in DICT.en), "en 应无 costOpencodeOnly").toBe(true);
  });

  // v2 M5 R2（TC-M5-04-4）：agent 空集空态随单选交互不可达 → noAgents 键清退
  it("token.chart.noAgents 已清退（agent 单选 tab 恒有一项选中，空态不可达）", async () => {
    const { DICT } = await import("./i18n");
    expect(!("token.chart.noAgents" in DICT.zh), "zh 应无 noAgents").toBe(true);
    expect(!("token.chart.noAgents" in DICT.en), "en 应无 noAgents").toBe(true);
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

describe("v2 M6 新键（TC-M6-06-4）", () => {
  it("token.hoverAgent zh/en 均有（分布行标签；完备性测试之上的显式钉）", async () => {
    const { DICT } = await import("./i18n");
    expect(DICT.zh["token.hoverAgent"]).toBe("今日 agent 分布");
    expect(DICT.en["token.hoverAgent"]).toBe("Today's tokens by agent");
  });
});
