import { useEffect, useState } from "react";
import TokenStats from "./TokenStats";
import Reminders from "./Reminders";
import Settings from "./Settings";
import { PANEL_TAB_EVENT, normalizeTab } from "../lib/interaction";
import { isTauriRuntime } from "../lib/token-stats";

/**
 * 控制面板（DESIGN §2.3：设置 / Token / Todo / 提醒）。
 *
 * M3：Token 统计标签页落地（TC-TK-08/09）。
 * M4：提醒标签页落地（规则 CRUD + 全局烟花开关 + 历史统计，TC-RM-07/11/13）。
 * M5：设置标签页落地"选择宠物"下拉（TC-SP-11 + TC-APP-12）。
 * M6：设置标签页接通"点击穿透"开关；监听 `panel://tab`（宠物右键菜单
 *      「设置…」/ Rust panel_open(tab)）直达指定 tab。
 */
type TabId = "token" | "reminders" | "settings" | "todo";

const TABS: { id: TabId; label: string; milestone?: string }[] = [
  { id: "token", label: "Token" },
  { id: "reminders", label: "提醒" },
  { id: "settings", label: "设置" },
  { id: "todo", label: "Todo", milestone: "M7" },
];

const PLACEHOLDERS: Partial<Record<TabId, string>> = {
  todo: "Todo 插件 — M7",
};

export default function Panel() {
  const [tab, setTab] = useState<TabId>("token");

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
      <h1>PulsePet 控制面板</h1>
      <nav className="panel-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "panel-tab active" : "panel-tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.milestone && <span className="tab-milestone">{t.milestone}</span>}
          </button>
        ))}
      </nav>
      {tab === "token" && <TokenStats />}
      {tab === "reminders" && <Reminders />}
      {tab === "settings" && <Settings />}
      {PLACEHOLDERS[tab] && <p className="panel-placeholder">{PLACEHOLDERS[tab]}</p>}
    </div>
  );
}
