import { useState } from "react";
import TokenStats from "./TokenStats";

/**
 * 控制面板（DESIGN §2.3：设置 / Token / Todo / 提醒）。
 *
 * M3：Token 统计标签页落地（TC-TK-08/09）；其余里程碑为占位 tab。
 */
type TabId = "token" | "reminders" | "settings" | "todo";

const TABS: { id: TabId; label: string; milestone?: string }[] = [
  { id: "token", label: "Token" },
  { id: "reminders", label: "提醒", milestone: "M4" },
  { id: "settings", label: "设置", milestone: "M5/M6" },
  { id: "todo", label: "Todo", milestone: "M7" },
];

const PLACEHOLDERS: Partial<Record<TabId, string>> = {
  reminders: "提醒配置（喝水 / 休息 + 烟花）— M4",
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
      {PLACEHOLDERS[tab] && <p className="panel-placeholder">{PLACEHOLDERS[tab]}</p>}
    </div>
  );
}
