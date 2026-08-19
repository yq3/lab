import { useEffect, useState } from "react";
import TokenStats from "./TokenStats";
import Reminders from "./Reminders";
import Settings from "./Settings";
import Todo from "./plugins/Todo";
import { PANEL_TAB_EVENT, normalizeTab } from "../lib/interaction";
import { isTauriRuntime } from "../lib/token-stats";
import { t, useLangStore } from "../lib/i18n";

/**
 * 控制面板（DESIGN §2.3：设置 / Token / Todo / 提醒）。
 *
 * M3：Token 统计标签页落地（TC-TK-08/09）。
 * M4：提醒标签页落地（规则 CRUD + 全局烟花开关 + 历史统计，TC-RM-07/11/13）。
 * M5：设置标签页落地"选择宠物"下拉（TC-SP-11 + TC-APP-12）。
 * M6：设置标签页接通"点击穿透"开关；监听 `panel://tab`（宠物右键菜单
 *      「设置…」/ Rust panel_open(tab)）直达指定 tab。
 * M7：Todo 插件标签页落地（内置 built-in-todo，TC-TD-01/02）。
 * M8：i18n——tab 标签/标题随语言（订阅 useLangStore 触发重渲染）。
 */
type TabId = "token" | "reminders" | "settings" | "todo";

const TABS: { id: TabId; labelKey: string; milestone?: string }[] = [
  { id: "token", labelKey: "panel.tab.token" },
  { id: "reminders", labelKey: "panel.tab.reminders" },
  { id: "todo", labelKey: "panel.tab.todo", milestone: "M7" },
  { id: "settings", labelKey: "panel.tab.settings" },
];

export default function Panel() {
  const [tab, setTab] = useState<TabId>("token");
  useLangStore((s) => s.lang); // M8 i18n：语言变化时整棵 tab 栏/标题重渲染

  // M6：外部直达 tab（PetMenu「设置…」→ Rust panel_open("settings") → 本事件）
  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: (() => void) | undefined;
    let alive = true;
    void import("@tauri-apps/api/event").then(({ listen }) =>
      listen(PANEL_TAB_EVENT, (event) => {
        const t = normalizeTab((event.payload as { tab?: unknown } | null)?.tab);
        if (t) setTab(t);
      }),
    ).then((un) => {
      if (alive) unlisten = un;
      else un();
    });
    return () => {
      alive = false;
      unlisten?.();
    };
  }, []);

  return (
    <div className="panel">
      <h1>{t("panel.title")}</h1>
      <nav className="panel-tabs" role="tablist">
        {TABS.map((tabDef) => (
          <button
            key={tabDef.id}
            role="tab"
            aria-selected={tab === tabDef.id}
            className={tab === tabDef.id ? "panel-tab active" : "panel-tab"}
            onClick={() => setTab(tabDef.id)}
          >
            {t(tabDef.labelKey)}
            {tabDef.milestone && <span className="tab-milestone">{tabDef.milestone}</span>}
          </button>
        ))}
      </nav>
      {tab === "token" && <TokenStats />}
      {tab === "reminders" && <Reminders />}
      {tab === "todo" && <Todo />}
      {tab === "settings" && <Settings />}
    </div>
  );
}
