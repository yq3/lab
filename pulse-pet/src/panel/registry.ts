/**
 * registry：v2 M2 tab 注册表 + feature flag（V2-DESIGN §2.5，TC-UI-07/14）。
 *
 * - 核心三 tab（token / reminders / settings）静态注册、顺序固定、不可关闭；
 * - 插件 tab 由 `plugins_list()` 返回的 enabled + manifest `panelTab` 字段
 *   动态生成——**前端读序列化键 `panel_tab`**（PluginInfo serde 无 rename，
 *   P3-③ 回归陷阱钉子），render 映射表 `{ "built-in-todo": Todo }` 前端
 *   静态绑定（v2 无插件 SDK，无动态代码加载）；
 * - 插件按 name 排序插在 reminders 与 settings 之间；
 * - 禁用（enabled=false）或无 panel_tab 声明 → 不生成 tab；
 * - `resolveTabId`：panel://tab 直达目标不在注册表（禁用）→ 回退首个可用。
 */

import type { ComponentType } from "react";
import type { PluginInfo } from "../lib/todos";
import TokenStats from "./TokenStats";
import Tasks from "./Tasks";
import Settings from "./Settings";

export interface TabDef {
  id: string;
  kind: "core" | "plugin";
  /** i18n 键（核心 tab）；插件 tab 用 manifest title（label 字段直显）。 */
  labelKey: string;
  /** 插件 tab 的 manifest panelTab.title（数据值不翻译）。 */
  label?: string;
  render: ComponentType;
}

/** 插件 tab 的输入形状（plugins_list 返回行的消费子集）。 */
export type PluginTabSource = Pick<PluginInfo, "id" | "name" | "enabled" | "panel_tab">;

/**
 * 插件 id → 前端静态绑定的渲染组件（设计 §2.5：无动态代码加载）。
 * Panel.tsx 注入（避免 registry → 组件 → registry 循环依赖）。
 */
export type PluginRenderMap = Record<string, ComponentType>;

/**
 * 核心 tab id（v2 M4：「提醒」→「定时任务」改名，id `reminders` → `tasks`，
 * 位置不变——token / tasks / settings；TC-M4-02）。
 */
export const CORE_TAB_IDS = {
  token: "token",
  tasks: "tasks",
  settings: "settings",
} as const;

/** 旧 tab id → 新 id 映射（panel://tab 直达兼容：v1 外部链接仍可打开任务页）。 */
const LEGACY_TAB_ALIASES: Record<string, string> = {
  reminders: "tasks",
};

/**
 * 插件 tab 的 i18n 显示名覆盖键（用户 2026-08-25 裁定：Todo tab zh 显示
 * 「待办」——manifest title 是双语单值数据，改 manifest 会波及 en；此处
 * 前端按 tab id 覆盖为 i18n 键，en 侧仍走 panel.tab.todo = "Todo"）。
 * 无覆盖的插件 tab 照旧直显 manifest title（数据值不翻译的原约定不变）。
 */
const PLUGIN_TAB_LABEL_KEYS: Record<string, string> = {
  "built-in-todo": "panel.tab.todo",
};

/** 旧 id 兼容映射（reminders → tasks；未知值原样返回由 resolveTabId 回退）。 */
export function normalizeTabId(id: string): string {
  return LEGACY_TAB_ALIASES[id] ?? id;
}

/** 核心三 tab（静态注册，顺序即渲染顺序；TC-UI-07-1 不可关闭）。 */
export const CORE_TABS: TabDef[] = [
  { id: "token", kind: "core", labelKey: "panel.tab.token", render: TokenStats },
  { id: "tasks", kind: "core", labelKey: "panel.tab.tasks", render: Tasks },
  { id: "settings", kind: "core", labelKey: "panel.tab.settings", render: Settings },
];

/**
 * 构建注册表：核心静态（token / tasks / settings）+ 插件动态
 * （enabled 且有 panel_tab 声明且 render 映射表有静态绑定，按 name 排序，
 * 插在 tasks 与 settings 之间）。
 */
export function buildTabs(plugins: PluginTabSource[], renderers: PluginRenderMap): TabDef[] {
  const pluginTabs: TabDef[] = plugins
    .filter((p) => p.enabled && p.panel_tab != null && renderers[p.id] != null)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((p) => ({
      id: p.id,
      kind: "plugin" as const,
      labelKey: PLUGIN_TAB_LABEL_KEYS[p.id] ?? "",
      label: typeof p.panel_tab?.title === "string" ? p.panel_tab.title : p.name,
      render: renderers[p.id],
    }));
  // 插件插位：tasks 与 settings 之间（§2.5）
  return [CORE_TABS[0], CORE_TABS[1], ...pluginTabs, CORE_TABS[2]];
}

/**
 * tab id 解析（panel://tab 直达 / 当前 tab 被禁用后的回退）：
 * 旧 id 先经 normalizeTabId 映射（reminders → tasks）；目标在注册表 →
 * 目标；否则（禁用 / 未知 / null）→ 首个可用 tab。
 */
export function resolveTabId(desired: string | null, tabs: TabDef[]): string {
  if (desired) {
    const normalized = normalizeTabId(desired);
    if (tabs.some((t) => t.id === normalized)) return normalized;
  }
  return tabs[0]?.id ?? "token";
}
