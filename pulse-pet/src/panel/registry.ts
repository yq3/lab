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
import Reminders from "./Reminders";
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

/** 核心三 tab（静态注册，顺序即渲染顺序；TC-UI-07-1 不可关闭）。 */
export const CORE_TABS: TabDef[] = [
  { id: "token", kind: "core", labelKey: "panel.tab.token", render: TokenStats },
  { id: "reminders", kind: "core", labelKey: "panel.tab.reminders", render: Reminders },
  { id: "settings", kind: "core", labelKey: "panel.tab.settings", render: Settings },
];

/**
 * 构建注册表：核心静态（token / reminders / settings）+ 插件动态
 * （enabled 且有 panel_tab 声明且 render 映射表有静态绑定，按 name 排序，
 * 插在 reminders 与 settings 之间）。
 */
export function buildTabs(plugins: PluginTabSource[], renderers: PluginRenderMap): TabDef[] {
  const pluginTabs: TabDef[] = plugins
    .filter((p) => p.enabled && p.panel_tab != null && renderers[p.id] != null)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((p) => ({
      id: p.id,
      kind: "plugin" as const,
      labelKey: "",
      label: typeof p.panel_tab?.title === "string" ? p.panel_tab.title : p.name,
      render: renderers[p.id],
    }));
  // 插件插位：reminders 与 settings 之间（§2.5）
  return [CORE_TABS[0], CORE_TABS[1], ...pluginTabs, CORE_TABS[2]];
}

/**
 * tab id 解析（panel://tab 直达 / 当前 tab 被禁用后的回退）：
 * 目标在注册表 → 目标；否则（禁用 / 未知 / null）→ 首个可用 tab。
 */
export function resolveTabId(desired: string | null, tabs: TabDef[]): string {
  if (desired && tabs.some((t) => t.id === desired)) return desired;
  return tabs[0]?.id ?? "token";
}
