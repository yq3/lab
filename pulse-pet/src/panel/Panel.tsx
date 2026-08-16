import { useState } from "react";
import TokenStats from "./TokenStats";
import Reminders from "./Reminders";

/**
 * 控制面板（DESIGN §2.3：设置 / Token / Todo / 提醒）。
 *
 * M3：Token 统计标签页落地（TC-TK-08/09）。
 * M4：提醒标签页落地（规则 CRUD + 全局烟花开关 + 历史统计，TC-RM-07/11/13）。
 */
type TabId = "token" | "reminders" | "settings" | "todo";

const TABS: { id: TabId; label: string; milestone?: string }[] = [
  { id: "token", label: "Token" },
  { id: "reminders", label: "提醒" },
  { id: "settings", label: "设置", milestone: "M5/M6" },
  { id: "todo", label: "Todo", milestone: "M7" },
];

const PLACEHOLDERS: Partial<Record<TabId, string>> = {
  settings: "设置（宠物选择 / 穿透 / 烟花全局开关）— M5/M6",
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
      {PLACEHOLDERS[tab] && <p className="panel-placeholder">{PLACEHOLDERS[tab]}</p>}
    </div>
  );
}
