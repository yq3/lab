import { useState } from "react";
import TokenStats from "./TokenStats";
import Reminders from "./Reminders";
import Settings from "./Settings";

/**
 * 控制面板（DESIGN §2.3：设置 / Token / Todo / 提醒）。
 *
 * M3：Token 统计标签页落地（TC-TK-08/09）。
 * M4：提醒标签页落地（规则 CRUD + 全局烟花开关 + 历史统计，TC-RM-07/11/13）。
 * M5：设置标签页落地"选择宠物"下拉（TC-SP-11 + TC-APP-12）；
 *     穿透 / 热键等其余设置 M6。
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
