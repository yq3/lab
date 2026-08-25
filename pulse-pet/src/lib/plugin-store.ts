/**
 * plugin-store：v2 M2 插件注册表状态（V2-DESIGN §2.5）。
 *
 * `plugins_list()` 快照放 zustand——Panel 的 tab 注册表（useTabs）与设置页
 * 「功能管理」区共享同一份：开关切换 → `plugins_set_enabled`（Rust 写列 +
 * 触发调度器 reload）→ 本 store 重拉 → tab 栏即时增删 / 徽标即时显隐。
 */

import { create } from "zustand";
import { fetchPlugins, type PluginInfo } from "./todos";

interface PluginStoreState {
  plugins: PluginInfo[] | null;
  load: () => Promise<void>;
}

export const usePluginStore = create<PluginStoreState>((set) => ({
  plugins: null,
  load: async () => {
    try {
      const list = await fetchPlugins();
      set({ plugins: list });
    } catch (e) {
      // 拉取失败保持已有快照（tab 栏不闪空）
      console.error("[pulsepet] plugins_list failed:", e);
    }
  },
}));

/**
 * 功能管理开关：Rust 写 `plugins.enabled` 列 + 调度器 reload（停派生的
 * 执行面），随后重拉快照（tab / 徽标联动）。失败时也重拉（回读权威值）。
 */
export async function setPluginEnabled(id: string, enabled: boolean): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    await invoke("plugins_set_enabled", { id, enabled });
  } finally {
    await usePluginStore.getState().load();
  }
}

/** 指定插件是否启用（快照未就绪 / 缺行 → 保守 true：不过滤）。 */
export function pluginEnabled(plugins: PluginInfo[] | null, id: string): boolean {
  if (!plugins) return true;
  return plugins.find((p) => p.id === id)?.enabled ?? true;
}
