import { useEffect, useMemo, useState } from "react";
import Todo from "./plugins/Todo";
import { usePanelStore, initPanelStore } from "./panelStore";
import { buildTabs, resolveTabId, type PluginRenderMap, type TabDef } from "./registry";
import { usePluginStore } from "../lib/plugin-store";
import { initThemeBridge } from "../lib/theme";
import { PANEL_TAB_EVENT, normalizeTab } from "../lib/interaction";
import { isTauriRuntime } from "../lib/token-stats";
import { t, useLangStore } from "../lib/i18n";

/**
 * 控制面板（v2 M2 面板壳，V2-DESIGN §2.4/§2.5；2026-08-24 修订）：
 * - 顶栏 = 「PulsePet · 控制面板」标题 + agent 状态芯片**两段布局**
 *   （修订：mini 猫移除；芯片 `● {agent} · {kind}` 等宽字体，agent/kind
 *   不翻译——P1-1 拉前的独立消费方，panelStore 供数）；
 * - tab 栏 = 注册表驱动（核心三静态 + 插件按 enabled 动态，禁用即隐藏；
 *   激活 tab 带 accent 硬阴影上浮）；`panel://tab` 直达保留，目标禁用回退
 *   首个可用；正查看的 tab 被禁用 → 立即切首个可用（hook 内处理）；
 * - 主题 data-theme 挂载点（panel 窗专属；initThemeBridge 拉偏好 + 订阅
 *   ui://theme / prefers-color-scheme 即时联动）。
 */

/** 插件 render 映射表（前端静态绑定，无动态代码加载——§2.5）。 */
const PLUGIN_RENDERERS: PluginRenderMap = {
  "built-in-todo": Todo,
};

/** 注册表 hook：插件快照 → tabs；当前 tab 被禁用自动回退首个可用。 */
function useTabs(tab: string, setTab: (id: string) => void): TabDef[] {
  const plugins = usePluginStore((s) => s.plugins);
  const tabs = useMemo(() => buildTabs(plugins ?? [], PLUGIN_RENDERERS), [plugins]);
  // 正查看的 tab 被禁用 → 立即切首个可用（TC-UI-07-2）
  useEffect(() => {
    const resolved = resolveTabId(tab, tabs);
    if (resolved !== tab) setTab(resolved);
  }, [tabs, tab, setTab]);
  return tabs;
}

export default function Panel() {
  const [tab, setTab] = useState("token");
  const tabs = useTabs(tab, setTab);
  const { kind, agent } = usePanelStore();
  useLangStore((s) => s.lang); // M8 i18n：语言变化时整棵 tab 栏/标题重渲染

  // 面板壳初始化：主题（panel 窗专属）+ 显示状态 + 插件快照
  useEffect(() => {
    void initThemeBridge();
    void initPanelStore();
    if (isTauriRuntime()) void usePluginStore.getState().load();
  }, []);

  // M6：外部直达 tab（PetMenu「设置…」→ Rust panel_open(tab) → 本事件）；
  // v2 M2：目标为禁用 tab 时回退首个可用（resolveTabId，TC-UI-07-5）
  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: (() => void) | undefined;
    let alive = true;
    void import("@tauri-apps/api/event").then(({ listen }) =>
      listen(PANEL_TAB_EVENT, (event) => {
        const target = normalizeTab((event.payload as { tab?: unknown } | null)?.tab);
        if (target) setTab(target); // 不在注册表时由 useTabs 回退 effect 处理
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

  const active = tabs.find((x) => x.id === tab) ?? tabs[0];
  const ActiveView = active?.render;
  // 状态芯片文案：agent 空（sessions 全空）→ 优雅降级只显示 kind（TC-UI-03-4）
  const statusText = agent ? `${agent} · ${kind}` : kind;

  return (
    <div className="panel">
      <header className="panel-header">
        <h1 className="panel-title">{t("panel.title")}</h1>
        <span
          className="panel-status-chip"
          aria-label={t("panel.statusAria", { text: statusText })}
        >
          <span className="chip-dot" aria-hidden="true" />
          {statusText}
        </span>
      </header>
      <nav className="panel-tabs" role="tablist">
        {tabs.map((tabDef) => {
          const on = tabDef.id === active?.id;
          return (
            <button
              key={tabDef.id}
              role="tab"
              aria-selected={on}
              className={on ? "panel-tab active" : "panel-tab"}
              onClick={() => setTab(tabDef.id)}
            >
              {tabDef.kind === "core" ? t(tabDef.labelKey) : (tabDef.label ?? tabDef.id)}
            </button>
          );
        })}
      </nav>
      {ActiveView && <ActiveView />}
    </div>
  );
}
